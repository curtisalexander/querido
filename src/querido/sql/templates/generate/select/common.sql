select
{% for col in columns %}
    {{ col.name }}{% if not loop.last %},
{% endif %}
{% endfor %}

from {{ table }};
