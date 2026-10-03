-- Purchase funnel: view_item > add_to_cart > begin_checkout > purchase.
-- One row per day and device category, counting the sessions that reached
-- each step.
--
-- The funnel is session-level and steps count in any order: a session counts
-- for a step if that event occurred in it, whether or not the earlier steps
-- did. This matters most for begin_checkout: almost half of checkout sessions
-- have no add_to_cart in the same session (the cart was filled earlier).
--
-- The table stores counts, not rates. To get a conversion rate over several
-- days or devices, sum the counts first and then divide. Averaging daily
-- rates would give the wrong answer.

select
    -- Primary key: one row per date and device category
    concat(cast(session_date as string), '-', device_category) as funnel_key,

    session_date,
    device_category,

    -- All sessions, whether or not they entered the funnel
    count(*) as sessions,

    -- Sessions in which each funnel step occurred
    countif(has_view_item) as view_item_sessions,
    countif(has_add_to_cart) as add_to_cart_sessions,
    countif(has_begin_checkout) as begin_checkout_sessions,
    countif(has_purchase) as purchase_sessions

from {{ ref('int_sessions') }}
group by session_date, device_category
