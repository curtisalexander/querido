SELECT
{% for col in columns %}
    {{ col.name }}{% if not loop.last %},
{% endif %}
{% endfor %}

FROM {{ table }};
