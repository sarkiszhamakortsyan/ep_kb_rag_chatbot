import math
from collections.abc import Iterable


def percentile(values: Iterable[float], pct: float) -> float | None:
    """Nearest-rank percentile (pct in 0..100); None for no values."""
    ordered = sorted(values)
    if not ordered:
        return None
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def latency_summary(values_ms: Iterable[float]) -> dict[str, float | None]:
    values = list(values_ms)
    return {
        "p50_ms": percentile(values, 50),
        "p95_ms": percentile(values, 95),
        "max_ms": max(values) if values else None,
    }
