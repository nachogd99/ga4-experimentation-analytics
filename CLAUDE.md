# Project: GA4 Experimentation & Product Analytics

## Goal
Portfolio project for Data Analyst roles. Owner must be able to
explain every line in an interview, so prefer simple, readable code
over clever code, and explain non-obvious choices in comments.

## About the owner
New to Claude Code and to dbt with BigQuery (has used dbt with Snowflake).
Go one step at a time, explain what each command does before running it,
and stop after each step so the owner can review.

## Stack
- BigQuery (sandbox, US location), source: bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*
- dbt-bigquery (Python 3.11 venv), layers: staging > intermediate > marts
- Python analysis (pandas, scipy, statsmodels), Streamlit app

## Rules
- Always filter events_* with _TABLE_SUFFIX to limit bytes scanned
- Materialize staging as tables so we don't rescan raw data repeatedly
- Every mart model gets dbt tests (unique, not_null, relationships)
- Never commit credentials, profiles.yml, or .env files
- Do NOT write the statistical functions in analysis/stats.py;
  the owner writes those. You may write tests for them and review them.
- Work in small steps; stop after each step so the owner can review and commit
- When you notice something worth doing later, don't do it now and don't
  only mention it in chat: append it to docs/backlog.md tagged with the
  roadmap step it belongs to ([step N] or [later]), and tell me you added it
- When starting a roadmap step, read docs/backlog.md and include any items
  tagged for that step in your plan, so I can decide on each one
- When an item is done or deliberately dropped, move it to "Done or dropped"
  with a few words on what happened
- Respect the 2-weekend scope: never start [later] items unless I ask

## Project layout
- dbt project lives in ga4_analytics/ (run dbt commands from there)
- GCP project: ga4-experimentation-510510, dbt dataset: dbt_dev (US)
- Auth: gcloud application-default credentials (oauth), no key files
- Python venv in venv/ at repo root (Python 3.11)

## Roadmap (2 weekends)
Weekend 1, product analytics:
1. Staging: stg_events with event_params unnested
2. Intermediate: int_sessions (session key = user_pseudo_id + ga_session_id)
3. Marts: fct_funnel (view_item > add_to_cart > begin_checkout > purchase),
   dim_users, fct_cohort_retention, all with tests and docs
4. First README draft
Weekend 2, experimentation:
5. Simulated experiment: hash-based assignment on user_pseudo_id,
   experiment period Jan 2021, pre-period Dec 2020 (for CUPED)
6. A/A test first to validate the pipeline, then inject a known lift
7. analysis/stats.py (owner writes it): power analysis, two-proportion
   z-test, SRM check, CUPED
8. Streamlit app, experiment_readout.md, final README
The experiment is simulated on real traffic; always state this openly.

## Experiment design (decided, do not change without asking)
- Unit of randomization and analysis: user (user_pseudo_id)
- Eligible users: users with at least one session in Jan 2021
- Assignment: MOD(ABS(FARM_FINGERPRINT(CONCAT(user_pseudo_id, salt))), 2),
  0 = control, 1 = treatment, default salt 'exp1'
- Primary metric: purchase conversion (user purchased at least once in Jan 2021)
- Secondary metric: revenue per user in Jan 2021
- Pre-period covariate for CUPED: same metrics for Dec 2020 (0 if no activity)
- Assignment and user metrics are dbt models (exp_assignments, exp_user_metrics)
- Lift injection and A/A simulations happen in Python only; dbt marts
  always contain real, unmodified data
- A/A test: rerun assignment with many salts (e.g. 1000), check that
  roughly 5% of runs give p < 0.05
- Claude may write the simulation harness, but it must call the owner's
  functions in analysis/stats.py

## Data scope
- Use the full dataset range: 2020-11-01 to 2021-01-31
- Funnel is session-level: a step counts if the event occurred in that session

## Repo structure
- ga4_analytics/: dbt project
- analysis/: stats.py (owner), simulations, tests
- app/: Streamlit app (reads from small cached exports, since sandbox
  tables expire after 60 days)
- docs/: experiment_readout.md, screenshots

## Git
- Never run git commit or git push. Stop and tell the owner what to commit.