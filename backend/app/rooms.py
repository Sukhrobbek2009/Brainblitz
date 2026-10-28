import json
import secrets
import uuid
from typing import Literal
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import get_session, open_session
from .models import GameResult, GameRoom, Host, Player, Question, Quiz
from .game import (
    deadline_for,
    award_badges,
    build_results,
    player_stats,
    question_report,
    cancel_timer,
    handle_message,
    load_question,
    question_shown_event,
    schedule_timer,
    state_snapshot,
)
from .ratelimit import SlidingWindowLimiter
from .realtime import Connection, connections
from .security import get_current_host, host_for_token

router = APIRouter()

MAX_PIN_ATTEMPTS = 10


class RoomIn(BaseModel):
    model_config = ConfigDict(extra="forbid")  # the host comes from the login, never the body

    quiz_id: int
    # optional; leaving it out is a classic room, exactly as before
    mode: Literal["classic", "blitz_racer"] = "classic"


def generate_pin() -> str:
    return str(100000 + secrets.randbelow(900000))  # 6 digits, no leading zero


@router.post("/rooms", status_code=201)
def create_room(
    body: RoomIn,
    host: Host = Depends(get_current_host),
    session: Session = Depends(get_session),
):
    quiz = session.get(Quiz, body.quiz_id)
    if quiz is None or quiz.host_id != host.id:
        raise HTTPException(status_code=404, detail="Quiz not found")

    for _ in range(MAX_PIN_ATTEMPTS):
        pin = generate_pin()
        if session.scalar(
            select(GameRoom.id).where(GameRoom.pin == pin, GameRoom.status != "ended")
        ):
            continue
        room = GameRoom(
            quiz_id=quiz.id, host_id=host.id, pin=pin, status="lobby", mode=body.mode,
            mode_state={"positions": {}} if body.mode == "blitz_racer" else {},
        )
        session.add(room)
        try:
            session.commit()
        except IntegrityError:  # another room took this PIN since the check
            session.rollback()
            continue
        return {"id": room.id, "pin": room.pin, "mode": room.mode}
    raise HTTPException(status_code=503, detail="Couldn't allocate a game PIN, try again")


# the Blitzer names from BB.BLITZERS in shared.js (the avatar picker); keep in sync
AVATARS = {
    "Hoppy", "Octo", "Pando", "Foxy", "Hootie", "Waddles",
    "Rexie", "Sparkle", "Ember", "Bolt", "Kingsley", "Nova",
}
NICKNAME_MAX = 14  # the join form's maxlength
JOINS_PER_PIN_PER_MINUTE = 120  # a full class can join in a burst, one script can't flood the room
join_limiter = SlidingWindowLimiter(JOINS_PER_PIN_PER_MINUTE, 60)
MAX_PLAYERS = 200  # the lobby's own upper limit; the PIN is the only key, so don't let a room grow forever


# the Turbo Lanes cars (CARS in racer.html); keep in sync
CARS = ("Viper", "Bolt", "Tank", "Drifter", "Comet")


def pick_car(taken: list[str | None]) -> str:
    """A random car nobody in the room has; once all five are used, a random one of the least-used."""
    counts = {c: taken.count(c) for c in CARS}
    fewest = min(counts.values())
    return secrets.choice([c for c in CARS if counts[c] == fewest])


class JoinIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: str
    avatar: str

    @field_validator("nickname")
    @classmethod
    def nickname_ok(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Give yourself a nickname first.")
        if len(v) > NICKNAME_MAX:
            raise ValueError(f"Nicknames can be at most {NICKNAME_MAX} characters.")
        return v

    @field_validator("avatar")
    @classmethod
    def avatar_ok(cls, v: str) -> str:
        if v not in AVATARS:
            raise ValueError("Pick one of the Blitzers.")
        return v


@router.post("/rooms/{pin}/join", status_code=201)
def join_room(pin: str, body: JoinIn, session: Session = Depends(get_session)):
    # keyed by PIN, not IP: a classroom shares one address. Every attempt counts, failed ones too.
    retry_after = join_limiter.hit(pin)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many people are joining this game. Wait a moment and try again.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    room = session.scalar(
        select(GameRoom).where(GameRoom.pin == pin, GameRoom.status != "ended")
    )
    if room is None:
        raise HTTPException(status_code=404, detail="Hmm, we can't find that game")
    if room.status != "lobby":
        raise HTTPException(
            status_code=409, detail="This game already started. Players can't jump in mid-game."
        )
    if session.scalar(select(func.count(Player.id)).where(Player.room_id == room.id)) >= MAX_PLAYERS:
        raise HTTPException(status_code=409, detail="This game is full.")
    taken = HTTPException(status_code=409, detail="That nickname is taken. Try another one.")
    if session.scalar(
        select(Player.id).where(
            Player.room_id == room.id, func.lower(Player.nickname) == body.nickname.lower()
        )
    ):
        raise taken
    player = Player(room_id=room.id, nickname=body.nickname, avatar=body.avatar)
    if room.mode == "blitz_racer":
        # lock the room row so two simultaneous joins can't both be handed the same free car
        session.refresh(room, with_for_update=True)
        player.car = pick_car(list(session.scalars(select(Player.car).where(Player.room_id == room.id))))
    session.add(player)
    try:
        session.commit()
    except IntegrityError:  # same nickname joined at the same moment
        session.rollback()
        raise taken
    out = {"player_id": str(player.id), "nickname": player.nickname, "avatar": player.avatar}
    if player.car is not None:  # racer rooms only; a classic join response is unchanged
        out["car"] = player.car
    return out


@router.get("/rooms/{pin}")
def get_room(pin: str, session: Session = Depends(get_session)):
    # Public like join: the PIN is the key. Player ids are left out on purpose;
    # they're each player's private credential. Prefer the live room for a PIN,
    # since an ended room's PIN can be reused.
    room = session.scalar(
        select(GameRoom)
        .where(GameRoom.pin == pin)
        .order_by((GameRoom.status == "ended"), GameRoom.id.desc())
        .limit(1)
    )
    if room is None:
        raise HTTPException(status_code=404, detail="Hmm, we can't find that game")
    players = session.scalars(
        select(Player)
        .where(Player.room_id == room.id)
        .order_by(Player.joined_at, Player.nickname)
    ).all()
    return {
        "id": room.id,
        "pin": room.pin,
        "status": room.status,
        "player_count": len(players),
        "players": [
            {"nickname": p.nickname, "avatar": p.avatar, "joined_at": p.joined_at}
            for p in players
        ],
    }


MIN_PLAYERS = 3  # the lobby's MIN_PLAYERS in lobby.html

def get_host_room(pin: str, host: Host, session: Session) -> GameRoom:
    room = session.scalar(
        select(GameRoom).where(GameRoom.pin == pin, GameRoom.status != "ended")
    )
    # someone else's room looks the same as a missing one, like the quiz routes
    if room is None or room.host_id != host.id:
        raise HTTPException(status_code=404, detail="Hmm, we can't find that game")
    return room


@router.post("/rooms/{pin}/start")
async def start_room(
    pin: str,
    host: Host = Depends(get_current_host),
    session: Session = Depends(get_session),
):
    room = get_host_room(pin, host, session)
    if load_question(session, room, 0) is None:
        raise HTTPException(status_code=409, detail="This quiz has no questions to play.")

    # One conditional UPDATE does the status check and the player count together,
    # so two Start clicks, or a player leaving mid-request, can't slip past either rule.
    player_count = (
        select(func.count(Player.id)).where(Player.room_id == room.id).scalar_subquery()
    )
    result = session.execute(
        update(GameRoom)
        .where(
            GameRoom.id == room.id,
            GameRoom.status == "lobby",
            player_count >= MIN_PLAYERS,
        )
        .values(
            status="question",
            current_question_index=0,
            question_started_at=datetime.now(timezone.utc),
        )
    )
    session.commit()
    session.refresh(room)
    if result.rowcount == 0:
        if room.status != "lobby":
            raise HTTPException(status_code=409, detail="This game has already started.")
        raise HTTPException(
            status_code=409, detail=f"Need at least {MIN_PLAYERS} players to start."
        )

    event = question_shown_event(session, room, load_question(session, room, 0))
    await connections.broadcast(room.id, event)
    schedule_timer(room.id, 0, deadline_for(room, load_question(session, room, 0)))
    return {"id": room.id, "pin": room.pin, "status": room.status,
            "current_question_index": room.current_question_index}


@router.post("/rooms/{pin}/next")
async def next_question(
    pin: str,
    host: Host = Depends(get_current_host),
    session: Session = Depends(get_session),
):
    room = get_host_room(pin, host, session)
    if room.status not in ("question", "reveal") or room.current_question_index is None:
        raise HTTPException(status_code=409, detail="This game isn't running a question.")
    next_index = room.current_question_index + 1
    question = load_question(session, room, next_index)
    if question is None:
        raise HTTPException(status_code=409, detail="That was the last question.")

    # only advance if nobody else moved the room since we read it (double click)
    result = session.execute(
        update(GameRoom)
        .where(
            GameRoom.id == room.id,
            GameRoom.status == room.status,
            GameRoom.current_question_index == room.current_question_index,
        )
        .values(
            status="question",
            current_question_index=next_index,
            question_started_at=datetime.now(timezone.utc),
        )
    )
    session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="The game already moved on.")
    session.refresh(room)

    await connections.broadcast(room.id, question_shown_event(session, room, question))
    schedule_timer(room.id, next_index, deadline_for(room, question))
    return {"id": room.id, "pin": room.pin, "status": room.status,
            "current_question_index": room.current_question_index}


