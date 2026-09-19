"""Bounded, ordered thread work with structured shutdown on early exit."""
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from itertools import islice


@contextmanager
def ordered_map[T, R](function: Callable[[T], R], items: Iterable[T], *,
                      workers: int = 8, capacity: int = 16) -> Iterator[Iterator[R]]:
    """At most capacity submitted results; exceptions reach the consuming thread.

    The yielded result counts toward capacity until consumption resumes. Early
    exit cancels queued work and joins running tasks before returning to caller.
    """
    if workers < 1 or capacity < 1:
        raise ValueError("workers and capacity must be positive")
    source = iter(items)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="curator-cpu") as pool:
        pending = deque(pool.submit(function, item) for item in islice(source, capacity))

        def consume() -> Iterator[R]:
            while pending:
                yield pending.popleft().result()
                for item in islice(source, 1):
                    pending.append(pool.submit(function, item))

        try:
            yield consume()
        finally:
            for future in pending:
                future.cancel()
