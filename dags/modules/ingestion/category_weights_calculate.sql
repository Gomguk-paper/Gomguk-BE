-- 1. 기존 가중치 데이터 초기화 (항상 최신 통계로 덮어쓰기)
TRUNCATE TABLE category_weights;

-- 2. 로그 평균(Log-Average) 기반 가중치 계산 및 적재
INSERT INTO category_weights (category_code, paper_count, avg_citation, weight)
WITH split_data AS (
    -- JSONB 카테고리 풀기
    SELECT
        jsonb_array_elements_text(categories) as cat,
        COALESCE(influential_citation_count, 0) as cit
    FROM papers
    WHERE categories IS NOT NULL
      AND jsonb_typeof(categories) = 'array'
),
cat_stats AS (
    -- 카테고리별 로그 평균 산출 (LN(x+1))
    SELECT
        cat,
        COUNT(*) as cnt,
        AVG(LN(cit + 1)) as log_avg
    FROM split_data
    GROUP BY cat
    HAVING COUNT(*) >= 5 -- 표본 5개 이상만 신뢰
),
global_stat AS (
    -- 전체 논문 로그 평균 (기준점)
    SELECT AVG(LN(COALESCE(influential_citation_count, 0) + 1)) as global_log_avg
    FROM papers
)
SELECT
    s.cat,
    s.cnt,
    s.log_avg,
    -- [핵심] 가중치 계산 (Global Log Avg / Category Log Avg)
    -- 결과값은 0.5 ~ 2.0 사이로 제한 (Clamping)
    GREATEST(0.5,
        LEAST(2.0,
            (g.global_log_avg::numeric / GREATEST(s.log_avg, 0.01)::numeric)
        )
    )
FROM cat_stats s, global_stat g;
