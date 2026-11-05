from collections.abc import Sequence
from math import isfinite, sqrt


def validated_embedding(vector: Sequence[float], expected_dimension: int) -> tuple[float, ...]:
    if len(vector) != expected_dimension:
        raise ValueError("dimension")
    normalized = tuple(float(value) for value in vector)
    if not all(isfinite(value) for value in normalized):
        raise ValueError("non_finite")
    return normalized


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("vectors must have the same non-zero dimension")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("zero-length embedding")
    return dot / (left_norm * right_norm)
