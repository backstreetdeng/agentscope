-- BCI-004 · 用户洞察档案存储 · 4 张表与索引（以 user_insight_loader 执行）
-- 前置：ops/bci_archive_ddl_owner.sql 已执行，bci schema 已存在且属主为 user_insight_loader。
-- 可重复执行；字段定义与 competitor_insight/docs/archive-tab-design.md §2.1 一致。

CREATE TABLE IF NOT EXISTS bci.archive_run (
    run_id              uuid PRIMARY KEY,
    template_id         text NOT NULL,
    template_version    text NOT NULL,
    mode                text NOT NULL CHECK (mode IN ('single','selected','missing','all')),
    request_json        jsonb NOT NULL,
    status              text NOT NULL CHECK (status IN ('queued','running','completed','partial','failed','cancelled')),
    total               integer NOT NULL DEFAULT 0,
    done                integer NOT NULL DEFAULT 0,
    failed              integer NOT NULL DEFAULT 0,
    model               text,
    prompt_version      text,
    error_text          text,
    created_by          text NOT NULL DEFAULT 'local',
    created_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz
);

CREATE TABLE IF NOT EXISTS bci.archive_run_item (
    run_id              uuid NOT NULL REFERENCES bci.archive_run(run_id) ON DELETE CASCADE,
    interview_id        text NOT NULL,
    status              text NOT NULL CHECK (status IN ('queued','running','done','failed','skipped')),
    error_text          text,
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, interview_id)
);

CREATE TABLE IF NOT EXISTS bci.archive (
    archive_id          bigserial PRIMARY KEY,
    interview_id        text NOT NULL,
    template_id         text NOT NULL,
    template_version    text NOT NULL,
    template_snapshot   jsonb NOT NULL,
    run_id              uuid REFERENCES bci.archive_run(run_id) ON DELETE SET NULL,
    revision            integer NOT NULL DEFAULT 1,
    status              text NOT NULL CHECK (status IN ('ready','partial','failed','stale')),
    coverage_required   numeric(5,2) NOT NULL DEFAULT 0,
    model               text,
    prompt_version      text,
    generated_at        timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (interview_id, template_id, template_version, revision)
);

CREATE TABLE IF NOT EXISTS bci.archive_field (
    archive_id          bigint NOT NULL REFERENCES bci.archive(archive_id) ON DELETE CASCADE,
    dimension_id        text NOT NULL,
    group_id            text NOT NULL,
    fill_mode           text NOT NULL CHECK (fill_mode IN ('metadata','tag','derived','llm','none')),
    value_text          text,
    value_json          jsonb,
    source_ref          jsonb NOT NULL DEFAULT '{}'::jsonb,
    no_data_reason      text,
    confidence          numeric(4,3),
    evidence_refs       jsonb NOT NULL DEFAULT '[]'::jsonb,
    review_status       text NOT NULL DEFAULT 'auto'
                        CHECK (review_status IN ('auto','ok','suspect','missing')),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (archive_id, dimension_id)
);

CREATE INDEX IF NOT EXISTS idx_archive_lookup
    ON bci.archive (template_id, template_version, revision DESC, status);
CREATE INDEX IF NOT EXISTS idx_archive_interview
    ON bci.archive (interview_id);
CREATE INDEX IF NOT EXISTS idx_run_item_status
    ON bci.archive_run_item (run_id, status);
