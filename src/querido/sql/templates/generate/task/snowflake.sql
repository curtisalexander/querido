CREATE OR REPLACE TASK {{ table }}_task
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

-- To activate: ALTER TASK {{ table }}_task RESUME;
-- To suspend: ALTER TASK {{ table }}_task SUSPEND;
