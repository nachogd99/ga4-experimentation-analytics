-- One row per user (user_pseudo_id), summarising all of the user's sessions
-- between 2020-11-01 and 2021-01-31.

with user_totals as (

    select
        user_pseudo_id,

        min(session_date) as first_session_date,
        max(session_date) as last_session_date,

        -- ga_session_number counts a user's sessions from 1. If the lowest
        -- number we see is 1, we saw the user's first ever session. If not,
        -- the user already existed before the data starts.
        min(ga_session_number) = 1 as is_new_user,

        count(*) as session_count,
        countif(is_engaged) as engaged_session_count,

        -- A user's country never changes in this dataset (checked)
        any_value(country) as country,

        sum(purchase_count) as purchase_count,
        sum(purchase_revenue_usd) as total_revenue_usd

    from {{ ref('int_sessions') }}
    group by user_pseudo_id

),

-- Device of the user's first session. Some users appear with more than one
-- device category, so pick the one they first arrived on.
first_sessions as (

    select
        user_pseudo_id,
        device_category as first_device_category
    from {{ ref('int_sessions') }}
    -- Keep one row per user: the earliest session. session_key breaks ties
    -- so the result is the same on every run.
    qualify row_number() over (
        partition by user_pseudo_id
        order by session_start_at, session_key
    ) = 1

),

-- Traffic source that first brought the user. GA4 stores it on every event
-- and it should be the same on all of a user's events, but in this obfuscated
-- dataset it differs for about 15% of users. Take it from the user's
-- earliest event.
first_touches as (

    select
        user_pseudo_id,
        first_touch_source,
        first_touch_medium,
        first_touch_campaign
    from {{ ref('stg_events') }}
    qualify row_number() over (
        partition by user_pseudo_id
        order by event_at, event_key
    ) = 1

)

select
    user_totals.user_pseudo_id,

    user_totals.first_session_date,
    user_totals.last_session_date,
    -- Week the user was first seen, used to group users into cohorts.
    -- BigQuery weeks start on Sunday, and the data starts on a Sunday.
    date_trunc(user_totals.first_session_date, week) as cohort_week,
    user_totals.is_new_user,

    user_totals.session_count,
    user_totals.engaged_session_count,

    first_sessions.first_device_category,
    user_totals.country,

    first_touches.first_touch_source,
    first_touches.first_touch_medium,
    first_touches.first_touch_campaign,

    user_totals.purchase_count,
    user_totals.total_revenue_usd,
    user_totals.purchase_count > 0 as is_purchaser

from user_totals
-- Every user has a first session and a first event, so these joins match
-- exactly one row each. Left joins keep every user even if one did not.
left join first_sessions
    on user_totals.user_pseudo_id = first_sessions.user_pseudo_id
left join first_touches
    on user_totals.user_pseudo_id = first_touches.user_pseudo_id
