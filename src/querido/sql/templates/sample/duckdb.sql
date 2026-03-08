(SELECT * FROM {{ table }} USING SAMPLE {{ sample_size }}) AS _sample
