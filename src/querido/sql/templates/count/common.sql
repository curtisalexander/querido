select count(*) as cnt from {{ table | quote_ident }}
