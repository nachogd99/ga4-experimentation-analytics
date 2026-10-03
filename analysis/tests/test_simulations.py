"""Tests for analysis/simulations.py.

Run from the repository root with:  python -m pytest analysis

These use small made-up tables, so they run without BigQuery.
"""

import pandas as pd
import pytest

from analysis.simulations import run_aa_test, summarize_aa_test
from analysis.stats import srm_check, two_proportion_ztest


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
