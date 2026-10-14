# 乘用车市场月度报告 - 自动化工作流文档

## 概述

本文档记录使用 python-pptx 库自动化更新乘用车市场月度报告的技术方案。在执行自动化生成时加载此文件。

## 环境准备

```bash
# Python 3.13+ (使用WorkBuddy管理版本)
# 安装依赖
pip install python-pptx openpyxl Pillow
```

## 核心自动化流程

### 步骤1: 加载模板

```python
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.dml.color import RGBColor

# 加载模板(从skill assets目录)
prs = Presentation("assets/template.pptx")
```

### 步骤2: 更新封面 (Slide 1)

```python
slide = prs.slides[0]
year = "2026"
month = "6"

for shape in slide.shapes:
    if shape.has_text_frame:
        text = shape.text_frame.paragraphs[0].text
        if "中国乘用车市场分析报告" in text:
            # 更新标题: "{年}年{月}月中国乘用车市场分析报告"
            shape.text_frame.paragraphs[0].runs[0].text = f"{year}年{month}月中国乘用车市场分析报告"
        elif "中汽数据" in text:
            pass  # 公司名不变
        elif "月" in text and "年" in text:
            # 更新日期: "{年}年{月+1}月"
            next_month = int(month) + 1
            shape.text_frame.paragraphs[0].runs[0].text = f"{year}年{next_month}月"
```

### 步骤3: 更新图表数据 (核心难点)

#### 3a. 更新COLUMN_CLUSTERED图表 (对比柱状图)

```python
from pptx.chart.data import CategoryChartData

def update_column_chart(slide, chart_index, categories, series_list):
    """
    更新簇状柱状图数据
    series_list: [(series_name, [values]), ...]
    """
    chart = None
    chart_count = 0
    for shape in slide.shapes:
        if shape.has_chart:
            if chart_count == chart_index:
                chart = shape.chart
                break
            chart_count += 1
    
    if chart is None:
        return
    
    # 更新每个Plot
    for plot_idx, plot in enumerate(chart.plots):
        if plot_idx < len(series_list):
            data = CategoryChartData()
            data.categories = categories
            for series_name, values in series_list[plot_idx]:
                data.add_series(series_name, values)
            plot.replace_data(data)
```

#### 3b. 更新表格数据

```python
def update_table(slide, table_index, rows_data):
    """
    更新表格数据
    rows_data: [[cell1, cell2, ...], ...] 二维列表
    """
    table_count = 0
    for shape in slide.shapes:
        if shape.has_table:
            if table_count == table_index:
                table = shape.table
                for row_idx, row_data in enumerate(rows_data):
                    if row_idx < len(table.rows):
                        for col_idx, cell_value in enumerate(row_data):
                            if col_idx < len(table.columns):
                                cell = table.cell(row_idx, col_idx)
                                cell.text = str(cell_value)
                break
            table_count += 1
```

#### 3c. 更新AUTO_SHAPE标注 (椭圆增速/矩形标签)

```python
def update_auto_shape_text(slide, shape_name, new_text):
    """通过形状名称更新文本"""
    for shape in slide.shapes:
        if shape.name == shape_name and shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                if para.runs:
                    para.runs[0].text = new_text
                    break
            break

def update_auto_shapes_batch(slide, updates):
    """
    批量更新自动形状文本
    updates: [(shape_name, new_text), ...]
    """
    for shape in slide.shapes:
        if shape.has_text_frame:
            for name, text in updates:
                if shape.name == name:
                    if shape.text_frame.paragraphs[0].runs:
                        shape.text_frame.paragraphs[0].runs[0].text = text
                    break
```

### 步骤4: 更新分析文本

```python
def update_analysis_text(slide, text_index, paragraphs):
    """
    更新分析文本框
    text_index: 文本框在slide中的索引(按TEXT_BOX类型排序)
    paragraphs: [段落1文本, 段落2文本, ...]
    """
    text_count = 0
    for shape in slide.shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.TEXT_BOX:
            if text_count == text_index:
                tf = shape.text_frame
                # 保留第一段格式,更新文本
                for i, para_text in enumerate(paragraphs):
                    if i < len(tf.paragraphs):
                        para = tf.paragraphs[i]
                        if para.runs:
                            para.runs[0].text = para_text
                        else:
                            para.text = para_text
                    else:
                        # 添加新段落
                        p = tf.add_paragraph()
                        p.text = para_text
                break
            text_count += 1
```

### 步骤5: 更新标题

