-- Experiment metrics per user. One row per eligible user, with the variant,
-- the metrics for the experiment period (January 2021) and the same metrics
-- for the pre-period (December 2020), which serve as the CUPED covariate.
--
-- The data here is real and unmodified. The experiment is simulated: any
-- treatment effect is injected later, in Python.
--
-- A session belongs to the period in which it started (session_date).

with experiment_period as (

    select
        user_pseudo_id,
        count(*) as sessions,
        -- purchase_count counts events named 'purchase' (see int_sessions)
        sum(purchase_count) as purchases,
        sum(purchase_revenue_usd) as revenue_usd
    from {{ ref('int_sessions') }}
    where session_date between '{{ var("experiment_start_date") }}'
        and '{{ var("experiment_end_date") }}'
    group by user_pseudo_id

),

pre_period as (

    select
        user_pseudo_id,
        count(*) as sessions,
        sum(purchase_count) as purchases,
        sum(purchase_revenue_usd) as revenue_usd
    from {{ ref('int_sessions') }}
    where session_date between '{{ var("pre_period_start_date") }}'
        and '{{ var("pre_period_end_date") }}'
    group by user_pseudo_id

)

select
    assignments.user_pseudo_id,
    assignments.variant_id,
    assignments.variant,

    -- Experiment period
    experiment_period.sessions,
    -- Primary metric: 1 if the user purchased at least once, else 0.
    -- An integer, so its average is the conversion rate.
    if(experiment_period.purchases > 0, 1, 0) as converted,
    -- Secondary metric: its average is revenue per user
    experiment_period.revenue_usd,

    -- Pre-period. Users with no activity in it have no row in pre_period,
    -- so the left join returns nulls; coalesce turns those into 0.
    coalesce(pre_period.sessions, 0) as pre_sessions,
    if(coalesce(pre_period.purchases, 0) > 0, 1, 0) as pre_converted,
    coalesce(pre_period.revenue_usd, 0) as pre_revenue_usd,
    pre_period.user_pseudo_id is not null as has_pre_activity

from {{ ref('exp_assignments') }} as assignments
-- Inner join: every assigned user has a session in the experiment period,
-- because that is what made them eligible.
inner join experiment_period
    on assignments.user_pseudo_id = experiment_period.user_pseudo_id
-- Left join: most users have no activity in the pre-period.
left join pre_period
    on assignments.user_pseudo_id = pre_period.user_pseudo_id
