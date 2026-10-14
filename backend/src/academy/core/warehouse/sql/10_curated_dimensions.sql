-- Dimensiones conformadas de tienda y producto.

CREATE OR REPLACE TABLE curated.dim_store AS
SELECT
    store_id,
    store_name,
    region,
    city,
    opened_at
FROM staging.stg_stores;

CREATE OR REPLACE TABLE curated.dim_product AS
SELECT
    p.sku,
    p.product_name,
    p.category,
    p.brand,
    p.unit_price AS list_price,
    p.unit_cost,
    p.supplier_id,
    s.supplier_name
FROM staging.stg_products AS p
LEFT JOIN staging.stg_suppliers AS s ON p.supplier_id = s.supplier_id;
