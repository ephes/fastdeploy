"""
Limit failed logins on ``POST /token``.

Attempts are counted per (user name, client address) and per client address
inside a fixed window. An attempt is counted when it begins, before the
password is checked, and taken back when the login succeeds, so requests sent
in parallel cannot exceed the limit while their password checks are still
running. State lives in this process, which matches the single API process.
"""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

from .config import settings

MAX_TRACKED_KEYS = 20_000
MAX_USERNAME_LENGTH = 256

Key = tuple[str, ...]


@dataclass(eq=False)
class Attempt:
    """
    One login attempt. It counts from the moment it begins; ``pending`` is
    True until its password check has finished.
    """

    stamp: float
    pair_key: Key
    address_key: Key
    pending: bool = True


class LoginThrottle:
    def __init__(
        self,
        *,
        limit: int | None = None,
        address_limit: int | None = None,
        window_seconds: float | None = None,
        max_tracked_keys: int = MAX_TRACKED_KEYS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        # None: read the setting on every call, so the configuration stays the single source
        self._limit = limit
        self._address_limit = address_limit
        self._window_seconds = window_seconds
        self.max_tracked_keys = max_tracked_keys
        self.clock = clock
        self._attempts: dict[Key, list[Attempt]] = {}

    @property
    def limit(self) -> int:
        return settings.login_failure_limit if self._limit is None else self._limit

    @property
    def address_limit(self) -> int:
        return settings.login_address_failure_limit if self._address_limit is None else self._address_limit

    @property
    def window_seconds(self) -> float:
        return settings.login_failure_window_seconds if self._window_seconds is None else self._window_seconds

    @property
    def enabled(self) -> bool:
        return self.limit > 0

    @staticmethod
    def _keys(username: str, address: str) -> tuple[Key, Key]:
        name = username[:MAX_USERNAME_LENGTH].casefold()
        return ("pair", name, address), ("address", address)

    def _store(self, key: Key, attempts: list[Attempt]) -> None:
        if attempts:
            self._attempts[key] = attempts
        else:
            self._attempts.pop(key, None)

    def _recent(self, key: Key, now: float) -> list[Attempt]:
        cutoff = now - self.window_seconds
        recent = [attempt for attempt in self._attempts.get(key, []) if attempt.stamp > cutoff]
        self._store(key, recent)
        return recent

    def _prune(self, now: float) -> None:
        for key in list(self._attempts):
            self._recent(key, now)
        overflow = len(self._attempts) - self.max_tracked_keys
        if overflow > 0:
            # drop the keys whose newest attempt is oldest, they are the closest to expiring anyway
            by_age = sorted(self._attempts, key=lambda key: self._attempts[key][-1].stamp)
            for key in by_age[:overflow]:
                self._attempts.pop(key, None)

    def retry_after(self, username: str, address: str) -> int | None:
        """
        Seconds until another attempt is allowed, or None if one is allowed now.
        """
        if not self.enabled:
            return None
        now = self.clock()
        waits: list[float] = []
        for key, limit in zip(self._keys(username, address), (self.limit, self.address_limit), strict=True):
            recent = self._recent(key, now)
            if limit > 0 and len(recent) >= limit:
                # allowed again when enough of the oldest counted attempts left the window
                waits.append(recent[len(recent) - limit].stamp + self.window_seconds - now)
        if not waits:
            return None
        return max(1, math.ceil(max(waits)))

    def begin_attempt(self, username: str, address: str) -> Attempt | None:
        """
        Count an attempt before its password check starts. The result has to
        be passed to ``record_failure`` or ``record_success`` afterwards.
        Returns None while the throttle is turned off.
        """
        if not self.enabled:
            return None
        now = self.clock()
        pair_key, address_key = self._keys(username, address)
        attempt = Attempt(stamp=now, pair_key=pair_key, address_key=address_key)
        for key, limit in ((pair_key, self.limit), (address_key, self.address_limit)):
            recent = self._recent(key, now)
            recent.append(attempt)
            # no need to keep more attempts than the limit can ever look at
            self._store(key, recent[-max(limit, 1) :])
        if len(self._attempts) > self.max_tracked_keys:
            self._prune(now)
        return attempt

    @staticmethod
    def record_failure(attempt: Attempt | None) -> None:
        """The password check of this attempt finished without a login: it stays counted."""
        if attempt is not None:
            attempt.pending = False

    def record_success(self, attempt: Attempt | None) -> None:
        """
        This attempt logged in: take exactly this attempt back and forget the
        finished failures of its user name from its address. Attempts of the
        same user name and address whose password check is still running stay
        counted, and so does every other attempt from the address.
        """
        if attempt is None:
            return
        attempt.pending = False
        pair = [other for other in self._attempts.get(attempt.pair_key, []) if other is not attempt and other.pending]
        self._store(attempt.pair_key, pair)
        address = [other for other in self._attempts.get(attempt.address_key, []) if other is not attempt]
        self._store(attempt.address_key, address)

    def clear(self) -> None:
        self._attempts.clear()


login_throttle = LoginThrottle()
