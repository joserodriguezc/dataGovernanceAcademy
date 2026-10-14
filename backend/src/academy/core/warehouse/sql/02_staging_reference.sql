-- Staging de tiendas, proveedores y productos del ERP.

CREATE OR REPLACE TABLE staging.stg_stores AS
SELECT
    store_id,
    store_name,
    region,
    city,
    CAST(opened_at AS DATE) AS opened_at
FROM raw.erp_stores;

CREATE OR REPLACE TABLE staging.stg_suppliers AS
SELECT
    supplier_id,
    supplier_name,
    tax_id,
    contact_name,
    lower(contact_email) AS contact_email,
    country
FROM raw.erp_suppliers;

CREATE OR REPLACE TABLE staging.stg_products AS
SELECT
    sku,
    product_name,
    category,
    brand,
    CAST(unit_price AS DOUBLE) AS unit_price,
    CAST(unit_cost AS DOUBLE) AS unit_cost,
    supplier_id
FROM raw.erp_products;
