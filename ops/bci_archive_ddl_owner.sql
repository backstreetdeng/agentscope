-- BCI-004 · 用户洞察档案存储 · bci schema 创建（以 owner 级账号执行）
-- 账号：.env.new-car 中的 NEW_CAR_PG_USER / NEW_CAR_PG_PASSWORD
-- 目标库：NEW_CAR_PG_HOST:NEW_CAR_PG_PORT/NEW_CAR_PG_DATABASE（192.168.3.146:5432/vectordb）
--
-- 原计划：CREATE SCHEMA bci AUTHORIZATION user_insight_loader;
-- 实测（2026-11-07）：owner 账号不是 user_insight_loader 的成员、也不是 superuser，
--   执行 AUTHORIZATION 会报 "must be member of role user_insight_loader"，因此改为：
--   1) owner 建 schema；
--   2) 只授予 loader USAGE + CREATE，使其能在其中建表并读写；
--   3) 表由 loader 创建，属主是 loader，业务进程仍只用 loader 账号。
-- 若业务要求 schema 属主也必须是 loader，需要 DBA 执行
--   ALTER SCHEMA bci OWNER TO user_insight_loader;（需要成员资格或 superuser），
--   本脚本不尝试该路径。
-- 可重复执行。

CREATE SCHEMA IF NOT EXISTS bci;
GRANT USAGE, CREATE ON SCHEMA bci TO user_insight_loader;
