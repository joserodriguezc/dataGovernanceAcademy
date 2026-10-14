-- Staging de clientes: tipos correctos, emails en minúsculas y teléfonos con solo 9 dígitos.
-- No se corrigen defectos de negocio (eso es trabajo de calidad de datos, capítulo 8).

CREATE OR REPLACE TABLE staging.stg_crm_customers AS
SELECT
    customer_id,
    trim(first_name) AS first_name,
    trim(last_name) AS last_name,
    lower(trim(email)) AS email,
    right(regexp_replace(phone, '[^0-9]', '', 'g'), 9) AS phone,
    CAST(birth_date AS DATE) AS birth_date,
    postal_code,
    city,
    loyalty_tier,
    CAST(consent_marketing AS BOOLEAN) AS consent_marketing,
    CAST(created_at AS DATE) AS created_at
FROM raw.crm_customers;

CREATE OR REPLACE TABLE staging.stg_ecom_customers AS
SELECT
    ecom_user_id,
    trim(full_name) AS full_name,
    lower(trim(email)) AS email,
    right(regexp_replace(phone, '[^0-9]', '', 'g'), 9) AS phone,
    postal_code,
    city,
    -- El e-commerce mezcla fechas ISO y dd/mm/aaaa
    CAST(coalesce(
        try_strptime(created_at, '%Y-%m-%d'),
        try_strptime(created_at, '%d/%m/%Y')
    ) AS DATE) AS created_at
FROM raw.ecom_customers;

CREATE OR REPLACE TABLE staging.stg_pos_loyalty_cards AS
SELECT
    card_id,
    trim(holder_name) AS holder_name,
    right(regexp_replace(phone, '[^0-9]', '', 'g'), 9) AS phone,
    postal_code,
    home_store_id
FROM raw.pos_loyalty_cards;
