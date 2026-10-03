# Backlog

Items noticed during development that are not for now. Each item is tagged
with the roadmap step where it becomes relevant ([step N], matching the
roadmap in CLAUDE.md) or [later] for anything outside the 8 steps.
Format: - [tag] short description (why it matters, in one line)

## Open

- [step 5] Use the same purchase definition in `exp_user_metrics`: `event_name = 'purchase'` (the primary metric would otherwise miss about 16% of purchases)
- [step 5] Check what share of Jan 2021 eligible users have any Dec 2020 activity (if most have a covariate of 0, CUPED will reduce variance very little, and the readout should say so)
- [step 6] Decide how the A/A harness reproduces `FARM_FINGERPRINT` for 1000 salts: run the assignment in BigQuery from Python, or use a farmhash library (not in requirements.txt; results must match `exp_assignments`)
- [step 7] Base the power analysis on January's own conversion rate, not the three-month average (session conversion was 0.94% in Jan 2021 against 1.59% in Dec 2020, so the average would overstate the baseline and the power)
- [step 8] Run the README's "How to run it" steps on a fresh clone before the final README (they were written from this machine's setup and never run end to end)
- [step 8] Rebuild the dbt tables right before creating the cached exports for the app (the tables may have expired by then)
- [later] Partition `stg_events` by `event_date` if the project moves off the sandbox (not possible now: the sandbox's 60-day partition expiry would drop all 2020-21 partitions)
- [later] Add `cluster_by: event_name` to `stg_events` (would cut bytes scanned by funnel queries; the 1.4 GB table is cheap enough without it)
- [later] Add the params left out of `stg_events` if a question needs them: `coupon`, `payment_type`, `shipping_tier`, `promotion_name`, `link_*` (skipped as low value for funnel and experiment work)
- [later] Run `gcloud auth login` if the `bq` command line is wanted (it has no logged-in account; dbt and Python work through application-default credentials)
- [later] When regenerating requirements.txt, use `pip freeze | Out-File -Encoding ascii requirements.txt` (PowerShell's `>` writes UTF-16, which git treats as binary)

## Done or dropped

- [step 2] Decide how `is_session_engaged` rolls up to a session. Done in `int_sessions`: `is_engaged` is true if any event in the session has the flag true, otherwise false (320,096 of 360,129 sessions engaged).
- [step 2] Take session source/medium/campaign from the first non-null event in the session. Done in `int_sessions`: all three come from the earliest event that has any of them; 94,553 sessions have none and stay null.
- [step 3] Define a purchase as `event_name = 'purchase'`, not as a non-null `transaction_id`. Done: `int_sessions` counts purchase events by name and the marts inherit it; `dim_users` totals match raw (5,692 purchases, $362,165).
- [step 3] Check whether any mart needs item-level data. Dropped: none of `dim_users`, `fct_funnel` or `fct_cohort_retention` needs it, so no staging model for `items`.
- [step 3] State the limits of traffic source if a mart breaks down by it. Done: `fct_funnel` has no source breakdown; the `dim_users` and `int_sessions` column docs state the missing, self-referral and obfuscated values, and that first-touch source differs between events for about 15% of users.
- [step 3] Decide whether a funnel step requires the earlier steps in the same session. Done in `fct_funnel`: steps count in any order, as the Data scope section says; the docs state that about 46% of checkout sessions have no add_to_cart in the same session.
- [step 4] README setup section with gcloud login and the `maximum_bytes_billed` setting. Done: "How to run it" has the login step and an example profiles.yml with the 5 GB cap and a placeholder project id.
- [step 4] README: say that sandbox tables expire after 60 days. Done: one line at the end of "How to run it".
- [step 4] Replace or delete `ga4_analytics/README.md`. Done: deleted; the root README is the only one.
