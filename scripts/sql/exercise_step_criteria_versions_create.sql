-- MomFit ERD: STEP별 평가 기준 버전
-- 새 DB에 적용할 때 1회 실행
-- 기존 테이블이 있으면 변경하지 않음

CREATE TABLE IF NOT EXISTS exercise_step_criteria_versions (
    id BIGINT NOT NULL AUTO_INCREMENT,
    exercise_step_id BIGINT NOT NULL,
    exercise_criteria_version_id BIGINT NOT NULL,
    evaluation_criteria JSON NOT NULL,
    step_criteria_version VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_step_criteria_exercise_step
        FOREIGN KEY (exercise_step_id)
        REFERENCES exercise_steps(id),
    CONSTRAINT fk_step_criteria_exercise_criteria
        FOREIGN KEY (exercise_criteria_version_id)
        REFERENCES exercise_criteria_versions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