@router.post("/rooms/{pin}/end")
async def end_room(
    pin: str,
    host: Host = Depends(get_current_host),
    session: Session = Depends(get_session),
):
    # prefer the live room for a PIN, since an ended room's PIN can be reused
    room = session.scalar(
        select(GameRoom)
        .where(GameRoom.pin == pin)
        .order_by((GameRoom.status == "ended"), GameRoom.id.desc())
        .limit(1)
    )
    if room is None or room.host_id != host.id:
        raise HTTPException(status_code=404, detail="Hmm, we can't find that game")

    now = datetime.now(timezone.utc)
    # The flip, the numbers and the archive row all commit together. The conditional
    # update means two End clicks can't both archive, and the unique room_id backs it up.
    flipped = session.execute(
        update(GameRoom)
        .where(GameRoom.id == room.id, GameRoom.status != "ended")
        .values(status="ended", ended_at=now)
    ).rowcount
    if not flipped:
        session.rollback()
        raise HTTPException(status_code=409, detail="This game has already ended.")
    session.refresh(room)
    results = build_results(session, room)
    quiz = session.get(Quiz, room.quiz_id) if room.quiz_id is not None else None
    questions = [
        {"position": q.position, "text": q.text, "type": q.type, "answers": list(q.answers),
         "correct_index": q.correct_index, "time_limit_seconds": q.time_limit_seconds,
         "points_mode": q.points_mode}
        for q in session.scalars(
            select(Question).where(Question.quiz_id == room.quiz_id).order_by(Question.position)
        ).all()
    ] if room.quiz_id is not None else None
    result = GameResult(
            room_id=room.id,
            quiz_id=room.quiz_id,
            host_id=room.host_id,
            quiz_title=quiz.title if quiz else None,
            questions=questions,
            pin=room.pin,
            player_count=results["player_count"],
            avg_score=results["avg_score"],
            avg_accuracy=results["avg_accuracy"],
            standings=results["standings"],
            started_at=room.created_at,
            ended_at=now,
            question_stats=question_report(session, room),
    )
    session.add(result)
    session.commit()

    cancel_timer(room.id)  # no reveal should fire for a finished game
    summary = {"game_result_id": result.id, **results}  # the id the host's report is fetched by
    await connections.broadcast(room.id, {"type": "game_ended", **summary})
    await connections.close_room(room.id)  # nobody stays connected to a finished game
    return {"id": room.id, "pin": room.pin, "status": "ended", **summary}


BADGES = [  # id, display name, what earns it (rules live in game.py)
    ("speed_demon", "Speed Demon"),
    ("sharpshooter", "Sharpshooter"),
    ("on_fire", "On Fire"),
]


