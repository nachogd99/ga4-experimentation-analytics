# Experiment readout: simulated A/B test on January 2021 traffic

> **This experiment is simulated on real traffic.** The Google Merchandise
> Store did not run this test. Users were split into control and treatment by
> hashing their id, and nothing was changed for either group. The purpose is to
> build and validate an experiment analysis pipeline, not to evaluate a product
> change. Where an effect appears below, it was injected in Python and is
> labelled as such.

## Summary

- **No difference between the groups, as expected.** Conversion was 1.136% in
  control and 1.119% in treatment (p = 0.81). Revenue per user was $0.585 and
  $0.625 (p = 0.52). Nothing was done to the treatment group, so this is the
  correct result.
- **The pipeline can be trusted.** In 1,000 A/A tests it raised a false alarm
  4.4% of the time, against an expected 5%. When a +25% lift was planted, it
  detected it (p = 0.0001) and measured it as +24.9%.
- **The experiment can only detect large effects.** With a 1.13% baseline and
  about 47,000 users per group, the smallest lift it would catch 80% of the
  time is +17.8%. A +10% lift would be missed almost two times in three.

## Design

| | |
|---|---|
| Unit of randomization and analysis | User (`user_pseudo_id`, a browser) |
| Eligible users | Users with at least one session in January 2021: 94,788 |
| Assignment | `MOD(ABS(FARM_FINGERPRINT(CONCAT(user_pseudo_id, salt))), 2)`, 0 = control, 1 = treatment, salt `exp1` |
| Primary metric | Purchase conversion: the user purchased at least once in January 2021 |
| Secondary metric | Revenue per user in January 2021 |
| Pre-period | December 2020, used as the covariate for CUPED |
| Significance level | 0.05, two-sided |

The assignment hashes the user id together with a salt. The same user always
lands in the same group, so the split is reproducible, and a different salt
gives an independent split of the same users.

## Check before reading results: is the split sound?

| | Control | Treatment |
|---|---|---|
| Users | 47,087 | 47,701 |
| Expected under a 50/50 design | 47,394 | 47,394 |

A sample ratio mismatch check (a chi-square test of the observed split against
the designed one) gives a p-value of **0.046**. The alert threshold is 0.001,
set before running the check, so **no mismatch is detected**.

The threshold is stricter than the 0.05 used for metrics because this check is
an alarm that stops the analysis: it should rarely fire on a healthy
experiment, and real assignment bugs produce far smaller p-values. A split
this uneven happens by chance about once in 22 experiments. The salt was not
changed to get a tidier split, since that would be choosing the data after
seeing it.

## Results

### Primary metric: conversion

| | Control | Treatment |
|---|---|---|
| Users | 47,087 | 47,701 |
| Converted | 535 | 534 |
| Conversion rate | 1.136% | 1.119% |

| | |
|---|---|
| Difference (treatment minus control) | -0.017 percentage points (-1.5% relative) |
| 95% confidence interval | -0.151 to +0.118 percentage points |
| z-score | -0.24 |
| p-value | 0.807 |
| Significant at 0.05 | No |

Test: two-proportion z-test. The interval contains zero. In relative terms it
runs from about -13% to +10%, so the data are consistent with no effect and
also with a moderate effect in either direction.

### Secondary metric: revenue per user

| | |
|---|---|
| Control | $0.585 |
| Treatment | $0.625 |
| Difference | +$0.040 (+6.9% relative) |
| 95% confidence interval | -$0.083 to +$0.163 |
| z-score | +0.64 |
| p-value | 0.521 |
| Significant at 0.05 | No |

Test: difference in means with unequal variances. A 6.9% gap looks large but
is well within chance: most users spend nothing and a few spend hundreds of
dollars, so revenue per user is very noisy.

## What this experiment could detect

A result of "not significant" only means something if the experiment was able
to detect an effect in the first place. With January's baseline of 1.128% and
47,087 users in the smaller group:

**Minimum detectable effect at 80% power: +17.8% relative** (from 1.128% to
1.329%).

| True lift | Chance of detecting it (power) |
|---|---|
| +5% | 13% |
| +10% | 36% |
| +15% | 66% |
| +20% | 88% |
| +25% | 97% |

| Lift to detect at 80% power | Users needed per group |
|---|---|
| +5% | 564,086 |
| +10% | 144,417 |
| +20% | 37,799 |

Purchases are rare, so the signal is weak. To detect a +10% lift reliably, the
experiment would need about three times as many users.

The baseline is January's own rate. Session conversion fell from 1.59% in
December to 0.94% in January, so a three-month average would have overstated
the baseline and made the experiment look more capable than it is.

## CUPED: it barely helps here

CUPED reduces noise by subtracting the part of each user's metric that their
pre-experiment behaviour predicts. The variance it removes equals the squared
correlation between the pre-period covariate and the metric.

