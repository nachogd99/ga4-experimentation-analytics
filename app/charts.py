"""Chart functions for the Streamlit app.

One function per chart. Each takes a small pandas table plus a palette and
returns an Altair chart. There is no Streamlit code here; app.py decides
where each chart goes.

Conventions used throughout:
  - one colour per chart, unless the chart has series that must be told apart
  - thin marks: bars 22px thick with a rounded end, lines 2px
  - every chart has tooltips, and app.py shows the same data as a table
"""

import altair as alt
import pandas as pd

# Colours for the light and the dark theme. The series colours are a
# colourblind-safe pair; the ramp is one hue from light to dark, used where
# colour shows "how much" (the retention heatmap).
LIGHT = {
    "series_1": "#2a78d6",  # blue: the default colour for a single series
    "series_2": "#eb6834",  # orange: only used when a second series is needed
    "ink": "#0b0b0b",       # text drawn on the chart
    "reference": "#898781", # reference lines such as "no difference"
    "ramp": ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"],
}
DARK = {
    "series_1": "#3987e5",
    "series_2": "#d95926",
    "ink": "#ffffff",
    "reference": "#898781",
    # Reversed: on a dark background, small values should fade towards it.
    "ramp": ["#0d366b", "#1c5cab", "#3987e5", "#86b6ef", "#cde2fb"],
}

BAR_THICKNESS = 22
BAR_CORNER = 4
LINE_WIDTH = 2
POINT_SIZE = 80


def funnel_chart(steps, palette):
    """Horizontal bars, one per funnel step, with the value at the tip.

    steps: one row per step with columns step, sessions and label
           (the text shown beside the bar)
    """
    # Leave room on the right for the labels.
    x_scale = alt.Scale(domain=[0, steps["sessions"].max() * 1.35])
    base = alt.Chart(steps).encode(
        # ",.0f" writes 20000 as 20,000. tickCount keeps the axis uncluttered.
        # No gridlines: each bar has its value written beside it.
        x=alt.X(
            "sessions:Q",
            title="Sessions",
            scale=x_scale,
            axis=alt.Axis(format=",.0f", tickCount=5, grid=False),
        ),
        # sort=None keeps the steps in the order of the table
        y=alt.Y("step:N", sort=None, title=None),
    )
    bars = base.mark_bar(
        size=BAR_THICKNESS, cornerRadiusEnd=BAR_CORNER, color=palette["series_1"]
    ).encode(
        tooltip=[
            alt.Tooltip("step:N", title="Step"),
            alt.Tooltip("sessions:Q", title="Sessions", format=","),
            alt.Tooltip("share:Q", title="Share of all sessions", format=".2%"),
        ]
    )
    labels = base.mark_text(align="left", dx=6, color=palette["ink"]).encode(text="label:N")
    return (bars + labels).properties(height=200)


def weekly_conversion_chart(weekly, palette):
    """Line of the share of sessions with a purchase, one point per week.

    weekly: columns week_start, sessions, purchase_sessions, conversion_rate
    """
    base = alt.Chart(weekly).encode(
        x=alt.X("week_start:T", title="Week starting", axis=alt.Axis(format="%b %d")),
        y=alt.Y(
            "conversion_rate:Q",
            title="Sessions with a purchase",
            axis=alt.Axis(format=".1%"),
            scale=alt.Scale(zero=True),
        ),
        tooltip=[
            alt.Tooltip("week_start:T", title="Week starting", format="%Y-%m-%d"),
            alt.Tooltip("sessions:Q", title="Sessions", format=","),
            alt.Tooltip("purchase_sessions:Q", title="With a purchase", format=","),
            alt.Tooltip("conversion_rate:Q", title="Conversion", format=".2%"),
        ],
    )
    line = base.mark_line(strokeWidth=LINE_WIDTH, color=palette["series_1"])
    points = base.mark_point(filled=True, opacity=1, size=POINT_SIZE, color=palette["series_1"])
    return (line + points).properties(height=280)


