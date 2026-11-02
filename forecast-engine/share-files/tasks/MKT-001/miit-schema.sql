-- MKT-001 工信部申报数据库表结构（建议稿 v0.1，2026-11-02）
-- 目标实例：192.168.3.146:5432 / vectordb（与 user_insight schema 同实例）
-- 执行账户：DDL 维护账户（用户持有）；建表后按文末授权 market_mcp_reader 只读
-- 设计原则：批次对账内建 / raw 留底防字段演进 / 唯一约束防重复导入

CREATE SCHEMA IF NOT EXISTS miit;

-- 1) 公告批次对账表
CREATE TABLE IF NOT EXISTS miit.batch (
    batch_no     text PRIMARY KEY,            -- 公告期数，如 '2026年第1批'
    publish_date date,                        -- 公告发布日期
    source_url   text,                        -- 公告页面来源
    record_count integer NOT NULL DEFAULT 0,  -- 该批次申报记录数（与 declaration 行数对账）
    file_sha256  char(64),                    -- 导入源文件 SHA256（对账与防篡改）
    imported_at  timestamptz NOT NULL DEFAULT now(),
    note         text
);

-- 2) 申报款型表（核心）
CREATE TABLE IF NOT EXISTS miit.declaration (
    id               bigserial PRIMARY KEY,
    batch_no         text NOT NULL REFERENCES miit.batch(batch_no),
    enterprise       text NOT NULL,           -- 生产企业
    brand            text,                    -- 品牌（从企业/车型名解析，允许空）
    model_name       text NOT NULL,           -- 车型名称（公告口径）
    model_code       text,                    -- 产品型号
    energy_type      text NOT NULL,           -- BEV / PHEV / EREV / ICE
    ev_range_km      numeric(6,1),            -- 纯电续驶里程（km）
    curb_weight_kg   numeric(7,1),            -- 整备质量（kg）
    energy_cons      numeric(6,2),            -- 能耗数值
    energy_cons_unit text,                    -- kWh/100km 或 L/100km
    battery_kwh      numeric(6,1),            -- 电池系统总能量（kWh）
    battery_type     text,                    -- 电池类型（磷酸铁锂/三元等）
    motor_power_kw   numeric(7,1),            -- 驱动电机峰值功率（kW）
    top_speed_kmh    numeric(5,1),            -- 最高车速（km/h）
    seat_count       smallint,                -- 核定载人数
    declared_at      date,                    -- 申报日期
    raw              jsonb,                   -- 原始行留底（新字段先入 raw，稳定后再提升为列）
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (batch_no, model_code, model_name)
);

CREATE INDEX IF NOT EXISTS idx_miit_decl_brand ON miit.declaration (brand, energy_type);
CREATE INDEX IF NOT EXISTS idx_miit_decl_range ON miit.declaration (energy_type, ev_range_km);
CREATE INDEX IF NOT EXISTS idx_miit_decl_batch ON miit.declaration (batch_no);
CREATE INDEX IF NOT EXISTS idx_miit_decl_raw   ON miit.declaration USING gin (raw);

-- 3) 只读授权（网页智能体经 market MCP 通道查询）
GRANT USAGE ON SCHEMA miit TO market_mcp_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA miit TO market_mcp_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA miit GRANT SELECT ON TABLES TO market_mcp_reader;

-- 使用说明：
-- 1. 首次导入 2026 全量数据若无批次号，batch_no 可先置 '2026-full' 占位，后续按真实批次拆分。
-- 2. 导入脚本（幂等、含 record_count/file_sha256 对账）由 TRAE 在 S4 交付。
-- 3. 字段演进策略：采集源新增字段先写入 raw，验证稳定后再提升为结构化列，避免频繁改表。
