"""Scoring, matching scoreRound() in lobby.html so the server and the screen agree.

Correct answer: 1000 x the question's multiplier, falling linearly to half of that as
the time runs out. From the 3rd correct answer in a row, a flat streak bonus of
+100 per answer beyond the 2nd, capped at +500. Wrong or missing answers score 0 and
end the streak. Polls have no right answer: 0 points, and the streak is left alone.
"""
import math
from dataclasses import dataclass

from .models import Question

MAX_POINTS = 1000
MIN_SPEED_FRACTION = 0.5  # share of the max still earned at the last instant
STREAK_START = 3
STREAK_STEP = 100
STREAK_CAP = 500
MULTIPLIERS = {"standard": 1, "double": 2, "none": 0}


@dataclass(frozen=True)
class ScoreResult:
    correct: bool
    speed_points: int  # the "865" part
    streak_bonus: int  # the flat streak part
    streak: int  # the player's streak after this answer

    @property
    def total(self) -> int:
        return self.speed_points + self.streak_bonus


def score_answer(
    question: Question,
    chosen_index: int | None,
    server_elapsed_ms: float,
    current_streak: int,
) -> ScoreResult:
    """Score one player's answer.

    chosen_index is what the player picked (None if they didn't answer); it is needed
    to tell right from wrong. server_elapsed_ms is measured by the server, from when
    the question was shown to when the answer arrived.
    """
    if question.type == "poll":
        return ScoreResult(False, 0, 0, current_streak)
    if chosen_index is None or chosen_index != question.correct_index:
        return ScoreResult(False, 0, 0, 0)

    limit_ms = question.time_limit_seconds * 1000
    used = min(1.0, max(0.0, server_elapsed_ms) / limit_ms)
    multiplier = MULTIPLIERS[question.points_mode]
    # floor(x + .5) rounds halves up, like JavaScript's Math.round (Python's round() doesn't)
    speed = math.floor(MAX_POINTS * multiplier * (1 - (1 - MIN_SPEED_FRACTION) * used) + 0.5)

    streak = current_streak + 1
    bonus = min(STREAK_CAP, (streak - STREAK_START + 1) * STREAK_STEP) if streak >= STREAK_START else 0
    return ScoreResult(True, speed, bonus, streak)
