## [ERR-20261013-RPA] patch_context

**Logged**: 2026-10-13
**Priority**: low
**Status**: resolved
**Area**: tests

### Summary
Two apply_patch attempts rejected stale or out-of-order context; no files changed in those attempts.

### Suggested Fix
Read exact current lines and keep patch hunks in source order. Separate unrelated test edits from deployment edits. Re-run targeted tests after correction.

### Windows encoding check
The inline JavaScript syntax check initially failed in Python's GBK stdin encoding, before Node ran. Set subprocess encoding explicitly to UTF-8; the unchanged JavaScript then passes.
