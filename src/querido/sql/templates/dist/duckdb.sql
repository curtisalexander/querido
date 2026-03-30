WITH stats AS (
    SELECT
        COUNT(*) AS total,
        COUNT_IF("{{ column }}" IS NULL) AS null_count,
        MIN("{{ column }}")::DOUBLE AS min_val,
        MAX("{{ column }}")::DOUBLE AS max_val
    FROM {{ source }}
),
binned AS (
    SELECT
        CASE
            WHEN s.max_val = s.min_val THEN 0
            ELSE LEAST(
                FLOOR(
                    ("{{ column }}"::DOUBLE - s.min_val)
                    / ((s.max_val - s.min_val) / {{ buckets }}.0)
                )::INTEGER,
                {{ buckets - 1 }}
            )
        END AS bucket
    FROM {{ source }}
    CROSS JOIN stats s
    WHERE "{{ column }}" IS NOT NULL
)
SELECT
    bucket,
    ROUND(s.min_val + bucket * ((s.max_val - s.min_val) / {{ buckets }}.0), 4) AS bucket_min,
    ROUND(s.min_val + (bucket + 1) * ((s.max_val - s.min_val) / {{ buckets }}.0), 4) AS bucket_max,
    COUNT(*) AS count,
    s.total AS total_rows,
    s.null_count AS null_count
FROM binned
CROSS JOIN stats s
GROUP BY bucket, s.min_val, s.max_val, s.total, s.null_count
ORDER BY bucket
