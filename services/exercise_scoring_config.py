"""운동별 점수 계산 설정. 운동 ID 1은 현재 Side Kick 테스트 데이터 기준."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ScoringRule:
    target_sets: int
    score_per_set: Decimal


SCORING_RULES: dict[int, ScoringRule] = {
    1: ScoringRule(target_sets=10, score_per_set=Decimal("10.00")),
}


def get_scoring_rule(exercise_id: int) -> ScoringRule:
    try:
        return SCORING_RULES[exercise_id]
    except KeyError:
        raise ValueError(f"점수 규칙이 등록되지 않은 운동 ID: {exercise_id}") from None
