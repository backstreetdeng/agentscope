"""Deterministic passenger-car forecasting. Internal volumes: 万辆; penetration: %."""
from __future__ import annotations
import calendar
import csv
import hashlib
import io
import math
import re
from datetime import date
from statistics import median


class ForecastInputError(ValueError):
    pass


def _num(value, where):
    try:
        result = float(str(value).replace(',', '').strip())
    except (ValueError, TypeError):
        raise ForecastInputError(f'{where} 不是有效数值：{value}') from None
    if isinstance(value, bool) or not math.isfinite(result):
        raise ForecastInputError(f'{where} 数值必须有限')
    return result


def _int(value, where):
    n = _num(value, where)
    if not n.is_integer():
        raise ForecastInputError(f'{where} 必须为整数')
    return int(n)


def _blank(v):
    return v is None or (isinstance(v, str) and not v.strip())


def _kind(value):
    h = re.sub(r'[\s_（）()%％\-]', '', str(value or '')).lower()
    if h in {'年份', '年', 'year'}: return 'year'
    if h in {'月份', '月', 'month'}: return 'month'
    if '渗透率' in h or h in {'penetration', 'nevshare'}: return 'penetration'
    if h in {'total', 'pc', '乘用车', '总量', '销量'} or '乘用车总量' in h or '乘用车销量' in h: return 'total'
    if h in {'nev', '新能源'} or '新能源销量' in h: return 'nev'
    if h in {'状态', '数据状态', '性质', 'status'}: return 'source_status'
    return None


