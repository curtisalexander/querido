INSERT INTO {{ table }} (
{% for col in columns %}
    {{ col.name }}{% if not loop.last %},
{% endif %}
{% endfor %}

) VALUES (
{% for col in columns %}
    :{{ col.name }}{% if not loop.last %},
{% endif %}
{% endfor %}

);
