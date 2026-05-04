from __future__ import annotations

from datetime import datetime, timedelta, timezone, date

from airflow import DAG
from airflow.decorators import task
from airflow.providers.postgres.hooks.postgres import PostgresHook


ACTIVE_EVENT_TYPES = ("login", "search", "view", "like", "save")
RETENTION_DAYS = (1, 7, 30)
FUNNEL_NAME = "login_view_save"
FUNNEL_STEPS = (
    (1, "login", "login"),
    (2, "view", "view"),
    (3, "save", "save"),
)


def resolve_target_date(dag_run=None) -> date:
    if dag_run and dag_run.conf and dag_run.conf.get("target_date"):
        return date.fromisoformat(dag_run.conf["target_date"])
    return (datetime.now(timezone.utc) - timedelta(days=1)).date()


with DAG(
    dag_id="stats_analytics_daily",
    start_date=datetime(2026, 5, 3),
    schedule="@daily",
    catchup=False,
    default_args={
        "owner": "airflow",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["analytics", "stats"],
) as dag:

    @task(task_id="update_daily_active_users")
    def update_daily_active_users_task(dag_run=None) -> str:
        target_date = resolve_target_date(dag_run)
        calculated_at = datetime.now(timezone.utc)
        hook = PostgresHook(postgres_conn_id="db")

        query = """
        WITH active_users AS (
            SELECT DISTINCT e.user_id
            FROM public.events e
            WHERE e.occurred_at::date = %(target_date)s
              AND e.event_type = ANY(%(active_event_types)s)
        )
        INSERT INTO public.daily_active_user_stats (
            stat_date,
            active_users,
            new_users,
            returning_users,
            calculated_at
        )
        SELECT
            %(target_date)s,
            COUNT(*)::int AS active_users,
            COUNT(*) FILTER (WHERE u.created_at::date = %(target_date)s)::int AS new_users,
            COUNT(*) FILTER (WHERE u.created_at::date < %(target_date)s)::int AS returning_users,
            %(calculated_at)s
        FROM active_users au
        JOIN public.users u ON u.id = au.user_id
        ON CONFLICT (stat_date) DO UPDATE
        SET
            active_users = EXCLUDED.active_users,
            new_users = EXCLUDED.new_users,
            returning_users = EXCLUDED.returning_users,
            calculated_at = EXCLUDED.calculated_at
        """

        hook.run(
            query,
            parameters={
                "target_date": target_date,
                "calculated_at": calculated_at,
                "active_event_types": list(ACTIVE_EVENT_TYPES),
            },
        )
        return target_date.isoformat()

    @task(task_id="update_retention_stats")
    def update_retention_stats_task(dag_run=None) -> str:
        target_date = resolve_target_date(dag_run)
        calculated_at = datetime.now(timezone.utc)
        hook = PostgresHook(postgres_conn_id="db")

        with hook.get_conn() as conn:
            with conn.cursor() as cursor:
                for retention_day in RETENTION_DAYS:
                    cohort_date = target_date - timedelta(days=retention_day)
                    cursor.execute(
                        """
                        WITH cohort_users AS (
                            SELECT u.id
                            FROM public.users u
                            WHERE u.created_at::date = %(cohort_date)s
                        ),
                        retained_users AS (
                            SELECT DISTINCT e.user_id
                            FROM public.events e
                            JOIN cohort_users cu ON cu.id = e.user_id
                            WHERE e.occurred_at::date = %(target_date)s
                              AND e.event_type = ANY(%(active_event_types)s)
                        )
                        INSERT INTO public.retention_stats (
                            cohort_date,
                            retention_day,
                            cohort_size,
                            retained_users,
                            retention_rate,
                            calculated_at
                        )
                        SELECT
                            %(cohort_date)s,
                            %(retention_day)s,
                            COUNT(cu.id)::int AS cohort_size,
                            COUNT(ru.user_id)::int AS retained_users,
                            CASE
                                WHEN COUNT(cu.id) = 0 THEN 0
                                ELSE ROUND(COUNT(ru.user_id)::numeric / COUNT(cu.id)::numeric, 4)
                            END AS retention_rate,
                            %(calculated_at)s
                        FROM cohort_users cu
                        LEFT JOIN retained_users ru ON ru.user_id = cu.id
                        ON CONFLICT (cohort_date, retention_day) DO UPDATE
                        SET
                            cohort_size = EXCLUDED.cohort_size,
                            retained_users = EXCLUDED.retained_users,
                            retention_rate = EXCLUDED.retention_rate,
                            calculated_at = EXCLUDED.calculated_at
                        """,
                        {
                            "cohort_date": cohort_date,
                            "retention_day": retention_day,
                            "target_date": target_date,
                            "calculated_at": calculated_at,
                            "active_event_types": list(ACTIVE_EVENT_TYPES),
                        },
                    )
            conn.commit()

        return target_date.isoformat()

    @task(task_id="update_funnel_stats")
    def update_funnel_stats_task(dag_run=None) -> str:
        target_date = resolve_target_date(dag_run)
        calculated_at = datetime.now(timezone.utc)
        hook = PostgresHook(postgres_conn_id="db")

        with hook.get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    WITH login_users AS (
                        SELECT DISTINCT e.user_id
                        FROM public.events e
                        WHERE e.occurred_at::date = %(target_date)s
                          AND e.event_type = 'login'
                    ),
                    view_users AS (
                        SELECT DISTINCT lu.user_id
                        FROM login_users lu
                        JOIN public.events e
                          ON e.user_id = lu.user_id
                        WHERE e.occurred_at::date = %(target_date)s
                          AND e.event_type = 'view'
                    ),
                    save_users AS (
                        SELECT DISTINCT vu.user_id
                        FROM view_users vu
                        JOIN public.events e
                          ON e.user_id = vu.user_id
                        WHERE e.occurred_at::date = %(target_date)s
                          AND e.event_type = 'save'
                    )
                    SELECT
                        (SELECT COUNT(*)::int FROM login_users),
                        (SELECT COUNT(*)::int FROM view_users),
                        (SELECT COUNT(*)::int FROM save_users)
                    """,
                    {"target_date": target_date},
                )
                login_users, view_users, save_users = cursor.fetchone()

                base_count = login_users or 0
                step_counts = {
                    "login": base_count,
                    "view": view_users or 0,
                    "save": save_users or 0,
                }

                for step_order, step_name, event_type in FUNNEL_STEPS:
                    user_count = step_counts[event_type]
                    conversion_rate = round(user_count / base_count, 4) if base_count else 0
                    cursor.execute(
                        """
                        INSERT INTO public.funnel_stats (
                            stat_date,
                            funnel_name,
                            step_name,
                            step_order,
                            user_count,
                            conversion_rate,
                            calculated_at
                        )
                        VALUES (
                            %(target_date)s,
                            %(funnel_name)s,
                            %(step_name)s,
                            %(step_order)s,
                            %(user_count)s,
                            %(conversion_rate)s,
                            %(calculated_at)s
                        )
                        ON CONFLICT (stat_date, funnel_name, step_name) DO UPDATE
                        SET
                            step_order = EXCLUDED.step_order,
                            user_count = EXCLUDED.user_count,
                            conversion_rate = EXCLUDED.conversion_rate,
                            calculated_at = EXCLUDED.calculated_at
                        """,
                        {
                            "target_date": target_date,
                            "funnel_name": FUNNEL_NAME,
                            "step_name": step_name,
                            "step_order": step_order,
                            "user_count": user_count,
                            "conversion_rate": conversion_rate,
                            "calculated_at": calculated_at,
                        },
                    )
            conn.commit()

        return target_date.isoformat()

    update_daily_active_users_task() >> update_retention_stats_task() >> update_funnel_stats_task()
