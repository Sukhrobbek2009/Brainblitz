import unittest

from app.models import AnswerLog
from app.ratelimit import SlidingWindowLimiter


class JoinRateLimitTests(unittest.TestCase):
    def test_caps_per_key_and_recovers(self):
        now = [0.0]
        lim = SlidingWindowLimiter(3, 60, clock=lambda: now[0])
        self.assertTrue(all(lim.hit("111111") is None for _ in range(3)))
        wait = lim.hit("111111")
        self.assertIsNotNone(wait)
        self.assertGreater(wait, 0)
        self.assertIsNone(lim.hit("222222"))  # other PINs are unaffected
        now[0] = 61
        self.assertIsNone(lim.hit("111111"))


class OneAnswerPerPlayerPerQuestionTests(unittest.TestCase):
    def test_db_unique_constraint_backs_the_server_check(self):
        cols = {
            tuple(c.name for c in con.columns)
            for con in AnswerLog.__table__.constraints
            if con.__class__.__name__ == "UniqueConstraint"
        }
        self.assertIn(("player_id", "question_index"), cols)
