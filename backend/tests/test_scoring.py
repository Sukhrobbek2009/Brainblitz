import unittest

from app.models import Question
from app.scoring import score_answer


def q(type_="quiz", mode="standard", limit=20, correct=1):
    return Question(type=type_, points_mode=mode, time_limit_seconds=limit,
                    correct_index=correct, answers=["a", "b", "c"], text="?")


class ScoreAnswerTests(unittest.TestCase):
    def test_instant_correct_is_1000(self):
        r = score_answer(q(), 1, 0, 0)
        self.assertEqual((r.correct, r.total, r.streak), (True, 1000, 1))

    def test_slides_to_half_at_the_deadline(self):
        self.assertEqual(score_answer(q(), 1, 20_000, 0).total, 500)
        self.assertEqual(score_answer(q(), 1, 10_000, 0).total, 750)

    def test_frontend_style_number(self):
        self.assertEqual(score_answer(q(), 1, 5_400, 0).speed_points, 865)

    def test_clamps_out_of_range_times(self):
        self.assertEqual(score_answer(q(), 1, 99_999, 0).total, 500)
        self.assertEqual(score_answer(q(), 1, -50, 0).total, 1000)

    def test_wrong_or_missing_scores_zero_and_resets_streak(self):
        for chosen in (0, 2, None):
            r = score_answer(q(), chosen, 1_000, 4)
            self.assertEqual((r.correct, r.total, r.streak), (False, 0, 0))

    def test_streak_bonus_starts_at_third_in_a_row(self):
        self.assertEqual(score_answer(q(), 1, 0, 0).streak_bonus, 0)   # 1st
        self.assertEqual(score_answer(q(), 1, 0, 1).streak_bonus, 0)   # 2nd
        self.assertEqual(score_answer(q(), 1, 0, 2).streak_bonus, 100) # 3rd
        self.assertEqual(score_answer(q(), 1, 0, 3).streak_bonus, 200) # 4th
        self.assertEqual(score_answer(q(), 1, 0, 2).total, 1100)

    def test_streak_bonus_is_capped(self):
        self.assertEqual(score_answer(q(), 1, 0, 6).streak_bonus, 500)
        self.assertEqual(score_answer(q(), 1, 0, 50).streak_bonus, 500)

    def test_double_points(self):
        self.assertEqual(score_answer(q(mode="double"), 1, 0, 0).speed_points, 2000)
        self.assertEqual(score_answer(q(mode="double"), 1, 20_000, 0).speed_points, 1000)

    def test_poll_scores_nothing_and_keeps_streak(self):
        r = score_answer(q("poll", "none", correct=None), 0, 500, 4)
        self.assertEqual((r.total, r.streak), (0, 4))

    def test_rounds_half_up(self):
        # 1000 * (1 - .5 * .0001) = 999.95 -> 1000 ; .5 boundary: 1000*(1-.5*.001)=999.5 -> 1000
        self.assertEqual(score_answer(q(limit=1), 1, 1, 0).speed_points, 1000)


if __name__ == "__main__":
    unittest.main()
