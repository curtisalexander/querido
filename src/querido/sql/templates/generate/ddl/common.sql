create table {{ table }} (
{% for col in columns %}
    {{ col.name }} {{ col.type }}{% if not col.nullable %} not null{% endif %}{% if col.default is not none %} default {{ col.default }}{% endif %}{% if col.primary_key %} primary key{% endif %}{% if not loop.last %},
{% endif %}
{% endfor %}
);
