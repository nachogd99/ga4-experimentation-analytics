"""Loads the experiment data from BigQuery.

This is the only file that talks to BigQuery. It reads the tables built by
dbt and never writes anything back: the dbt tables always hold real,
unmodified data.

Authentication uses gcloud application-default credentials, the same as dbt.
"""

from google.cloud import bigquery

# Change these two to point at your own project and dbt dataset.
PROJECT = "ga4-experimentation-510510"
DATASET = "dbt_dev"

# Safety cap: BigQuery rejects a query that would scan more than this (1 GB).
MAXIMUM_BYTES_BILLED = 10**9


def _run_query(sql):
    """Run a query and return the result as a pandas DataFrame."""
    client = bigquery.Client(project=PROJECT)
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=MAXIMUM_BYTES_BILLED)
    return client.query(sql, job_config=job_config).to_dataframe()


def load_user_metrics():
    """Load exp_user_metrics: one row per eligible user.

    Columns: variant_id (0 control, 1 treatment), converted, revenue_usd and
    the pre-period columns used as CUPED covariates.
    """
    return _run_query(f"""
        select
            user_pseudo_id,
            variant_id,
            converted,
            revenue_usd,
            pre_sessions,
            pre_converted,
            pre_revenue_usd
        from `{PROJECT}.{DATASET}.exp_user_metrics`
    """)


def load_aa_totals(number_of_salts=1000):
    """Reassign every user once per salt and return the totals per salt.

    An A/A test needs many independent splits of the same users. Each salt
    gives one: the query applies the same hash formula as exp_assignments
    to every user, with salts 'aa_0001', 'aa_0002', ..., and counts the users
    and converters that land in each group.

    The hashing runs in BigQuery so that it is exactly the function used by
    exp_assignments. Only the totals come back; the statistics run in Python.

    Returns one row per salt: salt, users_control, users_treatment,
    conversions_control, conversions_treatment.
    """
    return _run_query(f"""
        with salts as (
            -- 'aa_0001', 'aa_0002', ... one per A/A test
            select format('aa_%04d', salt_number) as salt
            from unnest(generate_array(1, {int(number_of_salts)})) as salt_number
        ),

        assigned as (
            -- cross join: every user paired with every salt
            select
                salts.salt,
                metrics.converted,
                -- Same formula as exp_assignments: 0 control, 1 treatment
                mod(
                    abs(farm_fingerprint(concat(metrics.user_pseudo_id, salts.salt))),
                    2
                ) as variant_id
            from `{PROJECT}.{DATASET}.exp_user_metrics` as metrics
            cross join salts
        )

        select
            salt,
            countif(variant_id = 0) as users_control,
            countif(variant_id = 1) as users_treatment,
            sum(if(variant_id = 0, converted, 0)) as conversions_control,
            sum(if(variant_id = 1, converted, 0)) as conversions_treatment
        from assigned
        group by salt
        order by salt
    """)
