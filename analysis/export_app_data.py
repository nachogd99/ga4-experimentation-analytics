"""Exports small data files for the Streamlit app.

Run from the repository root with:  python -m analysis.export_app_data

The app reads these files instead of BigQuery, so it works without
credentials and keeps working after the sandbox tables expire.

Only aggregates are exported, never per-user rows. The tests that need
per-user data (revenue and CUPED) are run here, and only their results are
saved. Writes to app/data/.
"""

from pathlib import Path

import pandas as pd

from analysis.data import (
    load_cohort_retention,
    load_funnel,
    load_overview,
    load_user_metrics,
)
from analysis.stats import cuped_adjust, difference_in_means_test, two_proportion_ztest

DATA_FOLDER = Path(__file__).parent.parent / "app" / "data"


def build_experiment_groups(user_metrics):
    """Totals per variant: users, converters and revenue."""
    groups = (
        user_metrics.groupby(["variant_id", "variant"])
        .agg(
            users=("converted", "size"),
            conversions=("converted", "sum"),
            revenue_usd=("revenue_usd", "sum"),
            users_with_pre_activity=("has_pre_activity", "sum"),
        )
        .reset_index()
    )
    groups["conversion_rate"] = groups["conversions"] / groups["users"]
    groups["revenue_per_user"] = groups["revenue_usd"] / groups["users"]
    return groups


def build_experiment_results(user_metrics):
    """Test results for both metrics, raw and with CUPED. One row per test."""
    is_control = (user_metrics["variant_id"] == 0).to_numpy(dtype=bool)
    is_treatment = ~is_control

    # Columns to keep from every test, so all rows have the same shape.
    shared = ["difference", "relative_lift", "z_score", "p_value", "ci_low", "ci_high", "significant"]
    rows = []

    # Conversion, raw: the two-proportion z-test on the group totals.
    converted = user_metrics["converted"].to_numpy(dtype=float)
    test = two_proportion_ztest(
        int(converted[is_control].sum()), int(is_control.sum()),
        int(converted[is_treatment].sum()), int(is_treatment.sum()),
    )
    rows.append({
        "metric": "conversion", "method": "two-proportion z-test", "covariate": "",
        "mean_control": test["rate_control"], "mean_treatment": test["rate_treatment"],
        **{key: test[key] for key in shared},
        "correlation": None, "variance_reduction": None,
    })

    # Revenue per user, raw: the difference-in-means test on per-user values.
    revenue = user_metrics["revenue_usd"].to_numpy(dtype=float)
    test = difference_in_means_test(revenue[is_control], revenue[is_treatment])
    rows.append({
        "metric": "revenue per user", "method": "difference in means", "covariate": "",
        "mean_control": test["mean_control"], "mean_treatment": test["mean_treatment"],
        **{key: test[key] for key in shared},
        "correlation": None, "variance_reduction": None,
    })

    # CUPED: adjust the metric with a December covariate, then test the
    # adjusted values. Theta is computed on both groups together.
    cuped_runs = [
        ("conversion", converted, "December purchase flag", "pre_converted"),
        ("conversion", converted, "December sessions", "pre_sessions"),
        ("revenue per user", revenue, "December revenue", "pre_revenue_usd"),
    ]
    for metric_name, metric_values, covariate_name, covariate_column in cuped_runs:
        covariate = user_metrics[covariate_column].to_numpy(dtype=float)
        cuped = cuped_adjust(metric_values, covariate)
        adjusted = cuped["adjusted"]
        test = difference_in_means_test(adjusted[is_control], adjusted[is_treatment])
        rows.append({
            "metric": metric_name, "method": "CUPED", "covariate": covariate_name,
            "mean_control": test["mean_control"], "mean_treatment": test["mean_treatment"],
            **{key: test[key] for key in shared},
            "correlation": cuped["correlation"],
            "variance_reduction": cuped["variance_reduction"],
        })

    return pd.DataFrame(rows)


def main():
    DATA_FOLDER.mkdir(parents=True, exist_ok=True)

    print("Loading from BigQuery...")
    user_metrics = load_user_metrics()
    # has_pre_activity is not in load_user_metrics; derive it from pre_sessions.
    user_metrics["has_pre_activity"] = user_metrics["pre_sessions"] > 0
    user_metrics["variant"] = user_metrics["variant_id"].map({0: "control", 1: "treatment"})

    exports = {
        "overview.csv": load_overview(),
        "funnel.csv": load_funnel(),
        "cohort_retention.csv": load_cohort_retention(),
        "experiment_groups.csv": build_experiment_groups(user_metrics),
        "experiment_results.csv": build_experiment_results(user_metrics),
    }

    for file_name, table in exports.items():
        table.to_csv(DATA_FOLDER / file_name, index=False)
        print(f"  {file_name:<26} {len(table):>4} rows")
    print(f"Saved to {DATA_FOLDER}")


if __name__ == "__main__":
    main()
