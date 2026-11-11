-- BCI-007 · 报告输出表（可重复执行，由 user_insight_loader 执行）
-- 说明：只维护 bci.report / bci.report_version，不改动 archive* 与既有业务表。
-- 口径（用户 2026-11-11 确认）：一个目标车型一份报告；子版本 v1.0 → v1.1 → v1.2；旧多车型报告转 legacy 只读。

CREATE TABLE IF NOT EXISTS bci.report (
    report_id    uuid PRIMARY KEY,
    title        text NOT NULL,
    model_keys   jsonb NOT NULL,
    sample_scope jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by   text NOT NULL DEFAULT 'web',
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- 一车一份：model_key 为唯一业务键；legacy 标记历史上偏离原型的多车型报告。
ALTER TABLE bci.report ADD COLUMN IF NOT EXISTS model_key text;
ALTER TABLE bci.report ADD COLUMN IF NOT EXISTS legacy boolean NOT NULL DEFAULT false;

UPDATE bci.report
   SET model_key = model_keys ->> 0
 WHERE model_key IS NULL;

UPDATE bci.report
   SET legacy = true
 WHERE coalesce(jsonb_array_length(model_keys), 0) > 1;

CREATE INDEX IF NOT EXISTS idx_report_model_key
    ON bci.report (model_key, created_at DESC);

CREATE TABLE IF NOT EXISTS bci.report_version (
    report_version_id uuid PRIMARY KEY,
    report_id         uuid NOT NULL REFERENCES bci.report(report_id) ON DELETE CASCADE,
    version_no        integer NOT NULL,
    content           jsonb NOT NULL,
    html              text NOT NULL,
    data_fingerprint  char(64) NOT NULL,
    source_snapshot   jsonb NOT NULL DEFAULT '{}'::jsonb,
    status            text NOT NULL DEFAULT 'valid',
    stale_reason      text,
    generated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT report_version_status_check CHECK (status IN ('valid', 'stale')),
    CONSTRAINT report_version_no_unique UNIQUE (report_id, version_no)
);

-- 子版本：version_label 展示与唯一键，parent_version_id 串版本线，patch 记录受控改稿指令。
ALTER TABLE bci.report_version ADD COLUMN IF NOT EXISTS version_label text;
ALTER TABLE bci.report_version ADD COLUMN IF NOT EXISTS parent_version_id uuid;
ALTER TABLE bci.report_version ADD COLUMN IF NOT EXISTS revision_kind text NOT NULL DEFAULT 'generate';
ALTER TABLE bci.report_version ADD COLUMN IF NOT EXISTS patch jsonb NOT NULL DEFAULT '{}'::jsonb;

DO $$
BEGIN
    ALTER TABLE bci.report_version
        ADD CONSTRAINT report_version_parent_fk
        FOREIGN KEY (parent_version_id) REFERENCES bci.report_version(report_version_id);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

UPDATE bci.report_version
   SET version_label = 'v' || version_no || '.0'
 WHERE version_label IS NULL;

ALTER TABLE bci.report_version ALTER COLUMN version_label SET DEFAULT 'v1.0';
ALTER TABLE bci.report_version ALTER COLUMN version_label SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_report_version_label
    ON bci.report_version (report_id, version_label);

CREATE INDEX IF NOT EXISTS idx_report_version_report
    ON bci.report_version (report_id, version_no DESC);

CREATE INDEX IF NOT EXISTS idx_report_version_fingerprint
    ON bci.report_version (data_fingerprint);
