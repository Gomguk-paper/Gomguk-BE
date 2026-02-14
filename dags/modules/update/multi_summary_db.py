import logging
from airflow.providers.postgres.hooks.postgres import PostgresHook


def get_registered_styles():
    from modules.update.multi_summary_generator import load_multi_summary_config

    config = load_multi_summary_config()
    profiles = config.get("prompt_profiles", [])
    return [p.get("style") for p in profiles if p.get("style")]


def get_papers_missing_styles(styles, limit=None):
    if not styles:
        return []

    hook = PostgresHook(postgres_conn_id="db")
    query = """
        SELECT
            p.id AS paper_id,
            p.title,
            p.short AS abstract
        FROM public.papers p
        LEFT JOIN public.paper_summaries ps
            ON ps.paper_id = p.id
            AND ps.style::text = ANY(%s)
        WHERE p.short IS NOT NULL
        GROUP BY p.id, p.title, p.short, p.created_at
        HAVING COUNT(DISTINCT ps.style::text) < %s
        ORDER BY p.created_at DESC
    """
    params = [styles, len(styles)]

    if limit:
        query += " LIMIT %s"
        params.append(limit)

    with hook.get_conn() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    papers = [{"paper_id": r[0], "title": r[1], "abstract": r[2]} for r in rows]
    logging.info("Fetched %d papers missing prompt styles.", len(papers))
    return papers


def upsert_multi_prompt_summaries(summary_items):
    if not summary_items:
        logging.info("No summary items to upsert.")
        return

    hook = PostgresHook(postgres_conn_id="db")
    success_count = 0

    with hook.get_conn() as conn:
        with conn.cursor() as cursor:
            for item in summary_items:
                paper_id = item.get("paper_id")
                style = item.get("style")
                summary = item.get("summary", {})
                hook_text = summary.get("hook", "")
                points = summary.get("points", [])
                detail = summary.get("detail", "")

                if not paper_id or not style:
                    continue

                try:
                    cursor.execute(
                        """
                        SELECT id
                        FROM public.paper_summaries
                        WHERE paper_id = %s AND style::text = %s
                        """,
                        (paper_id, style),
                    )
                    row = cursor.fetchone()

                    if row:
                        cursor.execute(
                            """
                            UPDATE public.paper_summaries
                            SET hook = %s, points = %s, detailed = %s
                            WHERE id = %s
                            """,
                            (hook_text, points, detail, row[0]),
                        )
                    else:
                        cursor.execute(
                            """
                            INSERT INTO public.paper_summaries
                            (paper_id, hook, points, detailed, style, created_at)
                            VALUES (%s, %s, %s, %s, %s::summary_style, NOW())
                            """,
                            (paper_id, hook_text, points, detail, style),
                        )

                    conn.commit()
                    success_count += 1
                except Exception as e:
                    conn.rollback()
                    logging.error(
                        "Failed upsert for paper_id=%s style=%s error=%s",
                        paper_id,
                        style,
                        e,
                    )

    logging.info("Upserted %d prompt-based summaries.", success_count)
