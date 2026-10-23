from services.environment_check.profiles import DEFAULT_PROFILE, profile_for_exercise_name


def test_side_kick_is_default_not_side_step_open_window():
    assert profile_for_exercise_name("Side Kick") is DEFAULT_PROFILE


def test_side_step_name_is_default_until_real_exercise_policy_is_registered():
    assert profile_for_exercise_name("side-step-open-window") is DEFAULT_PROFILE
