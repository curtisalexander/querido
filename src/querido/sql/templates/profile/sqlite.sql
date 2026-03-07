{% for col in columns %}
SELECT
    '{{ col.name }}' AS column_name,
    '{{ col.type }}' AS column_type,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN "{{ col.name }}" IS NULL THEN 1 ELSE 0 END) AS null_count,
    ROUND(100.0 * SUM(CASE WHEN "{{ col.name }}" IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS null_pct,
    COUNT(DISTINCT "{{ col.name }}") AS distinct_count,
{% if col.numeric %}
    MIN("{{ col.name }}") AS min_val,
    MAX("{{ col.name }}") AS max_val,
    ROUND(AVG("{{ col.name }}"), 4) AS mean_val,
    NULL AS median_val,
    NULL AS stddev_val,
    NULL AS min_length,
    NULL AS max_length
{% else %}
    NULL AS min_val,
    NULL AS max_val,
    NULL AS mean_val,
    NULL AS median_val,
    NULL AS stddev_val,
    MIN(LENGTH("{{ col.name }}")) AS min_length,
    MAX(LENGTH("{{ col.name }}")) AS max_length
{% endif %}
FROM {{ source }}{% if not loop.last %}
UNION ALL
{% endif %}
{% endfor %}
