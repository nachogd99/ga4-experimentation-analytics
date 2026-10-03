"""Simulation harness for the experiment: the A/A test and lift injection.

Everything here is simulated in Python on top of real data. No statistic is
computed in this file: every test calls a function from analysis/stats.py.
"""

from math import sqrt

import pandas as pd

from analysis.stats import srm_check, two_proportion_ztest


# ---------------------------------------------------------------------------
# A/A test
#
# In an A/A test both groups get the same experience, so there is no real
# effect. A sound pipeline should still call about 5% of such tests
# "significant", because that is what a 0.05 threshold means. Running many
# A/A tests, each with a different salt (a different random split of the same
# users), checks the assignment, the metric tables and the z-test together.
# ---------------------------------------------------------------------------


def run_aa_test(aa_totals, alpha=0.05):
    """Run the SRM check and the conversion z-test for every salt.

    aa_totals: one row per salt, with users_control, users_treatment,
               conversions_control and conversions_treatment
               (see analysis.data.load_aa_totals)

    Returns one row per salt with the results of both tests.
    """
    rows = []
    for split in aa_totals.itertuples():
        srm = srm_check(split.users_control, split.users_treatment)
        test = two_proportion_ztest(
            split.conversions_control,
            split.users_control,
            split.conversions_treatment,
            split.users_treatment,
            alpha=alpha,
        )
        rows.append(
            {
                "salt": split.salt,
                "users_control": split.users_control,
                "users_treatment": split.users_treatment,
                "conversions_control": split.conversions_control,
                "conversions_treatment": split.conversions_treatment,
                "srm_p_value": srm["p_value"],
                "srm_detected": srm["srm_detected"],
                "z_score": test["z_score"],
                "p_value": test["p_value"],
                "significant": test["significant"],
            }
        )
    return pd.DataFrame(rows)


def summarize_aa_test(aa_results, alpha=0.05):
    """Count the false alarms and compare the rate with what is expected.

    Every "significant" result in an A/A test is a false alarm, and each test
    is one with probability alpha. So the share of false alarms across many
    tests should be close to alpha. How close: a share measured on n tests
    has standard error sqrt(alpha * (1 - alpha) / n), and 95% of the time it
    lands within 1.96 standard errors of alpha.

    Returns a dictionary with the false alarm rate, the range it is expected
    to fall in, whether it does, and summaries of the z-scores and SRM checks.
    """
    number_of_tests = len(aa_results)
    false_alarms = int(aa_results["significant"].sum())
    false_alarm_rate = false_alarms / number_of_tests

    standard_error = sqrt(alpha * (1 - alpha) / number_of_tests)
    expected_low = alpha - 1.96 * standard_error
    expected_high = alpha + 1.96 * standard_error

    return {
        "number_of_tests": number_of_tests,
        "false_alarms": false_alarms,
        "false_alarm_rate": false_alarm_rate,
        "expected_low": expected_low,
        "expected_high": expected_high,
        "passed": expected_low <= false_alarm_rate <= expected_high,
        # With no real effect the z-scores should be centred on 0 with a
        # standard deviation of 1.
        "z_score_mean": float(aa_results["z_score"].mean()),
        "z_score_std": float(aa_results["z_score"].std()),
        # Splits flagged by the SRM check at its strict 0.001 threshold.
        # About 1 in 1,000 healthy splits is expected to trip it.
        "srm_alarms": int(aa_results["srm_detected"].sum()),
    }
