"""Statistical functions for the experiment analysis.

The formulas are written out by hand so that every step can be read and
explained. The only things taken from a library are two probability
distributions from scipy, used to turn a test statistic into a p-value:

    norm.sf(z)      probability that a standard normal value is greater than z
    norm.ppf(q)     the value below which a share q of the normal lies
    chi2.sf(x, df)  probability that a chi-square value is greater than x

The tests in analysis/tests/ compare each function against statsmodels or
scipy.
"""

from math import ceil, sqrt

from scipy.stats import chi2, norm


def two_proportion_ztest(
    conversions_control,
    users_control,
    conversions_treatment,
    users_treatment,
    alpha=0.05,
):
    """Test whether two groups have different conversion rates.

    Answers: is the gap between the two conversion rates larger than random
    assignment alone would typically produce?

    conversions_*: number of users who converted in each group
    users_*:       number of users in each group
    alpha:         significance level. 0.05 gives a 95% confidence interval.

    Returns a dictionary with the rates, the difference, the z-score, the
    p-value and the confidence interval for the difference.
    """
    for conversions, users in [
        (conversions_control, users_control),
        (conversions_treatment, users_treatment),
    ]:
        if users <= 0:
            raise ValueError("each group needs at least one user")
        if conversions < 0 or conversions > users:
            raise ValueError("conversions must be between 0 and the number of users")

    # Conversion rate of each group, and the gap between them.
    rate_control = conversions_control / users_control
    rate_treatment = conversions_treatment / users_treatment
    difference = rate_treatment - rate_control

    # Step 1: assume both groups share one true rate (the null hypothesis).
    # The best estimate of that rate pools everyone together.
    pooled_rate = (conversions_control + conversions_treatment) / (
        users_control + users_treatment
    )

    # Step 2: the standard error is how much the difference would typically
    # vary by chance if we repeated the random split many times.
    # The variance of a 0/1 outcome with rate p is p * (1 - p). Dividing by
    # the group size gives the variance of that group's rate, and the
    # variances of the two groups add up.
    standard_error_pooled = sqrt(
        pooled_rate * (1 - pooled_rate) * (1 / users_control + 1 / users_treatment)
    )
    if standard_error_pooled == 0:
        raise ValueError("no variation: every user converted, or none did")

    # Step 3: the z-score is the difference measured in standard errors.
    z_score = difference / standard_error_pooled

    # Step 4: the p-value is the chance of a gap at least this large, in
    # either direction, if there were no real difference. norm.sf gives the
    # chance of being above |z|; doubling it covers both directions.
    # float() turns scipy's numpy number into a plain Python number.
    p_value = float(2 * norm.sf(abs(z_score)))

    # Confidence interval for the difference. This one does not assume the
    # groups are equal, so it uses each group's own rate (unpooled).
    standard_error_unpooled = sqrt(
        rate_control * (1 - rate_control) / users_control
        + rate_treatment * (1 - rate_treatment) / users_treatment
    )
    # For alpha = 0.05 this is 1.96: 95% of a normal distribution lies within
    # 1.96 standard errors of its centre.
    z_critical = float(norm.ppf(1 - alpha / 2))
    ci_low = difference - z_critical * standard_error_unpooled
    ci_high = difference + z_critical * standard_error_unpooled

    return {
        "rate_control": rate_control,
        "rate_treatment": rate_treatment,
        "difference": difference,
        # Difference as a share of the control rate, e.g. 0.10 means +10%.
        # Undefined when the control rate is 0.
        "relative_lift": difference / rate_control if rate_control > 0 else None,
        "z_score": z_score,
        "p_value": p_value,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "significant": p_value < alpha,
    }


def srm_check(users_control, users_treatment, expected_share_control=0.5, alpha=0.001):
    """Check for a sample ratio mismatch (SRM).

    Answers: is the split between the groups close enough to the designed
    split, or is it so uneven that the assignment is probably broken?

    Run this before looking at any metric. If the split is wrong, the groups
    are not comparable and no other result can be trusted.

    users_*:                number of users in each group
    expected_share_control: designed share of users in control. 0.5 is 50/50.
    alpha:                  alert threshold. 0.001 is the usual choice for
                            SRM, much stricter than the 0.05 used for
                            metrics. This is an alarm that means "stop and
                            investigate", so it should rarely fire on a
                            healthy experiment, and real assignment bugs
                            give p-values far below 0.001.

    Returns a dictionary with the observed and expected split, the chi-square
    statistic, the p-value and whether a mismatch was detected.
    """
    if users_control < 0 or users_treatment < 0:
        raise ValueError("group sizes cannot be negative")
    total_users = users_control + users_treatment
    if total_users == 0:
        raise ValueError("there are no users")
    if not 0 < expected_share_control < 1:
        raise ValueError("expected_share_control must be between 0 and 1")

    # Step 1: how many users each group should have under the design.
    expected_control = total_users * expected_share_control
    expected_treatment = total_users * (1 - expected_share_control)

    # Steps 2 and 3: the chi-square statistic. For each group, take the gap
    # between observed and expected, square it (so over and under both count
    # as "off"), and divide by the expected count (so the gap is judged
    # relative to the group's size). Then add the groups up.
    # 0 means a perfect match with the design; larger means further from it.
    chi_square = (
        (users_control - expected_control) ** 2 / expected_control
        + (users_treatment - expected_treatment) ** 2 / expected_treatment
    )

    # Step 4: the p-value is the chance of a split at least this uneven if
    # the assignment were working as designed. df is the degrees of freedom:
    # with two groups and a fixed total, only one count is free to vary.
    p_value = float(chi2.sf(chi_square, df=1))

    return {
        "share_control": users_control / total_users,
        "expected_control": expected_control,
        "expected_treatment": expected_treatment,
        "chi_square": chi_square,
        "p_value": p_value,
        "srm_detected": p_value < alpha,
    }


