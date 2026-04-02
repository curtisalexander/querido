insert into {{ table }} (
{% for col in columns %}
    {{ col.name }}{% if not loop.last %},
{% endif %}
{% endfor %}

) values (
{% for col in columns %}
    :{{ col.name }}{% if not loop.last %},
{% endif %}
{% endfor %}

);
