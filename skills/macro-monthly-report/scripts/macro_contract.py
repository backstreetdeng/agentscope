# -*- coding: utf-8 -*-
"""Reviewed, versioned semantics for the 37 native charts in reference.pptx.

Units here describe source cells, not axis display units. Never infer a calendar
from a radar category or infer a quarterly series to be monthly.
"""
from __future__ import annotations
import calendar
from functools import lru_cache
import json
from pathlib import Path
from datetime import date, datetime, timedelta
import re

CONTRACT_VERSION = "macro-typed-v2-public1"
# semantics, frequency, raw unit, authorized publishers, measure
RULES = {
 "s4-shape5": ("time", "monthly", "指数", ["spglobal.com"], "全球PMI"),
 "s4-shape10": ("time", "monthly", "指数", ["spglobal.com", "stats.gov.cn", "ismworld.org"], "制造业PMI"),
 "s8-shape20": ("time", "weekly", "%", ["mysteel.com"], "唐山钢厂高炉开工率"),
 "s8-shape21": ("time", "weekly", "万平方米", ["wind.com.cn"], "房地产成交面积"),
 "s8-shape25": ("time", "weekly", "%", ["mysteel.com"], "全钢胎开工率"),
 "s8-shape11": ("time", "daily", "美元/桶", ["wind.com.cn", "cmegroup.com", "theice.com"], "原油连续期货结算价"),
 "s10-shape7": ("time", "quarterly", "%", ["stats.gov.cn"], "GDP当季同比及平减指数"),
 "s10-shape28": ("time", "quarterly", "百分点", ["stats.gov.cn"], "三大需求对GDP累计增长拉动"),
 "s11-shape12": ("time", "monthly", "指数", ["stats.gov.cn"], "制造业PMI企业规模"),
 "s11-shape15": ("snapshot", "monthly", "指数", ["stats.gov.cn"], "PMI分项指数"),
 "s12-shape13": ("time", "monthly", "指数", ["stats.gov.cn"], "消费者信心指数"),
 "s12-shape16": ("mixed", "monthly", "%", ["stats.gov.cn"], "企业景气与民间投资"),
 "s13-shape10": ("time", "monthly", "%", ["stats.gov.cn"], "工业增加值分行业累计同比"),
 "s13-shape17": ("time", "monthly", "%", ["stats.gov.cn"], "工业增加值同比"),
 "s14-shape15": ("time", "monthly", "亿元", ["stats.gov.cn"], "固定资产投资"),
 "s14-shape11": ("time", "monthly", "%", ["stats.gov.cn"], "投资分领域累计同比"),
 "s15-shape9": ("time", "monthly", "亿元", ["stats.gov.cn"], "社会消费品零售总额"),
 "s16-shape8": ("snapshot", "monthly", "%", ["stats.gov.cn"], "限额以上单位消费品零售当月同比"),
 "s17-shape15": ("time", "monthly", "%", ["stats.gov.cn"], "房地产累计同比"),
 "s17-shape20": ("seasonal", "weekly", "万平方米", ["wind.com.cn"], "30大中城市商品房成交面积"),
 "s18-shape17": ("time", "monthly", "%", ["stats.gov.cn"], "70城新房环比"),
 "s18-shape21": ("time", "monthly", "%", ["stats.gov.cn"], "70城新房同比"),
 "s19-shape13": ("time", "monthly", "亿美元", ["customs.gov.cn"], "美元计价进出口"),
 "s21-shape11": ("time", "monthly", "%", ["stats.gov.cn"], "CPI同比"),
 "s21-shape12": ("category_metrics", "monthly", "%", ["stats.gov.cn"], "CPI分类同比环比"),
 "s22-shape9": ("time", "monthly", "%", ["stats.gov.cn"], "PPI同比环比"),
 "s22-shape10": ("time", "monthly", "%", ["stats.gov.cn"], "PPI分项同比"),
 "s24-shape9": ("seasonal", "monthly", "亿元", ["pbc.gov.cn"], "新增人民币贷款"),
 "s24-shape17": ("snapshot", "monthly", "亿元", ["pbc.gov.cn"], "新增贷款部门结构"),
 "s25-shape9": ("seasonal", "monthly", "亿元", ["pbc.gov.cn"], "社会融资规模增量"),
 "s25-shape10": ("time", "monthly", "亿元", ["pbc.gov.cn"], "社会融资规模增量结构"),
 "s26-shape11": ("time", "monthly", "%", ["pbc.gov.cn"], "货币供应量同比"),
 "s26-shape12": ("time", "monthly", "%", ["pbc.gov.cn"], "货币与社融存量同比"),
 "s28-shape11": ("seasonal_current", "monthly", "辆", ["cpcaauto.com"], "乘联分会乘用车零售"),
 "s28-shape17": ("time", "monthly", "%", ["cpcaauto.com", "stats.gov.cn"], "零售和汽车制造业利润累计同比"),
 "s30-shape13": ("time", "monthly", "亿元", ["mof.gov.cn"], "一般公共预算累计收支"),
 "s30-shape18": ("time", "announcement_monthly", "%", ["pbc.gov.cn", "chinamoney.com.cn"], "贷款市场报价利率LPR"),
}
TEXT_SLOTS = {
 4:(2,[19],12), 10:(5,[6],11), 11:(9,[6],10), 12:(2,[4],10),
 13:(2,[4],12), 14:(2,[16],10), 15:(2,[4],10), 16:(2,[4],10),
 17:(2,[16],10),18:(2,[16],10),19:(9,[10],8),21:(5,[6],8),
 22:(2,[4],8),24:(2,[4],12),25:(2,[4],12),26:(5,[6],13),
 28:(5,[6],13),30:(9,[10],7),32:(10,[6],7),
}
STATIC_HINTS = ("分界", "荣枯", "临界", "基准线", "阈值")
OVERVIEW_ROWS = [
 ("GDP当季同比", "s10-shape7", "GDP:不变价:当季同比", "%"),
 ("工业增加值当月同比", "s13-shape17", "当月同比", "%"),
 ("CPI同比", "s21-shape11", "CPI", "%"), ("PPI同比", "s22-shape9", "同比", "%"),
 ("社会消费品零售当月同比", "s15-shape9", "当月同比", "%"),
 ("制造业PMI", "s11-shape12", "PMI", "指数"),
 ("固定资产投资累计同比", "s14-shape15", "固定资产投资累计同比", "%"),
 ("进口金额当月同比", "s19-shape13", "进口金额:当月同比", "%"),
 ("出口金额当月同比", "s19-shape13", "出口金额:当月同比", "%"),
 ("房地产投资累计同比", "s14-shape11", "房地产", "%"),
 ("商品房销售面积累计同比", "s17-shape15", "销售面积", "%"),
 ("M2同比", "s26-shape11", "M2", "%"),
 ("新增人民币贷款", "s24-shape9", "", "万亿元"),
 ("发电量当月同比", "overview::发电量当月同比", "", "%"),
 ("钢材产量当月同比", "overview::钢材产量当月同比", "", "%"),
 ("水泥产量当月同比", "overview::水泥产量当月同比", "", "%"),
]