# ---------------------------------------------------------------------------
# Power analysis
#
# Three functions, one relationship. Power is the chance that the test comes
# out significant when the treatment really has an effect. It depends on the
# baseline rate, the size of the effect and the number of users. Given any
# of them, the functions below solve for the missing one.
# ---------------------------------------------------------------------------


def _treatment_rate(baseline_rate, relative_lift):
    """Conversion rate of the treatment group for a given relative lift.

    A baseline of 0.01 with a relative lift of 0.20 (+20%) gives 0.012.
    """
    if not 0 < baseline_rate < 1:
        raise ValueError("baseline_rate must be between 0 and 1")
    treatment_rate = baseline_rate * (1 + relative_lift)
    if not 0 < treatment_rate < 1:
        raise ValueError("the lift gives a treatment rate outside 0 to 1")
    return treatment_rate


def power_of_test(baseline_rate, relative_lift, users_per_group, alpha=0.05):
    """Chance of detecting a given lift with a two-proportion z-test.

    Answers: if the treatment really changed conversion by this much, how
    often would the experiment come out significant?

    baseline_rate:   conversion rate of the control group, e.g. 0.011
    relative_lift:   true effect as a share of the baseline, e.g. 0.10 = +10%
    users_per_group: number of users in each group
    alpha:           significance level of the test

    Returns the power, a probability between 0 and 1.
    """
    if users_per_group <= 0:
        raise ValueError("users_per_group must be positive")
    treatment_rate = _treatment_rate(baseline_rate, relative_lift)
    difference = treatment_rate - baseline_rate

    # Standard error of the difference when the effect is real: each group
    # has its own rate, so each has its own variance p * (1 - p).
    standard_error = sqrt(
        baseline_rate * (1 - baseline_rate) / users_per_group
        + treatment_rate * (1 - treatment_rate) / users_per_group
    )

    # How many standard errors the true effect is worth. With no effect the
    # z-score is centred on 0; with a real effect it is centred here.
    expected_z = difference / standard_error

    # The test is significant when the z-score lands beyond +/- z_critical
    # (1.96 for alpha = 0.05).
    z_critical = norm.ppf(1 - alpha / 2)

    # The z-score varies around expected_z like a standard normal. Power is
    # the chance that it lands beyond the threshold on either side. The second
    # term (significant in the wrong direction) is almost always tiny.
    power = norm.sf(z_critical - expected_z) + norm.cdf(-z_critical - expected_z)
    return float(power)


def required_sample_size(baseline_rate, relative_lift, alpha=0.05, power=0.80):
    """Users needed in each group to detect a given lift.

    Answers: how big must the experiment be to detect this lift with the
    desired power?

    Returns the number of users per group, rounded up.
    """
    if relative_lift == 0:
        raise ValueError("a lift of 0 cannot be detected with any sample size")
    if not 0 < power < 1:
        raise ValueError("power must be between 0 and 1")
    treatment_rate = _treatment_rate(baseline_rate, relative_lift)
    difference = treatment_rate - baseline_rate

    # To be significant, the z-score must clear z_critical. To do so with the
    # desired probability, its centre must sit z_power beyond that threshold.
    # For alpha = 0.05 and power = 0.80 these are 1.96 and 0.84.
    z_critical = norm.ppf(1 - alpha / 2)
    z_power = norm.ppf(power)

    # So the effect must be worth (z_critical + z_power) standard errors:
    #     difference / standard_error = z_critical + z_power
    # The standard error is sqrt(variance_sum / n). Solving for n gives:
    variance_sum = baseline_rate * (1 - baseline_rate) + treatment_rate * (
        1 - treatment_rate
    )
    users_per_group = (z_critical + z_power) ** 2 * variance_sum / difference**2

    return ceil(users_per_group)


def minimum_detectable_effect(baseline_rate, users_per_group, alpha=0.05, power=0.80):
    """Smallest relative lift the experiment can detect with the desired power.

    Answers: with this many users, how big does a lift have to be before the
    experiment would usually catch it?

    Returns the lift as a share of the baseline, e.g. 0.17 means +17%.
    """
    if not 0 < power < 1:
        raise ValueError("power must be between 0 and 1")

    # There is no formula to solve for the lift directly, because the lift
    # also changes the treatment group's variance. So search for it: power
    # grows with the lift, which lets us halve the range at every step, like
    # guessing a number with "higher" or "lower".
    lift_low = 0.0
    # Largest lift that keeps the treatment rate just below 100%.
    lift_high = (1 - baseline_rate) / baseline_rate * 0.999

    if power_of_test(baseline_rate, lift_high, users_per_group, alpha) < power:
        raise ValueError("no lift reaches the desired power with this few users")

    # 60 halvings narrow the range far beyond any precision we need.
    for _ in range(60):
        lift_middle = (lift_low + lift_high) / 2
        if power_of_test(baseline_rate, lift_middle, users_per_group, alpha) < power:
            lift_low = lift_middle  # not enough power: the answer is higher
        else:
            lift_high = lift_middle  # enough power: the answer is this or lower

    return lift_high
