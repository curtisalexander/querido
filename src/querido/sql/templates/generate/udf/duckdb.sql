CREATE OR REPLACE FUNCTION my_udf(
{% for col in columns %}
    {{ col.name | lower }} {{ col.type }}{% if not loop.last %},
{% endif %}
{% endfor %}

) RETURNS VARCHAR
LANGUAGE SQL
AS $$
    SELECT CONCAT({{ columns | map(attribute='name') | map('lower') | join("::VARCHAR, ' ', ") }}::VARCHAR)
$$;

-- Example usage:
-- SELECT my_udf({{ columns | map(attribute='name') | join(', ') }}) FROM {{ table }};
