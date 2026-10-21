-- MomFit Side Kick: 기존 로컬 DB 기준 보정 SQL
-- 최신 develop ORM 기준으로 로컬 DB를 보정할 때 사용한 변경 사항.
-- 신규 DB 전체 생성용 마이그레이션이 아님.
-- DB 백업 및 실제 컬럼/인덱스 확인 후 필요한 구문만 적용.
-- 이미 보정된 DB에는 재실행하지 말 것.
--
-- Side Kick local MySQL alignment with latest develop ORM.
-- Review existing schema and back up DB before applying.
-- Do not run against an already migrated database.

ALTER TABLE exercise_records
    ADD COLUMN completed_sets INT NOT NULL DEFAULT 0;

ALTER TABLE exercise_records
    MODIFY COLUMN total_score DECIMAL(5,2) NULL DEFAULT 0.00,
    MODIFY COLUMN started_at DATETIME NULL DEFAULT NULL,
    ALTER COLUMN status SET DEFAULT 'in_progress';

ALTER TABLE exercise_step_records
    ALTER COLUMN status SET DEFAULT 'in_progress';

ALTER TABLE exercises
    MODIFY COLUMN video_url VARCHAR(500) NOT NULL;

ALTER TABLE exercise_steps
    MODIFY COLUMN clip_video_url VARCHAR(500) NOT NULL;

ALTER TABLE exercises
    DROP COLUMN target_reps;

ALTER TABLE exercise_criteria_versions
    ADD INDEX ix_exercise_criteria_versions_exercise_id (exercise_id);
