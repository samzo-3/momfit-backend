CREATE TABLE IF NOT EXISTS exercise_criteria_versions (
    id BIGINT NOT NULL AUTO_INCREMENT,
    exercise_id BIGINT NOT NULL,
    version VARCHAR(20) NOT NULL,
    target_sets INT NOT NULL,
    score_per_set DECIMAL(6,2) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_exercise_criteria_version (exercise_id, version),
    CONSTRAINT fk_criteria_exercise
        FOREIGN KEY (exercise_id) REFERENCES exercises(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS exercise_records (
    id BIGINT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    exercise_id BIGINT NOT NULL,
    exercise_criteria_version_id BIGINT NOT NULL,
    total_score DECIMAL(6,2) NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'IN_PROGRESS',
    started_at DATETIME NOT NULL,
    ended_at DATETIME NULL,
    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL,
    modified_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_record_user
        FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_record_exercise
        FOREIGN KEY (exercise_id) REFERENCES exercises(id),
    CONSTRAINT fk_record_criteria
        FOREIGN KEY (exercise_criteria_version_id)
        REFERENCES exercise_criteria_versions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO exercise_criteria_versions
    (exercise_id, version, target_sets, score_per_set)
SELECT e.id, '1.0.1', 10, 10.00
FROM exercises AS e
WHERE e.id = 1;
