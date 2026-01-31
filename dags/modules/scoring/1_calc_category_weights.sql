TRUNCATE TABLE category_weights;

INSERT INTO category_weights (category_code, paper_count, avg_citation, weight)
WITH global_stat AS (
    SELECT AVG(LN(COALESCE(influential_citation_count, 0) + 1)) as global_log_avg
    FROM papers
),
split_data AS (
    SELECT
        jsonb_array_elements_text(categories) as cat,
        COALESCE(influential_citation_count, 0) as cit
    FROM papers
    WHERE categories IS NOT NULL
      AND jsonb_typeof(categories) = 'array'
),
cat_stats AS (
    SELECT
        s.cat,
        COUNT(*) as cnt,
        AVG(LN(s.cit + 1)) as real_log_avg,
        (
            (50 * (SELECT global_log_avg FROM global_stat)) + SUM(LN(s.cit + 1))
        ) / (50 + COUNT(*)) as smoothed_log_avg
    FROM split_data s
    GROUP BY s.cat
)
SELECT
    s.cat,
    s.cnt,
    s.smoothed_log_avg,
    GREATEST(0.5,
        LEAST(2.0,
            (g.global_log_avg::numeric / GREATEST(s.smoothed_log_avg, 0.01)::numeric)
        )
    )
FROM cat_stats s, global_stat g;