def parse_history(data: bytes, filename: str, unit: str = 'vehicle') -> dict:
    """Accept PC/NEV matrices and long XLSX/CSV. Never infer units from magnitude."""
    if unit not in {'vehicle', 'wan'}:
        raise ForecastInputError('单位必须显式选择 vehicle（辆）或 wan（万辆）')
    if not data or len(data) > 15 * 1024 * 1024:
        raise ForecastInputError('文件为空或超过15MB')
    factor = 10000.0 if unit == 'vehicle' else 1.0
    matrices = []
    percentage_cells = set()
    if filename.lower().endswith(('.xlsx', '.xlsm')):
        from openpyxl import load_workbook
        from openpyxl.utils import get_column_letter
        try:
            values = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
            formulas = load_workbook(io.BytesIO(data), data_only=False, read_only=True)
        except Exception as exc:
            raise ForecastInputError(f'无法读取Excel：{exc}') from exc
        try:
            for sheet in values:
                if sheet.max_row > 20000 or sheet.max_column > 300:
                    raise ForecastInputError('Excel表过大，请提供月度数据表')
                rows = list(sheet.iter_rows(values_only=True))
                for ri, frow in enumerate(formulas[sheet.title].iter_rows()):
                    for ci, cell in enumerate(frow):
                        cached = rows[ri][ci]
                        if getattr(cell, 'number_format', None) and '%' in cell.number_format:
                            percentage_cells.add(f'{sheet.title}!{get_column_letter(ci+1)}{ri+1}')
                        if cell.data_type == 'f' and _blank(cached):
                            raise ForecastInputError(f'{sheet.title}!{cell.coordinate} 公式没有缓存值，请先在Excel计算并保存')
                        if cell.data_type == 'e' or (isinstance(cached, str) and cached.startswith(('#REF!', '#DIV/0!', '#VALUE!', '#N/A', '#NAME?', '#NUM!', '#NULL!'))):
                            raise ForecastInputError(f'{sheet.title}!{cell.coordinate} 存在Excel错误值')
                refs = [[f'{sheet.title}!{get_column_letter(c+1)}{r+1}' for c in range(len(row))] for r, row in enumerate(rows)]
                matrices.append((sheet.title, rows, refs))
        finally:
            values.close()
            formulas.close()
    elif filename.lower().endswith(('.csv', '.txt', '.tsv')):
        try:
            content = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                content = data.decode('gb18030')
            except UnicodeDecodeError as exc:
                raise ForecastInputError('CSV编码无法识别') from exc
        rows = list(csv.reader(io.StringIO(content), delimiter='\t' if filename.lower().endswith('.tsv') else ','))
        refs = [[f'{filename}:行{r+1}:列{c+1}' for c in range(len(row))] for r, row in enumerate(rows)]
        matrices.append((filename, rows, refs))
    else:
        raise ForecastInputError('请上传 .xlsx、.xlsm 或规范长表 .csv')
    records, pending, coverage, input_keys = {}, {}, set(), set()

    def add(year, month, total_raw, nev_raw, cells, source_values, source_status=None, ratio=None):
        year, month = _int(year, '年份'), _int(month, '月份')
        if not 1900 <= year <= 2200 or not 1 <= month <= 12:
            raise ForecastInputError(f'年月超界：{year}-{month}')
        key = year, month
        coverage.add(key)
        if key in input_keys:
            raise ForecastInputError(f'重复年月：{year}-{month:02d}')
        input_keys.add(key)
        if _blank(total_raw) and _blank(nev_raw) and _blank(ratio): return
        if _blank(total_raw) or (_blank(nev_raw) and _blank(ratio)):
            raise ForecastInputError(f'{year}-{month:02d} 总量与新能源配对缺失')
        total = _num(total_raw, cells.get('total')) / factor
        nev = _num(nev_raw, cells.get('nev')) / factor if not _blank(nev_raw) else None
        if not _blank(ratio):
            p = _num(str(ratio).rstrip('%％'), cells.get('penetration')) / 100
            if not 0 <= p <= 1:
                raise ForecastInputError(f'{year}-{month:02d} 渗透率超出0–100%')
            if nev is None: nev = total * p
            elif not math.isclose(nev, total*p, rel_tol=1e-7, abs_tol=0.00001):
                raise ForecastInputError(f'{year}-{month:02d} 新能源销量与渗透率不一致')
        if total < 0 or nev < 0 or nev > total:
            raise ForecastInputError(f'{year}-{month:02d} 销量为负数或新能源超过总量')
        records[key] = dict(year=year, month=month, total=total, nev=nev,
                            penetration=nev/total*100 if total else None,
                            source_cells=cells, source_values=source_values,
                            source_status=source_status or '未注明', status='provided')

    for name, rows, refs in matrices:
        long_header = None
        for r, row in enumerate(rows):
            mapping = {kind: c for c, v in enumerate(row) if (kind := _kind(v))}
            if {'year', 'month', 'total'} <= mapping.keys() and ({'nev', 'penetration'} & mapping.keys()):
                for name in ('total', 'nev'):
                    header = str(row[mapping[name]]) if name in mapping else ''
                    if '万辆' in header and unit != 'wan':
                        raise ForecastInputError('表头声明万辆，与所选输入单位不一致，请选择万辆')
                    if '万辆' not in header and ('（辆）' in header or '(辆)' in header) and unit != 'vehicle':
                        raise ForecastInputError('表头声明辆，与所选输入单位不一致，请选择辆')
                long_header = r, mapping
                break
        if long_header:
            start, columns = long_header
            for ri in range(start+1, len(rows)):
                row = rows[ri]
                if all(_blank(v) for v in row): continue
                vals = {k: row[c] if c < len(row) else None for k, c in columns.items()}
                cells = {k: refs[ri][c] if c < len(row) else f'{name}:行{ri+1}:列{c+1}' for k, c in columns.items()}
                ratio = vals.get('penetration')
                if cells.get('penetration') in percentage_cells and not _blank(ratio):
                    ratio = _num(ratio, cells['penetration']) * 100
                add(vals.get('year'), vals.get('month'), vals.get('total'), vals.get('nev'), cells, vals, vals.get('source_status'), ratio)
            continue
        active, years, mc = None, None, None
        for ri, row in enumerate(rows):
            nonempty = [v for v in row if not _blank(v)]
            if len(nonempty) == 1 and _kind(nonempty[0]) in {'total', 'nev'}:
                active, years = _kind(nonempty[0]), None
                continue
            if active and any(_kind(v) == 'month' for v in row):
                mc = next(c for c, v in enumerate(row) if _kind(v) == 'month')
                years = {}
                for c, value in enumerate(row):
                    if c <= mc or _blank(value): continue
                    try: year = _int(value, refs[ri][c])
                    except ForecastInputError: continue
                    if 1900 <= year <= 2200:
                        if year in years.values(): raise ForecastInputError(f'{name} 年份列重复：{year}')
                        years[c] = year
                continue
            if not years or mc is None or _blank(row[mc]): continue
            try: month = _int(str(row[mc]).removesuffix('月'), '月份')
            except ForecastInputError: continue
            if not 1 <= month <= 12: continue
            for c, year in years.items():
                key = year, month
                coverage.add(key)
                pair = pending.setdefault(key, {})
                if active in pair: raise ForecastInputError(f'重复年月或区块：{year}-{month:02d} {active}')
                pair[active] = row[c], refs[ri][c]
    for (year, month), pair in pending.items():
        total, tc = pair.get('total', (None, None))
        nev, nc = pair.get('nev', (None, None))
        add(year, month, total, nev, dict(total=tc, nev=nc), dict(total=total, nev=nev))
    if not records: raise ForecastInputError('未识别到成对月度数据；支持年份/月/总量/新能源长表或乘用车、新能源双区块')
    years = sorted({y for y, m in coverage})
    latest = max(records)
    return dict(records=[records[k] for k in sorted(records)], filename=filename,
                sha256=hashlib.sha256(data).hexdigest(), input_unit=unit, unit='万辆',
                summary=dict(count=len(records), complete_years=[y for y in years if all((y,m) in records for m in range(1,13))],
                latest_period=f'{latest[0]}-{latest[1]:02d}', missing_periods=[f'{y}-{m:02d}' for y in years for m in range(1,13) if (y,m) not in records]),
                warnings=[f"输入单位按本次选择的{'辆' if unit == 'vehicle' else '万辆'}解析。",
                '业务已确认：源文件中已发布月份作为实际历史输入；后续补充数据应保持相同统计范围。',
                '历史数据没有逐条发布时间/版本，历史回测仅作日期截断试算，不能视为严格实时可得数据回测。'])


