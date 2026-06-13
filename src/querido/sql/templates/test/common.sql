select * from {{ table | quote_ident }} limit {{ limit }}
