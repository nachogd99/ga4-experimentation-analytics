-- One row per session. A session is identified by session_key
-- (user_pseudo_id + ga_session_id), built in stg_events.
--
-- Rolls the events of each session up into session-level facts: when it
-- happened, how long it lasted, whether it was engaged, where it came from,
-- and which funnel steps occurred in it.

with session_totals as (

    select
        session_key,

        -- These columns have the same value on every event of a session
        -- (checked on the data), so any_value() just picks that value.
        any_value(user_pseudo_id) as user_pseudo_id,
        any_value(ga_session_id) as ga_session_id,
        any_value(ga_session_number) as ga_session_number,
        any_value(device_category) as device_category,
        any_value(device_os) as device_os,
        any_value(browser) as browser,
        any_value(country) as country,

        -- Timing. A few sessions run past midnight, so the session's date is
        -- the date of its first event.
        min(event_date) as session_date,
        min(event_at) as session_start_at,
        max(event_at) as session_end_at,
        timestamp_diff(max(event_at), min(event_at), second) as session_duration_seconds,

        -- Activity
        count(*) as event_count,
        countif(event_name = 'page_view') as page_view_count,

        -- The engaged flag starts false and turns true during the session, so
        -- the session is engaged if any of its events says so. logical_or()
        -- returns null when every value is null; treat that as not engaged.
        coalesce(logical_or(is_session_engaged), false) as is_engaged,
        coalesce(sum(engagement_time_msec), 0) as engagement_time_msec,

        -- Funnel steps: a step counts if the event occurred in the session.
        countif(event_name = 'view_item') > 0 as has_view_item,
        countif(event_name = 'add_to_cart') > 0 as has_add_to_cart,
        countif(event_name = 'begin_checkout') > 0 as has_begin_checkout,
        countif(event_name = 'purchase') > 0 as has_purchase,

        -- A purchase is an event named 'purchase'. transaction_id is not used
        -- because it is missing on some purchase events.
        countif(event_name = 'purchase') as purchase_count,
        coalesce(sum(purchase_revenue_usd), 0) as purchase_revenue_usd

    from {{ ref('stg_events') }}
    group by session_key

),

-- Traffic source of the session. Only some events carry source, medium and
-- campaign, and a session can carry more than one combination. Take all three
-- from the session's earliest event that has any of them, so they always come
-- from the same event.
session_sources as (

    select
        session_key,
        event_source as session_source,
        event_medium as session_medium,
        event_campaign as session_campaign
    from {{ ref('stg_events') }}
    where event_source is not null
        or event_medium is not null
        or event_campaign is not null
    -- Keep one row per session: the earliest. event_key breaks ties between
    -- events with the same timestamp so the result is the same on every run.
    qualify row_number() over (
        partition by session_key
        order by event_at, event_key
    ) = 1

)

select
    session_totals.session_key,
    session_totals.user_pseudo_id,
    session_totals.ga_session_id,
    session_totals.ga_session_number,

    session_totals.session_date,
    session_totals.session_start_at,
    session_totals.session_end_at,
    session_totals.session_duration_seconds,

    session_totals.event_count,
    session_totals.page_view_count,
    session_totals.is_engaged,
    session_totals.engagement_time_msec,

    -- Null for sessions where no event carries a traffic source
    session_sources.session_source,
    session_sources.session_medium,
    session_sources.session_campaign,

    session_totals.device_category,
    session_totals.device_os,
    session_totals.browser,
    session_totals.country,

    session_totals.has_view_item,
    session_totals.has_add_to_cart,
    session_totals.has_begin_checkout,
    session_totals.has_purchase,
    session_totals.purchase_count,
    session_totals.purchase_revenue_usd

from session_totals
-- Left join so sessions without a traffic source keep their row
left join session_sources
    on session_totals.session_key = session_sources.session_key
