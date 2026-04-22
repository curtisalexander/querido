select
    count(*) as _total_rows,
{% for col in columns %}
    count("{{ col.name }}") as "{{ col.name }}_non_nulls",
    min("{{ col.name }}") as "{{ col.name }}_min",
    max("{{ col.name }}") as "{{ col.name }}_max"{% if not loop.last %},{% endif %}
{% endfor %}
from {{ table }}
