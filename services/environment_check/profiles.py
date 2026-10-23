"""DB가 아닌 코드 설정으로 관리하는 환경 점검 정책."""
# 검사 설정표 - 운동별로 어떤 추가 환경 점검 규칙을 사용할지 결정합니다.


from dataclasses import dataclass


@dataclass(frozen=True)
class EnvironmentProfile:
    """운동별 환경 요구사항. DB 저장 대상이 아닌 서버 설정이다.

    현재 모든 운동은 맨몸운동이라 required_objects는 비어 있다. 도구가 필요한
    운동이 실제로 등록된 뒤에만 객체명을 넣는다.
    """
    name: str
    required_objects: frozenset[str] = frozenset()

# 운동에 따라 어떤 환경 검사를 실행할지 미리 정해 놓은 설정표
DEFAULT_PROFILE = EnvironmentProfile(name="default")

# 현재 exercises 테이블에 전용 환경 규칙이 확정된 운동은 없다.
EXERCISE_NAME_PROFILES: dict[str, EnvironmentProfile] = {}


def profile_for_exercise_name(exercise_name: str | None) -> EnvironmentProfile:
    """현재 ERD에는 slug/code가 없으므로, 등록된 운동명만 명시적으로 매핑한다.
    알 수 없는 이름과 Side Kick은 안전하게 공통 default 정책으로 처리한다.
    """
    normalized_name = exercise_name.strip().casefold() if exercise_name else ""
    return EXERCISE_NAME_PROFILES.get(normalized_name, DEFAULT_PROFILE)
