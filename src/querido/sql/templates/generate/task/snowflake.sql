CREATE OR REPLACE TASK {{ table_name }}_task
    WAREHOUSE = '<WAREHOUSE>'
    SCHEDULE = 'USING CRON 0 9 * * * America/New_York'  -- daily at 9am ET
    COMMENT = 'Task for {{ table }}'
AS
    SELECT
{% for col in columns %}
        {{ col.name }}{% if not loop.last %},
{% endif %}
{% endfor %}

    FROM {{ table }};

-- To activate: ALTER TASK {{ table_name }}_task RESUME;
-- To suspend: ALTER TASK {{ table_name }}_task SUSPEND;
