"""Answer collection and the reveal.

Everything here runs on the one event loop, and the handlers do their database
work without awaiting in between, so the check-then-insert steps can't interleave.
The reveal itself is a conditional status flip (question -> reveal), so it fires
exactly once per question whether the last answer or the timer gets there first.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from .db import open_session
from .models import GameRoom, Player, AnswerLog, Question
from .realtime import connections
from .scoring import score_answer

timers: dict[int, asyncio.Task] = {}  # room id -> pending reveal timer


def as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite returns naive


def load_question(session, room: GameRoom, index: int) -> Question | None:
    if room.quiz_id is None:
        return None
    return session.scalar(
        select(Question).where(Question.quiz_id == room.quiz_id, Question.position == index)
    )


# Answer slot -> shape and colour, as in the editor's SHAPES (create.html).
# True/False uses the first two.
ANSWER_SHAPES = [
    {"shape": "triangle", "color": "red"},
    {"shape": "diamond", "color": "blue"},
    {"shape": "circle", "color": "yellow"},
    {"shape": "square", "color": "green"},
]


def question_shown_event(session: Session, room: GameRoom, question: Question) -> dict:
    """What every client sees when a question goes up. Deliberately has no
    correct_index: players are on the other end of this message."""
    total = session.scalar(
        select(func.count(Question.id)).where(Question.quiz_id == room.quiz_id)
    )
    started_at = room.question_started_at
    if started_at.tzinfo is None:  # stored in UTC; SQLite hands back naive values
        started_at = started_at.replace(tzinfo=timezone.utc)
    return {
        "type": "question_shown",
        "question_index": room.current_question_index,
        "total_questions": total,
        "text": question.text,
        "question_type": question.type,
        "answers": [
            {"text": text, **ANSWER_SHAPES[i]} for i, text in enumerate(question.answers)
        ],
        "time_limit_seconds": question.time_limit_seconds,
        "points_mode": question.points_mode,
        "started_at": started_at.isoformat(),
    }


def deadline_for(room: GameRoom, question: Question) -> datetime:
    return as_utc(room.question_started_at) + timedelta(seconds=question.time_limit_seconds)


def schedule_timer(room_id: int, question_index: int, deadline: datetime) -> None:
    """(Re)start the server-side countdown for the question that just went up."""
    cancel_timer(room_id)
    timers[room_id] = asyncio.create_task(_timer(room_id, question_index, deadline))


def cancel_timer(room_id: int) -> None:
    task = timers.pop(room_id, None)
    if task is not None and task is not asyncio.current_task():
        task.cancel()


async def _timer(room_id: int, question_index: int, deadline: datetime) -> None:
    await asyncio.sleep(max(0.0, (deadline - datetime.now(timezone.utc)).total_seconds()))
    await reveal_question(room_id, question_index)


def reveal_event(session, room: GameRoom, question: Question) -> dict:
    index = room.current_question_index
    counts = [0] * len(question.answers)
    for chosen, n in session.execute(
        select(AnswerLog.chosen_index, func.count())
        .where(AnswerLog.room_id == room.id, AnswerLog.question_index == index)
        .group_by(AnswerLog.chosen_index)
    ):
        counts[chosen] = n
    return {
        "type": "reveal",
        "question_index": index,
        "correct_index": question.correct_index,  # null for polls
        "counts": counts,
        "total_answers": sum(counts),
    }


def leaderboard_event(session, room_id: int, question_index: int) -> dict:
    """Players ranked by score, highest first, with where each stood before this
    question so the screen can animate real movement. Player ids are left out on
    purpose; they're private credentials."""
    gained = dict(
        session.execute(
            select(AnswerLog.player_id, AnswerLog.points_awarded).where(
                AnswerLog.room_id == room_id, AnswerLog.question_index == question_index
            )
        ).all()
    )
    players = session.scalars(select(Player).where(Player.room_id == room_id)).all()
    rows = [
        {
            "id": p.id,
            "nickname": p.nickname,
            "avatar": p.avatar,
            "score": p.score,
            "previous_score": p.score - gained.get(p.id, 0),
            "streak": p.streak,
            "joined_at": p.joined_at,
        }
        for p in players
    ]

    def ranked(score_key):  # ties: whoever joined first, then nickname
        order = sorted(rows, key=lambda r: (-r[score_key], r["joined_at"], r["nickname"]))
        return {r["id"]: i + 1 for i, r in enumerate(order)}

    now, before = ranked("score"), ranked("previous_score")
    board = sorted(rows, key=lambda r: now[r["id"]])
    return {
        "type": "leaderboard",
        "question_index": question_index,
        "players": [
            {
                "rank": now[r["id"]],
                "previous_rank": before[r["id"]],
                "nickname": r["nickname"],
                "avatar": r["avatar"],
                "score": r["score"],
                "previous_score": r["previous_score"],
                "streak": r["streak"],
            }
            for r in board
        ],
    }