def _stats(samples):
    values = sorted(s['value'] for s in samples)
    def q(frac):
        pos = (len(values)-1)*frac
        lo, hi = int(pos), min(int(pos)+1, len(values)-1)
        return values[lo]+(values[hi]-values[lo])*(pos-lo)
    return dict(median=median(values) if values else None, count=len(values), years=[s['year'] for s in samples],
                min=min(values) if values else None, max=max(values) if values else None,
                q1=q(.25) if values else None, q3=q(.75) if values else None, samples=samples)


def _previous(y, m): return (y-1,12) if m == 1 else (y,m-1)


def _available(r, cutoff):
    period, latest = (r['year'],r['month']), (cutoff.year,cutoff.month)
    return period < latest or (period == latest and cutoff.day == calendar.monthrange(*latest)[1])


def _p(r): return r['nev']/r['total']*100 if r and r['total'] else None


def _history_stats(lookup, window, month):
    metrics = {n: [] for n in ('volume','share','yoy','mom','penetration','penetration_yoy_pp','penetration_mom_pp','nev_share','nev_yoy','nev_mom')}
    for year in window:
        row = lookup[year,month]
        annual = sum(lookup[year,m]['total'] for m in range(1,13))
        nev_annual = sum(lookup[year,m]['nev'] for m in range(1,13))
        def put(name, value, refs):
            if value is not None: metrics[name].append(dict(year=year,value=value,source_cells=refs))
        put('volume',row['total'],row.get('source_cells'))
        put('share',row['total']/annual if annual else None,row.get('source_cells'))
        put('penetration',_p(row),row.get('source_cells'))
        put('nev_share',row['nev']/nev_annual if nev_annual else None,row.get('source_cells'))
        for metric, key in (('yoy',(year-1,month)),('mom',_previous(year,month))):
            ref = lookup.get(key)
            if ref:
                cells = dict(numerator=row.get('source_cells'),denominator=ref.get('source_cells'))
                put(metric,row['total']/ref['total']-1 if ref['total'] else None,cells)
                put('nev_'+metric,row['nev']/ref['nev']-1 if ref['nev'] else None,cells)
                put('penetration_'+metric+'_pp',_p(row)-_p(ref) if _p(row) is not None and _p(ref) is not None else None,cells)
    return {name:_stats(samples) for name,samples in metrics.items()}


