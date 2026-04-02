create or replace procedure process_{{ table_name | lower }}()
returns varchar
language sql
as
$$
begin
    let row_count := (select count(*) from {{ table }});

    -- Example: insert processed rows into a target table
    -- insert into {{ table_name }}_processed
    -- select
{% for col in columns %}
    --     {{ col.name }}{% if not loop.last %},
{% endif %}
{% endfor %}

    -- from {{ table }};

    return 'Processed ' || :row_count || ' rows from {{ table }}';
end;
$$;

-- Example usage:
-- call process_{{ table_name | lower }}();
