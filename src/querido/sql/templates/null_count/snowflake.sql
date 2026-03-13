SELECT
    COUNT(*) AS total,
    COUNT_IF("{{ column }}" IS NULL) AS null_count
FROM {{ table }}
