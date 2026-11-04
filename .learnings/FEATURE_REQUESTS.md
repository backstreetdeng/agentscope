# Feature requests

## [FEAT-20261005-001] macro_same_month_indicator_reuse

**Logged**: 2026-10-05T21:03:11+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Requested Capability
同一个报告月份重新执行时，复用历史任务已核验指标，只续跑缺失、失败或需要更新的指标。

### User Context
业务会在下月不同日期多次生成同一个月份月报；不能每次把99/134项已完成证据重新检索。

### Complexity Estimate
medium

### Implementation
后台来源阶段传入本地任务档案；匹配统计请求，并在当前截止日独立回放原文证据，复核口径、历史长度、新鲜度和交叉验证。新任务复制证据及来源标识，但不继承旧PPT、预测、任务完成状态或交付验收。海关公报仍检查当前选定版本；日志显示复用与待补数量。

### Metadata
- Frequency: recurring
- Related Features: macro_report_jobs, source_recovery
- Related Files: app.py, skills/macro-monthly-report/scripts/macro_sources.py, tests/test_macro_source_reuse.py

### Resolution
- 真实2026-09历史来源按2026-10-05规则本地回放99/134项通过；零网络、零模型调用。
- 完成14项来源复用场景回归；这不代表剩余35项已补齐或正式PPT已验收。

---
