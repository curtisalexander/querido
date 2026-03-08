WITH bounds AS (
    SELECT
        MIN("{{ column }}") AS min_val,
        MAX("{{ column }}") AS max_val
    FROM {{ source }}
    WHERE "{{ column }}" IS NOT NULL
),
binned AS (
    SELECT
        LEAST(
            WIDTH_BUCKET(
                "{{ column }}"::DOUBLE,
                (SELECT min_val::DOUBLE FROM bounds),
                (SELECT max_val::DOUBLE + 1e-9 FROM bounds),
                {{ buckets }}
            ),
            {{ buckets }}
        ) AS bucket
    FROM {{ source }}
    WHERE "{{ column }}" IS NOT NULL
)
SELECT
    bucket,
    ROUND((SELECT min_val FROM bounds) + (bucket - 1) * ((SELECT max_val - min_val FROM bounds) / {{ buckets }}.0), 4) AS bucket_min,
    ROUND((SELECT min_val FROM bounds) + bucket * ((SELECT max_val - min_val FROM bounds) / {{ buckets }}.0), 4) AS bucket_max,
    COUNT(*) AS count
FROM binned
GROUP BY bucket
ORDER BY bucket
