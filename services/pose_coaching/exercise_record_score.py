"""운동별 버전 고정 점수 정책."""
from decimal import Decimal


def calculate_set_score(
    completed_sets: int,
    target_sets: int,
    score_per_set: Decimal,
) -> Decimal:
    if target_sets < 1 or completed_sets < 0 or completed_sets > target_sets:
        raise ValueError("INVALID_COMPLETED_SETS")
    if score_per_set < 0:
        raise ValueError("INVALID_SCORE_POLICY")

    return min(
        Decimal("100.00"),
        (Decimal(completed_sets) * score_per_set).quantize(Decimal("0.01")),
    )