def month_end(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])

def parse_period(value, frequency="monthly"):
    if isinstance(value, (date, datetime)):
        result = value.date() if isinstance(value, datetime) else value
    else:
        text = str(value).strip()
        if re.fullmatch(r"\d+(?:\.\d+)?", text) and 30000 < float(text) < 90000:
            result = date(1899,12,30) + timedelta(days=int(float(text)))
        else:
            quarter = re.search(r"(20\d{2})\s*[-年]?\s*[Qq]([1-4])", text)
            match = re.search(r"(20\d{2})[-/.年](\d{1,2})(?:[-/.月](\d{1,2}))?",text)
            if quarter:
                result = month_end(int(quarter[1]),int(quarter[2])*3)
            elif match:
                y,m = int(match[1]),int(match[2])
                result = date(y,m,int(match[3])) if match[3] else month_end(y,m)
            else:
                raise ValueError("Not a calendar period: " + text)
    if frequency == "quarterly":
        result = month_end(result.year, ((result.month-1)//3+1)*3)
    elif frequency == "monthly":
        result = month_end(result.year,result.month)
    return result

def static_series(name, values):
    # A real PMI can legitimately equal 50 in several periods. Values cannot
    # identify a reference line; only the reviewed semantic role/name can.
    return any(x in name for x in STATIC_HINTS)

def series_unit(chart_id, name, default):
    if chart_id == "s10-shape28" and "GDP" in name: return "%"
    if chart_id == "s12-shape16" and "景气" in name: return "指数"
    if any(x in name for x in ("同比", "环比", "增速")): return "%"
    return default


def official_labels(cid, name, definition, category=None):
    """Exact publisher labels and mandatory scope groups for literal proof."""
    aliases=[definition,name]; groups=[]; domains=None
    if cid=="s4-shape5":
        aliases=(["全球综合PMI","Global Composite PMI","Global Composite Output Index"] if "综合" in name else
                 ["全球服务业PMI","Global Services PMI","Global Services Business Activity Index"] if "服务" in name else
                 ["全球制造业PMI","Global Manufacturing PMI"])
        groups=[["全球","Global"]]
    elif cid=="s4-shape10":
        country={"美国":["美国","United States","U.S.","US Manufacturing"],"日本":["日本","Japan","Japanese"],
                 "欧元区":["欧元区","Eurozone","Euro area"],"中国":["中国","China","Chinese"]}[name]
        groups=[country,["制造业","Manufacturing"]]
        if name=="美国":
            aliases=["美国制造业PMI","ISM Manufacturing PMI","Manufacturing PMI"];domains=["ismworld.org"]
            groups.append(["ISM","Institute for Supply Management"])
        elif name=="日本":aliases=["日本制造业PMI","Japan Manufacturing PMI","Manufacturing PMI"];domains=["spglobal.com"]
        elif name=="欧元区":aliases=["欧元区制造业PMI","Eurozone Manufacturing PMI","Manufacturing PMI"];domains=["spglobal.com"]
        else:aliases=["制造业采购经理指数","制造业PMI","PMI"];domains=["stats.gov.cn"]
    elif cid=="s8-shape20":
        aliases=["唐山钢厂高炉开工率","唐山高炉开工率","高炉开工率"];groups=[["唐山"],["高炉"],["开工率"]]
    elif cid=="s8-shape21":
        land="土地" in name
        aliases=["土地成交面积"] if land else ["商品房成交面积"]
        groups=[["100大中城市","100个大中城市"] if land else ["30大中城市","30个大中城市"], ["土地"] if land else ["商品房"]]
    elif cid=="s8-shape25":aliases=["全钢胎开工率","全钢胎","全钢轮胎"];groups=[["全钢胎","全钢轮胎"],["开工率"]]
    elif cid=="s8-shape11":
        aliases=["WTI","West Texas Intermediate"] if "WTI" in name else ["布伦特","Brent"]
        # EIA/FRED spot prices cannot replace the original continuous futures.
        groups=[["期货","futures"],["结算价","settlement"],["连续","continuous"]]
        domains=["wind.com.cn","cmegroup.com"] if "WTI" in name else ["wind.com.cn","theice.com"]
    elif cid in {"s10-shape7","s10-shape28"}:
        if "平减" in name:aliases=["GDP平减指数","国内生产总值平减指数","GDP deflator"]
        elif "消费" in name:aliases=["最终消费支出","消费支出拉动"];groups=[["拉动","贡献","contribution"]]
        elif "资本" in name:aliases=["资本形成总额","资本形成拉动"];groups=[["拉动","贡献","contribution"]]
        elif "净出口" in name:aliases=["货物和服务净出口","净出口拉动"];groups=[["拉动","贡献","contribution"]]
        else:aliases=["国内生产总值","GDP"];groups=[["同比","year-on-year"],["不变价格","不变价","real"]]
        if "累计" in name:groups.append(["累计","上半年","前三季度","全年","一季度"])
        elif "当季" in name:groups.append(["季度","quarter"])
    elif cid=="s11-shape12":
        aliases=["大型企业"] if "大型" in name else ["中型企业"] if "中型" in name else ["小型企业"] if "小型" in name else ["制造业采购经理指数","制造业PMI","PMI"]
        groups=[["制造业"],["采购经理指数","PMI"]]
    elif cid=="s11-shape15":
        aliases=[str(category),str(category)+"指数"]
        groups=[["制造业"],["采购经理指数","PMI"]]
    elif cid=="s12-shape13":
        aliases=(["收入信心指数","收入"] if "收入" in name else ["消费意愿指数","消费意愿"] if "消费意愿" in name else
                 ["消费者预期指数","消费者预期"] if "预期" in name else ["消费者信心指数"])
        groups=[["消费者信心","消费者预期","消费意愿"]]
    elif cid=="s12-shape16":
        if "景气" in name:aliases=["企业景气预期指数","企业景气指数","预期指数"];groups=[["企业景气"],["预期"]]
        else:aliases=["民间固定资产投资","民间投资"];groups=[["民间"],["投资"],["累计","1—","1-","1至"]]
    elif cid in {"s13-shape10","s13-shape17"}:
        aliases=(["高技术制造业","高技术产业"] if "高技术" in name else ["采矿业"] if "采矿" in name else
                 ["电力、热力、燃气及水生产和供应业","电力、燃气及水的生产和供应业"] if "电力" in name else
                 ["制造业"] if "制造" in name else ["规模以上工业增加值","工业增加值"])
        groups=[["增加值"],["同比"]]
        if "累计" in name:groups.append(["累计","1—","1-","1至"])
    elif cid=="s14-shape15":
        aliases=["民间固定资产投资","民间投资"] if "民间" in name else ["固定资产投资"]
        groups=[["累计","1—","1-","1至"]]
        if "同比" in name:groups.append(["同比"])
    elif cid=="s14-shape11":
        aliases={"房地产":["房地产开发投资"],"制造业":["制造业投资"],"基建":["基础设施投资"]}[name]
        groups=[["累计","1—","1-","1至"],["同比"]]
        if name=="基建":groups.append(["不含电力","不包括电力"])
    elif cid=="s15-shape9":
        aliases=["社会消费品零售总额"]
        if "同比" in name:groups.append(["同比"])
        if "累计" in name:groups.append(["累计","1—","1-","1至"])
    elif cid=="s16-shape8":
        aliases=[str(category)]+(["社会消费品零售总额"] if category=="零售总额" else [])
        groups=[["零售","餐饮"],["同比"]]
        if category not in {"零售总额","餐饮收入","商品零售"}:groups.append(["限额以上"])
    elif cid=="s17-shape15":
        aliases=["新建商品房销售额","商品房销售额"] if "销售额" in name else ["新建商品房销售面积","商品房销售面积"] if "销售面积" in name else ["商品房待售面积"]
        groups=[["同比"]]
        if "待售" not in name:groups.append(["累计","1—","1-","1至"])
    elif cid=="s17-shape20":aliases=["商品房成交面积"];groups=[["30大中城市","30个大中城市"],["成交面积"]]
    elif cid in {"s18-shape17","s18-shape21"}:aliases=[name];groups=[["新建商品住宅"],["环比"] if cid.endswith("shape17") else ["同比"]]
    elif cid=="s19-shape13":
        aliases=["贸易差额","贸易顺差","进出口差额"] if "差额" in name else ["出口"] if "出口" in name else ["进口"]
        groups=[["美元","US dollar","USD"]]
        if "同比" in name:groups.append(["同比","year-on-year"])
    elif cid=="s21-shape11":
        aliases=["核心CPI","扣除食品和能源价格的核心CPI"] if "核心" in name else ["食品价格"] if "食品" in name else ["居民消费价格","CPI"]
        groups=[["同比"]]
    elif cid=="s21-shape12":
        aliases={"食品":["食品价格"],"交通通信":["交通通信","交通和通信"],
                 "教育文化和娱乐":["教育文化娱乐","教育文化和娱乐"],
                 "其他用品服务":["其他用品及服务","其他用品服务"]}.get(str(category),[str(category)])
        # Food and the broader food/tobacco/alcohol basket are different.
        # A generic 食品 substring must not prove a 食品烟酒 table row.
        groups=[["居民消费价格","CPI"],[name]]
    elif cid in {"s22-shape9","s22-shape10"}:
        aliases=["工业生产者出厂价格","PPI"] if cid.endswith("shape9") else ["工业生产者出厂价格","全部工业品"] if "全部" in name else [name]
        groups=[["工业生产者出厂价格","PPI"],["环比"] if "环比" in name else ["同比"]]
    elif cid=="s24-shape9":aliases=["人民币贷款","人民币贷款增加","人民币贷款新增"];groups=[["人民币贷款"],["增加","新增","减少"]]
    elif cid=="s24-shape17":
        if int(category)==4:aliases=["票据融资"];groups=[["贷款"]]
        else:
            aliases=["短期贷款"] if int(category)%2==0 else ["中长期贷款"]
            groups=[["住户","居民"] if int(category)<2 else ["企（事）业单位","企事业单位","企业"],["贷款"]]
    elif cid=="s25-shape9":aliases=["社会融资规模增量","新增社会融资规模"];groups=[["社会融资规模"],["增量","新增"]]
    elif cid=="s25-shape10":
        aliases={"贷款":["对实体经济发放的人民币贷款"],"非标融资":["非标融资","非标准化融资"],"直接融资":["直接融资"],"政府债券":["政府债券融资"]}[name]
        groups=[["社会融资规模"],["增量","新增"]]
    elif cid=="s26-shape11":aliases=["狭义货币","M1"] if "M1" in name else ["广义货币","M2"];groups=[["同比"]]
    elif cid=="s26-shape12":aliases=["广义货币","M2"] if "M2" in name else ["社会融资规模存量"];groups=[["同比"]]
    elif cid=="s28-shape11":
        aliases=["新能源乘用车零售","新能源乘用车市场零售"] if "新能源" in name else ["乘用车市场零售","乘用车零售"]
        groups=[["零售"],["新能源"]] if "新能源" in name else [["零售"]]
        if "同比" in name:groups.append(["同比"])
    elif cid=="s28-shape17":
        if "利润" in name:aliases=["汽车制造业"];domains=["stats.gov.cn"];groups=[["利润"],["同比"],["累计","1—","1-","1至"]]
        else:aliases=["乘用车市场零售","乘用车零售"];domains=["cpcaauto.com"];groups=[["零售"],["累计","1—","1-","1至"],["同比"]]
    elif cid=="s30-shape13":
        aliases=["一般公共预算收入"] if "收入" in name else ["一般公共预算支出"]
        groups=[["全国"],["累计","1—","1-","1至","上半年","前三季度","全年"]]
        if "增速" in name:groups.append(["同比"])
    elif cid=="s30-shape18":
        aliases=["1年期LPR","1年期"] if "1年" in name else ["5年期以上LPR","5年期以上"]
        groups=[["贷款市场报价利率","LPR"]]
    return list(dict.fromkeys(x for x in aliases if x)),groups,domains


def template_latest_period(chart, series_name, frequency, category_index=None):
    """Discovery hint, never proof authorizing template facts or forecasting."""
    semantics=RULES[chart["id"]][0];periods=[]
    if semantics in {"time","mixed"}:
        series=next((s for s in chart["series"] if s["name"]==series_name),None)
        for raw,value in zip(chart["categories"],series["values"] if series else []):
            if value is None:continue
            day=parse_period(raw,"daily")
            if frequency=="quarterly" and day.month not in {3,6,9,12}:continue
            periods.append(parse_period(raw,frequency))
    elif semantics in {"snapshot","category_metrics"}:
        for series in chart["series"]:
            if category_index is not None and series["values"][category_index] is None:continue
            try:periods.append(parse_period(series["name"],frequency))
            except ValueError:pass
        if not periods and chart.get("reference_month"):periods.append(parse_period(chart["reference_month"],frequency))
    elif chart.get("reference_month"):
        year=int(chart["reference_month"][:4])
        series=next((s for s in chart["series"] if s["name"]==series_name or str(year)==str(s["name"])),None)
        if series:
            for index,value in enumerate(series["values"]):
                if value is None:continue
                if frequency=="weekly":
                    try:periods.append(date.fromisocalendar(year,index+1,7))
                    except ValueError:pass
                else:periods.append(month_end(year,index+1))
    if not periods:return ""
    latest=max(periods)
    if frequency=="quarterly":return f"{latest.year}-Q{(latest.month-1)//3+1}"
    return latest.isoformat() if frequency in {"daily","weekly","announcement_monthly"} else latest.strftime("%Y-%m")


@lru_cache(maxsize=1)
def public_source_policy():
    path=Path(__file__).resolve().parents[1]/"references/public-source-policy.json"
    return json.loads(path.read_text(encoding="utf-8"))


def attach_public_source_policy(request):
    """Supplier labels are provenance, not credentials required from users."""
    policy=public_source_policy();cid=request.get("chart_id")
    original=list(dict.fromkeys(request["source_domains"]+policy.get("additional_original_domains",{}).get(cid,[])))
    request["source_domains"]=original
    request["original_publisher_domains"]=original
    if cid not in policy["high_frequency_charts"]:
        return request
    request["secondary_source_domains"]=policy["secondary_source_domains"]
    request["secondary_publishers"]={}
    for publisher in policy["publishers"]:
        for domain in list(dict.fromkeys(publisher["domains"]+policy["mirror_domains"])):
            request["secondary_publishers"].setdefault(domain,[]).append(publisher)
    request["origin_attribution_aliases"]=policy["origin_attribution_by_chart"][cid]
    request["secondary_latest_corroboration_required"]=True
    return request

def request_contract(chart):
    cid = chart["id"]
    semantics,frequency,unit,domains,measure = RULES[cid]
    requests = []
    def add(rid, name, definition, raw_unit, freq=frequency, category_index=None, label=None):
        aliases,context,own_domains=official_labels(cid,name,definition,label if label is not None else category_index)
        source_domains=own_domains or domains
        # Reuse publisher releases across their many chart series. This query
        # is discovery only; each returned number still needs exact scope proof.
        query_label=measure
        if cid=="s4-shape10":query_label=("ISM " if name=="美国" else "")+name+" 制造业PMI"
        if cid=="s28-shape17":query_label="汽车制造业利润" if "利润" in name else "乘用车市场零售"
        item = {"id":rid,"chart_id":cid,"series_name":name,"definition":definition,
            "definition_aliases":aliases,"context_groups":context,
            "unit":raw_unit,"frequency":freq,"source_domains":source_domains,
            "template_latest_period":template_latest_period(chart,name,freq,category_index),
            "history_count": 4 if freq == "quarterly" else 10 if freq == "daily" else 8 if freq == "weekly" else 3,
            "query":f"{query_label} 最新发布 原始历史数据 " + "(" + " OR ".join("site:"+d for d in source_domains) + ")"}
        attach_public_source_policy(item)
        if category_index is not None: item["category_index"] = category_index
        requests.append(item)
    if semantics in {"time","mixed","seasonal_current"}:
        for s in chart["series"]:
            if static_series(s["name"], s["values"]): continue
            freq = "quarterly" if cid == "s12-shape16" and "景气" in s["name"] else frequency
            name = s["name"]
            add(cid+"::"+name,name,measure+"："+name,series_unit(cid,name,unit),freq)
    elif semantics == "seasonal":
        add(cid+"::current", "current", measure, unit)
    elif semantics == "snapshot":
        loan_names = ["住户短期贷款","住户中长期贷款","企事业单位短期贷款","企事业单位中长期贷款","票据融资"]
        for i,category in enumerate(chart["categories"]):
            definition = loan_names[i] if cid == "s24-shape17" else measure+"："+str(category)
            add(cid+f"::category{i}","snapshot",definition,unit,category_index=i,label=category if cid!="s24-shape17" else i)
    else:
        for s in chart["series"]:
            for i,category in enumerate(chart["categories"]):
                add(cid+"::"+s["name"]+f"::category{i}",s["name"],measure+"："+str(category)+"："+s["name"],unit,category_index=i,label=category)
    return requests

def attach_contract(inventory):
    charts = [c for slide in inventory["slides"] for c in slide["charts"]]
    actual = {c["id"] for c in charts}
    if actual != set(RULES):
        raise ValueError("Template/contract drift: " + str(actual.symmetric_difference(RULES)))
    requests = []
    cover=" ".join(t["text"] for t in inventory["slides"][0]["texts"])
    cover_month=re.search(r"(20\d{2})年(\d{1,2})月.*报告",cover)
    reference_month=f"{cover_month[1]}-{int(cover_month[2]):02d}" if cover_month else ""
    for c in charts:
        semantic,frequency,unit,domains,measure=RULES[c["id"]]
        c.update(semantics=semantic,frequency=frequency,raw_unit=unit,source_domains=domains,definition=measure,reference_month=reference_month)
        c["requests"] = request_contract(c)
        requests.extend(c["requests"])
    for label,_,_,unit in OVERVIEW_ROWS[-3:]:
        indicator=label.replace("当月同比", "")
        request={"id":"overview::"+label,"chart_id":"overview","series_name":indicator,
            "definition":label,"definition_aliases":[label,indicator]+(["规模以上工业发电量"] if indicator=="发电量" else ["钢材"] if indicator=="钢材产量" else ["水泥"] if indicator=="水泥产量" else []),"context_groups":[["同比"],["当月","月份"]],
            "frequency":"monthly","history_count":3,"template_latest_period":reference_month,
            "unit":unit,"source_domains":["stats.gov.cn"],
            "query":indicator+" 最新发布 原始历史数据 site:stats.gov.cn"}
        requests.append(attach_public_source_policy(request))
    inventory.update(contract_version=CONTRACT_VERSION,source_requests=requests,table_count_after_update=2)
    return inventory