def build_forecast(history: dict, target_year: int, annual_targets: dict, as_of_date: str, allow_draft: bool = True) -> dict:
    if not allow_draft: raise ForecastInputError('单位、口径及实际性质尚待业务确认；当前仅支持明确标注的草稿试跑')
    try: cutoff = date.fromisoformat(as_of_date)
    except (ValueError,TypeError): raise ForecastInputError('as_of_date 必须为 YYYY-MM-DD') from None
    year = _int(target_year,'目标年份')
    targets = {_int(y,'年度年份'):_num(v,'年度采用值（万辆）') for y,v in annual_targets.items()}
    if year not in targets: raise ForecastInputError(f'缺少{year}年用户年度采用值，不能自动生成')
    if any(v < 0 for v in targets.values()): raise ForecastInputError('年度采用值不能为负')
    raw = history.get('records',[])
    lookup = {(r['year'],r['month']):r for r in raw if _available(r,cutoff)}
    if not lookup: raise ForecastInputError('截止日前没有完整月份数据')
    warnings = list(history.get('warnings',[]))
    excluded = [f"{r['year']}-{r['month']:02d}" for r in raw if not _available(r,cutoff)]
    if excluded: warnings.append(f'截止日之后或尚未结束月份的{len(excluded)}条记录已排除。')
    complete = [y for y in sorted({k[0] for k in lookup}) if all((y,m) in lookup for m in range(1,13)) and sum(lookup[y,m]['total'] for m in range(1,13)) > 0 and (y < cutoff.year or (y == cutoff.year and cutoff.month == 12 and cutoff.day == 31))]
    derived, results = dict(lookup), {}

    def run(y):
        if y in results: return results[y]
        if y not in targets: raise ForecastInputError(f'{year}年预测需要衔接{y}年，但未提供{y}年年度采用值')
        window = [s for s in complete if s < y][-5:]
        if not window: raise ForecastInputError(f'{y}年以前没有完整年度，无法建立全年占比基准')
        if not all((y-1,m) in derived for m in range(1,13)):
            if y-1 < min(k[0] for k in lookup): raise ForecastInputError('缺少有依据的去年同期结构参照')
            run(y-1)
        stats = {m:_history_stats(lookup,window,m) for m in range(1,13)}
        weights = {m:stats[m]['share']['median'] for m in range(1,13)}
        supplied = {m:lookup[y,m] for m in range(1,13) if (y,m) in lookup}
        future = [m for m in range(1,13) if m not in supplied]
        annual, locked = targets[y], sum(r['total'] for r in supplied.values())
        if annual < locked-1e-9: raise ForecastInputError(f'{y}年年度约束{annual}万辆低于已提供月份累计{locked}万辆')
        if not future and not math.isclose(annual,locked,abs_tol=1e-8): raise ForecastInputError(f'{y}年12个月已提供值与年度约束冲突，不能覆盖源数据')
        remaining = annual-locked
        denominator = sum(weights[m] or 0 for m in future)
        if future and (any(weights[m] is None for m in future) or denominator <= 0): raise ForecastInputError('剩余月份季节权重缺失或为零，不能擅自等分')
        rows = []
        for m in range(1,13):
            st, py, pm = stats[m], derived.get((y-1,m)), derived.get(_previous(y,m))
            yp, mp, dy, dm = _p(py), _p(pm), st['penetration_yoy_pp']['median'], st['penetration_mom_pp']['median']
            p_yoy = yp+dy if yp is not None and dy is not None else None
            p_mom = mp+dm if mp is not None and dm is not None else None
            t_yoy = py['total']*(1+st['yoy']['median']) if py and st['yoy']['median'] is not None else None
            t_mom = pm['total']*(1+st['mom']['median']) if pm and st['mom']['median'] is not None else None
            seasonal = annual*weights[m]
            source = supplied.get(m)
            if source:
                t,n,p,status = source['total'],source['nev'],_p(source),'provided'
                p_method = '源文件提供值计算，实际性质待业务确认'
            else:
                t = remaining*weights[m]/denominator
                p = p_yoy if p_yoy is not None else p_mom
                if p is None: raise ForecastInputError(f'{y}-{m:02d} 缺少渗透率趋势或环比参照')
                if not 0 <= p <= 100: raise ForecastInputError(f'{y}-{m:02d} 渗透率外推{p:.4f}%超出0–100%，请调整规则或提供依据；未静默截断')
                n,status = t*p/100,'forecast'
                if t == 0: p = None
                p_method = '去年同月渗透率＋历史同比百分点中位数' if p_yoy is not None else '上月渗透率＋历史环比百分点中位数（缺去年参照）'
            row = dict(year=y,month=m,total=t,penetration=p,nev=n,traditional=t-n,status=status,
                       seasonal_baseline=seasonal,baseline_total=t,independent_total=t,annual_adjustment=0.0,
                       seasonal_adjustment=t-seasonal,net_driver=None,penetration_driver_pp=None,
                       seasonal_weight=weights[m],allocation_weight=weights[m]/denominator if m in future else None,
                       annual_share=t/annual if annual else None,
                       yoy=t/py['total']-1 if py and py['total'] else None,
                       mom=t/pm['total']-1 if pm and pm['total'] else None,
                       penetration_yoy_pp=p-yp if p is not None and yp is not None else None,
                       penetration_mom_pp=p-mp if p is not None and mp is not None else None,
                       nev_yoy=n/py['nev']-1 if py and py['nev'] else None,nev_mom=n/pm['nev']-1 if pm and pm['nev'] else None,
                       source_cells=source.get('source_cells') if source else None,source_values=source.get('source_values') if source else None,
                       audit=dict(history=st,total_yoy_reference=t_yoy,total_mom_reference=t_mom,
                       penetration_yoy_reference=p_yoy,penetration_mom_reference=p_mom,penetration_method=p_method,
                       previous_year_period=f'{y-1}-{m:02d}',previous_year_status=py.get('status','provided') if py else 'missing',
                       previous_month_status=pm.get('status','provided') if pm else 'missing',
                       reference_boundary_issues=[dict(reference=label,value=value) for label,value in (('penetration_yoy',p_yoy),('penetration_mom',p_mom)) if value is not None and not 0 <= value <= 100]))
            rows.append(row)
            derived[y,m] = row
        n_total = sum(r['nev'] for r in rows)
        result = dict(year=y,annual_total=annual,rows=rows,history_window=window,
                      summary=dict(total=sum(r['total'] for r in rows),nev=n_total,traditional=sum(r['traditional'] for r in rows),
                      penetration=n_total/annual*100 if annual else None,provided_total=locked,provided_months=sorted(supplied),forecast_months=future,
                      remaining_total=remaining,annual_closure_difference=sum(r['total'] for r in rows)-annual,
                      displayed_total_rounding_difference=round(sum(round(r['total'],2) for r in rows)-round(annual,2),2),
                      displayed_nev_rounding_difference=round(sum(round(r['nev'],2) for r in rows)-round(n_total,2),2)),
                      spring_festival_reference=dict(months=[1,2],historical_combined_shares=[dict(year=s,share=sum(lookup[s,m]['total'] for m in (1,2))/sum(lookup[s,m]['total'] for m in range(1,13))) for s in window],note='1–2月合并用于春节错位对照，尚未量化目标年日历调整'))
        results[y] = result
        return result

    result = run(year)
    bridges = [results[y] for y in sorted(results) if y != year]
    if bridges: warnings.append('目标年同期参照依赖上一年未发布月份的估计路径；桥接预测不属于实际历史数据。')
    if len(result['history_window']) < 5: warnings.append(f"完整历史样本仅{len(result['history_window'])}年，少于默认五年。")
    warnings.append('政策、价格、新车、供给、春节错位及异常基数驱动尚未量化（null），本结果为年度固定的规则基准试算。')
    result.update(bridge_rows=[r for b in bridges for r in b['rows']],bridges=bridges,warnings=warnings,
                  assumptions=['源表总量包含新能源且统计范围一致；单位按上传时选择处理，待业务确认。',
                  '使用截止日前完整月份记录；源表没有发布时间，不能保证严格历史版本可得性。',
                  '保留所有选定完整年，未自动剔除疫情或其他异常年份。','默认渗透率同比百分点趋势延续；没有估计政策、新车或价格的独立影响。'],
                  method=dict(name='年度约束历史中位数规则基准',version='1.0',total='A×历史月度占比中位数为季节参照；剩余年度按未提供月权重归一分配。',
                  penetration='去年同月渗透率＋历史同期同比百分点变化中位数；环比单列交叉参照。',
                  annual_adjustment='最终采用值−独立月度建议；seasonal_adjustment另外保留相对A×原始中位占比的差额。',
                  forecast_precision='内部未舍入；展示建议2位小数，展示尾差不得回写源数据。'),
                  as_of_date=as_of_date,status='draft',unit='万辆',source_sha256=history.get('sha256'),excluded_periods=excluded,
                  annual_targets={str(y):v for y,v in targets.items()})
    return result


