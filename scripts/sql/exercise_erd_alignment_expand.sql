ALTER TABLE exercise_criteria_versions
    ADD COLUMN evaluation_criteria JSON NULL,
    ADD COLUMN criteria_version VARCHAR(100) NULL,
    ADD COLUMN schema_version INT NULL,
    ADD COLUMN status VARCHAR(20) NULL,
    ADD COLUMN created_at DATETIME NULL;

UPDATE exercise_criteria_versions
SET
    evaluation_criteria = JSON_OBJECT(
        'migration_status', 'LEGACY_SCORE_POLICY',
        'reference_available', false
    ),
    criteria_version = version,
    schema_version = 1,
    status = 'DRAFT',
    created_at = UTC_TIMESTAMP()
WHERE id = 1;
