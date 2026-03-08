CREATE TABLE {{ table }} (
{% for col in columns %}
    {{ col.name }} {{ col.type }}{% if not col.nullable %} NOT NULL{% endif %}{% if col.default is not none %} DEFAULT {{ col.default }}{% endif %}{% if col.primary_key %} PRIMARY KEY{% endif %}{% if not loop.last %},
{% endif %}
{% endfor %}

);
