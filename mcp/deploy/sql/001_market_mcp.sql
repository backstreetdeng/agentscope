BEGIN;

CREATE TABLE IF NOT EXISTS market_dataset_meta (
    domain text PRIMARY KEY CHECK (domain IN ('policy', 'rights')),
    generated_at timestamptz,
    as_of_date date,
    source_name text NOT NULL DEFAULT '',
    headers jsonb NOT NULL DEFAULT '[]'::jsonb,
    options jsonb NOT NULL DEFAULT '{}'::jsonb,
    extraction_method text NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS policy_record (
    record_id text PRIMARY KEY,
    monitor_date date,
    province text NOT NULL DEFAULT '',
    city text NOT NULL DEFAULT '',
    policy_name text NOT NULL DEFAULT '',
    policy_start_date date,
    policy_end_date date,
    source_url text NOT NULL DEFAULT '',
    payload jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS policy_record_region_idx ON policy_record (province, city);
CREATE INDEX IF NOT EXISTS policy_record_date_idx ON policy_record (monitor_date DESC);
CREATE INDEX IF NOT EXISTS policy_record_payload_gin ON policy_record USING gin (payload);

CREATE TABLE IF NOT EXISTS rights_record (
    record_id text PRIMARY KEY,
    monitor_date date,
    brand text NOT NULL DEFAULT '',
    model text NOT NULL DEFAULT '',
    activity_start_date date,
    activity_end_date date,
    activity_types text[] NOT NULL DEFAULT '{}',
    source_url text NOT NULL DEFAULT '',
    payload jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rights_record_brand_model_idx ON rights_record (brand, model);
CREATE INDEX IF NOT EXISTS rights_record_date_idx ON rights_record (monitor_date DESC);
CREATE INDEX IF NOT EXISTS rights_record_activity_types_gin ON rights_record USING gin (activity_types);
CREATE INDEX IF NOT EXISTS rights_record_payload_gin ON rights_record USING gin (payload);

COMMIT;

