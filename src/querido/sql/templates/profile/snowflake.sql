select
    count(*) as total_rows
{% for col in columns %}
    , count_if("{{ col.name }}" is null) as "{{ col.name }}__null_count"
    , round(100.0 * count_if("{{ col.name }}" is null) / nullif(count(*), 0), 2) as "{{ col.name }}__null_pct"
{% if approx %}
    , approx_count_distinct("{{ col.name }}") as "{{ col.name }}__distinct_count"
{% else %}
    , count(distinct "{{ col.name }}") as "{{ col.name }}__distinct_count"
{% endif %}
{% if col.numeric %}
    , min("{{ col.name }}") as "{{ col.name }}__min_val"
    , max("{{ col.name }}") as "{{ col.name }}__max_val"
    , round(avg("{{ col.name }}"::double), 4) as "{{ col.name }}__mean_val"
{% if approx %}
    , approx_percentile("{{ col.name }}"::double, 0.5) as "{{ col.name }}__median_val"
{% else %}
    , median("{{ col.name }}"::double) as "{{ col.name }}__median_val"
{% endif %}
    , round(stddev("{{ col.name }}"::double), 4) as "{{ col.name }}__stddev_val"
{% else %}
    , min(length("{{ col.name }}")) as "{{ col.name }}__min_length"
    , max(length("{{ col.name }}")) as "{{ col.name }}__max_length"
{% endif %}
{% endfor %}
from {{ source }}
