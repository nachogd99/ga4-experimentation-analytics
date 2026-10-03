-- Weekly cohort retention. Users are grouped by the week of their first
-- session (the cohort). For each cohort and each later week, the table says
-- how many of those users had a session that week.
--
-- One row per cohort_week and week_number. week_number 0 is the cohort's own
-- week, so its retention is always 100%.
--
-- The data ends on Sunday 2021-01-31. Weeks start on Sunday, so that day is a
-- week with a single day in it. It is left out, both as a cohort and as an
-- activity week, because a one-day week would look like a drop in retention.

with new_users as (

    select
        user_pseudo_id,
        cohort_week
    from {{ ref('dim_users') }}
    -- Only users whose first ever session is in the data. For users who
    -- already existed before 2020-11-01 we cannot know their real first week.
    where is_new_user
        and cohort_week < '2021-01-31'

),

-- Number of users in each cohort: the denominator of the retention rate
cohort_sizes as (

    select
        cohort_week,
        count(*) as cohort_size
    from new_users
    group by cohort_week

),

-- Number of the cohort's users with at least one session in each week
weekly_activity as (

    select
        new_users.cohort_week,
        -- Whole weeks between the week of the session and the cohort week.
        -- Both are Sundays, so this is 0, 1, 2, ...
        date_diff(
            date_trunc(sessions.session_date, week),
            new_users.cohort_week,
            week
        ) as week_number,
        -- distinct: a user with several sessions in a week counts once
        count(distinct new_users.user_pseudo_id) as active_users
    from new_users
    inner join {{ ref('int_sessions') }} as sessions
        on new_users.user_pseudo_id = sessions.user_pseudo_id
    where sessions.session_date < '2021-01-31'
    group by 1, 2

)

select
    -- Primary key: one row per cohort and week number
    concat(
        cast(weekly_activity.cohort_week as string), '-',
        cast(weekly_activity.week_number as string)
    ) as cohort_retention_key,

    weekly_activity.cohort_week,
    weekly_activity.week_number,
    cohort_sizes.cohort_size,
    weekly_activity.active_users,
    weekly_activity.active_users / cohort_sizes.cohort_size as retention_rate

from weekly_activity
inner join cohort_sizes
    on weekly_activity.cohort_week = cohort_sizes.cohort_week
