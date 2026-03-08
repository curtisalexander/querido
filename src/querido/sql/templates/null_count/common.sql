SELECT
    COUNT(*) AS total,
    SUM(CASE WHEN "{{ column }}" IS NULL THEN 1 ELSE 0 END) AS null_count
FROM {{ table }}
