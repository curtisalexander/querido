create or replace temporary table tmp_{{ table_name }} (
{% for col in columns %}
    {{ col.name }} {{ col.type }}{% if not col.nullable %} not null{% endif %}{% if not loop.last %},
{% endif %}
{% endfor %}
);
{% for row in rows %}
insert into tmp_{{ table_name }} ({{ columns | map(attribute='name') | join(', ') }}) values ({{ row }});
{% endfor %}

-- Now query your scratch table:
-- select * from tmp_{{ table_name }};
