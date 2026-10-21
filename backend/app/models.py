import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Float,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Host(Base):
    __tablename__ = "hosts"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    host_id: Mapped[int] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    cover_color: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(Text, nullable=False, server_default="private")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("quiz_id", "position"),
        CheckConstraint("cardinality(answers) <= 4", name="answers_max_4"),
        CheckConstraint(
            "correct_index IS NULL OR correct_index BETWEEN 0 AND 3",
            name="correct_index_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    answers: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    correct_index: Mapped[int | None] = mapped_column(Integer)  # NULL for polls
    time_limit_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    points_mode: Mapped[str] = mapped_column(Text, nullable=False)


class GameRoom(Base):
    __tablename__ = "game_rooms"
    __table_args__ = (
        # a PIN is unique among rooms that haven't ended; ended rooms free theirs up
        Index(
            "uq_game_rooms_active_pin",
            "pin",
            unique=True,
            postgresql_where=text("status <> 'ended'"),
            sqlite_where=text("status <> 'ended'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # kept (as NULL) if the quiz is deleted later, so finished games stay as history
    quiz_id: Mapped[int | None] = mapped_column(
        ForeignKey("quizzes.id", ondelete="SET NULL"), index=True
    )
    host_id: Mapped[int] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pin: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="lobby")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # which question is on screen; NULL until the game starts
    current_question_index: Mapped[int | None] = mapped_column(Integer)
    # server clock time at which the current question was shown to everyone
    question_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        # nicknames are unique within a room, ignoring case
        Index("uq_players_room_nickname", "room_id", func.lower(text("nickname")), unique=True),
    )

    # random UUID rather than a counter: the browser keeps it for the rest of the
    # game and it is the only thing identifying that player, so it must not be guessable
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("game_rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nickname: Mapped[str] = mapped_column(Text, nullable=False)
    avatar: Mapped[str] = mapped_column(Text, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # running total and current correct-in-a-row, updated as each answer is scored
    score: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    streak: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)


class AnswerLog(Base):
    """One permanent row per scored answer, wrong ones included. Rows are only ever
    inserted: nothing in the app updates or deletes them."""

    __tablename__ = "answers_log"
    __table_args__ = (UniqueConstraint("player_id", "question_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("game_rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    # Editing a quiz (PUT) re-creates its questions with new ids, so this goes NULL
    # rather than deleting history; question_index is the stable position in the game.
    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL")
    )
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chosen_index: Mapped[int] = mapped_column(Integer, nullable=False)
    server_elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    points_awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    # the server's clock at the moment the message arrived; never a client-reported time
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GameResult(Base):
    """One archived row per finished game, written when the host ends the room."""

    __tablename__ = "game_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    # the archive outlives the room and quiz it came from, so these go NULL, not away
    room_id: Mapped[int | None] = mapped_column(
        ForeignKey("game_rooms.id", ondelete="SET NULL"), unique=True
    )
    quiz_id: Mapped[int | None] = mapped_column(ForeignKey("quizzes.id", ondelete="SET NULL"))
    host_id: Mapped[int] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quiz_title: Mapped[str | None] = mapped_column(Text)  # as it was when the game ended
    pin: Mapped[str] = mapped_column(Text, nullable=False)
    player_count: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_score: Mapped[float | None] = mapped_column(Float)  # NULL when nobody played
    # mean over players of (correct answers / questions asked); polls excluded
    avg_accuracy: Mapped[float | None] = mapped_column(Float)
    # the questions as they were when the game ended (text, type, answers, correct_index,
    # time_limit_seconds, points_mode), so the archive survives later edits or deletion of the quiz
    questions: Mapped[list | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    # final standings: rank, nickname, avatar, score, correct, graded, accuracy
    standings: Mapped[list] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    # per-question numbers frozen at the end (text, correct answer, how many got it right), so the
    # report survives the quiz being edited or deleted later. NULL for games archived before this existed.
    question_stats: Mapped[list | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
