"""Tests for analysis/stats.py.

Run from the repository root with:  python -m pytest analysis

Each function is checked in two ways: against statsmodels, an established
statistics library, and against cases where the right answer is known
without any library.
"""

import pytest
from scipy.stats import chisquare
from statsmodels.stats.proportion import confint_proportions_2indep, proportions_ztest

from analysis.stats import srm_check, two_proportion_ztest


# ---------------------------------------------------------------------------
# two_proportion_ztest
# ---------------------------------------------------------------------------


def test_ztest_matches_statsmodels():
    # 500 of 10,000 control users converted, 570 of 10,000 treatment users.
    result = two_proportion_ztest(500, 10_000, 570, 10_000)

    # statsmodels takes the groups as lists. Treatment first, so that the
    # sign of z matches ours (treatment minus control).
    expected_z, expected_p = proportions_ztest(count=[570, 500], nobs=[10_000, 10_000])

    assert result["z_score"] == pytest.approx(expected_z)
    assert result["p_value"] == pytest.approx(expected_p)


def test_ztest_matches_statsmodels_with_unequal_groups():
    # The real split of the experiment (salt 'exp1'), with no effect injected.
    result = two_proportion_ztest(535, 47_087, 534, 47_701)

    expected_z, expected_p = proportions_ztest(count=[534, 535], nobs=[47_701, 47_087])

    assert result["z_score"] == pytest.approx(expected_z)
    assert result["p_value"] == pytest.approx(expected_p)


def test_ztest_confidence_interval_matches_statsmodels():
    result = two_proportion_ztest(500, 10_000, 570, 10_000)

    # method="wald" is the plain unpooled interval our function computes.
    expected_low, expected_high = confint_proportions_2indep(
        570, 10_000, 500, 10_000, method="wald", compare="diff", alpha=0.05
    )

    assert result["ci_low"] == pytest.approx(expected_low)
    assert result["ci_high"] == pytest.approx(expected_high)


def test_ztest_rates_and_lift():
    result = two_proportion_ztest(500, 10_000, 570, 10_000)

    assert result["rate_control"] == pytest.approx(0.05)
    assert result["rate_treatment"] == pytest.approx(0.057)
    assert result["difference"] == pytest.approx(0.007)
    # 0.007 on a base of 0.05 is a 14% relative lift.
    assert result["relative_lift"] == pytest.approx(0.14)


def test_ztest_identical_groups_show_no_difference():
    result = two_proportion_ztest(300, 10_000, 300, 10_000)

    assert result["z_score"] == pytest.approx(0)
    assert result["p_value"] == pytest.approx(1)
    assert result["significant"] is False


def test_ztest_swapping_groups_flips_the_sign_only():
    one_way = two_proportion_ztest(500, 10_000, 570, 10_000)
    other_way = two_proportion_ztest(570, 10_000, 500, 10_000)

    assert other_way["z_score"] == pytest.approx(-one_way["z_score"])
    assert other_way["p_value"] == pytest.approx(one_way["p_value"])


def test_ztest_large_difference_is_significant():
    # 5% against 10% with 10,000 users each is far beyond chance.
    result = two_proportion_ztest(500, 10_000, 1_000, 10_000)

    assert result["significant"] is True
    assert result["p_value"] < 0.001
    # The interval for the difference excludes zero.
    assert result["ci_low"] > 0


def test_ztest_same_rates_with_more_users_give_a_smaller_p_value():
    # Same 5.0% against 5.5%, with 10 times the users: the standard error
    # shrinks, so the same gap becomes stronger evidence.
    small = two_proportion_ztest(50, 1_000, 55, 1_000)
    large = two_proportion_ztest(500, 10_000, 550, 10_000)

    assert large["p_value"] < small["p_value"]


def test_ztest_rejects_impossible_inputs():
    with pytest.raises(ValueError):
        two_proportion_ztest(10, 0, 10, 100)  # a group with no users
    with pytest.raises(ValueError):
        two_proportion_ztest(200, 100, 10, 100)  # more conversions than users
    with pytest.raises(ValueError):
        two_proportion_ztest(0, 100, 0, 100)  # nobody converted: no variation


# ---------------------------------------------------------------------------
# srm_check
# ---------------------------------------------------------------------------


def test_srm_matches_scipy():
    result = srm_check(47_087, 47_701)

    # scipy's chi-square test compares observed counts with expected counts.
    expected = chisquare([47_087, 47_701], f_exp=[47_394, 47_394])

    assert result["chi_square"] == pytest.approx(expected.statistic)
    assert result["p_value"] == pytest.approx(expected.pvalue)


def test_srm_expected_counts_and_share():
    result = srm_check(47_087, 47_701)

    assert result["expected_control"] == pytest.approx(47_394)
    assert result["expected_treatment"] == pytest.approx(47_394)
    assert result["share_control"] == pytest.approx(47_087 / 94_788)


def test_srm_perfect_split_shows_no_mismatch():
    result = srm_check(5_000, 5_000)

    assert result["chi_square"] == pytest.approx(0)
    assert result["p_value"] == pytest.approx(1)
    assert result["srm_detected"] is False


def test_srm_real_split_passes_at_the_default_threshold():
    # The real split with salt 'exp1' is uneven by chance: p is about 0.046.
    result = srm_check(47_087, 47_701)

    assert 0.04 < result["p_value"] < 0.05
    # No alarm at the default threshold of 0.001 ...
    assert result["srm_detected"] is False
    # ... but the same split would raise one at 0.05.
    assert srm_check(47_087, 47_701, alpha=0.05)["srm_detected"] is True


def test_srm_detects_a_broken_split():
    # 52% against 48% with 100,000 users is far beyond chance.
    result = srm_check(52_000, 48_000)

    assert result["srm_detected"] is True
    assert result["p_value"] < 0.001


def test_srm_swapping_groups_gives_the_same_result():
    one_way = srm_check(47_087, 47_701)
    other_way = srm_check(47_701, 47_087)

    assert other_way["chi_square"] == pytest.approx(one_way["chi_square"])
    assert other_way["p_value"] == pytest.approx(one_way["p_value"])


def test_srm_with_an_uneven_design():
    # A 20/80 design that came out exactly 20/80 is a perfect match.
    assert srm_check(2_000, 8_000, expected_share_control=0.2)["p_value"] == pytest.approx(1)
    # The same counts against a 50/50 design are badly off.
    assert srm_check(2_000, 8_000)["srm_detected"] is True


def test_srm_rejects_impossible_inputs():
    with pytest.raises(ValueError):
        srm_check(0, 0)  # no users at all
    with pytest.raises(ValueError):
        srm_check(-5, 100)  # negative group size
    with pytest.raises(ValueError):
        srm_check(100, 100, expected_share_control=1.5)  # not a share
