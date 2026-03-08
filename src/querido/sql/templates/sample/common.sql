(SELECT * FROM {{ table }} ORDER BY RANDOM() LIMIT {{ sample_size }}) AS _sample
