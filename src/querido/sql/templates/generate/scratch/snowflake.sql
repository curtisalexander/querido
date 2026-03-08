CREATE OR REPLACE TEMPORARY TABLE tmp_{{ table }} (
{% for col in columns %}
    {{ col.name }} {{ col.type }}{% if not col.nullable %} NOT NULL{% endif %}{% if not loop.last %},
{% endif %}
{% endfor %}
);
{% for row in rows %}
INSERT INTO tmp_{{ table }} ({{ columns | map(attribute='name') | join(', ') }}) VALUES ({{ row }});
{% endfor %}

-- Now query your scratch table:
-- SELECT * FROM tmp_{{ table }};
