"""Streamlit app for the GA4 product analytics and experimentation project.

Run from the repository root with:  streamlit run app/app.py

The app reads small CSV files that are committed to the repository:
  app/data/          exported from the dbt tables (analysis/export_app_data.py)
  analysis/results/  saved by the A/A test and lift injection scripts
It never connects to BigQuery, so it needs no credentials.

This file handles layout: it loads each table, prepares it, and places the
tiles, charts and text. The charts themselves are built in charts.py.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

# Make the repository root importable, so the app can use analysis/stats.py,
# and the app folder importable, so it can use charts.py.
APP_FOLDER = Path(__file__).parent
ROOT = APP_FOLDER.parent
sys.path.append(str(ROOT))
sys.path.append(str(APP_FOLDER))

import charts  # noqa: E402  (must come after the sys.path lines above)
from analysis.simulations import summarize_aa_test  # noqa: E402
from analysis.stats import minimum_detectable_effect, power_of_test, srm_check  # noqa: E402

DATA_FOLDER = APP_FOLDER / "data"
RESULTS_FOLDER = ROOT / "analysis" / "results"

SIMULATED_NOTICE = (
    "**This experiment is simulated on real traffic.** The Google Merchandise "
    "Store did not run this test. Users are split into control and treatment "
    "by hashing their id, and nothing was changed for either group, so no real "
    "difference is expected. Where an effect appears, it was injected in Python "
    "and is labelled as such."
)


@st.cache_data
def load_csv(folder, file_name, date_columns=None):
    """Read one CSV file. st.cache_data keeps it in memory between reruns."""
    return pd.read_csv(Path(folder) / file_name, parse_dates=date_columns)


def current_palette():
    """Pick the chart colours that match the viewer's light or dark theme."""
    try:
        is_dark = st.context.theme.type == "dark"
    except Exception:
        is_dark = False
    return charts.DARK if is_dark else charts.LIGHT


