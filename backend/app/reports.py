import csv
import io
import re

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .models import AnswerLog, GameResult, Host, Player
from .security import get_current_host

router = APIRouter()

NEEDS_HELP_BELOW = 0.5  # the report flags players under 50% overall accuracy


def owned_result(game_result_id: int, host: Host, session: Session) -> GameResult:
    result = session.get(GameResult, game_result_id)
    # someone else's game looks the same as a missing one, like the quiz routes
    if result is None or result.host_id != host.id:
        raise HTTPException(status_code=404, detail="Report not found")
    if result.question_stats is None:
        raise HTTPException(status_code=409, detail="This game was archived without question details.")
    return result


@router.get("/results/{game_result_id}/report")
def game_report(
    game_result_id: int,
    host: Host = Depends(get_current_host),
    session: Session = Depends(get_session),
):
    """The teacher's report for one finished game, read from its archive row."""
    result = owned_result(game_result_id, host, session)

    graded = [q for q in result.question_stats if not q["poll"]]
    polls = [q for q in result.question_stats if q["poll"]]
    # hardest first (lowest share correct; the earlier question wins a tie), polls last
    questions = sorted(graded, key=lambda q: (q["accuracy_pct"], q["n"])) + sorted(polls, key=lambda q: q["n"])
    needs_help = sorted(
        (s for s in result.standings if s["graded"] and s["correct"] / s["graded"] < NEEDS_HELP_BELOW),
        key=lambda s: (s["correct"] / s["graded"], s["rank"]),
    )
    return {
        "game_result_id": result.id,
        "quiz_title": result.quiz_title,
        "pin": result.pin,
        "ended_at": result.ended_at,
        "player_count": result.player_count,
        "avg_score": result.avg_score,
        "avg_accuracy_pct": None if result.avg_accuracy is None else round(result.avg_accuracy * 100),
        "hardest": questions[0] if graded else None,
        "questions": questions,
        "needs_help": [
            {
                "nickname": s["nickname"],
                "avatar": s["avatar"],
                "correct": s["correct"],
                "graded": s["graded"],
                "accuracy_pct": round(100 * s["correct"] / s["graded"]),
            }
            for s in needs_help
        ],
    }


def safe_cell(value) -> str:
    """Quiz text and nicknames are typed by users. A cell starting with = + - @ (or a tab or
    carriage return) would run as a formula when the file is opened in a spreadsheet, so
    those get a leading apostrophe. (A real negative number is never passed through here.)"""
    text = "" if value is None else str(value)
    return "'" + text if re.match(r"^[=+\-@\t\r]", text) else text


@router.get("/results/{game_result_id}/report.csv")
def game_report_csv(
    game_result_id: int,
    host: Host = Depends(get_current_host),
    session: Session = Depends(get_session),
):
    """The same report as a downloadable spreadsheet: a players table, a blank row, then a
    question table, in question order. Only this game's own host can download it."""
    result = owned_result(game_result_id, host, session)
    questions = sorted(result.question_stats, key=lambda q: q["n"])

    # what each player did on each question, when the game's answers are still around
    points: dict[tuple[str, int], int] | None = None
    if result.room_id is not None:
        points = {
            (nickname.lower(), qi): pts
            for nickname, qi, pts in session.execute(
                select(Player.nickname, AnswerLog.question_index, AnswerLog.points_awarded)
                .join(Player, Player.id == AnswerLog.player_id)
                .where(AnswerLog.room_id == result.room_id)
            )
        }

    def outcome(nickname: str, q: dict) -> tuple[str, int]:
        pts = points.get((nickname.lower(), q["n"] - 1))
        if pts is None:
            return "No answer", 0
        if q["poll"]:
            return "Answered", 0
        return ("Correct" if pts > 0 else "Wrong"), pts

    header = ["Rank", "Player", "Score", "Correct answers", "Questions graded", "Accuracy %", "May need help"]
    if points is not None:
        header += [col for q in questions for col in (f"Q{q['n']} result", f"Q{q['n']} points")]
    rows = [header]
    for s in sorted(result.standings, key=lambda s: s["rank"]):
        graded = s["graded"]
        row = [
            s["rank"], s["nickname"], s["score"], s["correct"], graded,
            round(100 * s["correct"] / graded) if graded else "",
            "Yes" if graded and s["correct"] / graded < NEEDS_HELP_BELOW else "No",
        ]
        if points is not None:
            for q in questions:
                row += outcome(s["nickname"], q)
        rows.append(row)
    rows.append([])
    rows.append(["Question", "Text", "Type", "Correct answer", "Players correct", "Players", "Accuracy %", "Average answer time (s)"])
    for q in questions:
        poll = q["poll"]
        rows.append([
            f"Q{q['n']}", q["text"], "Poll" if poll else "Graded", "" if poll else q["answer"],
            "" if poll else q["correct"], q["total"], "" if poll else q["accuracy_pct"],
            "" if q["avg_ms"] is None else f"{q['avg_ms'] / 1000:.1f}",
        ])

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    for row in rows:
        writer.writerow([safe_cell(c) if isinstance(c, str) else c for c in row])
    slug = re.sub(r"[^a-z0-9]+", "-", (result.quiz_title or "").lower()).strip("-") or "quiz"
    filename = f"brainblitz-results-{slug}-{result.ended_at.date().isoformat()}.csv"
    return Response(
        content="\ufeff" + out.getvalue(),  # the byte-order mark makes Excel read it as UTF-8
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",  # private to the host
            "X-Content-Type-Options": "nosniff",
        },
    )
