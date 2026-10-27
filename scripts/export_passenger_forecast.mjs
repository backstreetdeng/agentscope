import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => i % 2 ? a : [...a, [v, all[i + 1]]], []));
const { result, history } = JSON.parse(await fs.readFile(args['--input'], 'utf8'));
const out = path.resolve(args['--output']);
const require = createRequire(path.join(path.resolve(args['--modules']), '..', 'package.json'));
const { Workbook, SpreadsheetFile } = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const pptxgen = require('pptxgenjs');
const rows = result.rows;
if (!Array.isArray(rows) || rows.length !== 12 || rows.some((r, i) => r.month !== i + 1)) throw new Error('Expected 12 chronological monthly rows');
await fs.mkdir(out, { recursive: true });
const previewDir = path.join(out, '..', 'working', 'export_previews');
await fs.mkdir(previewDir, { recursive: true });
const font = 'Microsoft YaHei';
const navy = '#183B56', blue = '#3478B8', teal = '#008A83';
const label = v => typeof v === 'string' ? v : JSON.stringify(v ?? '');
const records = history.records || [];
const cutoffRecord = [...records].sort((a, b) => a.year - b.year || a.month - b.month).at(-1);
const cutoff = cutoffRecord ? `${cutoffRecord.year}-${String(cutoffRecord.month).padStart(2, '0')}` : '未提供';
const source = history.source_filename || history.filename || history.source_name || '业务提供历史销量工作簿';
const note = '基准试算草稿：已发布月份作为实际历史输入；政策、价格、新车驱动尚未量化。';
const workbook = Workbook.create();
const forecast = workbook.worksheets.add('月度预测');
const inputs = workbook.worksheets.add('历史输入');
const audit = workbook.worksheets.add('假设与核验');
for (const [sh, lastRow] of [[forecast, 35], [inputs, records.length + 26], [audit, 45]]) {
  sh.showGridLines = false;
  sh.getRange(`A1:M${lastRow}`).format.font = { name: font, size: 10, color: '#172B4D' };
  sh.getRange(`A1:M${lastRow}`).format.verticalAlignment = 'center';
  sh.getRange(`A1:M${lastRow}`).format.rowHeight = 22;
  sh.getRange(`A1:M${lastRow}`).format.columnWidth = 15;
}
function title(sh, text) {
  sh.getRange('A2').values = [[text]];
  sh.getRange('A2:G2').format.font = { name: font, size: 16, bold: true, color: navy };
  sh.getRange('A2:G2').format.rowHeight = 30;
}
function header(sh, range) {
  sh.getRange(range).format = { fill: navy, font: { name: font, color: '#FFFFFF', bold: true, size: 10 }, horizontalAlignment: 'center', verticalAlignment: 'center', rowHeight: 29 };
}
forecast.tabColor = navy;
title(forecast, `${result.year} 年乘用车月度预测（万辆）`);
forecast.getRange('A4:B6').values = [['年度约束（用户确认）', result.annual_total], ['业务提供数据截至', cutoff], ['预测状态', '基准试算草稿']];
forecast.getRange('B4').setNumberFormat('#,##0.00');
forecast.getRange('A4:A6').format.columnWidth = 24;
forecast.getRange('A8:G8').values = [['月份', '乘用车总量', '新能源渗透率', '新能源销量', '传统车销量', '数据属性', '结果来源']];
header(forecast, 'A8:G8');
forecast.getRange('A9:G20').values = rows.map(r => [`${r.month}月`, r.total, r.penetration / 100, null, null, r.status === 'provided' ? '业务提供' : '预测试算', r.status === 'provided' ? '历史输入' : '年度约束及历史基准']);
forecast.getRange('D9:E9').formulas = [['=B9*C9', '=B9-D9']];
forecast.getRange('D9:E20').fillDown();
forecast.getRange('A21').values = [['全年']];
forecast.getRange('B21:E21').formulas = [['=SUM(B9:B20)', '=D21/B21', '=SUM(D9:D20)', '=SUM(E9:E20)']];
forecast.getRange('F21:G21').values = [['年度加权', '新能源合计 / 总量合计']];
forecast.getRange('A21:G21').format = { fill: '#EDF3F8', font: { name: font, bold: true, size: 10 }, rowHeight: 28 };
forecast.getRange('B9:B21').setNumberFormat('#,##0.00');
forecast.getRange('C9:C21').setNumberFormat('0.00%');
forecast.getRange('D9:E21').setNumberFormat('#,##0.00');
forecast.getRange('B9:C20').format.font = { name: font, size: 10, color: blue };
forecast.getRange('G8:G21').format.columnWidth = 28;
forecast.getRange('A23').values = [[note]];
forecast.getRange('A23:G24').merge();
forecast.getRange('A23:G24').format = { fill: '#FFF2D5', wrapText: true, rowHeight: 24, font: { name: font, size: 10, color: '#785415' } };
const roundingDifference = result.summary?.displayed_total_rounding_difference ?? (rows.reduce((s, r) => s + Math.round(r.total * 100) / 100, 0) - result.annual_total);
const roundingNote = `月度显示舍入尾差 ${roundingDifference >= 0 ? '+' : ''}${roundingDifference.toFixed(2)} 万辆；年度以未舍入值闭合。`;
forecast.getRange('A26').values = [[roundingNote]];
const volumeChart = forecast.charts.add('bar', [forecast.getRange('A8:A20'), forecast.getRange('B8:B20')]);
volumeChart.title = '月度乘用车总量（万辆）';
volumeChart.titleTextStyle.fontSize = 13;
volumeChart.titleTextStyle.typeface = font;
volumeChart.hasLegend = false;
volumeChart.series.items[0].fill = blue;
volumeChart.xAxis = { axisType: 'textAxis', textStyle: { typeface: font, fontSize: 11 } };
volumeChart.yAxis = { numberFormatCode: '0', numberFormatSourceLinked: false, textStyle: { typeface: font, fontSize: 11 } };
volumeChart.setPosition('I3', 'Q18');
const rateChart = forecast.charts.add('line', [forecast.getRange('A8:A20'), forecast.getRange('C8:C20')]);
rateChart.title = '新能源渗透率';
rateChart.titleTextStyle.fontSize = 13;
rateChart.titleTextStyle.typeface = font;
rateChart.hasLegend = false;
rateChart.series.items[0].line = { fill: teal, style: 'solid', width: 2 };
rateChart.xAxis = { axisType: 'textAxis', textStyle: { typeface: font, fontSize: 11 } };
rateChart.yAxis = { numberFormatCode: '0%', numberFormatSourceLinked: false, textStyle: { typeface: font, fontSize: 11 } };
rateChart.setPosition('I20', 'Q35');