@router.get("/rooms/{pin}/results")
def room_results(pin: str, session: Session = Depends(get_session)):
    """Final standings and badges for a finished game. Public like the other room reads:
    the PIN is the key, and nicknames/avatars/scores are already shown to the whole room."""
    room = session.scalar(
        select(GameRoom)
        .where(GameRoom.pin == pin, GameRoom.status == "ended")
        .order_by(GameRoom.id.desc())
        .limit(1)
    )
    if room is None:
        if session.scalar(select(GameRoom.id).where(GameRoom.pin == pin).limit(1)) is None:
            raise HTTPException(status_code=404, detail="Hmm, we can't find that game")
        raise HTTPException(status_code=409, detail="This game isn't finished yet.")

    stats = player_stats(session, room)
    winners = award_badges(stats)
    quiz = session.get(Quiz, room.quiz_id) if room.quiz_id is not None else None
    players = [
        {
            "rank": s["rank"],
            "nickname": s["nickname"],
            "avatar": s["avatar"],
            "score": s["score"],
            "correct": s["correct"],
            "graded": s["graded"],
            "accuracy_pct": None if s["accuracy"] is None else round(s["accuracy"] * 100),
            "best_streak": s["best_streak"],
            "badges": [bid for bid, _ in BADGES if s["nickname"] in winners[bid]],
        }
        for s in stats
    ]
    return {
        "pin": room.pin,
        "status": room.status,
        "quiz_title": quiz.title if quiz else None,
        "player_count": len(players),
        "graded_questions": stats[0]["graded"] if stats else 0,
        "players": players,
        "badges": [{"id": bid, "name": name, "winners": winners[bid]} for bid, name in BADGES],
    }


@router.websocket("/rooms/{pin}/ws")
async def room_socket(
    websocket: WebSocket,
    pin: str,
    player_id: str | None = None,
    token: str | None = None,
):
    """Browsers can't set headers on a WebSocket, so credentials go in the query string:
    ?player_id=<uuid> for a joined player, or ?token=<jwt> for the room's host.
    A dropped player reconnects the same way, with the same player_id."""
    # Check credentials in a short-lived session; don't hold one open for the whole socket.
    with open_session() as session:
        room = session.scalar(
            select(GameRoom).where(GameRoom.pin == pin, GameRoom.status != "ended")
        )
        conn: Connection | None = None
        player: Player | None = None
        if room is not None:
            if token is not None:
                host = host_for_token(token, session)
                if host is not None and host.id == room.host_id:
                    conn = Connection(websocket, "host")
            elif player_id is not None:
                try:
                    player = session.get(Player, uuid.UUID(player_id))
                except ValueError:
                    player = None
                if player is not None and player.room_id == room.id:
                    conn = Connection(websocket, "player", str(player.id))
        room_id = room.id if room is not None else None

    await websocket.accept()
    if room_id is None:
        await websocket.close(code=4404, reason="Hmm, we can't find that game")
        return
    if conn is None:
        await websocket.close(code=4401, reason="Not authenticated")
        return

    announce = None
    if conn.role == "player":
        nickname, avatar = player.nickname, player.avatar
        again = connections.has_connected_before(room_id, conn.player_id)
        announce = {
            "type": "player_reconnected" if again else "player_joined",
            "nickname": nickname,
            "avatar": avatar,
        }
        connections.mark_connected(room_id, conn.player_id)

    connections.add(room_id, conn)
    try:
        # catch the socket up on where the game is (also covers joining mid-question)
        with open_session() as session:
            fresh_room = session.get(GameRoom, room_id)
            fresh_player = session.get(Player, player.id) if player is not None else None
            snapshot = state_snapshot(session, fresh_room, fresh_player)
        await websocket.send_json(snapshot)
        if announce is not None:
            await connections.broadcast(room_id, announce, exclude=conn)
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            await handle_message(room_id, conn, message)
    except WebSocketDisconnect:
        pass
    finally:
        connections.remove(room_id, conn)
        # a player stays in the room when their socket drops; tell the others, unless
        # another socket of theirs (e.g. a refreshed tab) is still connected
        if conn.role == "player" and not connections.has_connection(room_id, conn.player_id):
            # detached task: this handler may be getting cancelled as the socket dies,
            # and the notice still has to go out
            connections.broadcast_detached(
                room_id, {"type": "player_reconnecting", "nickname": nickname, "avatar": avatar}
            )
