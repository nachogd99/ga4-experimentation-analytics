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
