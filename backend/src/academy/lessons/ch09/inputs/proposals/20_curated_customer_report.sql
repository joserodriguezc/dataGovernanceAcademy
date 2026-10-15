-- Propuesta de cambio de Marketing: un informe de clientes con sus compras en tienda.
-- Se revisa con `review` antes de incorporarlo al warehouse (ver el README del capítulo 9).

CREATE OR REPLACE TABLE curated.customer_report AS
SELECT
    c.*,
    s.amount AS last_amount,
    s.sale_ts AS lastSale
FROM raw.crm_customers AS c
JOIN staging.stg_pos_loyalty_cards AS l ON l.phone = c.phone
JOIN staging.stg_pos_sales AS s ON s.card_id = l.card_id;
