(SELECT * FROM {{ table }} SAMPLE ({{ sample_size }} ROWS)) AS _sample
