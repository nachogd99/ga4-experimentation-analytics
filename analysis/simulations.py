"""Simulation harness for the experiment: the A/A test and lift injection.

Everything here is simulated in Python on top of real data. No statistic is
computed in this file: every test calls a function from analysis/stats.py.
"""

from math import sqrt

import numpy as np
import pandas as pd

from analysis.stats import power_of_test, srm_check, two_proportion_ztest


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


# ---------------------------------------------------------------------------
# Lift injection
#
# The A/A test shows the pipeline stays quiet when nothing is going on. The
# opposite check: plant an effect of known size and see whether the pipeline
# finds it. The effect is simulated; the real data is never modified.
# ---------------------------------------------------------------------------


def inject_lift(converted, is_treatment, relative_lift, random):
    """Simulate a treatment effect by turning some non-converters into converters.

    converted:     one value per user, 1 if the user converted, else 0
    is_treatment:  one value per user, True if the user is in treatment
    relative_lift: size of the effect as a share of the baseline rate,
                   e.g. 0.25 raises the treatment rate by about 25%
    random:        a numpy random generator, e.g. np.random.default_rng(42).
                   Passing it in makes the result reproducible.

    Returns a new array of 0s and 1s. The inputs are not changed, control
    users are never touched, and nobody who converted is un-converted.
    """
    if relative_lift < 0:
        raise ValueError("relative_lift cannot be negative")
    converted = np.asarray(converted)
    is_treatment = np.asarray(is_treatment, dtype=bool)

    # The baseline is the conversion rate of all users before any effect.
    baseline_rate = converted.mean()

    # Give each treatment user who did not convert the same small chance of
    # converting. To raise a rate p to p * (1 + lift), the extra conversions
    # must amount to p * lift of the group. They can only come from the
    # non-converters, who are a share (1 - p) of it, so each one needs a
    # chance of p * lift / (1 - p).
    flip_probability = baseline_rate * relative_lift / (1 - baseline_rate)
    if flip_probability > 1:
        raise ValueError("the lift is too large for this baseline rate")

    # One random number between 0 and 1 per user. A user flips when their
    # number falls below the flip probability.
    flips = random.random(len(converted)) < flip_probability

    injected = converted.copy()
    injected[is_treatment & (converted == 0) & flips] = 1
    return injected


def analyze_conversion(converted, is_treatment, alpha=0.05):
    """Analyze one experiment: the SRM check, then the conversion z-test.

    Returns a dictionary with the group sizes and conversions, the SRM
    p-value and the z-test results.
    """
    converted = np.asarray(converted)
    is_treatment = np.asarray(is_treatment, dtype=bool)

    users_treatment = int(is_treatment.sum())
    users_control = len(converted) - users_treatment
    conversions_treatment = int(converted[is_treatment].sum())
    conversions_control = int(converted[~is_treatment].sum())

    srm = srm_check(users_control, users_treatment)
    test = two_proportion_ztest(
        conversions_control, users_control, conversions_treatment, users_treatment, alpha
    )

    return {
        "users_control": users_control,
        "users_treatment": users_treatment,
        "conversions_control": conversions_control,
        "conversions_treatment": conversions_treatment,
        "srm_p_value": srm["p_value"],
        "srm_detected": srm["srm_detected"],
        **test,  # adds every result of the z-test
    }


def run_lift_detection(converted, relative_lifts, number_of_simulations=1000, seed=0, alpha=0.05):
    """Measure how often a planted lift is detected, for several lift sizes.

    Power is a statement about many experiments: the share of them in which
    a real effect comes out significant. So each simulation is a complete
    experiment:
        1. split the users at random into control and treatment
        2. inject the lift into the treatment group
        3. run the z-test
    The split has to be redone every time. With a single fixed split, the
    starting gap between the groups would never change and the outcome would
    be almost the same in every simulation.

    converted:      one value per user, real and unmodified
    relative_lifts: the lift sizes to try, e.g. [0.05, 0.10, 0.25]

    Returns one row per lift with the share of simulations that detected it
    and the power predicted by power_of_test, for comparison.
    """
    converted = np.asarray(converted)
    random = np.random.default_rng(seed)
    baseline_rate = converted.mean()
    users_per_group = len(converted) / 2

    rows = []
    for relative_lift in relative_lifts:
        detected = 0
        for _ in range(number_of_simulations):
            # A fresh 50/50 split: each user is treatment with probability 0.5.
            is_treatment = random.random(len(converted)) < 0.5
            injected = inject_lift(converted, is_treatment, relative_lift, random)
            if analyze_conversion(injected, is_treatment, alpha)["significant"]:
                detected += 1

        rows.append(
            {
                "relative_lift": relative_lift,
                "simulations": number_of_simulations,
                "detected": detected,
                "detection_rate": detected / number_of_simulations,
                "predicted_power": power_of_test(
                    baseline_rate, relative_lift, users_per_group, alpha
                ),
            }
        )
    return pd.DataFrame(rows)
