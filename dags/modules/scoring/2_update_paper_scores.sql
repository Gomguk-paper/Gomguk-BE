UPDATE paper_pool p
SET citation_score = (
    (LN(COALESCE(p.influential_citation_count, 0) + 1) /
     SQRT(GREATEST(1, EXTRACT(YEAR FROM NOW()) - EXTRACT(YEAR FROM p.published_at) + 8)))
    *
    (
    COALESCE(
        (
            SELECT AVG(COALESCE(cw.weight, 1.0))
            FROM jsonb_array_elements_text(p.categories) AS p_cat_text
            LEFT JOIN category_weights cw ON p_cat_text = cw.category_code
        ),
        1.0
        )
    )
)
WHERE p.published_at IS NOT NULL;