```python
def update_title(slide, new_title):
    """更新标题占位符"""
    for shape in slide.shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.PLACEHOLDER:
            if shape.has_text_frame:
                if shape.text_frame.paragraphs[0].runs:
                    shape.text_frame.paragraphs[0].runs[0].text = new_title
                break
```

### 步骤6: 保存

```python
prs.save("output/{年}年{月}月中国乘用车市场分析报告.pptx")
```

---

## 逐页更新指南

### Slide 1 (封面) — 更新年月
- 更新标题: "{year}年{month}月中国乘用车市场分析报告"
- 更新日期: "{year}年{next_month}月"
- 公司名和网址不变

### Slide 3 (零售量) — 整体市场总览
1. 更新标题: "1.2 零售量：{当月核心趋势描述}"
2. 更新分析文本(2段: 当月分析+累计分析)
3. 更新主图表(双Plot):
   - Plot 0: 2系列(2025年零售量, 2026年零售量)，12月类别，数值单位万辆，今年当月+1至12月用None
   - Plot 1: 2系列(2025年增速, 2026增速)，12月类别，增速为小数(如-0.15)
4. 更新表格(4x13):
   - Row 0: 历史月均(12个月值)
   - Row 1: 2025累计(逐月累计)
   - Row 2: 今年累计(1-当月有值，当月+1至12月空)
   - Row 3: 累计增速(百分比字符串)

### Slide 4 (新品驱动) — 新车增量贡献
1. 更新标题: "1.2.4 新品驱动—{当月新品趋势描述}"
2. 更新分析文字(1段，可含◼要点标记)
3. 更新左侧主图表(双Plot):
   - Plot 0: 新车增量，12个月(跨年，当月+1月至当月)，单位: 辆
   - Plot 1: 新车增量贡献率，12个月，小数
4. 更新左侧表格(2x13): 新车数量/车均销量
5. 更新右侧3个子图表(各车型月度销量，单位: 辆)
6. 更新右侧3个子表格(增量贡献度百分比)
7. 车型图片可能需要替换(使用shape.image.replace())

### Slide 5 (库存) — 库存健康度
1. 更新标题: "1.3 库存(行业)：{当月库存趋势描述}"
2. 更新左侧主图表(双Plot):
   - Plot 0: 乘用车库存量，18个月(去年1月至今年当月)，单位: 辆
   - Plot 1: 乘用车存销比，18个月，小数
3. 更新右侧分类图表(双Plot):
   - Plot 0: 库存量，4类别(传统车/新能源/自主/合资)
   - Plot 1: 存销比，4类别对比

### Slide 7-13, 15 (标准对比页) — 通用更新流程
每页更新模式一致(详见 report_structure.md 各页描述):

1. 更新标题: "{章节号} {主题}：{当月核心趋势}"
2. 更新分析文本(2段: 当月分析+累计分析)
3. 更新左侧当月柱状图(COLUMN_CLUSTERED):
   - 2系列(2025/2026)，各类别当月销量(万辆)
4. 更新左侧累计柱状图(COLUMN_CLUSTERED):
   - 2系列(2025/2026)，各类别累计销量(万辆)
5. 更新右侧份额堆叠图(COLUMN_STACKED):
   - N系列(N个类别)，4个时间点(上月/当月/去年全年/今年累计)
6. 更新椭圆AutoShape标注:
   - 当月同比增速(每组柱子上方)
   - 累计同比增速(累计柱状图上方)
7. 更新矩形AutoShape标注:
   - 类别名(每组柱子下方)
   - 份额变化值(堆叠图旁)
8. 更新表格(环比数据行)
9. 更新数据来源文本框

### Slide 9-11 (轿车/SUV/MPV级别) — 额外更新
在标准对比页基础上增加:
10. 更新BAR_CLUSTERED图表(TOP15车型，1系列当月销量)
11. 更新TOP15车型明细表格(16x6: 车型名/同比/环比/级别/份额/排名变化)
12. 更新累计份额汇总表格

### Slide 14 (省份) — 区域市场
1. 更新标题: "2.6 区域市场：{当月区域趋势描述}"
2. 更新分析文本(1段)
3. 更新主图表(双Plot):
   - Plot 0: 31省份当月销量(万辆)
   - Plot 1: 31省份同比增速(小数)
4. 更新区域汇总表格(4x5: 空/同比/当月份额/份额变化)

### Slide 16 (企业竞争) — TOP15企业
1. 更新标题: "2.7 企业竞争：{当月企业竞争描述}"
2. 更新分析文本(2段: 当月+累计)
3. 更新当月柱状图(COLUMN_CLUSTERED): TOP15企业，2系列(2025/2026)
4. 更新累计柱状图(COLUMN_CLUSTERED): TOP15企业，2系列(2025/2026)
5. 更新15个矩形标注(当月企业名) + 15个矩形标注(累计企业名)
6. 更新15个椭圆标注(当月同比增速) + 15个椭圆标注(累计同比增速)
7. 更新表格(4x16: 环比/当月份额/同期份额Δ/环比排名Δ)

