import json
from airflow.providers.postgres.hooks.postgres import PostgresHook
from psycopg2.extras import RealDictCursor


def get_pending_papers_from_db(limit=None):
    """
    업로드 대상 논문을 DB에서 조회하여 반환합니다.
    조건: paper_evaluation_log(is_recommended=true) AND NOT IN papers
    """
    hook = PostgresHook(postgres_conn_id='db')

    sql_query = """
        SELECT 
            pp.id as pool_id,
            pp.title,
            pp.pdf_href,
            pp.authors,
            pp.summary as abstract,
            pp.published_at
        FROM public.paper_pool pp
        JOIN public.paper_evaluation_log pel ON pp.id = pel.paper_id
        WHERE pel.is_recommended = true
          AND NOT EXISTS (
              SELECT 1 
              FROM public.papers p 
              WHERE p.paper_pool_id = pp.id
          )
        ORDER BY pp.published_at DESC
    """

    if limit:
        sql_query += f" LIMIT {limit}"

    results = []

    with hook.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql_query)
            rows = cursor.fetchall()

            for row in rows:
                paper_data = {
                    "pool_id": row['pool_id'],
                    "title": row['title'],
                    "pdf_url": row['pdf_href'],
                    "authors": row['authors'] if row['authors'] else [],
                    "abstract": row['abstract'],
                    "published_at": row['published_at'].isoformat() if row['published_at'] else None,
                }
                results.append(paper_data)

    print(f"INFO: Found {len(results)} pending papers.")
    return results