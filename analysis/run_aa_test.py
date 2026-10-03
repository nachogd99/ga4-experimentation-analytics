"""Runs the A/A test and saves the results.

Run from the repository root with:  python -m analysis.run_aa_test

Reassigns the eligible users 1,000 times with different salts, tests each
split, saves one row per salt to analysis/results/aa_test.csv and prints a
summary. Needs the dbt tables to exist in BigQuery.
"""

from pathlib import Path

from analysis.data import load_aa_totals
from analysis.simulations import run_aa_test, summarize_aa_test

NUMBER_OF_SALTS = 1000
RESULTS_FILE = Path(__file__).parent / "results" / "aa_test.csv"


def main():
    print(f"Loading totals for {NUMBER_OF_SALTS:,} salts from BigQuery...")
    aa_totals = load_aa_totals(NUMBER_OF_SALTS)

    aa_results = run_aa_test(aa_totals)
    RESULTS_FILE.parent.mkdir(exist_ok=True)
    aa_results.to_csv(RESULTS_FILE, index=False)
    print(f"Saved {len(aa_results):,} rows to {RESULTS_FILE}")

    summary = summarize_aa_test(aa_results)
    print()
    print(f"A/A tests run:        {summary['number_of_tests']:,}")
    print(f"False alarms:         {summary['false_alarms']} "
          f"({summary['false_alarm_rate']:.1%})")
    print(f"Expected range:       {summary['expected_low']:.2%} "
          f"to {summary['expected_high']:.2%}")
    print(f"Within the range:     {summary['passed']}")
    print(f"z-score mean:         {summary['z_score_mean']:+.3f}  (expected 0)")
    print(f"z-score std:          {summary['z_score_std']:.3f}  (expected 1)")
    print(f"SRM alarms at 0.001:  {summary['srm_alarms']}  (about 1 expected)")


if __name__ == "__main__":
    main()
