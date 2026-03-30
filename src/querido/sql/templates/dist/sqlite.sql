WITH stats AS (
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN "{{ column }}" IS NULL THEN 1 ELSE 0 END) AS null_count,
        MIN("{{ column }}") AS min_val,
        MAX("{{ column }}") AS max_val
    FROM {{ source }}
),
bins AS (
    SELECT
        CASE
        {% for i in range(buckets) %}
            WHEN "{{ column }}" >= s.min_val + {{ i }} * (s.max_val - s.min_val) / {{ buckets }}.0
                 AND "{{ column }}" {{ '<' if not loop.last else '<=' }} s.min_val + {{ i + 1 }} * (s.max_val - s.min_val) / {{ buckets }}.0
            THEN {{ i }}
        {% endfor %}
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
FROM bins
CROSS JOIN stats s
WHERE bucket IS NOT NULL
GROUP BY bucket, s.min_val, s.max_val, s.total, s.null_count
ORDER BY bucket
