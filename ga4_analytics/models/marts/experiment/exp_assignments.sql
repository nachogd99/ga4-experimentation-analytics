-- Assigns each eligible user to control or treatment. One row per user.
--
-- This is a simulated experiment on real traffic: the store did not run this
-- test. The assignment is real and reproducible, and this table changes no
-- data. Any treatment effect is injected later, in Python.

with eligible_users as (

    -- Eligible: at least one session that started in the experiment period
    select distinct user_pseudo_id
    from {{ ref('int_sessions') }}
    where session_date between '{{ var("experiment_start_date") }}'
        and '{{ var("experiment_end_date") }}'

),

assigned as (

    select
        user_pseudo_id,
        '{{ var("experiment_salt") }}' as experiment_salt,

        -- Hash-based assignment, read from the inside out:
        --   concat:           append the salt to the user id
        --   farm_fingerprint: hash that text into a large integer. It looks
        --                     random but is always the same for the same
        --                     input, so the assignment can be reproduced.
        --   abs:              the hash can be negative; make it positive
        --   mod(..., 2):      remainder after dividing by 2, so 0 or 1 with
        --                     equal chance
        mod(
            abs(farm_fingerprint(
                concat(user_pseudo_id, '{{ var("experiment_salt") }}')
            )),
            2
        ) as variant_id

    from eligible_users

)

select
    user_pseudo_id,
    experiment_salt,
    variant_id,
    if(variant_id = 0, 'control', 'treatment') as variant
from assigned