def state_snapshot(session, room: GameRoom, player: Player | None) -> dict:
    """Everything a (re)connecting socket needs to catch up with the game."""
    snap = {
        "type": "state",
        "status": room.status,
        "question_index": room.current_question_index,
    }
    if player is not None:
        snap["score"] = player.score
    question = (
        load_question(session, room, room.current_question_index)
        if room.status in ("question", "reveal")
        else None
    )
    if question is not None and room.status == "question":
        snap["question"] = question_shown_event(session, room, question)
        snap["seconds_remaining"] = max(
            0.0, (deadline_for(room, question) - datetime.now(timezone.utc)).total_seconds()
        )
        if player is not None:
            snap["already_answered"] = session.scalar(
                select(AnswerLog.id).where(
                    AnswerLog.player_id == player.id,
                    AnswerLog.room_id == room.id,
                    AnswerLog.question_index == room.current_question_index,
                )
            ) is not None
    elif question is not None:  # reveal
        snap["reveal"] = reveal_event(session, room, question)
    return snap


async def reveal_question(room_id: int, question_index: int) -> None:
    with open_session() as session:
        flipped = session.execute(
            update(GameRoom)
            .where(
                GameRoom.id == room_id,
                GameRoom.status == "question",
                GameRoom.current_question_index == question_index,
            )
            .values(status="reveal")
        ).rowcount
        session.commit()
        if not flipped:  # already revealed, or the host moved on
            return
        room = session.get(GameRoom, room_id)
        question = load_question(session, room, question_index)
        if question.type != "poll":
            # no answer counts as a miss: it ends the streak (there's no log row,
            # since nothing was submitted)
            answered = select(AnswerLog.player_id).where(
                AnswerLog.room_id == room_id, AnswerLog.question_index == question_index
            )
            session.execute(
                update(Player)
                .where(Player.room_id == room_id, Player.id.not_in(answered))
                .values(streak=0)
            )
            session.commit()
        event = reveal_event(session, room, question)
        board = leaderboard_event(session, room_id, question_index)
    cancel_timer(room_id)
    await connections.broadcast(room_id, event)
    await connections.broadcast(room_id, board)  # settles streaks of players who didn't answer


async def handle_message(room_id: int, conn, message: object) -> None:
    """A message from a player's socket. Stamp the arrival time before anything else."""
    received_at = datetime.now(timezone.utc)
    if conn.role != "player" or not isinstance(message, dict):
        return
    if message.get("type") != "answer_submitted":
        return

    chosen = message.get("index")
    with open_session() as session:
        room = session.get(GameRoom, room_id)
        # Ignored without a reply: the question already moved to its reveal (or isn't
        # running), the player already answered it, or the time is up. Nothing is
        # stored, so nothing can be scored twice or after the deadline.
        if room.status != "question":
            return
        question_index = room.current_question_index
        already = session.scalar(
            select(AnswerLog.id).where(
                AnswerLog.player_id == uuid.UUID(conn.player_id),
                AnswerLog.room_id == room_id,
                AnswerLog.question_index == question_index,
            )
        )
        if already is not None:
            return
        question = load_question(session, room, question_index)
        if question is None or received_at > deadline_for(room, question):
            return
        if type(chosen) is not int or not 0 <= chosen < len(question.answers):
            return await conn.ws.send_json({"type": "answer_rejected", "reason": "invalid_index"})
        player = session.get(Player, uuid.UUID(conn.player_id))
        elapsed_ms = max(
            0, int((received_at - as_utc(room.question_started_at)).total_seconds() * 1000)
        )
        result = score_answer(question, chosen, elapsed_ms, player.streak)
        # the log row, the score and the streak commit together or not at all
        session.add(
            AnswerLog(
                room_id=room_id,
                player_id=player.id,
                question_id=question.id,
                question_index=question_index,
                chosen_index=chosen,
                server_elapsed_ms=elapsed_ms,
                points_awarded=result.total,
                answered_at=received_at,
            )
        )
        session.execute(
            update(Player)
            .where(Player.id == player.id)
            .values(score=Player.score + result.total, streak=result.streak)
        )
        try:
            session.commit()
        except IntegrityError:  # two answers from the same player at the same instant
            session.rollback()
            return
        answered = session.scalar(
            select(func.count(AnswerLog.id)).where(
                AnswerLog.room_id == room_id, AnswerLog.question_index == question_index
            )
        )
        joined = session.scalar(select(func.count(Player.id)).where(Player.room_id == room_id))
        board = leaderboard_event(session, room_id, question_index)
    await conn.ws.send_json({"type": "answer_received", "question_index": question_index})
    # Only the host sees a board while the question is open (its answered counter). Sent to
    # players, a score jump would show who just got it right, before the reveal.
    await connections.broadcast(room_id, board, only_role="host")
    if answered >= joined:
        await reveal_question(room_id, question_index)


# Badge rules. Nothing in the frontend defines these yet, so they live here as constants.
SPEED_DEMON_MIN_CORRECT = 2  # fastest average time on correct answers, among those with this many
SHARPSHOOTER_MIN_GRADED = 3  # every graded question right, in a quiz with at least this many
ON_FIRE_STREAK = 3  # best streak of at least this many in a row (where the streak bonus starts)