### Slide 17 (新能源走势) — 新能源总览
1. 更新标题: "2.8 新能源：{当月新能源趋势描述}"
2. 更新分析文本(2段)
3. 更新LINE_MARKERS图表(12月走势，2系列: 2025/2026新能源销量)
4. 更新COLUMN_CLUSTERED图表(销量及增速对比)
5. 更新COLUMN_STACKED图表(去年1-当月 vs 今年1-当月累计对比)
6. 更新表格1(1x3: 渗透率2025 vs 2026)
7. 更新表格2(1x13: 月度环比12个月)

### Slide 18 (纯电插混) — BEV/PHEV结构
1. 更新标题: "2.8 新能源：{纯电插混趋势描述}"
2. 更新分析文本(1段)
3. 更新主图表(双Plot):
   - Plot 0: 纯电销量+插混销量，13个月(跨年，去年当月至今年当月)
   - Plot 1: 纯电增速+插混增速，13个月
4. 更新副图表(COLUMN_CLUSTERED): 2026年累计，2系列(BEV/PHEV)
5. 更新表格1(4x15: NEV占比BEV/PHEV + 乘用车占比BEV/PHEV，13个月)
6. 更新表格2(2x3: 累计占比+占比变化)
7. 更新AutoShape标注: BEV/PHEV累计销量值 + 增速标注

### Slide 19 (新能源分级别) — BEV/PHEV级别结构
1. 更新标题: "2.8 新能源：{分级别趋势描述}"
2. 更新分析文本
3. 更新4个COLUMN_CLUSTERED图表:
   - BEV单月(5级别: A00/A0/A/B/C+)，2系列(2025/2026)
   - BEV累计，2系列
   - PHEV单月(4级别: A0/A/B/C+)，2系列
   - PHEV累计，2系列
4. 更新4个表格(BEV环比+份额 / BEV累计份额 / PHEV环比+份额 / PHEV累计份额)
5. 更新椭圆标注(BEV+PHEV同比增速)

### Slide 20 (新能源企业) — TOP10新能源企业
同Slide 16模式，替换为TOP10新能源企业:
1. 更新标题: "2.8 新能源：{企业趋势描述}"
2. 更新当月+累计柱状图(TOP10，2系列)
3. 更新10个矩形标注(企业名) + 10个椭圆标注(同比增速)
4. 更新表格(4x11)

### Slide 21 (TOP20车型) — 热销车型排名
1. 更新标题: "附--乘用车市场销量TOP20车型表现"(固定标题，可不含月份)
2. 更新左侧当月TOP20:
   - BAR_CLUSTERED图表(1系列: 2026当月销量，20个车型)
   - 明细表格(21x5: 车型名/同比/环比/份额/级别/排名变化)
   - 汇总表格(1x2: TOP20累计份额)
3. 更新右侧累计TOP20:
   - BAR_CLUSTERED图表(1系列: 2025累计销量，20个车型)
   - 明细表格(21x4: 车型名/同比/份额/级别/排名变化)
   - 汇总表格(1x2: TOP20累计份额)
4. 条形图填充色: 传统车型蓝色，新能源车型绿色

---

## 关键技术注意事项

### 1. think-cell 兼容性
- 报告使用think-cell插件创建图表，表现为EMBEDDED_OLE_OBJECT
- python-pptx可以读取和修改图表数据，但不会影响think-cell链接
- **重要**: 如果用户在PowerPoint中打开生成的文件，think-cell可能会尝试重新链接数据，导致图表数据被覆盖
- **建议方案**: 
  - 方案A: 生成前移除think-cell OLE对象(可能影响图表)
  - 方案B: 生成后告知用户不要在装有think-cell的PowerPoint中打开，或先禁用think-cell
  - 方案C: 使用python-pptx完全重建图表(不依赖think-cell)

### 2. 图表数据更新
- `plot.replace_data()` 方法会替换整个Plot的数据
- 需要保留原始格式(颜色、字体等)，只替换数值
- 对于无类别名的图表(Slide 7+)，需要传入空列表或保持原始类别
- 增速数据使用小数(如-0.15)，图表会自动显示为百分比

