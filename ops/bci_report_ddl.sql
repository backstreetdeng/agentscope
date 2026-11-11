-- BCI-007 · 报告输出表（可重复执行，由 user_insight_loader 执行）
-- 说明：只新增 bci.report / bci.report_version，不改动 archive* 与既有业务表。

CREATE TABLE IF NOT EXISTS bci.report (
    report_id    uuid PRIMARY KEY,
    title        text NOT NULL,
    model_keys   jsonb NOT NULL,
    sample_scope jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by   text NOT NULL DEFAULT 'web',
    created_at   timestamptz NOT NULL DEFAULT now()
);

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

CREATE INDEX IF NOT EXISTS idx_report_version_report
    ON bci.report_version (report_id, version_no DESC);

CREATE INDEX IF NOT EXISTS idx_report_version_fingerprint
    ON bci.report_version (data_fingerprint);