def player_stats(session, room: GameRoom) -> list[dict]:
    """Per-player final numbers, ranked, from the players and their answers_log rows.

    A question counts once it has been shown, including one the host ended mid-way.
    Polls are left out. An answer is correct if it earned points (a correct answer
    always earns at least half the maximum). An unanswered question is a miss, so
    it also ends a streak.
    """
    asked = 0 if room.current_question_index is None else room.current_question_index + 1
    graded_positions = sorted(
        session.scalars(
            select(Question.position).where(
                Question.quiz_id == room.quiz_id,
                Question.type != "poll",
                Question.position < asked,
            )
        ).all()
        if room.quiz_id is not None
        else []
    )
    outcome = {  # (player, question) -> (points, elapsed ms)
        (pid, qi): (pts, ms)
        for pid, qi, pts, ms in session.execute(
            select(
                AnswerLog.player_id,
                AnswerLog.question_index,
                AnswerLog.points_awarded,
                AnswerLog.server_elapsed_ms,
            ).where(
                AnswerLog.room_id == room.id, AnswerLog.question_index.in_(graded_positions)
            )
        )
    }
    players = sorted(
        session.scalars(select(Player).where(Player.room_id == room.id)).all(),
        key=lambda p: (-p.score, as_utc(p.joined_at), p.nickname),
    )
    graded = len(graded_positions)
    stats = []
    for rank, p in enumerate(players, start=1):
        streak = best = right = 0
        right_ms = []
        for qi in graded_positions:
            pts, ms = outcome.get((p.id, qi), (0, None))
            if pts > 0:
                streak += 1
                best = max(best, streak)
                right += 1
                right_ms.append(ms)
            else:
                streak = 0
        stats.append(
            {
                "rank": rank,
                "nickname": p.nickname,
                "avatar": p.avatar,
                "score": p.score,
                "correct": right,
                "graded": graded,
                "accuracy": round(right / graded, 4) if graded else None,
                "best_streak": best,
                "avg_correct_ms": round(sum(right_ms) / len(right_ms)) if right_ms else None,
            }
        )
    return stats


def award_badges(stats: list[dict]) -> dict[str, list[str]]:
    """Who earned which badge. `stats` is already ranked, so ties go to the higher rank."""
    fast = [
        s for s in stats if s["correct"] >= SPEED_DEMON_MIN_CORRECT and s["avg_correct_ms"] is not None
    ]
    fastest = min(fast, key=lambda s: (s["avg_correct_ms"], s["rank"]), default=None)
    return {
        "speed_demon": [fastest["nickname"]] if fastest else [],
        "sharpshooter": [
            s["nickname"]
            for s in stats
            if s["graded"] >= SHARPSHOOTER_MIN_GRADED and s["correct"] == s["graded"]
        ],
        "on_fire": [s["nickname"] for s in stats if s["best_streak"] >= ON_FIRE_STREAK],
    }


def build_results(session, room: GameRoom) -> dict:
    """The numbers archived in game_results and sent with game_ended."""
    standings = [
        {k: v for k, v in s.items() if k != "avg_correct_ms"} for s in player_stats(session, room)
    ]
    n = len(standings)
    accuracies = [r["accuracy"] for r in standings if r["accuracy"] is not None]
    return {
        "player_count": n,
        "avg_score": round(sum(r["score"] for r in standings) / n, 2) if n else None,
        "avg_accuracy": round(sum(accuracies) / len(accuracies), 4) if accuracies else None,
        "standings": standings,
    }


def question_report(session, room: GameRoom) -> list[dict]:
    """Per-question numbers for the teacher's report, from the quiz and the answers_log.

    Accuracy is the share of all players who answered correctly (someone who didn't
    answer counts as wrong). For a poll there's no right answer, so its figure is
    participation instead: the share who voted.
    """
    asked = 0 if room.current_question_index is None else room.current_question_index + 1
    total = session.scalar(select(func.count(Player.id)).where(Player.room_id == room.id))
    questions = (
        session.scalars(
            select(Question)
            .where(Question.quiz_id == room.quiz_id, Question.position < asked)
            .order_by(Question.position)
        ).all()
        if room.quiz_id is not None
        else []
    )
    by_question: dict[int, list[tuple[int, int]]] = {}
    for qi, pts, ms in session.execute(
        select(AnswerLog.question_index, AnswerLog.points_awarded, AnswerLog.server_elapsed_ms).where(
            AnswerLog.room_id == room.id
        )
    ):
        by_question.setdefault(qi, []).append((pts, ms))
    report = []
    for q in questions:
        rows = by_question.get(q.position, [])
        poll = q.type == "poll"
        correct = 0 if poll else sum(1 for pts, _ in rows if pts > 0)
        share = len(rows) if poll else correct
        report.append(
            {
                "n": q.position + 1,
                "text": q.text,
                "type": q.type,
                "poll": poll,
                "total": total,
                "answered": len(rows),
                "correct": correct,
                "answer": None if poll else q.answers[q.correct_index],
                "accuracy_pct": round(100 * share / total) if total else 0,
                "avg_ms": round(sum(ms for _, ms in rows) / len(rows)) if rows else None,
            }
        )
    return report