def show_chart(chart, table):
    """Show a chart with the same data available as a table underneath."""
    st.altair_chart(chart, width="stretch")
    with st.expander("Show this data as a table"):
        st.dataframe(table, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def overview_page():
    overview = load_csv(DATA_FOLDER, "overview.csv").iloc[0]

    st.markdown(
        "A dbt pipeline on BigQuery turns the raw Google Analytics 4 export of "
        "the Google Merchandise Store into funnel, user and retention tables. "
        "A simulated A/B test is then analysed with statistics written by hand."
    )
    st.caption(f"Data from {overview['first_date']} to {overview['last_date']}.")

    tiles = st.columns(5)
    tiles[0].metric("Events", f"{overview['events'] / 1e6:.1f}M")
    tiles[1].metric("Sessions", f"{overview['sessions'] / 1e3:.0f}K")
    tiles[2].metric("Users", f"{overview['users'] / 1e3:.0f}K")
    tiles[3].metric("Purchases", f"{overview['purchases']:,.0f}")
    tiles[4].metric("Revenue", f"${overview['revenue_usd'] / 1e3:.0f}K")

    st.markdown(
        f"- **{overview['purchasers'] / overview['users']:.1%}** of users purchased at least once.\n"
        f"- **{overview['single_session_users'] / overview['users']:.0%}** of users had exactly one session.\n"
        "- The dataset is obfuscated by Google, which affects some results. "
        "Traffic source in particular is unreliable, so nothing here is broken down by channel."
    )
    st.info(SIMULATED_NOTICE)


def funnel_page(palette):
    funnel = load_csv(DATA_FOLDER, "funnel.csv", date_columns=["session_date"])

    # One filter above everything it applies to.
    device = st.selectbox("Device", ["All devices", "desktop", "mobile", "tablet"])
    if device != "All devices":
        funnel = funnel[funnel["device_category"] == device]

    total_sessions = funnel["sessions"].sum()
    steps = pd.DataFrame(
        {
            "step": ["Viewed an item", "Added to cart", "Began checkout", "Purchased"],
            "sessions": [
                funnel["view_item_sessions"].sum(),
                funnel["add_to_cart_sessions"].sum(),
                funnel["begin_checkout_sessions"].sum(),
                funnel["purchase_sessions"].sum(),
            ],
        }
    )
    steps["share"] = steps["sessions"] / total_sessions
    steps["label"] = [
        f"{sessions:,}  ({share:.1%} of sessions)"
        for sessions, share in zip(steps["sessions"], steps["share"])
    ]

    tiles = st.columns(3)
    tiles[0].metric("Sessions", f"{total_sessions:,}")
    tiles[1].metric("Viewed an item", f"{steps['share'][0]:.1%}")
    tiles[2].metric("Purchased", f"{steps['share'][3]:.2%}")

    st.subheader("Sessions reaching each step")
    st.caption(
        "A session counts for a step if the event occurred in it, in any order. "
        "About 46% of checkout sessions have no add-to-cart in the same session, "
        "because the cart was filled earlier."
    )
    show_chart(charts.funnel_chart(steps, palette), steps[["step", "sessions", "share"]])

    st.subheader("Share of sessions with a purchase, by week")
    # Weeks start on Sunday. dayofweek is 0 for Monday and 6 for Sunday, so
    # (dayofweek + 1) % 7 is the number of days since the last Sunday.
    days_since_sunday = (funnel["session_date"].dt.dayofweek + 1) % 7
    funnel = funnel.assign(week_start=funnel["session_date"] - pd.to_timedelta(days_since_sunday, unit="D"))
    weekly = funnel.groupby("week_start", as_index=False)[["sessions", "purchase_sessions"]].sum()
    # The last week holds a single day (2021-01-31), so leave it out.
    weekly = weekly[weekly["week_start"] < "2021-01-31"]
    weekly["conversion_rate"] = weekly["purchase_sessions"] / weekly["sessions"]
    st.caption("Conversion falls after the holiday season: January is about 60% of December's rate.")
    show_chart(charts.weekly_conversion_chart(weekly, palette), weekly)


def retention_page(palette):
    retention = load_csv(DATA_FOLDER, "cohort_retention.csv")
    retention["cohort_label"] = retention["cohort_week"].astype(str)
    # Week 0 is the week of the first visit and is always 100%. Leaving it
    # out lets the colour scale show the differences in the later weeks.
    later_weeks = retention[retention["week_number"] >= 1]

    st.markdown(
        "Users are grouped by the week of their first visit. Each cell shows the "
        "share of that group who came back in a later week. Only new users are "
        "included. Later groups have fewer cells because less time has passed."
    )

    week_1 = later_weeks[later_weeks["week_number"] == 1]
    tiles = st.columns(3)
    tiles[0].metric("Cohorts", f"{retention['cohort_week'].nunique()}")
    tiles[1].metric(
        "Back in week 1, average",
        f"{week_1['active_users'].sum() / week_1['cohort_size'].sum():.1%}",
    )
    tiles[2].metric(
        "Back in week 1, range",
        f"{week_1['retention_rate'].min():.1%} to {week_1['retention_rate'].max():.1%}",
    )

    st.subheader("Share of each cohort returning")
    st.caption("Week 0, the week of the first visit, is always 100% and is not shown.")
    table = later_weeks.pivot(index="cohort_label", columns="week_number", values="retention_rate")
    table = (table * 100).round(1).reset_index().rename(columns={"cohort_label": "First visit, week of"})
    table.columns = [str(column) for column in table.columns]
    show_chart(charts.retention_heatmap(later_weeks, palette), table)

    st.subheader("Average retention by week")
    curve = later_weeks.groupby("week_number", as_index=False)[["cohort_size", "active_users"]].sum()
    curve = curve.rename(columns={"cohort_size": "cohort_users"})
    curve["retention_rate"] = curve["active_users"] / curve["cohort_users"]
    st.caption("All cohorts combined, counting each cohort only for the weeks it has been observed.")
    show_chart(charts.retention_curve_chart(curve, palette), curve)


def experiment_page(palette):
    groups = load_csv(DATA_FOLDER, "experiment_groups.csv").set_index("variant")
    results = load_csv(DATA_FOLDER, "experiment_results.csv")
    control, treatment = groups.loc["control"], groups.loc["treatment"]

    st.info(SIMULATED_NOTICE)
    st.markdown(
        "**Design.** Users with a session in January 2021 are eligible. Each is "
        "assigned to control or treatment by hashing their id. The primary metric "
        "is purchase conversion; the secondary metric is revenue per user."
    )

    # Check the split before reading any metric.
    st.subheader("1. Is the split sound?")
    srm = srm_check(int(control["users"]), int(treatment["users"]))
    tiles = st.columns(3)
    tiles[0].metric("Control users", f"{control['users']:,.0f}")
    tiles[1].metric("Treatment users", f"{treatment['users']:,.0f}")
    tiles[2].metric("Sample ratio check, p-value", f"{srm['p_value']:.3f}")
    st.caption(
        "The split is uneven by chance. The check raises an alarm below 0.001, a "
        "threshold set before looking, so this split passes. "
        + ("**A mismatch was detected.**" if srm["srm_detected"] else "No mismatch detected.")
    )

    st.subheader("2. Results on the real data")
    results["label"] = np.where(
        results["method"] == "CUPED", "CUPED, " + results["covariate"].fillna(""), "No adjustment"
    )
    conversion = results[results["metric"] == "conversion"].copy()
    revenue = results[results["metric"] == "revenue per user"].copy()

    tiles = st.columns(3)
    tiles[0].metric("Control conversion", f"{control['conversion_rate']:.3%}")
    tiles[1].metric("Treatment conversion", f"{treatment['conversion_rate']:.3%}")
    tiles[2].metric("p-value", f"{conversion['p_value'].iloc[0]:.3f}")
    st.caption(
        "Neither metric shows a significant difference, which is the correct "
        "answer: nothing was done to the treatment group."
    )

    st.markdown("**Conversion: treatment minus control, with 95% confidence intervals**")
    # Show the difference in percentage points.
    for column in ["difference", "ci_low", "ci_high"]:
        conversion[column] = conversion[column] * 100
    show_chart(
        charts.interval_chart(conversion, palette, "Difference in percentage points", "+.3f"),
        conversion[["label", "difference", "ci_low", "ci_high", "z_score", "p_value"]].round(4),
    )

    st.markdown("**Revenue per user: treatment minus control, with 95% confidence intervals**")
    show_chart(
        charts.interval_chart(revenue, palette, "Difference in US dollars per user", "+.3f"),
        revenue[["label", "difference", "ci_low", "ci_high", "z_score", "p_value"]].round(4),
    )

    st.subheader("3. Does CUPED help?")
    best = results["variance_reduction"].max()
    st.markdown(
        "CUPED uses each user's December activity to remove noise from the January "
        f"metrics. Here it removes at most **{best:.1%}** of the variance, so the "
        "intervals above barely narrow. The reason is retention: only "
        f"**{(control['users_with_pre_activity'] + treatment['users_with_pre_activity']) / (control['users'] + treatment['users']):.1%}** "
        "of eligible users were active in December, so almost everyone has a "
        "December value of zero. The method works; this dataset gives it little to use."
    )
    cuped = results[results["method"] == "CUPED"][["metric", "covariate", "correlation", "variance_reduction"]]
    st.dataframe(cuped.round(4), hide_index=True, width="stretch")

    st.subheader("4. What could this experiment detect?")
    st.markdown(
        "Power is the chance of detecting an effect that really exists. Change the "
        "inputs to see how the baseline rate and the number of users affect it."
    )
    real_baseline = (control["conversions"] + treatment["conversions"]) / (control["users"] + treatment["users"])
    inputs = st.columns(2)
    baseline_rate = inputs[0].number_input(
        "Baseline conversion rate (%)", min_value=0.1, max_value=50.0,
        value=round(real_baseline * 100, 3), step=0.1, format="%.3f",
    ) / 100
    users_per_group = inputs[1].number_input(
        "Users per group", min_value=1_000, max_value=5_000_000,
        value=int(min(control["users"], treatment["users"])), step=1_000,
    )

    target_power = 0.80
    mde = minimum_detectable_effect(baseline_rate, users_per_group, power=target_power)
    tiles = st.columns(2)
    tiles[0].metric("Smallest lift detectable 80% of the time", f"+{mde:.1%}")
    tiles[1].metric("Chance of detecting a +10% lift", f"{power_of_test(baseline_rate, 0.10, users_per_group):.0%}")

    # Largest lift to plot: up to +50%, staying below a 100% treatment rate.
    largest_lift = min(0.50, (1 - baseline_rate) / baseline_rate * 0.99)
    lifts = np.linspace(0, largest_lift, 51)
    curve = pd.DataFrame(
        {
            "relative_lift": lifts,
            "power": [power_of_test(baseline_rate, lift, users_per_group) for lift in lifts],
        }
    )
    show_chart(charts.power_chart(curve, palette, target_power), curve.round(4))


def validation_page(palette):
    aa_results = load_csv(RESULTS_FOLDER, "aa_test.csv")
    lift_demo = load_csv(RESULTS_FOLDER, "lift_demo.csv")
    detection = load_csv(RESULTS_FOLDER, "lift_detection.csv")
    groups = load_csv(DATA_FOLDER, "experiment_groups.csv")

    st.markdown(
        "Two checks that the pipeline can be trusted: it should stay quiet when "
        "nothing is going on, and it should find an effect that was planted."
    )

    st.subheader("1. A/A test: does it stay quiet?")
    st.markdown(
        "The same users were split 1,000 times with different salts and no effect. "
        "At a 0.05 threshold, about 5% of these tests should come out significant by chance."
    )
    summary = summarize_aa_test(aa_results)
    tiles = st.columns(3)
    tiles[0].metric("A/A tests", f"{summary['number_of_tests']:,}")
    tiles[1].metric("False alarms", f"{summary['false_alarm_rate']:.1%}")
    tiles[2].metric(
        "Expected range",
        f"{summary['expected_low']:.2%} to {summary['expected_high']:.2%}",
    )
    st.caption(
        "The range was set before running the test. "
        + ("The result is inside it." if summary["passed"] else "**The result is outside it.**")
    )

    st.markdown("**Spread of the 1,000 p-values**")
    edges = np.linspace(0, 1, 11)
    counts, _ = np.histogram(aa_results["p_value"], bins=edges)
    bins = pd.DataFrame(
        {
            "bin": [f"{low:.1f} to {high:.1f}" for low, high in zip(edges[:-1], edges[1:])],
            "tests": counts,
        }
    )
    show_chart(charts.pvalue_histogram(bins, palette, len(aa_results) / 10), bins)

    st.subheader("2. Planted effect: does it find it?")
    st.info("The lift below is injected in Python. The data in BigQuery is not modified.")
    real, with_lift = lift_demo.iloc[0], lift_demo.iloc[1]
    tiles = st.columns(3)
    tiles[0].metric("Lift injected", f"+{with_lift['injected_lift']:.0%}")
    tiles[1].metric("Lift measured", f"{with_lift['relative_lift']:+.1%}")
    tiles[2].metric("p-value", f"{with_lift['p_value']:.4f}")

    demo = pd.DataFrame(
        {
            "label": ["Real data", f"With +{with_lift['injected_lift']:.0%} injected"],
            "difference": [real["difference"] * 100, with_lift["difference"] * 100],
            "ci_low": [real["ci_low"] * 100, with_lift["ci_low"] * 100],
            "ci_high": [real["ci_high"] * 100, with_lift["ci_high"] * 100],
            "p_value": [real["p_value"], with_lift["p_value"]],
        }
    )
    st.markdown("**Conversion: treatment minus control, with 95% confidence intervals**")
    show_chart(
        charts.interval_chart(demo, palette, "Difference in percentage points", "+.3f"),
        demo.round(4),
    )

    st.subheader("3. Is it detected as often as predicted?")
    st.markdown(
        "For each lift, 1,000 complete experiments were simulated: a fresh random "
        "split, the lift injected, the test run. The share detected should match "
        "the power predicted beforehand. Small lifts are usually missed, as predicted."
    )
    baseline_rate = groups["conversions"].sum() / groups["users"].sum()
    users_per_group = groups["users"].sum() / 2
    lifts = np.linspace(0, 0.30, 31)
    predicted = pd.DataFrame(
        {
            "relative_lift": lifts,
            "rate": [power_of_test(baseline_rate, lift, users_per_group) for lift in lifts],
            "series": "Predicted power",
        }
    )
    measured = pd.DataFrame(
        {
            "relative_lift": detection["relative_lift"],
            "rate": detection["detection_rate"],
            "series": "Detected in simulation",
        }
    )
    show_chart(
        charts.detection_chart(predicted, measured, palette),
        detection[["relative_lift", "simulations", "detected", "detection_rate", "predicted_power"]].round(4),
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

st.set_page_config(page_title="GA4 Experimentation & Product Analytics", layout="wide")
# Streamlit offers two widths: "centered" (about 700px, cramped for charts)
# and "wide" (the full window, too stretched to read). This caps the wide
# layout at 1,100px. "block-container" is Streamlit's name for the main column.
st.markdown(
    "<style>.block-container {max-width: 1100px;}</style>",
    unsafe_allow_html=True,
)
st.title("GA4 Experimentation & Product Analytics")

palette = current_palette()
overview_tab, funnel_tab, retention_tab, experiment_tab, validation_tab = st.tabs(
    ["Overview", "Funnel", "Retention", "Experiment", "Validation"]
)
with overview_tab:
    overview_page()
with funnel_tab:
    funnel_page(palette)
with retention_tab:
    retention_page(palette)
with experiment_tab:
    experiment_page(palette)
with validation_tab:
    validation_page(palette)
