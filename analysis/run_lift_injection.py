"""Injects a known lift and checks that the pipeline detects it.

Run from the repository root with:  python -m analysis.run_lift_injection

Two parts:
  1. A demonstration on the real 'exp1' assignment: analyze the experiment
     as it is, then again with a +25% lift injected into treatment.
  2. A detection study: for several lift sizes, simulate many complete
     experiments and compare the share detected with the predicted power.

The lift is simulated in Python. The data in BigQuery is never modified.
Saves analysis/results/lift_demo.csv and analysis/results/lift_detection.csv.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from analysis.data import load_user_metrics
from analysis.simulations import analyze_conversion, inject_lift, run_lift_detection

DEMO_LIFT = 0.25
DEMO_SEED = 42

DETECTION_LIFTS = [0.05, 0.10, 0.15, 0.20, 0.25]
DETECTION_SIMULATIONS = 1000
DETECTION_SEED = 7

RESULTS_FOLDER = Path(__file__).parent / "results"


def print_analysis(title, result):
    print(f"\n{title}")
    print(f"  control:    {result['conversions_control']:>4} of {result['users_control']:,} "
          f"= {result['rate_control']:.3%}")
    print(f"  treatment:  {result['conversions_treatment']:>4} of {result['users_treatment']:,} "
          f"= {result['rate_treatment']:.3%}")
    print(f"  SRM check:  p = {result['srm_p_value']:.3f}, mismatch detected: {result['srm_detected']}")
    print(f"  difference: {result['difference'] * 100:+.3f} percentage points "
          f"({result['relative_lift']:+.1%} relative)")
    print(f"  z = {result['z_score']:+.2f}, p = {result['p_value']:.4f}, "
          f"95% CI {result['ci_low'] * 100:+.3f} to {result['ci_high'] * 100:+.3f} points")
    print(f"  significant: {result['significant']}")


def main():
    print("Loading user metrics from BigQuery...")
    user_metrics = load_user_metrics()
    # dtype=... turns the pandas columns into plain numpy integers and booleans
    converted = user_metrics["converted"].to_numpy(dtype=int)
    is_treatment = (user_metrics["variant_id"] == 1).to_numpy(dtype=bool)

    # Part 1: demonstration on the real assignment
    real = analyze_conversion(converted, is_treatment)
    print_analysis("Real data, no effect injected (salt 'exp1')", real)

    random = np.random.default_rng(DEMO_SEED)
    injected = inject_lift(converted, is_treatment, DEMO_LIFT, random)
    with_lift = analyze_conversion(injected, is_treatment)
    print_analysis(f"With a simulated +{DEMO_LIFT:.0%} lift injected into treatment", with_lift)

    RESULTS_FOLDER.mkdir(exist_ok=True)
    demo = pd.DataFrame([
        {"scenario": "real data", "injected_lift": 0.0, **real},
        {"scenario": "simulated lift", "injected_lift": DEMO_LIFT, **with_lift},
    ])
    demo.to_csv(RESULTS_FOLDER / "lift_demo.csv", index=False)

    # Part 2: detection study
    print(f"\nDetection study: {DETECTION_SIMULATIONS:,} simulated experiments per lift...")
    detection = run_lift_detection(
        converted, DETECTION_LIFTS, DETECTION_SIMULATIONS, seed=DETECTION_SEED
    )
    detection.to_csv(RESULTS_FOLDER / "lift_detection.csv", index=False)

    print("\n  lift    detected   predicted power")
    for row in detection.itertuples():
        print(f"  +{row.relative_lift:>3.0%}    {row.detection_rate:>6.1%}        {row.predicted_power:>6.1%}")
    print(f"\nSaved results to {RESULTS_FOLDER}")


if __name__ == "__main__":
    main()
