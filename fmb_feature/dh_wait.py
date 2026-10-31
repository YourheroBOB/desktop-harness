"""Race-free polling helpers (wait_for / wait_stable) for desktop-harness.

Why this exists
---------------
Agents today either sleep a fixed amount (``wait(0.5)``) or read the UI once
immediately after an action.  Fixed sleeps are slow *and* still racy; a single
read right after a click is a coin flip.  ``SKILL.md`` already tells agents to
"verify, don't assume" and ``docs/PRE-RELEASE-REVIEW.md`` lists the missing
``wait_for(text/role, timeout=)`` as a High-severity capability gap -- this
module is the primitive that makes "poll until the screen agrees" cheap.

Design constraints (deliberate)
-------------------------------
* Pure stdlib: no pyobjc, no network, no filesystem, no environment lookups.
* The caller injects *what* to poll (``lambda: find("Save")``), so this module
  needs no Mac and is fully unit-testable off-device.
* Clock and sleep are injectable, so tests are deterministic and fast.
* Polling only *observes*.  It never synthesises input, so every existing
  safety gate (sensitive-app checks, audit log) still applies to the polled
  callable exactly as before.

Typical use inside a harness script::

    from dh_wait import wait_for, wait_for_change

    before = labels(app="Music")
    click_text("Play", app="Music")
    res = wait_for_change(lambda: labels(app="Music"), before, timeout=2.0)
    print(res.ok, res.attempts, f"{res.elapsed:.2f}s")

    node = wait_for(lambda: find("Save", app="TextEdit"), timeout=3.0)
    if not node:
        print("Save button never appeared")
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = [
    "DEFAULT_BACKOFF",
    "DEFAULT_INTERVAL",
    "DEFAULT_MAX_INTERVAL",
    "DEFAULT_TIMEOUT",
    "Deadline",
    "WaitResult",
    "wait_for",
    "wait_for_change",
    "wait_stable",
    "wait_until",
    "wait_until_gone",
]

DEFAULT_TIMEOUT = 5.0
DEFAULT_INTERVAL = 0.1
DEFAULT_BACKOFF = 1.5
DEFAULT_MAX_INTERVAL = 0.5

# Never spin: even interval=0 is clamped to 1ms so a zero-cost clock (tests,
# or a very fast predicate) cannot turn the loop into a busy-wait.
MIN_INTERVAL = 0.001

Predicate = Callable[[], Any]
Snapshot = Callable[[], Any]

_UNSET = object()


@dataclass(frozen=True)
class WaitResult:
    """Outcome of one bounded poll.

    ``ok`` is True when the predicate reported the wanted state before the
    deadline.  On failure ``value`` holds the *last observed* value (useful
    for "what was on screen instead?") and ``last_error`` the last exception
    raised by the predicate, if any.
    """

    ok: bool
    value: Any = None
    attempts: int = 0
    elapsed: float = 0.0
    last_error: BaseException | None = None

    def __bool__(self) -> bool:
        return self.ok

    @property
    def timed_out(self) -> bool:
        return not self.ok

    def unwrap(self) -> Any:
        """Return the value, or raise ``TimeoutError`` with poll details."""
        if self.ok:
            return self.value
        detail = f"attempts={self.attempts} elapsed={self.elapsed:.3f}s"
        if self.last_error is not None:
            detail += (
                f" last_error={type(self.last_error).__name__}: {self.last_error}"
            )
        raise TimeoutError(f"wait timed out ({detail})")


@dataclass
class Deadline:
    """A shared time budget for multi-step sequences.

    ``clock`` is injectable so tests can drive it deterministically.
    """

    timeout: float
    clock: Callable[[], float] = time.monotonic
    _start: float = field(init=False, repr=False, default=0.0)

    def __post_init__(self) -> None:
        if self.timeout < 0:
            raise ValueError(f"timeout must be >= 0, got {self.timeout!r}")
        self._start = self.clock()

    def elapsed(self) -> float:
        return self.clock() - self._start

    def remaining(self) -> float:
        return max(0.0, self.timeout - self.elapsed())

    def expired(self) -> bool:
        return self.remaining() <= 0.0

    def clamp(self, seconds: float) -> float:
        """``seconds`` capped to what is left in the budget (never negative)."""
        return max(0.0, min(seconds, self.remaining()))


def _identity(value: Any) -> Any:
    return value


def _eq(a: Any, b: Any) -> bool:
    return a == b


def _validate(
    *,
    timeout: float,
    interval: float,
    backoff: float,
    max_interval: float,
) -> None:
    if timeout < 0:
        raise ValueError(f"timeout must be >= 0, got {timeout!r}")
    if interval < 0:
        raise ValueError(f"interval must be >= 0, got {interval!r}")
    if max_interval < 0:
        raise ValueError(f"max_interval must be >= 0, got {max_interval!r}")
    if backoff < 1:
        raise ValueError(f"backoff must be >= 1, got {backoff!r}")


def _drive(
    step: Callable[[], tuple[bool, Any]],
    *,
    timeout: float,
    interval: float,
    backoff: float,
    max_interval: float,
    clock: Callable[[], float] | None,
    sleep: Callable[[float], None] | None,
    errors: Any,
) -> WaitResult:
    """Call ``step()`` until it reports done or the deadline passes.

    ``step`` returns ``(done, value)``.  Exceptions matching ``errors`` count
    as a failed attempt (transient AX reads fail while an app is switching);
    anything else propagates untouched.
    """
    _validate(
        timeout=timeout,
        interval=interval,
        backoff=backoff,
        max_interval=max_interval,
    )
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    cap = max(max_interval, interval)

    start = clock()
    delay = interval
    attempts = 0
    value: Any = None
    last_error: BaseException | None = None

    while True:
        attempts += 1
        try:
            done, value = step()
        except errors as exc:  # noqa: B902 - caller-controlled retry set
            done, value, last_error = False, None, exc
        else:
            last_error = None

        elapsed = clock() - start
        if done:
            return WaitResult(
                ok=True,
                value=value,
                attempts=attempts,
                elapsed=elapsed,
                last_error=last_error,
            )

        remaining = timeout - elapsed
        if remaining <= 0:
            return WaitResult(
                ok=False,
                value=value,
                attempts=attempts,
                elapsed=elapsed,
                last_error=last_error,
            )

        # Always poll at least once (already-true is 0 sleeps), never sleep
        # past the deadline.
        sleep(min(max(delay, MIN_INTERVAL), remaining))
        delay = min(delay * backoff, cap)


def wait_until(
    predicate: Predicate,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    interval: float = DEFAULT_INTERVAL,
    backoff: float = DEFAULT_BACKOFF,
    max_interval: float = DEFAULT_MAX_INTERVAL,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    errors: Any = (Exception,),
) -> WaitResult:
    """Poll ``predicate`` until it returns something truthy or time runs out.

    The predicate is always called at least once, so an already-satisfied
    condition costs zero sleeps.
    """
    def step() -> tuple[bool, Any]:
        value = predicate()
        return bool(value), value

    return _drive(
        step,
        timeout=timeout,
        interval=interval,
        backoff=backoff,
        max_interval=max_interval,
        clock=clock,
        sleep=sleep,
        errors=errors,
    )


def wait_for(match: Predicate, **kwargs: Any) -> WaitResult:
    """Intention-revealing alias of :func:`wait_until` for node finders.

    Use it when the callable returns a *matched object* (``find(...)``) rather
    than a bool; ``result.value`` is then the match.
    """
    return wait_until(match, **kwargs)


def wait_until_gone(
    predicate: Predicate,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    interval: float = DEFAULT_INTERVAL,
    backoff: float = DEFAULT_BACKOFF,
    max_interval: float = DEFAULT_MAX_INTERVAL,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    errors: Any = (Exception,),
) -> WaitResult:
    """Poll until ``predicate`` reports *nothing* (spinner/dialog gone).

    On success ``value`` is the falsy observation (usually ``None``).  On
    timeout ``value`` is the last truthy thing still on screen.
    """
    def step() -> tuple[bool, Any]:
        value = predicate()
        return (not value), value

    return _drive(
        step,
        timeout=timeout,
        interval=interval,
        backoff=backoff,
        max_interval=max_interval,
        clock=clock,
        sleep=sleep,
        errors=errors,
    )


def wait_for_change(
    snapshot: Snapshot,
    baseline: Any,
    *,
    key: Callable[[Any], Any] | None = None,
    equal: Callable[[Any, Any], bool] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    interval: float = DEFAULT_INTERVAL,
    backoff: float = DEFAULT_BACKOFF,
    max_interval: float = DEFAULT_MAX_INTERVAL,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    errors: Any = (Exception,),
) -> WaitResult:
    """Poll until the snapshot differs from ``baseline`` (did the click land?).

    ``key`` projects a volatile snapshot (labels, AX dump) down to the part
    that must change, so unrelated churn does not count as success.
    """
    project = key or _identity
    same = equal or _eq
    base = project(baseline)

    def step() -> tuple[bool, Any]:
        value = snapshot()
        return (not same(project(value), base)), value

    return _drive(
        step,
        timeout=timeout,
        interval=interval,
        backoff=backoff,
        max_interval=max_interval,
        clock=clock,
        sleep=sleep,
        errors=errors,
    )


def wait_stable(
    snapshot: Snapshot,
    *,
    settle: int = 2,
    key: Callable[[Any], Any] | None = None,
    equal: Callable[[Any, Any], bool] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    interval: float = DEFAULT_INTERVAL,
    backoff: float = DEFAULT_BACKOFF,
    max_interval: float = DEFAULT_MAX_INTERVAL,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    errors: Any = (Exception,),
) -> WaitResult:
    """Poll until ``settle`` consecutive observations agree (UI settled).

    ``settle=2`` means "read the same thing twice in a row", which is the
    cheapest real evidence that a transition finished.  ``settle=1`` accepts
    the first observation (equivalent to a single read).
    """
    if settle < 1:
        raise ValueError(f"settle must be >= 1, got {settle!r}")
    project = key or _identity
    same = equal or _eq
    state: dict[str, Any] = {"prev": _UNSET, "streak": 0}

    def step() -> tuple[bool, Any]:
        value = snapshot()
        k = project(value)
        if state["prev"] is not _UNSET and same(state["prev"], k):
            state["streak"] += 1
        else:
            state["streak"] = 1
        state["prev"] = k
        return state["streak"] >= settle, value

    return _drive(
        step,
        timeout=timeout,
        interval=interval,
        backoff=backoff,
        max_interval=max_interval,
        clock=clock,
        sleep=sleep,
        errors=errors,
    )
