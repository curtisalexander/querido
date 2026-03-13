SELECT
    COUNT(*) AS total_rows
{% for col in columns %}
    , SUM(CASE WHEN "{{ col.name }}" IS NULL THEN 1 ELSE 0 END) AS "{{ col.name }}__null_count"
    , ROUND(100.0 * SUM(CASE WHEN "{{ col.name }}" IS NULL THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS "{{ col.name }}__null_pct"
{% if approx %}
    , APPROX_COUNT_DISTINCT("{{ col.name }}") AS "{{ col.name }}__distinct_count"
{% else %}
    , COUNT(DISTINCT "{{ col.name }}") AS "{{ col.name }}__distinct_count"
{% endif %}
{% if col.numeric %}
    , MIN("{{ col.name }}") AS "{{ col.name }}__min_val"
    , MAX("{{ col.name }}") AS "{{ col.name }}__max_val"
    , ROUND(AVG("{{ col.name }}"), 4) AS "{{ col.name }}__mean_val"
    , MEDIAN("{{ col.name }}") AS "{{ col.name }}__median_val"
    , ROUND(STDDEV("{{ col.name }}"), 4) AS "{{ col.name }}__stddev_val"
{% else %}
    , MIN(LENGTH("{{ col.name }}")) AS "{{ col.name }}__min_length"
    , MAX(LENGTH("{{ col.name }}")) AS "{{ col.name }}__max_length"
{% endif %}
{% endfor %}
FROM {{ source }}
