CREATE OR REPLACE PROCEDURE process_{{ table_name | lower }}()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
BEGIN
    LET row_count := (SELECT COUNT(*) FROM {{ table }});

    -- Example: insert processed rows into a target table
    -- INSERT INTO {{ table_name }}_processed
    -- SELECT
{% for col in columns %}
    --     {{ col.name }}{% if not loop.last %},
{% endif %}
{% endfor %}

    -- FROM {{ table }};

    RETURN 'Processed ' || :row_count || ' rows from {{ table }}';
END;
$$;

-- Example usage:
-- CALL process_{{ table_name | lower }}();