def retention_heatmap(retention, palette):
    """Grid of cohort (rows) by weeks since first visit (columns).

    Darker (lighter on a dark theme) means a larger share of the cohort came
    back that week.

    retention: columns cohort_label, week_number, cohort_size, active_users,
               retention_rate
    """
    return (
        alt.Chart(retention)
        .mark_rect()
        .encode(
            # paddingInner leaves a small gap between cells
            x=alt.X(
                "week_number:O",
                title="Weeks since first visit",
                scale=alt.Scale(paddingInner=0.08),
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y(
                "cohort_label:O",
                title="First visit, week of",
                scale=alt.Scale(paddingInner=0.08),
            ),
            color=alt.Color(
                "retention_rate:Q",
                title="Share returning",
                scale=alt.Scale(range=palette["ramp"]),
                legend=alt.Legend(format=".0%"),
            ),
            tooltip=[
                alt.Tooltip("cohort_label:O", title="First visit, week of"),
                alt.Tooltip("week_number:O", title="Weeks since first visit"),
                alt.Tooltip("cohort_size:Q", title="Users in cohort", format=","),
                alt.Tooltip("active_users:Q", title="Came back", format=","),
                alt.Tooltip("retention_rate:Q", title="Share returning", format=".2%"),
            ],
        )
        .properties(height=380)
    )


def retention_curve_chart(curve, palette):
    """Line of average retention by weeks since first visit.

    curve: columns week_number, cohort_users, active_users, retention_rate
    """
    base = alt.Chart(curve).encode(
        x=alt.X("week_number:O", title="Weeks since first visit", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("retention_rate:Q", title="Share returning", axis=alt.Axis(format=".1%")),
        tooltip=[
            alt.Tooltip("week_number:O", title="Weeks since first visit"),
            alt.Tooltip("cohort_users:Q", title="Users observed that long", format=","),
            alt.Tooltip("active_users:Q", title="Came back", format=","),
            alt.Tooltip("retention_rate:Q", title="Share returning", format=".2%"),
        ],
    )
    line = base.mark_line(strokeWidth=LINE_WIDTH, color=palette["series_1"])
    points = base.mark_point(filled=True, opacity=1, size=POINT_SIZE, color=palette["series_1"])
    return (line + points).properties(height=260)


def interval_chart(rows, palette, value_title, value_format):
    """Dot with its 95% confidence interval, one row per test.

    The vertical line marks "no difference". An interval that crosses it
    means the result is not statistically significant.

    rows: columns label, difference, ci_low, ci_high
    """
    y = alt.Y("label:N", sort=None, title=None, axis=alt.Axis(labelLimit=260))
    tooltip = [
        alt.Tooltip("label:N", title="Test"),
        alt.Tooltip("difference:Q", title="Difference", format=value_format),
        alt.Tooltip("ci_low:Q", title="Interval, low", format=value_format),
        alt.Tooltip("ci_high:Q", title="Interval, high", format=value_format),
    ]
    intervals = (
        alt.Chart(rows)
        .mark_rule(strokeWidth=LINE_WIDTH, color=palette["series_1"])
        .encode(x=alt.X("ci_low:Q", title=value_title), x2="ci_high:Q", y=y, tooltip=tooltip)
    )
    dots = (
        alt.Chart(rows)
        .mark_point(filled=True, opacity=1, size=110, color=palette["series_1"])
        .encode(x="difference:Q", y=y, tooltip=tooltip)
    )
    no_difference = (
        alt.Chart(pd.DataFrame({"value": [0]}))
        .mark_rule(color=palette["reference"])
        .encode(x="value:Q")
    )
    # 46px per row keeps the rows evenly spaced however many there are.
    return (no_difference + intervals + dots).properties(height=46 * len(rows) + 30)


def power_chart(curve, palette, target_power):
    """Line of power against the size of the true lift.

    The horizontal line marks the target power (usually 80%).

    curve: columns relative_lift, power
    """
    line = (
        alt.Chart(curve)
        .mark_line(strokeWidth=LINE_WIDTH, color=palette["series_1"])
        .encode(
            x=alt.X("relative_lift:Q", title="True relative lift", axis=alt.Axis(format="+.0%")),
            y=alt.Y(
                "power:Q",
                title="Chance of detecting it (power)",
                axis=alt.Axis(format=".0%"),
                scale=alt.Scale(domain=[0, 1]),
            ),
            tooltip=[
                alt.Tooltip("relative_lift:Q", title="True lift", format="+.0%"),
                alt.Tooltip("power:Q", title="Power", format=".1%"),
            ],
        )
    )
    target = pd.DataFrame({"power": [target_power], "label": [f"{target_power:.0%} target"]})
    target_line = alt.Chart(target).mark_rule(color=palette["reference"]).encode(y="power:Q")
    target_label = (
        alt.Chart(target)
        .mark_text(align="left", dx=4, dy=-8, color=palette["ink"])
        .encode(x=alt.value(0), y="power:Q", text="label:N")
    )
    return (target_line + line + target_label).properties(height=300)


def pvalue_histogram(bins, palette, expected_count):
    """Bars counting the A/A tests whose p-value falls in each tenth.

    With no real effect, p-values are spread evenly, so every bar should be
    near the horizontal line.

    bins: columns bin (text such as "0.0 to 0.1") and tests
    """
    bars = (
        alt.Chart(bins)
        .mark_bar(size=BAR_THICKNESS, cornerRadiusEnd=BAR_CORNER, color=palette["series_1"])
        .encode(
            x=alt.X("bin:O", sort=None, title="p-value", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("tests:Q", title="A/A tests"),
            tooltip=[
                alt.Tooltip("bin:O", title="p-value"),
                alt.Tooltip("tests:Q", title="A/A tests"),
            ],
        )
    )
    expected = pd.DataFrame({"tests": [expected_count], "label": ["expected if evenly spread"]})
    expected_line = alt.Chart(expected).mark_rule(color=palette["reference"]).encode(y="tests:Q")
    expected_label = (
        alt.Chart(expected)
        .mark_text(align="left", dx=4, dy=-8, color=palette["ink"])
        .encode(x=alt.value(0), y="tests:Q", text="label:N")
    )
    return (bars + expected_line + expected_label).properties(height=280)


def detection_chart(predicted, measured, palette):
    """Predicted power (line) against the share detected in simulation (dots).

    This is the only chart with two series, so it is the only one with a
    second colour and a legend.

    predicted: columns relative_lift, rate, series
    measured:  columns relative_lift, rate, series
    """
    series_names = [predicted["series"].iloc[0], measured["series"].iloc[0]]
    color = alt.Color(
        "series:N",
        title=None,
        scale=alt.Scale(domain=series_names, range=[palette["series_1"], palette["series_2"]]),
        legend=alt.Legend(orient="top"),
    )
    x = alt.X("relative_lift:Q", title="Injected relative lift", axis=alt.Axis(format="+.0%"))
    y = alt.Y(
        "rate:Q",
        title="Share of experiments that detect it",
        axis=alt.Axis(format=".0%"),
        scale=alt.Scale(domain=[0, 1]),
    )
    tooltip = [
        alt.Tooltip("series:N", title="Series"),
        alt.Tooltip("relative_lift:Q", title="Lift", format="+.0%"),
        alt.Tooltip("rate:Q", title="Share detected", format=".1%"),
    ]
    line = (
        alt.Chart(predicted)
        .mark_line(strokeWidth=LINE_WIDTH)
        .encode(x=x, y=y, color=color, tooltip=tooltip)
    )
    dots = (
        alt.Chart(measured)
        .mark_point(filled=True, opacity=1, size=110)
        .encode(x=x, y=y, color=color, tooltip=tooltip)
    )
    return (line + dots).properties(height=320)