def validate_forecast(result: dict, history: dict, annual_targets: dict) -> dict:
    """Check independent accounting, bounds, dates and source preservation."""
    checks = []
    def check(name, passed, detail=None):
        checks.append(dict(name=name,status='passed' if passed else 'failed',detail=detail))
    try:
        cutoff = date.fromisoformat(result['as_of_date'])
        original = {(r['year'],r['month']):r for r in history['records'] if _available(r,cutoff)}
        targets = {int(y):float(v) for y,v in annual_targets.items()}
        resolved = dict(original)
        for b in result.get('bridges',[]):
            for r in b['rows']: resolved[b['year'],r['month']] = r
        seen = set()
        for case in list(result.get('bridges',[]))+[result]:
            y,rows = case['year'],case['rows']
            label = str(y)
            check(label+'年份唯一',y not in seen)
            seen.add(y)
            check(label+'十二个月唯一完整',len(rows)==12 and sorted(r['month'] for r in rows)==list(range(1,13)))
            check(label+'年度来自用户',y in targets and math.isclose(case['annual_total'],targets.get(y,-1),abs_tol=1e-8))
            total = sum(r['total'] for r in rows)
            check(label+'月度年度闭合',math.isclose(total,targets.get(y,-1),abs_tol=1e-7),total)
            check(label+'历史窗口无穿越',bool(case['history_window']) and len(case['history_window'])<=5 and all(s<y and (s<cutoff.year or (s==cutoff.year and cutoff.month==12 and cutoff.day==31)) and all((s,m) in original for m in range(1,13)) for s in case['history_window']))
            expected_years = [s for s in sorted({key[0] for key in original}) if s < y and (s < cutoff.year or (s == cutoff.year and cutoff.month == 12 and cutoff.day == 31)) and all((s,m) in original for m in range(1,13)) and sum(original[s,m]['total'] for m in range(1,13)) > 0][-5:]
            check(label+'完整历史窗口选择',case['history_window']==expected_years)
            check(label+'未知驱动保留空值',all(r.get('net_driver') is None and r.get('penetration_driver_pp') is None for r in rows))
            future = [r for r in rows if r['status']!='provided']
            check(label+'剩余月份权重闭合',not future or math.isclose(sum(r['allocation_weight'] for r in future),1,abs_tol=1e-10))
            remaining = targets.get(y,-1)-sum(v['total'] for (s,m),v in original.items() if s==y)
            for r in rows:
                name = f"{y}-{r['month']:02d}"
                t,n,c,p = (r[k] for k in ('total','nev','traditional','penetration'))
                check(name+'销量边界',all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in (t,n,c)) and n<=t)
                check(name+'能源恒等式',math.isclose(n+c,t,abs_tol=1e-9))
                check(name+'渗透率计算',(t==0 and p is None and n==0) or (t>0 and p is not None and 0<=p<=100 and math.isclose(n/t*100,p,abs_tol=1e-9)))
                source = original.get((y,r['month']))
                check(name+'输入值与性质保持',(source is not None and r['status']=='provided' and t==source['total'] and n==source['nev'] and r.get('source_cells')==source.get('source_cells') and r.get('source_values')==source.get('source_values')) or (source is None and r['status']=='forecast'))
                check(name+'预测按显式权重分配',source is not None or math.isclose(t,remaining*r['allocation_weight'],abs_tol=1e-8))
                expected_weight = median(original[s,r['month']]['total']/sum(original[s,m]['total'] for m in range(1,13)) for s in expected_years)
                check(name+'季节权重来自源数据',math.isclose(r['seasonal_weight'],expected_weight,abs_tol=1e-12) and math.isclose(r['seasonal_baseline'],targets[y]*expected_weight,abs_tol=1e-8))
                if source is None and t > 0:
                    py = resolved.get((y-1,r['month']))
                    changes = [_p(original[s,r['month']])-_p(original[s-1,r['month']]) for s in expected_years if (s-1,r['month']) in original and _p(original[s,r['month']]) is not None and _p(original[s-1,r['month']]) is not None]
                    if py and _p(py) is not None and changes:
                        check(name+'结构趋势来自源数据',math.isclose(p,_p(py)+median(changes),abs_tol=1e-8))
                check(name+'调整来源透明',math.isclose(r['annual_adjustment'],t-r['independent_total'],abs_tol=1e-10) and math.isclose(r['seasonal_adjustment'],t-r['seasonal_baseline'],abs_tol=1e-10))
                check(name+'统计样本截止日',all(s['year'] in case['history_window'] for metric in r['audit']['history'].values() for s in metric['samples']))
                resolved[y,r['month']] = r
            s = case['summary']
            check(label+'全年加权结构',math.isclose(s['nev'],sum(r['nev'] for r in rows),abs_tol=1e-8) and math.isclose(s['traditional'],sum(r['traditional'] for r in rows),abs_tol=1e-8) and math.isclose(s['total'],total,abs_tol=1e-8) and ((total==0 and s['penetration'] is None) or (total>0 and math.isclose(s['penetration'],s['nev']/total*100,abs_tol=1e-8))))
        check('源文件哈希一致',result.get('source_sha256')==history.get('sha256'))
        check('桥接展示与计算一致',result.get('bridge_rows',[])==[r for b in result.get('bridges',[]) for r in b['rows']])
    except (KeyError,TypeError,ValueError,ZeroDivisionError) as exc:
        check('结果结构完整',False,str(exc))
    return dict(status='passed' if checks and all(c['status']=='passed' for c in checks) else 'failed',
                checks=checks,count=len(checks),failed=[c for c in checks if c['status']=='failed'])
