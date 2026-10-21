-- MomFit Exercise ERD migration: contract
-- Prerequisite:
-- 1. exercise_erd_alignment_expand.sql applied
-- 2. exercise_step_criteria_versions table created
-- 3. Existing criteria rows backfilled
-- 4. New required columns contain no NULL values
--
-- IMPORTANT: Back up the database before applying.
-- This migration removes three legacy columns.

ALTER TABLE exercise_criteria_versions
    DROP INDEX uq_exercise_criteria_version,
    ADD UNIQUE INDEX uq_exercise_criteria_version
        (exercise_id, criteria_version),
    MODIFY COLUMN evaluation_criteria JSON NOT NULL,
    MODIFY COLUMN criteria_version VARCHAR(100) NOT NULL,
    MODIFY COLUMN schema_version INT NOT NULL,
    MODIFY COLUMN status VARCHAR(20) NOT NULL,
    MODIFY COLUMN created_at DATETIME NOT NULL,
    DROP COLUMN version,
    DROP COLUMN target_sets,
    DROP COLUMN score_per_set;