title(inputs, '业务提供的月度历史输入');
inputs.getRange('A4').values = [[`来源：${source}。销量统一换算为万辆；原值及单元格位置保留。已发布月份作为实际历史输入。`]];
inputs.getRange('A4:I5').merge();
inputs.getRange('A4:I5').format.wrapText = true;
inputs.getRange('A7:I7').values = [['年份', '月份', '乘用车总量（万辆）', '新能源销量（万辆）', '新能源渗透率', '数据属性', '来源单元格', '来源原值', '来源文件']];
header(inputs, 'A7:I7');
if (records.length) {
  inputs.getRange(`A8:I${7 + records.length}`).values = records.map(r => [r.year, r.month, r.total, r.nev, null, '已发布实际', label(r.source_cells), label(r.source_values), source]);
  inputs.getRange('E8').formulas = [['=D8/C8']];
  inputs.getRange(`E8:E${7 + records.length}`).fillDown();
  inputs.getRange(`C8:D${7 + records.length}`).setNumberFormat('#,##0.0000');
  inputs.getRange(`E8:E${7 + records.length}`).setNumberFormat('0.00%');
}
inputs.getRange('C7:D200').format.columnWidth = 25;
inputs.getRange('F7:I200').format.columnWidth = 36;
inputs.freezePanes.freezeRows(7);
title(audit, '试算假设与年度核验');
audit.getRange('A4:B10').values = [
  ['年度约束来源', '用户确认值'], ['历史窗口', label(result.history_window)], ['预测计算日期', result.as_of_date || '未提供'],
  ['业务提供数据截至', cutoff], ['预测方法', result.method?.name || label(result.method)], ['输入属性', '统计口径、单位及实际/估计性质待业务确认'], ['驱动量化', '政策、价格、新车等驱动尚未量化']
];
audit.getRange('A4:A35').format.columnWidth = 25;
audit.getRange('B4:B35').format.columnWidth = 100;
audit.getRange('B4:B35').format.wrapText = true;
audit.getRange('A12:B12').values = [['核验项目', '差额 / 结果']];
header(audit, 'A12:B12');
audit.getRange('A13:A15').values = [['年度闭合差额（万辆）'], ['能源拆分差额（万辆）'], ['加权渗透率']];
audit.getRange('B13:B15').formulas = [["='月度预测'!B21-'月度预测'!B4"], ["='月度预测'!D21+'月度预测'!E21-'月度预测'!B21"], ["='月度预测'!C21"]];
audit.getRange('B13:B14').setNumberFormat('0.000000');
audit.getRange('B15').setNumberFormat('0.00%');
const details = [
  ['总量分配规则', result.method?.total || '按历史季节性分配年度总量'],
  ['渗透率规则', result.method?.penetration || '历史结构趋势'],
  ['显示舍入说明', roundingNote],
  ...((Array.isArray(result.assumptions) ? result.assumptions : [result.assumptions]).filter(Boolean).map(v => ['试算假设', label(v)])),
  ...((Array.isArray(result.warnings) ? result.warnings : [result.warnings]).filter(Boolean).map(v => ['待确认 / 限制', label(v)]))
];
if (details.length) {
  audit.getRange(`A18:B${17 + details.length}`).values = details;
  audit.getRange(`A18:B${17 + details.length}`).format.rowHeight = 40;
}
const bridge = result.bridge_rows || [];
if (bridge.length) {
  const base = records.length + 11;
  inputs.getRange(`A${base}:F${base}`).values = [['衔接年份', '月份', '总量（万辆）', '新能源（万辆）', '新能源渗透率', '数据属性']];
  header(inputs, `A${base}:F${base}`);
  inputs.getRange(`A${base + 1}:F${base + bridge.length}`).values = bridge.map(r => [r.year || result.year - 1, r.month, r.total, r.nev, r.penetration / 100, r.status === 'provided' ? '业务提供' : '衔接预测试算']);
  inputs.getRange(`C${base + 1}:D${base + bridge.length}`).setNumberFormat('#,##0.00');
  inputs.getRange(`E${base + 1}:E${base + bridge.length}`).setNumberFormat('0.00%');
}
workbook.recalculate();
const inspection = await workbook.inspect({ kind: 'table', range: '月度预测!A8:G21', include: 'values,formulas', tableMaxRows: 14, tableMaxCols: 7, maxChars: 8000 });
await fs.writeFile(path.join(previewDir, 'formula-inspection.jsonl'), inspection.ndjson);
const errorScan = await workbook.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 100 }, maxChars: 3000 });
await fs.writeFile(path.join(previewDir, 'formula-error-scan.jsonl'), errorScan.ndjson);
for (const [sheetName, range, slug] of (args['--preview'] === 'true' ? [['月度预测', 'A1:Q35', 'forecast'], ['历史输入', 'A1:I17', 'history'], ['假设与核验', `A1:B${17 + details.length}`, 'assumptions']] : [])) {
  const preview = await workbook.render({ sheetName, range, scale: 1.3, format: 'png' });
  await fs.writeFile(path.join(previewDir, `${slug}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const xlsxPath = path.join(out, `${result.year}年乘用车月度预测.xlsx`);
await (await SpreadsheetFile.exportXlsx(workbook)).save(xlsxPath);

const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = '乘用车市场预测助手';
pptx.subject = '业务历史输入支持的年度约束基准试算';
pptx.title = `${result.year} 年乘用车市场预测（草稿）`;
pptx.company = '市场预测';
pptx.lang = 'zh-CN';
const months = rows.map(r => `${r.month}月`);
const sumNev = rows.reduce((s, r) => s + r.total * r.penetration / 100, 0);
const weighted = sumNev / rows.reduce((s, r) => s + r.total, 0) * 100;
function slideBase(titleText, index) {
  const slide = pptx.addSlide();
  slide.background = { color: 'FFFFFF' };
  slide.addText(titleText, { x: 0.55, y: 0.45, w: 12.2, h: 0.6, margin: 0, fontFace: font, fontSize: 30, bold: true, color: '183B56' });
  slide.addText(`年度约束 ${Number(result.annual_total).toLocaleString('zh-CN')} 万辆；业务提供数据截至 ${cutoff}`, { x: 0.55, y: 1.16, w: 12.2, h: 0.35, margin: 0, fontFace: font, fontSize: 14, color: '536779' });
  slide.addText(note, { x: 0.55, y: 6.65, w: 11.8, h: 0.42, margin: 0, fontFace: font, fontSize: 11, color: '8A601E' });
  slide.addText(`${index}/2`, { x: 12.3, y: 6.75, w: 0.48, h: 0.2, margin: 0, fontFace: font, fontSize: 10, align: 'right', color: '64748B' });
  return slide;
}
function chartOptions() {
  return { x: 0.55, y: 1.82, w: 12.1, h: 4.5, fontFace: font, catAxisLabelFontFace: font, catAxisLabelFontSize: 12, valAxisLabelFontFace: font, valAxisLabelFontSize: 11, catAxisLabelColor: '536779', valAxisLabelColor: '536779', catGridLine: { style: 'none' }, valGridLine: { color: 'E6EDF2', size: 0.5 }, chartArea: { fill: { color: 'FFFFFF' } }, showLegend: false, showTitle: false, showValue: true, dataLabelColor: '183B56', dataLabelFormatCode: '0.00', showBorder: false };
}
const first = slideBase(`${result.year} 年月度乘用车总量预测`, 1);
first.addChart(pptx.ChartType.bar, [{ name: '乘用车总量（万辆）', labels: months, values: rows.map(r => r.total) }], { ...chartOptions(), barDir: 'col', chartColors: ['3478B8'], valAxisMinVal: 0, showCatName: false, dataLabelPosition: 'outEnd' });
first.addNotes(`来源：${source}；已发布月份作为实际历史输入。年度总量为用户确认值，月度总量同网页结果。方法：${label(result.method)}。历史窗口：${label(result.history_window)}。`);
const second = slideBase(`${result.year} 年新能源渗透率预测`, 2);
second.addText(`全年销量加权渗透率 ${weighted.toFixed(2)}%`, { x: 9.1, y: 1.18, w: 3.65, h: 0.3, margin: 0, fontFace: font, fontSize: 14, bold: true, align: 'right', color: '008A83' });
second.addChart(pptx.ChartType.line, [{ name: '新能源渗透率', labels: months, values: rows.map(r => r.penetration / 100) }], { ...chartOptions(), chartColors: ['008A83'], lineSize: 2.5, lineSmooth: false, valAxisMinVal: 0, valAxisMaxVal: 1, valAxisMajorUnit: 0.2, valAxisLabelFormatCode: '0%', dataLabelFormatCode: '0.0%', showMarker: true, markerSize: 4, dataLabelPosition: 't' });
second.addNotes(`月度渗透率 = 月度新能源 / 月度总量；全年按销量加权。来源：${source}。统计口径及历史输入实际属性尚待业务确认；短期驱动未量化。`);
const pptxPath = path.join(out, `${result.year}年乘用车月度预测.pptx`);
await pptx.writeFile({ fileName: pptxPath });
console.log(JSON.stringify({ artifacts: [{ path: xlsxPath, kind: 'spreadsheet', label: 'Excel 月度预测与来源' }, { path: pptxPath, kind: 'presentation', label: 'PPT 原生可编辑图表' }], preview_dir: previewDir }));
// All file writes are awaited before explicitly completing this worker process.
process.exit(0);
