SELECT
    CAST("{{ column }}" AS TEXT) AS value,
    COUNT(*) AS count
FROM {{ source }}
GROUP BY "{{ column }}"
ORDER BY count DESC
LIMIT {{ top }}
