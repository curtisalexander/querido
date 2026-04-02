create or replace task {{ table_name }}_task
    warehouse = '<WAREHOUSE>'
    schedule = 'USING CRON 0 9 * * * America/New_York'  -- daily at 9am ET
    comment = 'Task for {{ table }}'
as
    select
{% for col in columns %}
        {{ col.name }}{% if not loop.last %},
{% endif %}
{% endfor %}

    from {{ table }};

-- To activate: alter task {{ table_name }}_task resume;
-- To suspend: alter task {{ table_name }}_task suspend;
