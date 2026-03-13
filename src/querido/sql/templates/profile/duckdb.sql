{% for col in columns %}
SELECT
    '{{ col.name }}' AS column_name,
    '{{ col.type }}' AS column_type,
    COUNT(*) AS total_rows,
    COUNT_IF("{{ col.name }}" IS NULL)::BIGINT AS null_count,
    ROUND(100.0 * COUNT_IF("{{ col.name }}" IS NULL) / NULLIF(COUNT(*), 0), 2) AS null_pct,
    COUNT(DISTINCT "{{ col.name }}")::BIGINT AS distinct_count,
{% if col.numeric %}
    MIN("{{ col.name }}") AS min_val,
    MAX("{{ col.name }}") AS max_val,
    ROUND(AVG("{{ col.name }}")::DOUBLE, 4) AS mean_val,
    MEDIAN("{{ col.name }}") AS median_val,
    ROUND(STDDEV("{{ col.name }}")::DOUBLE, 4) AS stddev_val,
    NULL::BIGINT AS min_length,
    NULL::BIGINT AS max_length
{% else %}
    NULL AS min_val,
    NULL AS max_val,
    NULL AS mean_val,
    NULL AS median_val,
    NULL AS stddev_val,
    MIN(LENGTH("{{ col.name }}"::VARCHAR))::BIGINT AS min_length,
    MAX(LENGTH("{{ col.name }}"::VARCHAR))::BIGINT AS max_length
{% endif %}
FROM {{ source }}
{% if not loop.last %}
UNION ALL
{% endif %}
{% endfor %}
