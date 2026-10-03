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

from math import sqrt

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
