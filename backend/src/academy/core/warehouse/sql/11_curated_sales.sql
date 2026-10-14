-- Hechos de venta de todos los canales y la cifra diaria de ventas por canal.

CREATE OR REPLACE TABLE curated.fct_sales AS
SELECT
    'tienda' AS channel,
    s.line_id AS sale_line_id,
    s.ticket_id AS transaction_id,
    CAST(s.sale_ts AS DATE) AS sale_date,
    s.store_id,
    s.sku,
    p.category,
    s.quantity,
    s.amount AS net_amount,
    'completada' AS status
FROM staging.stg_pos_sales AS s
LEFT JOIN curated.dim_product AS p ON s.sku = p.sku
UNION ALL
SELECT
    'online' AS channel,
    o.order_line_id AS sale_line_id,
    o.order_id AS transaction_id,
    CAST(o.order_ts AS DATE) AS sale_date,
    NULL AS store_id,
    o.sku,
    p.category,
    o.quantity,
    o.amount AS net_amount,
    o.status
FROM staging.stg_ecom_orders AS o
LEFT JOIN curated.dim_product AS p ON o.sku = p.sku;

-- Cifra de ventas: excluye pedidos cancelados y devueltos.
CREATE OR REPLACE TABLE curated.agg_sales_daily_channel AS
SELECT
    sale_date,
    channel,
    sum(net_amount) AS revenue,
    count(DISTINCT transaction_id) AS transactions
FROM curated.fct_sales
WHERE status NOT IN ('cancelado', 'devuelto')
GROUP BY sale_date, channel;