### 3. AUTO_SHAPE标注
- 椭圆(Oval)用于同比增速标注，需逐个更新
- 矩形(Rectangle)用于类别名和份额变化值
- 线条(Line)连接柱子和标签，位置可能需要随数据变化调整
- **建议**: 如果柱子高度变化大，需要重新计算线条和标签位置

### 4. 文本格式保留
- 更新文本时，优先修改 `run.text` 而非 `paragraph.text`，以保留字体格式
- 如果run不存在，需要新建run并手动设置字体属性
- 标题: 黑体20pt加粗; 正文: 黑体16pt; 图表标题: 微软雅黑16pt加粗; 数据来源: Arial 9pt

### 5. 表格格式
- 更新单元格文本时，会丢失原有格式
- **建议**: 更新后重新设置字体(黑体/微软雅黑)、大小、对齐方式

### 6. 图片处理 (Slide 4)
- 新车图片可能需要替换
- 使用 `shape.image.replace()` 或删除旧图片后插入新图片

---

## 完整自动化脚本框架

```python
#!/usr/bin/env python3
"""
乘用车市场月度报告自动化生成脚本
输入: 底层数据(Excel) + 模板PPTX
输出: 生成的月度报告PPTX
"""

import os
import sys
import json
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
import openpyxl

class MonthlyReportGenerator:
    def __init__(self, template_path, data_dir, output_path):
        self.prs = Presentation(template_path)
        self.data_dir = data_dir
        self.output_path = output_path
        self.data = {}  # 加载的数据
        
    def load_data(self):
        """从Excel文件加载所有底层数据"""
        pass
    
    def update_cover(self, year, month):
        """更新Slide 1 - 封面"""
        pass
    
    def update_retail_volume(self):
        """更新Slide 3 - 零售量走势"""
        pass
    
    def update_new_products(self):
        """更新Slide 4 - 新品驱动"""
        pass
    
    def update_inventory(self):
        """更新Slide 5 - 库存"""
        pass
    
    def update_standard_comparison_page(self, slide_idx, data, config):
        """
        更新标准对比页(Slide 7-13, 15)
        config: {
            'categories': [...],  # 类别名列表
            'chart_series': [...],  # 图表系列数据
            'table_data': [...],  # 表格数据
            'annotations': [...],  # 标注数据
        }
        """
        pass
    
    def update_vehicle_category(self):
        """更新Slide 7 - 车型类别"""
        pass
    
    def update_top_models(self, slide_idx, vehicle_type):
        """更新Slide 9-11 - 轿车/SUV/MPV TOP15"""
        pass
    
    def update_provinces(self):
        """更新Slide 14 - 省份"""
        pass
    
    def update_enterprise(self, slide_idx, top_n):
        """更新Slide 16/20 - 企业竞争(通用)"""
        pass
    
    def update_nev_trend(self):
        """更新Slide 17 - 新能源走势"""
        pass
    
    def update_nev_bev_phev(self):
        """更新Slide 18 - 纯电插混"""
        pass
    
    def update_nev_by_level(self):
        """更新Slide 19 - 新能源分级别"""
        pass
    
    def update_top20(self):
        """更新Slide 21 - TOP20车型"""
        pass
    
    def save(self):
        """保存生成的报告"""
        self.prs.save(self.output_path)
    
    def generate(self, year, month):
        """主生成流程"""
        self.load_data()
        self.update_cover(year, month)
        self.update_retail_volume()
        self.update_new_products()
        self.update_inventory()
        self.update_vehicle_category()
        # ... 依次更新所有页面
        self.update_top20()
        self.save()

# 使用示例
if __name__ == "__main__":
    generator = MonthlyReportGenerator(
        template_path="assets/template.pptx",
        data_dir="input/{年}年{月}月数据/",
        output_path="output/{年}年{月}月中国乘用车市场分析报告.pptx"
    )
    generator.generate("2026", "6")
```

---

## 数据到图表的映射规则

### 单位转换
- 图表销量数据单位: **万辆** (底层数据可能是辆，需除以10000)
- 增速数据: **小数** (如-0.15，图表自动显示为百分比)
- 表格百分比: **字符串** (如"-15.0%"，"+3.0%")

### 空值处理
- 今年当月+1至12月数据: 图表中使用 `None`，表格中使用空字符串 `""`
- 新车无同比: 使用 `"-"` 或 `">500%"` 或 `">1000%"`

### 排名变化表示
- 无变化: `"--"`
- 上升: `"+1"`，`"+2"`，...
- 下降: `"-1"`，`"-2"`，...

### 能源类型颜色填充
- 传统车型: 蓝色填充
- 新能源车型: 绿色填充
- 用于Slide 21 TOP20车型表格和Slide 9-11 TOP15条形图
