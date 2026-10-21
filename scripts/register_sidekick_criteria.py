"""기존 Side Kick 트레이너 기준 JSON을 MySQL에 등록한다."""

import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/pose_references/sidekick"

exercise = json.loads(
    (BASE / "sidekick_reference_candidates_v0.1.0.json").read_text(encoding="utf-8")
)
study = json.loads(
    (BASE / "sidekick_study_steps_v0.1.0.json").read_text(encoding="utf-8")
)

if exercise["exercise_code"] != "SIDE_KICK_SIDE_BEND":
    raise SystemExit("STOP: 운동 코드가 일치하지 않습니다.")

if exercise["criteria_version"] != study["criteria_version"]:
    raise SystemExit("STOP: 기준 버전이 다릅니다.")

if [s["step_no"] for s in study["steps"]] != [1, 2, 3, 4, 5]:
    raise SystemExit("STOP: STEP 순서가 일치하지 않습니다.")

if exercise["review_status"] != "EXPERIMENTAL_NOT_APPROVED":
    raise SystemExit("STOP: 예상한 검토 상태가 아닙니다.")

print("===== REGISTRATION PLAN =====")
print("운동: SIDE_KICK_SIDE_BEND")
print("기준 버전:", exercise["criteria_version"])
print("STEP 수:", len(study["steps"]))
print("검토 상태:", exercise["review_status"])
print("DB 사용 상태: ACTIVE (전문가 승인 의미 아님)")

if "--apply" not in sys.argv:
    print("DRY_RUN_OK: 실제 DB 변경 없음")
    raise SystemExit(0)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.session import engine

with engine.begin() as conn:
    exercise_name = conn.execute(
        text("SELECT exercise_name FROM exercises WHERE id = 1")
    ).scalar_one_or_none()

    if exercise_name != "Side Kick":
        raise ValueError("운동 ID 1이 Side Kick이 아닙니다.")

    rows = conn.execute(text("""
        SELECT id, step_order
        FROM exercise_steps
        WHERE exercise_id = 1
        ORDER BY step_order
    """)).mappings().all()

    if [r["step_order"] for r in rows] != [
        step["step_no"] for step in study["steps"]
    ]:
        raise ValueError("DB STEP 순서가 일치하지 않습니다.")

    existing = conn.execute(text("""
        SELECT id
        FROM exercise_criteria_versions
        WHERE exercise_id = 1 AND criteria_version = :version
    """), {"version": exercise["criteria_version"]}).scalar_one_or_none()

    if existing is not None:
        raise ValueError("이미 등록된 운동 기준 버전입니다.")

    result = conn.execute(text("""
        INSERT INTO exercise_criteria_versions
        (exercise_id, evaluation_criteria, criteria_version,
         schema_version, status, created_at,
         version, target_sets, score_per_set)
        VALUES
        (1, :criteria, :criteria_version, :schema_version,
         'ACTIVE', UTC_TIMESTAMP(), :legacy_version, 10, 10.00)
    """), {
        "criteria": json.dumps(exercise, ensure_ascii=False),
        "criteria_version": exercise["criteria_version"],
        "schema_version": exercise["schema_version"],
        "legacy_version": "legacy-json-0.1.0",
    })

    criteria_id = result.lastrowid

    for row, step in zip(rows, study["steps"]):
        conn.execute(text("""
            INSERT INTO exercise_step_criteria_versions
            (exercise_step_id, exercise_criteria_version_id,
             evaluation_criteria, step_criteria_version, created_at)
            VALUES
            (:step_id, :criteria_id, :criteria,
             :version, UTC_TIMESTAMP())
        """), {
            "step_id": row["id"],
            "criteria_id": criteria_id,
            "criteria": json.dumps(step, ensure_ascii=False),
            "version": study["criteria_version"],
        })

print("REGISTRATION_COMPLETED")
