import unittest

from app.services.retry import retry_call


class RetryCallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.slept: list[float] = []

    def _sleep(self, seconds: float) -> None:
        self.slept.append(seconds)

    def test_returns_value_on_first_success_without_sleeping(self) -> None:
        calls = {"n": 0}

        def op() -> str:
            calls["n"] += 1
            return "ok"

        result = retry_call(op, attempts=3, base_delay=0.5, sleep=self._sleep)

        self.assertEqual(result, "ok")
        self.assertEqual(calls["n"], 1)
        self.assertEqual(self.slept, [])

    def test_retries_until_success(self) -> None:
        calls = {"n": 0}

        def op() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("transient")
            return "ok"

        result = retry_call(op, attempts=3, base_delay=0.5, sleep=self._sleep)

        self.assertEqual(result, "ok")
        self.assertEqual(calls["n"], 3)
        # Slept between the two failures, not after the final success.
        self.assertEqual(self.slept, [0.5, 1.0])

    def test_raises_last_exception_after_exhausting_attempts(self) -> None:
        calls = {"n": 0}

        def op() -> str:
            calls["n"] += 1
            raise RuntimeError(f"fail {calls['n']}")

        with self.assertRaises(RuntimeError) as ctx:
            retry_call(op, attempts=3, base_delay=0.5, sleep=self._sleep)

        self.assertEqual(str(ctx.exception), "fail 3")
        self.assertEqual(calls["n"], 3)
        # Sleeps only between attempts, so attempts - 1 times.
        self.assertEqual(self.slept, [0.5, 1.0])


if __name__ == "__main__":
    unittest.main()
