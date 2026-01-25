UPDATE papers p
SET citation_score = (
    -- 기본 점수: 로그 인용수 / 시간의 제곱근(SQRT)
    (LN(COALESCE(p.influential_citation_count, 0) + 1) /
     SQRT(GREATEST(1, EXTRACT(YEAR FROM NOW()) - EXTRACT(YEAR FROM p.published_at) + 8)))
    * -- 도메인 부스터: 해당 논문의 카테고리 가중치 평균
    -- category_weights 테이블 조인
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