WITH top_k AS (
    SELECT APPROX_TOP_K("{{ column }}", {{ top }}) AS arr
    FROM {{ source }}
)
SELECT f.value:"value"::VARCHAR AS value,
       f.value:"count"::INTEGER AS count
FROM top_k, TABLE(FLATTEN(INPUT => top_k.arr)) f
ORDER BY count DESC
