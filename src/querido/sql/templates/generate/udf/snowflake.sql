create or replace function my_udf(
{% for col in columns %}
    {{ col.name | lower }} {{ col.type }}{% if not loop.last %},
{% endif %}
{% endfor %}

)
returns varchar
language sql
as
$$
    select concat({{ columns | map(attribute='name') | map('lower') | join("::varchar, ' ', ") }}::varchar)
$$;

-- Example usage:
-- select my_udf({{ columns | map(attribute='name') | join(', ') }}) from {{ table }};
