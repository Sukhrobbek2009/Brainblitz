"""POST /quizzes. Validation mirrors the editor's rules in create.html
(problems(), the swatch/visibility/time/points controls); keep the two in sync."""
from typing import Literal, Self

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .db import get_session
from .models import GameRoom, Host, Question, Quiz
from .security import get_current_host

router = APIRouter()

# the editor's cover swatches, timer chips and points chips
COVER_COLORS = {"#7C3AED", "#EC4899", "#F59E0B", "#84CC16", "#0EA5E9", "#EF4444"}
TIME_LIMITS = {5, 10, 20, 30}


class QuestionIn(BaseModel):
    text: str
    type: Literal["quiz", "tf", "poll"] = "quiz"
    answers: list[str]
    correct_index: int | None = None
    time_limit_seconds: int
    # editor: Standard = 1, Double = 2; polls award no points
    points_mode: Literal["standard", "double", "none"]

    @field_validator("text")
    @classmethod
    def text_required(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Add your question text so players know what to answer.")
        return v

    @field_validator("time_limit_seconds")
    @classmethod
    def time_allowed(cls, v: int) -> int:
        if v not in TIME_LIMITS:
            raise ValueError(f"time_limit_seconds must be one of {sorted(TIME_LIMITS)}")
        return v

    @model_validator(mode="after")
    def check_answers(self) -> Self:
        answers = [a.strip() for a in self.answers]
        if self.type == "tf":
            if len(answers) != 2:
                raise ValueError("True/False questions need exactly 2 answers.")
        elif not 2 <= len(answers) <= 4:
            raise ValueError("Questions need between 2 and 4 answers.")
        if any(not a for a in answers):
            raise ValueError("Answers can't be blank.")
        self.answers = answers

        if self.type == "poll":
            if self.correct_index is not None:
                raise ValueError("Polls have no correct answer.")
            if self.points_mode != "none":
                raise ValueError("Polls don't award points.")
        else:
            if self.correct_index is None or not 0 <= self.correct_index < len(answers):
                raise ValueError("correct_index must point at one of the answers.")
            if self.points_mode == "none":
                raise ValueError("points_mode must be 'standard' or 'double'.")
        return self


class QuizIn(BaseModel):
    title: str
    cover_color: str
    visibility: Literal["private", "public"]
    questions: list[QuestionIn] = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def title_required(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Give your quiz a title.")
        return v

    @field_validator("cover_color")
    @classmethod
    def color_allowed(cls, v: str) -> str:
        v = v.upper()
        if v not in COVER_COLORS:
            raise ValueError("cover_color must be one of the editor's swatches.")
        return v


@router.post("/quizzes", status_code=201)
def create_quiz(
    body: QuizIn,
    host: Host = Depends(get_current_host),
    session: Session = Depends(get_session),
):
    quiz = Quiz(
        host_id=host.id,
        title=body.title,
        cover_color=body.cover_color,
        visibility=body.visibility,
    )
    session.add(quiz)
    session.flush()
    for position, q in enumerate(body.questions):
        session.add(Question(quiz_id=quiz.id, position=position, **q.model_dump()))
    session.commit()
    return {"id": quiz.id, "title": quiz.title, "questions": len(body.questions)}


@router.get("/quizzes")
def list_quizzes(
    host: Host = Depends(get_current_host),
    session: Session = Depends(get_session),
):
    count = (
        select(func.count(Question.id))
        .where(Question.quiz_id == Quiz.id)
        .scalar_subquery()
    )
    rows = session.execute(
        select(Quiz, count)
        .where(Quiz.host_id == host.id)
        .order_by(Quiz.created_at.desc(), Quiz.id.desc())
    ).all()
    return [
        {
            "id": quiz.id,
            "title": quiz.title,
            "cover_color": quiz.cover_color,
            "visibility": quiz.visibility,
            "created_at": quiz.created_at,
            "question_count": n,
        }
        for quiz, n in rows
    ]


@router.get("/quizzes/{quiz_id}")
def get_quiz(
    quiz_id: int,
    host: Host = Depends(get_current_host),
    session: Session = Depends(get_session),
):
    quiz = session.get(Quiz, quiz_id)
    # same 404 for "missing" and "someone else's" so ids can't be probed
    if quiz is None or quiz.host_id != host.id:
        raise HTTPException(status_code=404, detail="Quiz not found")
    questions = session.scalars(
        select(Question).where(Question.quiz_id == quiz.id).order_by(Question.position)
    ).all()
    return {
        "id": quiz.id,
        "title": quiz.title,
        "cover_color": quiz.cover_color,
        "visibility": quiz.visibility,
        "created_at": quiz.created_at,
        "questions": [
            {
                "id": q.id,
                "position": q.position,
                "text": q.text,
                "type": q.type,
                "answers": q.answers,
                "correct_index": q.correct_index,
                "time_limit_seconds": q.time_limit_seconds,
                "points_mode": q.points_mode,
            }
            for q in questions
        ],
    }


@router.put("/quizzes/{quiz_id}")
def replace_quiz(
    quiz_id: int,
    body: QuizIn,
    host: Host = Depends(get_current_host),
    session: Session = Depends(get_session),
):
    quiz = session.get(Quiz, quiz_id)
    if quiz is None or quiz.host_id != host.id:
        raise HTTPException(status_code=404, detail="Quiz not found")
    quiz.title = body.title
    quiz.cover_color = body.cover_color
    quiz.visibility = body.visibility
    # one transaction: the old questions only go if the new ones are saved
    session.execute(delete(Question).where(Question.quiz_id == quiz.id))
    for position, q in enumerate(body.questions):
        session.add(Question(quiz_id=quiz.id, position=position, **q.model_dump()))
    session.commit()
    return {"id": quiz.id, "title": quiz.title, "questions": len(body.questions)}


def has_active_room(session: Session, quiz_id: int) -> bool:
    """True if a game room that hasn't ended is using this quiz."""
    return (
        session.scalar(
            select(GameRoom.id)
            .where(GameRoom.quiz_id == quiz_id, GameRoom.status != "ended")
            .limit(1)
        )
        is not None
    )


@router.delete("/quizzes/{quiz_id}", status_code=204)
def delete_quiz(
    quiz_id: int,
    host: Host = Depends(get_current_host),
    session: Session = Depends(get_session),
):
    quiz = session.get(Quiz, quiz_id)
    if quiz is None or quiz.host_id != host.id:
        raise HTTPException(status_code=404, detail="Quiz not found")
    if has_active_room(session, quiz.id):
        raise HTTPException(
            status_code=409,
            detail="This quiz has a game in progress. End the game before deleting it.",
        )
    session.delete(quiz)  # questions go with it (ON DELETE CASCADE)
    session.commit()
