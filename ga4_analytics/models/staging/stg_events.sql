-- One row per GA4 event, with the nested event_params record flattened into
-- ordinary columns. Built as a table (see dbt_project.yml) so downstream models
-- never rescan the raw data.
--
-- How the event_params lines work: event_params is an array of key/value pairs
-- stored inside each event row. unnest() turns that one row's array into a small
-- table, the where clause picks one key, and the parentheses make it a scalar
-- subquery (a query that returns a single value). Each key appears at most once
-- per event, so the subquery never returns more than one row.
--
-- Each value sits in one of several typed slots (string_value, int_value, ...).
-- Which slot each key uses was checked by profiling the raw data.

with flattened as (

    select
        -- Raw columns needed to build the keys in the final select
        user_pseudo_id,
        event_name,
        event_timestamp as event_timestamp_micros,

        -- Dates and times. Raw event_date is a string like '20210131' and raw
        -- timestamps are microseconds since 1970 (UTC).
        parse_date('%Y%m%d', event_date) as event_date,
        timestamp_micros(event_timestamp) as event_at,
        timestamp_micros(user_first_touch_timestamp) as user_first_touch_at,

        -- Session params (present on every event)
        (select value.int_value from unnest(event_params) where key = 'ga_session_id') as ga_session_id,
        (select value.int_value from unnest(event_params) where key = 'ga_session_number') as ga_session_number,

        -- Page params
        (select value.string_value from unnest(event_params) where key = 'page_location') as page_location,
        (select value.string_value from unnest(event_params) where key = 'page_title') as page_title,
        (select value.string_value from unnest(event_params) where key = 'page_referrer') as page_referrer,

        -- Engagement params.
        -- session_engaged is stored as a string on most events and as an int on
        -- the rest, so read both slots. Null when the event has no such param.
        (
            select coalesce(value.string_value, cast(value.int_value as string))
            from unnest(event_params)
            where key = 'session_engaged'
        ) = '1' as is_session_engaged,
        (select value.int_value from unnest(event_params) where key = 'engagement_time_msec') as engagement_time_msec,
        -- Only on scroll events
        (select value.int_value from unnest(event_params) where key = 'percent_scrolled') as percent_scrolled,
        -- Only on page_view events: true for the first page view of a session
        (select value.int_value from unnest(event_params) where key = 'entrances') = 1 as is_entrance,

        -- Traffic source of the event's session (only on some events)
        (select value.string_value from unnest(event_params) where key = 'source') as event_source,
        (select value.string_value from unnest(event_params) where key = 'medium') as event_medium,
        (select value.string_value from unnest(event_params) where key = 'campaign') as event_campaign,

        -- Traffic source that first brought the user (same on all of a user's events)
        traffic_source.source as first_touch_source,
        traffic_source.medium as first_touch_medium,
        traffic_source.name as first_touch_campaign,

        -- Device and location
        device.category as device_category,
        device.operating_system as device_os,
        device.web_info.browser as browser,
        geo.country as country,

        -- Ecommerce. The raw transaction_id is the text '(not set)' on events
        -- that have no transaction, so turn that into null.
        nullif(ecommerce.transaction_id, '(not set)') as transaction_id,
        ecommerce.purchase_revenue_in_usd as purchase_revenue_usd,
        ecommerce.total_item_quantity as total_item_quantity

    from {{ source('ga4', 'events') }}
    -- _table_suffix is the date part of each daily table name (events_20210131).
    -- Filtering on it limits which daily tables BigQuery scans.
    where _table_suffix between '{{ var("ga4_start_date") }}' and '{{ var("ga4_end_date") }}'

)

select
    -- Primary key. GA4 has no event id, but user + timestamp + event name is
    -- unique in this dataset (checked on all rows, and enforced by a dbt test).
    to_hex(md5(concat(
        user_pseudo_id, '-', cast(event_timestamp_micros as string), '-', event_name
    ))) as event_key,

    -- ga_session_id is only unique within a user, so a session is identified
    -- by the user and the session id together.
    concat(user_pseudo_id, '-', cast(ga_session_id as string)) as session_key,

    user_pseudo_id,
    event_name,
    event_date,
    event_at,

    ga_session_id,
    ga_session_number,

    page_location,
    page_title,
    page_referrer,

    is_session_engaged,
    engagement_time_msec,
    percent_scrolled,
    is_entrance,

    event_source,
    event_medium,
    event_campaign,

    first_touch_source,
    first_touch_medium,
    first_touch_campaign,
    user_first_touch_at,

    device_category,
    device_os,
    browser,
    country,

    transaction_id,
    purchase_revenue_usd,
    total_item_quantity

from flattened
