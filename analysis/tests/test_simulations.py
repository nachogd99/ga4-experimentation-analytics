"""Tests for analysis/simulations.py.

Run from the repository root with:  python -m pytest analysis

These use small made-up tables, so they run without BigQuery.
"""

import numpy as np
import pandas as pd
import pytest

from analysis.simulations import (
    analyze_conversion,
    inject_lift,
    run_aa_test,
    run_lift_detection,
    summarize_aa_test,
)
from analysis.stats import power_of_test, srm_check, two_proportion_ztest


# ---------------------------------------------------------------------------
# A/A test
# ---------------------------------------------------------------------------


def make_aa_totals():
    """Three made-up splits of 20,000 users."""
    return pd.DataFrame(
        {
            "salt": ["even", "big_gap", "uneven_split"],
            "users_control": [10_000, 10_000, 11_000],
            "users_treatment": [10_000, 10_000, 9_000],
            # "even": same rate in both groups. "big_gap": 5% against 7%.
            "conversions_control": [500, 500, 550],
            "conversions_treatment": [500, 700, 450],
        }
    )


def test_aa_returns_one_row_per_salt():
    results = run_aa_test(make_aa_totals())

    assert list(results["salt"]) == ["even", "big_gap", "uneven_split"]


def test_aa_uses_the_functions_from_stats():
    # The harness must not compute statistics itself: each row has to equal
    # what the functions in stats.py return for the same numbers.
    results = run_aa_test(make_aa_totals()).set_index("salt")

    expected_test = two_proportion_ztest(500, 10_000, 700, 10_000)
    assert results.loc["big_gap", "z_score"] == pytest.approx(expected_test["z_score"])
    assert results.loc["big_gap", "p_value"] == pytest.approx(expected_test["p_value"])

    expected_srm = srm_check(11_000, 9_000)
    assert results.loc["uneven_split", "srm_p_value"] == pytest.approx(expected_srm["p_value"])


def test_aa_flags_the_right_rows():
    results = run_aa_test(make_aa_totals()).set_index("salt")

    # Same rate in both groups: nothing to detect.
    assert not results.loc["even", "significant"]
    # 5% against 7% with 10,000 users each is a clear difference.
    assert results.loc["big_gap", "significant"]
    # 11,000 against 9,000 is far from 50/50.
    assert results.loc["uneven_split", "srm_detected"]
    assert not results.loc["even", "srm_detected"]


def test_aa_summary_counts_the_false_alarms():
    results = run_aa_test(make_aa_totals())

    summary = summarize_aa_test(results)

    assert summary["number_of_tests"] == 3
    assert summary["false_alarms"] == 1  # only "big_gap"
    assert summary["false_alarm_rate"] == pytest.approx(1 / 3)
    assert summary["srm_alarms"] == 1  # only "uneven_split"


def test_aa_summary_expected_range_for_1000_tests():
    # Build 1,000 results of which exactly 50 are "significant" (5%).
    results = pd.DataFrame(
        {
            "significant": [True] * 50 + [False] * 950,
            "srm_detected": [False] * 1000,
            "z_score": [0.0] * 1000,
        }
    )

    summary = summarize_aa_test(results)

    # 5% plus or minus 1.96 * sqrt(0.05 * 0.95 / 1000)
    assert summary["expected_low"] == pytest.approx(0.0365, abs=0.0001)
    assert summary["expected_high"] == pytest.approx(0.0635, abs=0.0001)
    assert summary["passed"] is True


def test_aa_summary_fails_when_the_rate_is_far_from_alpha():
    # 150 false alarms in 1,000 tests (15%) means something is broken.
    results = pd.DataFrame(
        {
            "significant": [True] * 150 + [False] * 850,
            "srm_detected": [False] * 1000,
            "z_score": [0.0] * 1000,
        }
    )

    assert summarize_aa_test(results)["passed"] is False


# ---------------------------------------------------------------------------
# Lift injection
# ---------------------------------------------------------------------------


def make_experiment(users=200_000, rate=0.05, seed=1):
    """Made-up users: who converted, and a random 50/50 split."""
    random = np.random.default_rng(seed)
    converted = (random.random(users) < rate).astype(int)
    is_treatment = random.random(users) < 0.5
    return converted, is_treatment


