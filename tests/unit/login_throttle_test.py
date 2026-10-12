from deploy.login_throttle import LoginThrottle


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(limit=3, address_limit=5, window=60, **kwargs):
    clock = Clock()
    return LoginThrottle(limit=limit, address_limit=address_limit, window_seconds=window, clock=clock, **kwargs), clock


def fail(throttle, username="user", address="10.0.0.1", times=1):
    for _ in range(times):
        throttle.record_failure(throttle.begin_attempt(username, address))


def test_allows_attempts_below_the_limit():
    throttle, _ = make()
    fail(throttle, times=2)
    assert throttle.retry_after("user", "10.0.0.1") is None


def test_locks_user_and_address_pair_at_the_limit():
    throttle, clock = make()
    fail(throttle, times=3)
    assert throttle.retry_after("user", "10.0.0.1") == 60
    clock.now += 20
    assert throttle.retry_after("user", "10.0.0.1") == 40
    # other user names and other addresses are not affected
    assert throttle.retry_after("other", "10.0.0.1") is None
    assert throttle.retry_after("user", "10.0.0.2") is None


def test_user_name_case_does_not_dodge_the_limit():
    throttle, _ = make()
    fail(throttle, username="user")
    fail(throttle, username="USER")
    fail(throttle, username="User")
    assert throttle.retry_after("uSeR", "10.0.0.1") is not None


def test_address_limit_covers_attempts_spread_over_user_names():
    throttle, _ = make()
    for index in range(5):
        fail(throttle, username=f"user{index}")
    assert throttle.retry_after("someone-new", "10.0.0.1") == 60
    assert throttle.retry_after("someone-new", "10.0.0.2") is None


def test_window_expiry_unlocks():
    throttle, clock = make()
    fail(throttle, times=3)
    clock.now += 60
    assert throttle.retry_after("user", "10.0.0.1") is None


def test_retry_after_is_the_time_until_enough_attempts_expired():
    throttle, clock = make()
    fail(throttle)
    clock.now += 30
    fail(throttle, times=2)
    # the oldest counted attempt leaves the window in 30 seconds
    assert throttle.retry_after("user", "10.0.0.1") == 30


def test_successful_attempt_is_taken_back_and_resets_the_pair():
    throttle, _ = make()
    fail(throttle, times=2)
    throttle.record_success(throttle.begin_attempt("user", "10.0.0.1"))
    fail(throttle, times=2)
    assert throttle.retry_after("user", "10.0.0.1") is None
    # the two earlier failures still count for the address (2 + 2), the successful attempt does not
    fail(throttle, username="other")
    assert throttle.retry_after("third", "10.0.0.1") == 60


def test_parallel_attempts_are_counted_before_they_finish():
    throttle, _ = make()
    # three requests passed the check and are still verifying their password
    for _ in range(3):
        assert throttle.retry_after("user", "10.0.0.1") is None
        throttle.begin_attempt("user", "10.0.0.1")
    assert throttle.retry_after("user", "10.0.0.1") is not None


def test_success_finishing_first_takes_back_its_own_attempt_not_a_newer_failure():
    throttle, clock = make(limit=10, address_limit=2, window=60)
    success = throttle.begin_attempt("user", "10.0.0.1")
    clock.now += 10
    failure = throttle.begin_attempt("other", "10.0.0.1")
    # the checks finish out of order: the older attempt succeeds, the newer one fails afterwards
    throttle.record_success(success)
    throttle.record_failure(failure)
    clock.now += 20
    fail(throttle, username="third")
    # The failures are 20 s and 0 s old, so the address stays limited for 40 s. Taking back the newest
    # entry instead of the successful one would have left 30 s.
    assert throttle.retry_after("fourth", "10.0.0.1") == 40


def test_success_keeps_attempts_of_the_same_pair_that_are_still_running():
    throttle, _ = make(limit=3)
    fail(throttle, times=1)
    running = [throttle.begin_attempt("user", "10.0.0.1") for _ in range(2)]
    success = throttle.begin_attempt("user", "10.0.0.1")
    throttle.record_success(success)
    # the finished failure is forgotten, the two running checks still count
    assert throttle.retry_after("user", "10.0.0.1") is None
    fail(throttle, times=1)
    assert throttle.retry_after("user", "10.0.0.1") is not None
    for attempt in running:
        throttle.record_failure(attempt)
    assert throttle.retry_after("user", "10.0.0.1") is not None


def test_failure_recorded_after_a_success_of_the_same_pair_still_counts():
    throttle, _ = make(limit=2)
    slow_failure = throttle.begin_attempt("user", "10.0.0.1")
    throttle.record_success(throttle.begin_attempt("user", "10.0.0.1"))
    throttle.record_failure(slow_failure)
    fail(throttle, times=1)
    assert throttle.retry_after("user", "10.0.0.1") is not None


def test_turned_off_throttle_hands_out_no_attempts():
    throttle, _ = make(limit=0)
    attempt = throttle.begin_attempt("user", "10.0.0.1")
    assert attempt is None
    throttle.record_failure(attempt)
    throttle.record_success(attempt)
    assert throttle._attempts == {}


def test_limit_zero_turns_the_throttle_off():
    throttle, _ = make(limit=0)
    fail(throttle, times=50)
    assert throttle.retry_after("user", "10.0.0.1") is None


def test_address_limit_zero_only_turns_the_address_limit_off():
    throttle, _ = make(limit=3, address_limit=0)
    for index in range(20):
        fail(throttle, username=f"user{index}")
    assert throttle.retry_after("fresh", "10.0.0.1") is None
    fail(throttle, username="fresh", times=3)
    assert throttle.retry_after("fresh", "10.0.0.1") is not None


def test_tracked_keys_are_bounded():
    throttle, clock = make(max_tracked_keys=10)
    for index in range(200):
        clock.now += 0.001
        fail(throttle, username=f"user{index}", address=f"10.0.{index}.1")
    assert len(throttle._attempts) <= 10


def test_very_long_user_names_share_a_bounded_key():
    throttle, _ = make()
    fail(throttle, username="x" * 100_000, times=3)
    assert all(len(part) <= 256 for key in throttle._attempts for part in key)
    assert throttle.retry_after("x" * 100_000, "10.0.0.1") is not None


def test_defaults_come_from_the_settings(monkeypatch):
    from deploy.config import settings

    throttle = LoginThrottle()
    assert throttle.limit == settings.login_failure_limit == 10
    assert throttle.address_limit == settings.login_address_failure_limit == 50
    assert throttle.window_seconds == settings.login_failure_window_seconds == 900
    monkeypatch.setattr(settings, "login_failure_limit", 2)
    fail(throttle, times=2)
    assert throttle.retry_after("user", "10.0.0.1") is not None
