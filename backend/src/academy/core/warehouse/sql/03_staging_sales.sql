-- Staging de ventas en tienda (POS) y pedidos online (e-commerce).

CREATE OR REPLACE TABLE staging.stg_pos_sales AS
SELECT
    line_id,
    ticket_id,
    store_id,
    CAST(sale_ts AS TIMESTAMP) AS sale_ts,
    card_id,
    sku,
    CAST(quantity AS INTEGER) AS quantity,
    CAST(unit_price AS DOUBLE) AS unit_price,
    CAST(amount AS DOUBLE) AS amount
FROM raw.pos_sales;

CREATE OR REPLACE TABLE staging.stg_ecom_orders AS
SELECT
    order_line_id,
    order_id,
    ecom_user_id,
    CAST(order_ts AS TIMESTAMP) AS order_ts,
    sku,
    CAST(quantity AS INTEGER) AS quantity,
    CAST(unit_price AS DOUBLE) AS unit_price,
    CAST(quantity AS INTEGER) * CAST(unit_price AS DOUBLE) AS amount,
    shipping_postal_code,
    status
FROM raw.ecom_orders;
