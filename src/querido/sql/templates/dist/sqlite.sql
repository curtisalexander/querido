WITH bounds AS (
    SELECT
        MIN("{{ column }}") AS min_val,
        MAX("{{ column }}") AS max_val
    FROM {{ source }}
    WHERE "{{ column }}" IS NOT NULL
),
bins AS (
    SELECT
        CASE
        {% for i in range(buckets) %}
            WHEN "{{ column }}" >= (SELECT min_val + {{ i }} * (max_val - min_val) / {{ buckets }}.0 FROM bounds)
                 AND "{{ column }}" {{ '<' if not loop.last else '<=' }} (SELECT min_val + {{ i + 1 }} * (max_val - min_val) / {{ buckets }}.0 FROM bounds)
            THEN {{ i }}
        {% endfor %}
        END AS bucket
    FROM {{ source }}
    WHERE "{{ column }}" IS NOT NULL
)
SELECT
    bucket,
    ROUND((SELECT min_val FROM bounds) + bucket * ((SELECT max_val - min_val FROM bounds) / {{ buckets }}.0), 4) AS bucket_min,
    ROUND((SELECT min_val FROM bounds) + (bucket + 1) * ((SELECT max_val - min_val FROM bounds) / {{ buckets }}.0), 4) AS bucket_max,
    COUNT(*) AS count
FROM bins
WHERE bucket IS NOT NULL
GROUP BY bucket
ORDER BY bucket
