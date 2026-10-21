# MomFit 운동 평가 기준 ERD 마이그레이션

## 변경 내용

- exercise_criteria_versions: 운동 평가 기준 JSON 및 버전 관리
- exercise_step_criteria_versions: STEP별 평가 기준 JSON
- exercise_records.completed_sets: 완료 세트 수
- 운동별 점수 정책: Python 코드에서 관리

## 마이그레이션 파일

1. exercise_erd_alignment_expand.sql
   - 신규 평가 기준 컬럼 추가
   - 기존 id=1 데이터 변환

2. exercise_step_criteria_versions_create.sql
   - STEP 기준 테이블 생성

3. exercise_erd_alignment_contract.sql
   - UNIQUE 인덱스 변경
   - 신규 컬럼 NOT NULL 적용
   - 과거 점수 정책 컬럼 제거

## 주의사항

- 반드시 DB를 백업한 후 실행한다.
- 현재 expand.sql은 기존 기준 id=1이 있는 개발 DB를 전제로 한다.
- 다른 팀원의 DB에 확인 없이 실행하면 안 된다.
- contract.sql 실행 전 신규 필수 컬럼에 NULL이 없어야 한다.
- 기존 운동 기록과 STEP 기록을 삭제하거나 초기화하지 않는다.

## 추가 DB 변경

exercise_records 테이블에 completed_sets 컬럼이 없다면 다음 SQL을 적용한다.

ALTER TABLE exercise_records ADD COLUMN completed_sets INT NOT NULL DEFAULT 0;

기존 기록의 completed_sets=0은 실제 과거 수행 세트 수를 복원한 값이 아니라 기본값이다.

## Side Kick 평가 기준

- exercise_code: SIDE_KICK_SIDE_BEND
- criteria_version: 0.1.0
- review_status: EXPERIMENTAL_NOT_APPROVED
- STEP: 5개

전문가 검토가 완료된 자료가 아니다.

등록 스크립트는 로컬 개발 DB의 운동 ID 1과 STEP 순서 1~5를 전제로 한다.
팀원별 DB의 운동 ID와 STEP ID를 확인한 후 사용한다.

## 검증 결과

- DB 및 ORM 조회 통과
- 운동 시작, 일시정지, 재개, 완료 서비스 통합 테스트 통과
- HTTP API 통합 테스트 통과
- 테스트 기록 롤백 및 기존 데이터 보존 확인

HTTP 테스트에서는 인증 의존성을 대체했으므로 실제 로그인 통합 테스트는 별도로 필요하다.