def test_inject_lift_raises_the_treatment_rate_by_about_the_lift():
    converted, is_treatment = make_experiment()

    injected = inject_lift(converted, is_treatment, 0.20, np.random.default_rng(2))

    rate_before = converted[is_treatment].mean()
    rate_after = injected[is_treatment].mean()
    # +20% on about 5% is about +1 percentage point. The injection is random,
    # so allow a little slack.
    assert rate_after / rate_before == pytest.approx(1.20, abs=0.03)


def test_inject_lift_never_touches_the_control_group():
    converted, is_treatment = make_experiment()

    injected = inject_lift(converted, is_treatment, 0.50, np.random.default_rng(2))

    assert (injected[~is_treatment] == converted[~is_treatment]).all()


def test_inject_lift_never_removes_a_conversion():
    converted, is_treatment = make_experiment()

    injected = inject_lift(converted, is_treatment, 0.50, np.random.default_rng(2))

    # Every user who had converted is still converted.
    assert (injected >= converted).all()
    # And the values are still only 0 and 1.
    assert set(np.unique(injected)) == {0, 1}


def test_inject_lift_does_not_change_its_input():
    converted, is_treatment = make_experiment()
    original = converted.copy()

    inject_lift(converted, is_treatment, 0.50, np.random.default_rng(2))

    assert (converted == original).all()


def test_inject_lift_of_zero_changes_nothing():
    converted, is_treatment = make_experiment()

    injected = inject_lift(converted, is_treatment, 0, np.random.default_rng(2))

    assert (injected == converted).all()


def test_inject_lift_is_reproducible_with_the_same_seed():
    converted, is_treatment = make_experiment()

    first = inject_lift(converted, is_treatment, 0.20, np.random.default_rng(99))
    second = inject_lift(converted, is_treatment, 0.20, np.random.default_rng(99))

    assert (first == second).all()


def test_inject_lift_rejects_a_negative_lift():
    converted, is_treatment = make_experiment(users=1_000)

    with pytest.raises(ValueError):
        inject_lift(converted, is_treatment, -0.10, np.random.default_rng(2))


def test_analyze_conversion_matches_the_functions_from_stats():
    converted = np.array([1] * 50 + [0] * 950 + [1] * 80 + [0] * 920)
    is_treatment = np.array([False] * 1_000 + [True] * 1_000)

    result = analyze_conversion(converted, is_treatment)

    assert result["users_control"] == 1_000
    assert result["users_treatment"] == 1_000
    assert result["conversions_control"] == 50
    assert result["conversions_treatment"] == 80
    expected = two_proportion_ztest(50, 1_000, 80, 1_000)
    assert result["p_value"] == pytest.approx(expected["p_value"])
    assert result["srm_p_value"] == pytest.approx(srm_check(1_000, 1_000)["p_value"])


def test_lift_detection_matches_predicted_power():
    # 20,000 made-up users at a 5% baseline, +30% lift, 400 experiments.
    converted, _ = make_experiment(users=20_000, rate=0.05, seed=3)

    results = run_lift_detection(converted, [0.30], number_of_simulations=400, seed=4)
    row = results.iloc[0]

    predicted = power_of_test(converted.mean(), 0.30, 10_000)
    assert row["predicted_power"] == pytest.approx(predicted)
    # 400 experiments pin a rate down to within about 5 points.
    assert row["detection_rate"] == pytest.approx(predicted, abs=0.06)


def test_lift_detection_with_no_lift_gives_about_alpha():
    # With no effect planted, the detections are false alarms: about 5%.
    converted, _ = make_experiment(users=20_000, rate=0.05, seed=5)

    results = run_lift_detection(converted, [0.0], number_of_simulations=600, seed=6)

    assert results.iloc[0]["detection_rate"] == pytest.approx(0.05, abs=0.025)


def test_lift_detection_rises_with_the_lift():
    converted, _ = make_experiment(users=20_000, rate=0.05, seed=7)

    results = run_lift_detection(converted, [0.05, 0.40], number_of_simulations=200, seed=8)

    assert results.iloc[1]["detection_rate"] > results.iloc[0]["detection_rate"]
