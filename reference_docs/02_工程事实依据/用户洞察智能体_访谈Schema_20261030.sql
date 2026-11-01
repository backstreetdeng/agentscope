-- 用户洞察智能体：真实访谈证据检索最小 schema
-- 目标库：PostgreSQL 12 + pgvector 0.7.x
-- 约束：独立 schema，不复用/覆盖现有 public.documents、public.chunks

CREATE SCHEMA IF NOT EXISTS user_insight;

CREATE EXTENSION IF NOT EXISTS vector;
-- 可选：启用后才使用 trigram 关键词检索；第一阶段可只用向量 + 结构化筛选 + reranker。
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 一个受访者的一次访谈。API 默认只暴露 respondent_code，不返回姓名。
CREATE TABLE IF NOT EXISTS user_insight.interview (
    interview_id        text PRIMARY KEY,                 -- 如 R001
    project_id          text NOT NULL DEFAULT '2025H2-depth-interview',
    respondent_code     text NOT NULL UNIQUE,             -- 对外稳定编号，如 R001
    source_label        text NOT NULL,                    -- 内部溯源标签，不返回给模型
    city                text,
    vehicle_model       text,
    purchase_type       text,
    source_version      text NOT NULL,
    transcript_uri      text,
    consent_scope       text NOT NULL DEFAULT 'internal_research_only',
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- 85 题题源。题文在 answer 中另存快照，避免题源修订影响历史证据。
CREATE TABLE IF NOT EXISTS user_insight.question (
    question_id         integer PRIMARY KEY CHECK (question_id BETWEEN 1 AND 85),
    category            text NOT NULL DEFAULT '',
    section             text NOT NULL DEFAULT '',
    priority            text NOT NULL DEFAULT '',
    question_text       text NOT NULL
);

-- 一人一问一条，保留标准答案与可检索向量。
CREATE TABLE IF NOT EXISTS user_insight.answer (
    answer_id           text PRIMARY KEY,                 -- A-R001-Q001
    interview_id        text NOT NULL REFERENCES user_insight.interview(interview_id) ON DELETE CASCADE,
    question_id         integer NOT NULL REFERENCES user_insight.question(question_id),
    question_text       text NOT NULL,
    answer_text         text NOT NULL,
    confidence          text,
    unanswered_items    jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence_ranges     jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_format       text NOT NULL,                    -- answer_json / answer_docx
    source_uri          text NOT NULL,
    time_available      boolean NOT NULL DEFAULT false,
    embedding           vector(1024),
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (interview_id, question_id)
);

-- 可引用的最小证据单元。秒级与段落级用 time_precision 区分。
CREATE TABLE IF NOT EXISTS user_insight.evidence (
    evidence_id         text PRIMARY KEY,
    answer_id           text NOT NULL REFERENCES user_insight.answer(answer_id) ON DELETE CASCADE,
    interview_id        text NOT NULL REFERENCES user_insight.interview(interview_id) ON DELETE CASCADE,
    question_id         integer NOT NULL,
    start_sec           numeric(12,3),
    end_sec             numeric(12,3),
    time_precision      text NOT NULL CHECK (time_precision IN ('second', 'paragraph', 'none')),
    speaker_label       text,
    quote_text          text NOT NULL,
    block_index         integer NOT NULL DEFAULT 0,
    segment_index       integer NOT NULL DEFAULT 0,
    source_locator      jsonb NOT NULL DEFAULT '{}'::jsonb,
    checksum            char(64) NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CHECK (start_sec IS NULL OR end_sec IS NULL OR start_sec <= end_sec)
);

-- 已完成的 85 题标签。tag_value 是业务值，不是定量问卷比例。
CREATE TABLE IF NOT EXISTS user_insight.tag (
    tag_id              text PRIMARY KEY,
    interview_id        text NOT NULL REFERENCES user_insight.interview(interview_id) ON DELETE CASCADE,
    batch_code          text NOT NULL,
    content_group       text NOT NULL,
    tag_name            text NOT NULL,
    allowed_values      text,
    mapped_question_ids integer[] NOT NULL DEFAULT '{}',
    tag_value           text NOT NULL,
    programmatic_evidence text,
    extraction_status   text,
    cross_question_review text,
    format_review       text,
    trust_status        text,
    confidence          text,
    source_uri          text NOT NULL,
    embedding           vector(1024),
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (interview_id, batch_code, tag_name)
);

-- 标签工作簿“证据明细”中的原始证据。一个标签可对应多行。
-- 与 answer.evidence 分开保存，避免把两套证据源强行合并后制造伪关联。
CREATE TABLE IF NOT EXISTS user_insight.tag_evidence (
    tag_evidence_id     text PRIMARY KEY,
    tag_id              text NOT NULL REFERENCES user_insight.tag(tag_id) ON DELETE CASCADE,
    question_id         integer,
    time_range_text     text,
    start_sec           numeric(12,3),
    end_sec             numeric(12,3),
    speaker_label       text,
    question_text       text,
    quote_text          text NOT NULL,
    source_row          integer,
    source_locator      jsonb NOT NULL DEFAULT '{}'::jsonb,
    checksum            char(64) NOT NULL,
    CHECK (start_sec IS NULL OR end_sec IS NULL OR start_sec <= end_sec)
);

-- 查询运行状态。第一阶段同步请求也可写一条，便于排障和证据回放。
CREATE TABLE IF NOT EXISTS user_insight.retrieval_run (
    run_id              text PRIMARY KEY,
    query_hash          text,               -- HMAC-SHA256，30 天后清理；不默认持久化完整提问
    query_summary       text,               -- 脱敏摘要，30 天后清理；无法可靠脱敏则不保存
    filters             jsonb NOT NULL DEFAULT '{}'::jsonb,
    status              text NOT NULL CHECK (status IN ('queued','retrieving','answering','completed','failed','cancelled')),
    evidence_ids        text[] NOT NULL DEFAULT '{}',
    retrieval_meta      jsonb NOT NULL DEFAULT '{}'::jsonb,
    answer_preview      text,
    error               jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    completed_at        timestamptz
);

CREATE INDEX IF NOT EXISTS idx_interview_filters
    ON user_insight.interview (city, vehicle_model, purchase_type);
CREATE INDEX IF NOT EXISTS idx_answer_question
    ON user_insight.answer (question_id);
CREATE INDEX IF NOT EXISTS idx_answer_interview
    ON user_insight.answer (interview_id);
CREATE INDEX IF NOT EXISTS idx_evidence_answer_time
    ON user_insight.evidence (answer_id, start_sec, end_sec);
CREATE INDEX IF NOT EXISTS idx_tag_interview_name
    ON user_insight.tag (interview_id, tag_name);
CREATE INDEX IF NOT EXISTS idx_tag_value
    ON user_insight.tag (tag_name, tag_value);

-- 约 5,355 条 answer，第一阶段无需向量索引也可全表扫描。
-- 若已有更多项目数据，再按数据量设置 lists 并 ANALYZE。
-- CREATE INDEX idx_answer_embedding ON user_insight.answer
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

