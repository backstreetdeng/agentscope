## [ERR-20261012-NCE] source_excel_error_cells

**Logged**: 2026-10-12
**Priority**: medium
**Status**: resolved
**Area**: tests

### Summary
The trusted 12-column baseline contains three literal #N/A markers in the business series classification field. Openpyxl append inferred active error cell types from these text values; final workbook validation correctly rejected them.

### Resolution
Preserve the source files and original business text. In the new output only, store error text explicitly as string, attach provenance comments and a separate review sheet, without inferring replacement classifications. Validate cell types and row values independently. Inspect input error cells before generating future maintenance files.

### Metadata
- Reproducible: yes
- Related Files: ops/complete_new_car_september.py
