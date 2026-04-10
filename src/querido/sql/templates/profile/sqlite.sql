select
    count(*) as total_rows
{% for col in columns %}
    , sum(case when "{{ col.name }}" is null then 1 else 0 end) as "{{ col.name }}__null_count"
    , round(100.0 * sum(case when "{{ col.name }}" is null then 1 else 0 end) / nullif(count(*), 0), 2) as "{{ col.name }}__null_pct"
    , count(distinct "{{ col.name }}") as "{{ col.name }}__distinct_count"
{% if not quick %}
{% if col.numeric %}
    , min("{{ col.name }}") as "{{ col.name }}__min_val"
    , max("{{ col.name }}") as "{{ col.name }}__max_val"
    , round(avg("{{ col.name }}"), 4) as "{{ col.name }}__mean_val"
{% else %}
    , min(length("{{ col.name }}")) as "{{ col.name }}__min_length"
    , max(length("{{ col.name }}")) as "{{ col.name }}__max_length"
{% endif %}
{% endif %}
{% endfor %}
from {{ source }}
