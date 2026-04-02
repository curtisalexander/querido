"""Shared concurrency helper for parallel query execution."""

from __future__ import annotations

import collections.abc


def run_parallel[T, K, V](
    items: list[T],
    fn: collections.abc.Callable[[T], tuple[K, V]],
    *,
    max_workers: int = 4,
) -> dict[K, V]:
    """Execute *fn* on each item concurrently, returning ``{key: value}``.

    *fn* must accept a single argument from *items* and return a
    ``(key, value)`` tuple.  Results are collected into a dict.

    Falls back to sequential execution when *items* has one or zero entries.
    """
    if len(items) <= 1:
        return dict(fn(item) for item in items)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    workers = min(len(items), max_workers)
    result: dict[K, V] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, item): item for item in items}
        for future in as_completed(futures):
            key, value = future.result()
            result[key] = value
    return result


def run_parallel_ordered[T, V](
    items: list[T],
    fn: collections.abc.Callable[[T], V],
    *,
    max_workers: int = 4,
) -> list[V]:
    """Execute *fn* on each item concurrently, preserving input order.

    *fn* must accept a single argument and return a result.
    Returns a list in the same order as *items*.
    """
    if len(items) <= 1:
        return [fn(item) for item in items]

    from concurrent.futures import ThreadPoolExecutor, as_completed

    workers = min(len(items), max_workers)
    results: dict[int, V] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, item): i for i, item in enumerate(items)}
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()

    return [results[i] for i in range(len(items))]
