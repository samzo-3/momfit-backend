import json
from pathlib import Path

BASE = Path("data/pose_references/sidekick")

exercise = json.loads(
    (BASE / "sidekick_reference_candidates_v0.1.0.json").read_text(
        encoding="utf-8"
    )
)
study = json.loads(
    (BASE / "sidekick_study_steps_v0.1.0.json").read_text(
        encoding="utf-8"
    )
)

assert exercise["exercise_code"] == study["exercise_code"]
assert exercise["criteria_version"] == study["criteria_version"]
assert len(study["steps"]) == 5

print("===== EXERCISE CRITERIA =====")
print("exercise_code:", exercise["exercise_code"])
print("criteria_version:", exercise["criteria_version"])
print("review_status:", exercise["review_status"])
print("reference states:", list(exercise["reference_metrics"]))

print("\n===== STEP CRITERIA =====")
for step in study["steps"]:
    print(
        "step_no:", step["step_no"],
        "| code:", step["step_code"],
        "| assessment:", step["assessment_status"],
    )

print("\nVALIDATION_OK")