| Metric | December covariate | Correlation | Variance removed | Interval narrower by |
|---|---|---|---|---|
| Conversion | Purchased in December | 0.080 | 0.65% | 0.32% |
| Conversion | Sessions in December | 0.101 | 1.02% | 0.51% |
| Revenue per user | Revenue in December | 0.021 | 0.04% | 0.02% |

The best case narrows the confidence interval by half a percent. The cause is
retention: only 3,206 of the 94,788 eligible users (3.4%) had any activity in
December, so the covariate is zero for almost everyone and carries almost no
information.

This is a property of the data, not a failure of the method. On synthetic data
with a covariate that predicts the metric, the same function narrows the
interval by more than 20% while leaving the estimate unchanged; the test suite
checks this. CUPED pays off for products with returning users, which this
store, over this period, mostly does not have.

## Validation

### A/A test: does the pipeline stay quiet when nothing is going on?

The 94,788 users were reassigned 1,000 times, each with a different salt, and
tested each time. No effect exists in any of these splits, so every
"significant" result is a false alarm. At a 0.05 threshold, about 5% are
expected.

The pass criterion was fixed before the run: with 1,000 tests, a true 5% rate
should be observed between 3.65% and 6.35%.

| | Result | Expected |
|---|---|---|
| A/A tests | 1,000 | |
| False alarms | 44 (4.4%) | 3.65% to 6.35% |
| **Passed** | **Yes** | |

**An unplanned check, and how it was resolved.** After the run, one diagnostic
that was not part of the criterion looked off: the standard deviation of the
1,000 z-scores was 0.949, where 1 is expected. A gap that large occurs by
chance about 2% of the time. To tell chance from a slightly over-cautious
test, the harness was run on 4,000 further salts that the first run had not
used.

| | First 1,000 (official) | 4,000 further salts (follow-up) |
|---|---|---|
| False alarm rate | 4.4% | 5.08% |
| z-score standard deviation | 0.949 | 0.992 |
| Sample ratio alarms at 0.001 | 3 | 2 |

On the larger set every figure is where it should be, so the first result was
chance. The follow-up is reported separately because it was not planned: the
official result is the first 1,000.

### Planted effect: does the pipeline find it?

A +25% lift was injected into the treatment group of the real `exp1` split by
turning a random 143 non-converting treatment users into converters. Control
was not touched.

| | Real data | With +25% injected |
|---|---|---|
| Control conversion | 1.136% | 1.136% |
| Treatment conversion | 1.119% | 1.419% |
| Difference | -0.017 points | +0.283 points |
| Relative lift measured | -1.5% | +24.9% |
| 95% confidence interval | -0.151 to +0.118 | +0.140 to +0.426 |
| p-value | 0.807 | 0.0001 |

The test detects the planted effect and recovers its size. The interval is
still wide, about +12% to +37% in relative terms: even a clearly detected
effect cannot be measured precisely at this sample size.

### Is the effect detected as often as predicted?

For each of five lift sizes, 1,000 complete experiments were simulated and the
share that came out significant was compared with the power predicted
beforehand.

| Injected lift | Detected in simulation | Predicted power |
|---|---|---|
| +5% | 11.0% | 12.8% |
| +10% | 36.7% | 36.1% |
| +15% | 64.7% | 66.3% |
| +20% | 89.0% | 88.0% |
| +25% | 97.5% | 97.2% |

Every measured rate is within 2 points of the prediction, which is the
precision 1,000 simulations allow. This validates the injection, the z-test
and the power analysis together.

**Why each simulation uses a new random split.** Power describes what happens
across many experiments, in which the assignment itself is random. Injecting
the lift repeatedly into the single `exp1` split would not measure that: the
two groups' starting rates would never change, so the outcome would be nearly
the same every time and would depend on how `exp1` happened to fall. Each
simulated experiment therefore splits the users afresh, injects the lift, and
runs the test.

## Limitations

- **The experiment is simulated.** There was no treatment. The real-data
  results show that the pipeline finds nothing when nothing is there; the
  injected results show that it finds an effect of known size.
- **Only conversion is modified by the injection.** Revenue is left as it is,
  so there is no simulated result for the secondary metric.
- **The revenue test leans on the normal approximation.** With about 47,000
  users per group that is reasonable, but one user can spend $1,200. Capping
  extreme values or bootstrapping would be more robust.
- **A user is a browser.** The dataset has no logged-in user id, so one person
  on two devices counts as two users and could land in both groups.
- **The dataset is obfuscated by Google.** This affects traffic source in
  particular, which is why no result is broken down by channel.

## How to reproduce

From the repository root, after `dbt build` has created the tables:

```
python -m pytest analysis
python -m analysis.run_aa_test
python -m analysis.run_lift_injection
python -m analysis.export_app_data
```

The statistics are in `analysis/stats.py`, written out by hand and tested
against statsmodels and scipy. The simulation harness is in
`analysis/simulations.py`. Results are saved in `analysis/results/` and
`app/data/`.
