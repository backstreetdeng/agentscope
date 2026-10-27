-- 乘用车市场预测引擎 数据模型 v0.1
-- 口径铁律：indicators 只插入不更新（point-in-time），修订值新开 series_id

CREATE TABLE IF NOT EXISTS indicators (
  series_id   TEXT NOT NULL,        -- 'retail.bev' / 'retail.phev' / ...
  metric      TEXT NOT NULL,        -- retail / wholesale / insurance
  powertrain  TEXT NOT NULL,        -- bev / phev / hev / ice / total
  province    TEXT NOT NULL DEFAULT 'national',
  ym          TEXT NOT NULL,        -- '2026-09'
  value       REAL NOT NULL,
  source      TEXT NOT NULL,        -- 来源名
  source_url  TEXT,
  collected_at TEXT NOT NULL,       -- 采集时间戳，禁止回填
  PRIMARY KEY (series_id, ym, collected_at)
);

CREATE INDEX IF NOT EXISTS idx_ind_series_ym ON indicators(series_id, ym);

-- 事件库：预测的灵魂。mult_* = 乘法系数（1.05 即 +5%）
CREATE TABLE IF NOT EXISTS events (
  event_id     TEXT PRIMARY KEY,
  event_type   TEXT NOT NULL,       -- tax / subsidy / standard / cycle / oil / price_war
  date_start   TEXT NOT NULL,       -- 生效月 'YYYY-MM'
  date_end     TEXT NOT NULL,       -- 结束月（含）
  scope        TEXT NOT NULL,       -- all / bev / phev / hev / ice / nev
  mult_base    REAL NOT NULL,       -- 基准情景系数
  mult_bull    REAL NOT NULL,       -- 乐观情景
  mult_bear    REAL NOT NULL,       -- 悲观情景
  evidence_url TEXT,
  note         TEXT,
  created_at   TEXT NOT NULL
);

-- 口径字典：消歧。同一术语只允许指向一个 series_id 或公式
CREATE TABLE IF NOT EXISTS metric_dict (
  term        TEXT PRIMARY KEY,
  points_to   TEXT NOT NULL,
  definition  TEXT NOT NULL
);

-- 预测档案：命中率的来源。每次预测完整快照
CREATE TABLE IF NOT EXISTS forecast_runs (
  run_id       TEXT NOT NULL,
  model_version TEXT NOT NULL,
  data_cutoff  TEXT NOT NULL,       -- 输入数据截止月
  ym           TEXT NOT NULL,       -- 被预测月
  powertrain   TEXT NOT NULL,
  scenario     TEXT NOT NULL,       -- base / bull / bear
  p10          REAL, p50 REAL NOT NULL, p90 REAL,
  assumptions  TEXT,                -- JSON快照：事件修正链
  created_at   TEXT NOT NULL,
  PRIMARY KEY (run_id, ym, powertrain)
);
