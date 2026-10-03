# Backlog

Items noticed during development that are not for now. Each item is tagged
with the roadmap step where it becomes relevant ([step N], matching the
roadmap in CLAUDE.md) or [later] for anything outside the 8 steps.
Format: - [tag] short description (why it matters, in one line)

## Open

- [step 2] Decide how `is_session_engaged` rolls up to a session, e.g. max over the session's events (it is null on about 7% of events, which carry no `session_engaged` param)
- [step 2] Take session source/medium/campaign from the first non-null event in the session (`event_source` etc. are filled on only about 28% of events, so most rows are null)
- [step 3] Define a purchase as `event_name = 'purchase'`, not as a non-null `transaction_id` (906 of 5,692 purchase events have no real id, so the id undercounts purchases by about 16%)
- [step 3] Check whether any mart needs item-level data; if so, add a staging model for the `items` array (`stg_events` does not read `items`)
- [step 4] README setup section: gcloud application-default login and the `maximum_bytes_billed` profile setting (profiles.yml is not in the repo, so a fresh clone has no byte cap)
- [step 4] README: say that sandbox tables expire after 60 days and `dbt run` rebuilds them (`stg_events` built 2026-10-03 expires 2026-12-02)
- [step 4] Replace or delete `ga4_analytics/README.md` (still the stock `dbt init` text, which looks unfinished in a portfolio repo)
- [step 5] Use the same purchase definition in `exp_user_metrics`: `event_name = 'purchase'` (the primary metric would otherwise miss about 16% of purchases)
- [step 5] Check what share of Jan 2021 eligible users have any Dec 2020 activity (if most have a covariate of 0, CUPED will reduce variance very little, and the readout should say so)
- [step 6] Decide how the A/A harness reproduces `FARM_FINGERPRINT` for 1000 salts: run the assignment in BigQuery from Python, or use a farmhash library (not in requirements.txt; results must match `exp_assignments`)
- [step 8] Rebuild the dbt tables right before creating the cached exports for the app (the tables may have expired by then)
- [later] Partition `stg_events` by `event_date` if the project moves off the sandbox (not possible now: the sandbox's 60-day partition expiry would drop all 2020-21 partitions)
- [later] Add `cluster_by: event_name` to `stg_events` (would cut bytes scanned by funnel queries; the 1.4 GB table is cheap enough without it)
- [later] Add the params left out of `stg_events` if a question needs them: `coupon`, `payment_type`, `shipping_tier`, `promotion_name`, `link_*` (skipped as low value for funnel and experiment work)
- [later] Run `gcloud auth login` if the `bq` command line is wanted (it has no logged-in account; dbt and Python work through application-default credentials)
- [later] When regenerating requirements.txt, use `pip freeze | Out-File -Encoding ascii requirements.txt` (PowerShell's `>` writes UTF-16, which git treats as binary)

## Done or dropped
