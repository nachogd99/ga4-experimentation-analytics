"""Tests for analysis/stats.py.

Run from the repository root with:  python -m pytest analysis

Each function is checked in two ways: against statsmodels, an established
statistics library, and against cases where the right answer is known
without any library.
"""

import numpy as np
import pytest
from scipy.stats import chisquare
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import (
    confint_proportions_2indep,
    proportion_effectsize,
    proportions_ztest,
)

from analysis.stats import (
    minimum_detectable_effect,
    power_of_test,
    required_sample_size,
    srm_check,
    two_proportion_ztest,
)


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


# ---------------------------------------------------------------------------
# Power analysis
# ---------------------------------------------------------------------------


def test_power_is_close_to_statsmodels():
    # statsmodels measures the effect on a transformed scale (Cohen's h), so
    # the two answers are close but not identical.
    ours = power_of_test(baseline_rate=0.05, relative_lift=0.10, users_per_group=20_000)

    effect_size = proportion_effectsize(0.055, 0.05)
    theirs = NormalIndPower().power(effect_size=effect_size, nobs1=20_000, alpha=0.05)

    assert ours == pytest.approx(theirs, abs=0.01)


def test_sample_size_is_close_to_statsmodels():
    ours = required_sample_size(baseline_rate=0.05, relative_lift=0.10)

    effect_size = proportion_effectsize(0.055, 0.05)
    theirs = NormalIndPower().solve_power(effect_size=effect_size, alpha=0.05, power=0.80)

    assert ours == pytest.approx(theirs, rel=0.02)


def test_power_matches_a_simulation():
    # Power is the share of experiments that come out significant. So run
    # many simulated experiments with a real +20% lift and count them.
    baseline_rate, relative_lift, users_per_group = 0.05, 0.20, 5_000
    treatment_rate = baseline_rate * (1 + relative_lift)

    random = np.random.default_rng(seed=42)
    number_of_experiments = 4_000
    significant_count = 0
    for _ in range(number_of_experiments):
        # Draw how many users convert in each group.
        conversions_control = random.binomial(users_per_group, baseline_rate)
        conversions_treatment = random.binomial(users_per_group, treatment_rate)
        result = two_proportion_ztest(
            conversions_control, users_per_group, conversions_treatment, users_per_group
        )
        if result["significant"]:
            significant_count += 1

    simulated_power = significant_count / number_of_experiments
    predicted_power = power_of_test(baseline_rate, relative_lift, users_per_group)

    assert simulated_power == pytest.approx(predicted_power, abs=0.03)


def test_power_with_no_lift_equals_alpha():
    # With no real effect, the only "detections" are false alarms, and those
    # happen at the rate alpha.
    assert power_of_test(0.05, 0, 10_000, alpha=0.05) == pytest.approx(0.05)
    assert power_of_test(0.05, 0, 10_000, alpha=0.01) == pytest.approx(0.01)


def test_power_grows_with_users_and_with_lift():
    assert power_of_test(0.05, 0.10, 20_000) > power_of_test(0.05, 0.10, 5_000)
    assert power_of_test(0.05, 0.20, 5_000) > power_of_test(0.05, 0.10, 5_000)


def test_sample_size_gives_the_requested_power():
    # Round trip: the sample size computed for 80% power must give 80% power.
    users = required_sample_size(baseline_rate=0.05, relative_lift=0.10, power=0.80)

    assert power_of_test(0.05, 0.10, users) == pytest.approx(0.80, abs=0.001)


def test_sample_size_quadruples_when_the_lift_halves():
    # The sample size depends on 1 / difference squared, so detecting half
    # the lift takes about four times the users.
    users_for_10_percent = required_sample_size(0.05, 0.10)
    users_for_5_percent = required_sample_size(0.05, 0.05)

    assert users_for_5_percent / users_for_10_percent == pytest.approx(4, rel=0.05)


def test_mde_gives_the_requested_power():
    # Round trip: the minimum detectable effect must have exactly 80% power.
    lift = minimum_detectable_effect(baseline_rate=0.05, users_per_group=20_000)

    assert power_of_test(0.05, lift, 20_000) == pytest.approx(0.80, abs=0.0001)


def test_mde_and_sample_size_agree():
    # Detecting the MDE of 20,000 users should require 20,000 users.
    lift = minimum_detectable_effect(baseline_rate=0.05, users_per_group=20_000)

    assert required_sample_size(0.05, lift) == pytest.approx(20_000, rel=0.001)


def test_mde_shrinks_with_more_users():
    assert minimum_detectable_effect(0.05, 80_000) < minimum_detectable_effect(0.05, 20_000)


def test_power_functions_reject_impossible_inputs():
    with pytest.raises(ValueError):
        power_of_test(1.5, 0.10, 1_000)  # baseline is not a rate
    with pytest.raises(ValueError):
        power_of_test(0.05, 0.10, 0)  # no users
    with pytest.raises(ValueError):
        required_sample_size(0.05, 0)  # a lift of 0 cannot be detected
    with pytest.raises(ValueError):
        # From a 90% baseline there is little room to improve, and 2 users
        # cannot detect even the largest possible lift.
        minimum_detectable_effect(0.90, 2)
