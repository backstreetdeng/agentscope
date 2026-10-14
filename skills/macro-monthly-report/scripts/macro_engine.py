# -*- coding: utf-8 -*-
"""Typed macro updater. Source facts and projections are separate data layers.

The immutable reference supplies layout and archival chart history only. It is
never proof of the latest actual and never used as an unverified forecast fit.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
import zipfile

from lxml import etree
from openpyxl import load_workbook
from openpyxl.utils.cell import range_boundaries, get_column_letter
from openpyxl.utils.datetime import to_excel
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Pt

from inspect_macro_template import inventory, all_shapes
from macro_contract import CONTRACT_VERSION, TEXT_SLOTS, OVERVIEW_ROWS, parse_period, month_end, static_series
from macro_constraints import validate_constraints

NS = {"c":"http://schemas.openxmlformats.org/drawingml/2006/chart", "a":"http://schemas.openxmlformats.org/drawingml/2006/main"}
def C(name): return "{"+NS["c"]+"}"+name
def A(name): return "{"+NS["a"]+"}"+name
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path, value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")

def normalize_series(periods, values, frequency):
    """Chronological, finite, unique same-frequency observations, no zero-fill."""
    result = {}
    for period,value in zip(periods,values):
        if value is None or isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value): continue
        d=parse_period(period,frequency)
        if frequency == "quarterly":
            raw=parse_period(period,"daily")
            if raw.month not in {3,6,9,12}: continue
        if d in result and result[d] != float(value): raise ValueError("duplicate_period_conflict")
        result[d]=float(value)
    return sorted(result.items())

def advance(period, frequency):
    if frequency == "daily":
        result=period+timedelta(days=1)
        while result.weekday()>4: result+=timedelta(days=1)
        return result
    if frequency == "weekly": return period+timedelta(days=7)
    months=3 if frequency=="quarterly" else 1
    key=period.year*12+period.month-1+months
    return month_end(key//12,key%12+1)

def forecast_series(observations, target, frequency="monthly", unit="%", policy=False):
    """Walk-forward selected simple baseline; never forecast across categories.

    Monthly/quarterly inputs need several independently evidenced periods.
    Small samples select conservative level forecasts, not spurious causality.
    """
    points=sorted(observations)
    minimum=4 if frequency=="quarterly" else 8 if frequency=="weekly" else 10 if frequency=="daily" else 3
    if policy: minimum=1
    if len(points)<minimum: raise ValueError("forecast_verified_history_insufficient")
    last=points[-1][0]
    future=[]
    cursor=advance(last,"monthly" if frequency=="announcement_monthly" else frequency)
    while cursor<=target:
        future.append(cursor)
        if len(future)> (65 if frequency=="daily" else 13 if frequency=="weekly" else 3):
            raise ValueError("forecast_horizon_too_long")
        cursor=advance(cursor,"monthly" if frequency=="announcement_monthly" else frequency)
    if not future: return {"values":[],"method":"none","training_periods":[],"backtest_mae":None}
    values=[v for _,v in points]
    season=4 if frequency=="quarterly" else 12 if frequency=="monthly" else 0
    methods=["last","mean3"]
    if len(values)>=6 and not policy: methods.append("damped_trend")
    if season and len(values)>=season+minimum: methods.append("seasonal")
    if policy: methods=["policy_hold_scenario"]
    def predict(history,method):
        if method in {"last","policy_hold_scenario"}: return history[-1]
        if method=="mean3": return statistics.mean(history[-3:])
        if method=="seasonal": return history[-season]
        slope=statistics.median([history[i]-history[i-1] for i in range(max(1,len(history)-4),len(history))])
        return history[-1]+0.5*slope
    scores={}
    for method in methods:
        errors=[]
        start=max(2,len(values)-6,season if method=="seasonal" else 2)
        for i in range(start,len(values)): errors.append(abs(predict(values[:i],method)-values[i]))
        scores[method]=statistics.mean(errors) if errors else 0.0
    method=min(methods,key=lambda m:(scores[m],methods.index(m)))
    train=list(values)
    margin=max(scores[method]*1.96,statistics.pstdev(values[-min(6,len(values)):])*0.5,0.1)
    predicted=[]
    for step,period in enumerate(future,1):
        value=predict(train,method)
        if unit=="指数": value=max(0.0,min(200.0,value))
        elif unit in {"美元/桶","辆","万平方米"}: value=max(0.0,value)
        predicted.append({"period":period.isoformat(),"value":round(value,4),"lower":round(value-margin*math.sqrt(step),4),"upper":round(value+margin*math.sqrt(step),4),"status":"forecast"})
        train.append(value)
    return {"values":predicted,"method":method,"training_periods":[p.isoformat() for p,_ in points],
        "training_values":values,"backtest_mae":scores[method],"candidate_mae":scores,
        "assumption":"维持现行政策利率的情景假设，不是新公告" if policy else "基于同口径已核验历史的统计基线，不解释未取证原因"}

def verified_observations(package, contract, source_root):
    """Independently replay publisher text checks, don't trust 'ready' flags."""
    from macro_sources import validate_observation, expected_latest_period, verify_source_corroboration
    if package.get("synthetic") or package.get("data_kind") in {"fixture","synthetic","test"}:
        raise ValueError("synthetic_data_not_business_evidence")
    requests={r["id"]:r for r in contract["source_requests"]}
    pages={}
    for path in (Path(source_root)/"working/macro-sources/pages").glob("*.json"):
        page=json.loads(path.read_text(encoding="utf-8"))
        if page.get("text_sha256") != hashlib.sha256(str(page.get("text","")).encode()).hexdigest():
            raise ValueError("source_checkpoint_hash_mismatch")
        if page.get("synthetic") or page.get("fetch_provider") not in {"direct-primary-publisher", "direct-public-publisher"} or not page.get("fetched_at"):
            raise ValueError("source_receipt_not_live")
        pages[page.get("receipt_id")]=page
    cutoff=date.fromisoformat(package["cutoff_date"])
    observations={rid:[] for rid in requests}
    # Independently prove the real publisher and upstream attribution of public
    # research, not merely a whitelisted storage domain. Secondary latest facts
    # require two distinct original publishers; copies of one report are one.
    replay=verify_source_corroboration(package,contract,pages)
    if replay.get("issues"):
        first=replay["issues"][0]
        raise ValueError("source_corroboration_failed:"+str(first.get("code",first)))
    for observation in replay.get("observations",[]):
        rid=observation.get("request_id")
        if rid not in requests: raise ValueError("unexpected_source_request")
        page=pages.get(observation.get("receipt_id"))
        if not page: raise ValueError("source_receipt_missing_original_page")
        item=validate_observation(observation,requests[rid],page,cutoff,package["report_month"])
        d=parse_period(item["period"],requests[rid]["frequency"])
        if requests[rid]["frequency"]=="announcement_monthly" and len(item["period"])==7:
            d=date.fromisoformat(item["published_at"])
            if d.strftime("%Y-%m")!=item["period"]: raise ValueError("announcement_month_mismatch")
        observations[rid].append({**item,"date":d})
    for rid,request in requests.items():
        if observations[rid]:
            threshold=expected_latest_period(request,cutoff,package["report_month"])
            latest=max(o["date"] for o in observations[rid])
            if threshold:
                freq=request["frequency"]
                latest_check=parse_period(latest,"monthly") if freq=="announcement_monthly" else latest
                if latest_check<parse_period(threshold,"monthly" if freq=="announcement_monthly" else freq):
                    raise ValueError("latest_actual_not_current_as_of_cutoff:"+rid)
        if request.get("template_latest_period") and observations[rid]:
            latest=max(o["date"] for o in observations[rid])
            if latest<parse_period(request["template_latest_period"],request["frequency"]):
                raise ValueError("latest_actual_older_than_template:"+rid)
    return observations

def _series_name(ser):
    values=ser.findall("./"+C("tx")+"//"+C("v"))
    return values[0].text if values else ""

def _range(formula, count):
    sheet,area=formula.rsplit("!",1)
    c1,r1,c2,r2=range_boundaries(area.replace("$",""))
    if c1!=c2: raise ValueError("chart_formula_not_single_column")
    return sheet.strip("'"),c1,r1,r2, f"{sheet}!${get_column_letter(c1)}${r1}:${get_column_letter(c1)}${r1+count-1}"

def _set_cache(reference, values, workbook, names=False):
    cache_tag="strCache" if names else "numCache"
    cache=reference.find(C(cache_tag))
    if cache is None: cache=etree.SubElement(reference,C(cache_tag))
    fmt=cache.find(C("formatCode"))
    fmt_text=fmt.text if fmt is not None else "General"
    for child in list(cache): cache.remove(child)
    if not names: etree.SubElement(cache,C("formatCode")).text=fmt_text
    etree.SubElement(cache,C("ptCount"),val=str(len(values)))
    formula=reference.find(C("f"))
    sheet,col,start,oldend,newformula=_range(formula.text,len(values))
    formula.text=newformula
    ws=workbook[sheet]
    for row in range(start,max(oldend,start+len(values)-1)+1): ws.cell(row,col).value=None
    for i,value in enumerate(values):
        if value is None: continue
        point=etree.SubElement(cache,C("pt"),idx=str(i))
        etree.SubElement(point,C("v")).text=str(value)
        ws.cell(start+i,col).value=value

def update_native_chart(chart, rebuilt):
    """Keep each original series' plot, axis and formulas; update cache+xlsx."""
    xml=chart._chartSpace
    workbook_rel=xml.find(C("externalData"))
    if workbook_rel is None: raise ValueError("native_chart_has_no_workbook")
    relid=workbook_rel.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
    part=chart.part.related_part(relid)
    workbook=load_workbook(io.BytesIO(part.blob))
    originals=list(xml.xpath(".//c:ser"))
    inherited_cat=next((ser.find(C("cat")) for ser in originals if ser.find(C("cat")) is not None),None)
    lookup={s["original_name"]:s for s in rebuilt["series"]}
    maxidx=max(int(x.get("val")) for ser in originals for x in ser.xpath("./c:idx"))
    for ser in originals:
        name=_series_name(ser)
        item=lookup.get(name)
        if item is None: raise ValueError("series_contract_missing:"+name)
        tx=ser.find(C("tx"))
        if item["name"]!=name:
            txref=tx.find(C("strRef"))
            if txref is not None:
                formula=txref.find(C("f")).text
                sheet,area=formula.rsplit("!",1)
                workbook[sheet.strip("'")][area.replace("$","")]=item["name"]
                for v in txref.findall(".//"+C("v")): v.text=item["name"]
            else:
                for v in tx.findall(".//"+C("v")): v.text=item["name"]
        cat=ser.find(C("cat"))
        if cat is None:
            if inherited_cat is None: raise ValueError("chart_category_contract_missing")
            cat=deepcopy(inherited_cat)
            value_node=ser.find(C("val"))
            ser.insert(list(ser).index(value_node),cat)
        ref=cat.find(C("numRef"))
        categories=rebuilt["categories"]
        if cat.find(C("multiLvlStrRef")) is not None:
            if rebuilt["semantics"] != "snapshot": raise ValueError("unreviewed_multilevel_category")
            # Household/corporate hierarchical category headers remain immutable.
        elif ref is None:
            ref=cat.find(C("strRef")); _set_cache(ref,categories,workbook,True)
        else: _set_cache(ref,categories,workbook)
        valref=ser.find("./"+C("val")+"/"+C("numRef"))
        _set_cache(valref,item["actual_values"],workbook)
        if any(v is not None for v in item["forecast_values"]):
            forecast=deepcopy(ser)
            maxidx+=1
            forecast.find(C("idx")).set("val",str(maxidx))
            forecast.find(C("order")).set("val",str(maxidx))
            ftx=forecast.find(C("tx"))
            for child in list(ftx): ftx.remove(child)
            etree.SubElement(ftx,C("v")).text=item["name"]+"（预测）"
            fref=forecast.find("./"+C("val")+"/"+C("numRef"))
            old=fref.find(C("f"))
            _,_,start,_,_= _range(old.text,len(categories))
            col=workbook.active.max_column+1
            # An independent column prevents prediction cache from overwriting actuals.
            old.text=f"'{workbook.active.title}'!${get_column_letter(col)}${start}:${get_column_letter(col)}${start+len(categories)-1}"
            workbook.active.cell(1,col).value=item["name"]+"（预测）"
            _set_cache(fref,item["forecast_values"],workbook)
            sp=forecast.find(C("spPr"))
            if sp is None:
                sp=etree.Element(C("spPr"));forecast.insert(3,sp)
            if ser.getparent().tag==C("barChart"):
                for fill in list(sp):
                    if fill.tag in {A("solidFill"),A("gradFill"),A("pattFill"),A("noFill")}:
                        sp.remove(fill)
                fill=etree.Element(A("pattFill"),prst="ltDnDiag")
                fg=etree.SubElement(fill,A("fgClr"));etree.SubElement(fg,A("srgbClr"),val="6E91C1")
                bg=etree.SubElement(fill,A("bgClr"));etree.SubElement(bg,A("srgbClr"),val="EDF3FB")
                sp.insert(0,fill)
            ln=sp.find(A("ln"))
            if ln is None: ln=etree.SubElement(sp,A("ln"))
            for dash in ln.findall(A("prstDash")): ln.remove(dash)
            etree.SubElement(ln,A("prstDash"),val="dash")
            if ser.getparent().tag in {C("lineChart"),C("radarChart"),C("scatterChart")}:
                marker=forecast.find(C("marker"))
                if marker is None:
                    marker=etree.Element(C("marker"))
                    insert_after=forecast.find(C("spPr"))
                    forecast.insert(list(forecast).index(insert_after)+1,marker)
                symbol=marker.find(C("symbol"))
                if symbol is None: symbol=etree.SubElement(marker,C("symbol"))
                symbol.set("val","diamond")
                size=marker.find(C("size"))
                if size is None: size=etree.SubElement(marker,C("size"))
                size.set("val","6")
            plot=ser.getparent()
            last_series=list(plot.findall(C("ser")))[-1]
            plot.insert(list(plot).index(last_series)+1,forecast)
    # Date limits must move with categories; leave calendar number format intact.
    if rebuilt["semantics"] in {"time","mixed"}:
        numbers=[float(v) for v in rebuilt["categories"]]
        for axis in xml.findall(".//"+C("dateAx")):
            scaling=axis.find(C("scaling"))
            for key,value in (("min",min(numbers)),("max",max(numbers))):
                bound=scaling.find(C(key))
                if bound is None: bound=etree.SubElement(scaling,C(key))
                bound.set("val",str(value))
            span=max(numbers)-min(numbers)
            monthly=rebuilt["frequency"] in {"monthly","quarterly","announcement_monthly"}
            interval=max(1,math.ceil(span/(30.4375*8))) if monthly else max(1,math.ceil(span/8))
            for tag,val in (("majorTimeUnit","months" if monthly else "days"),("majorUnit",str(interval))):
                node=axis.find(C(tag))
                if node is None: node=etree.SubElement(axis,C(tag))
                node.set("val",val)
            fmt=axis.find(C("numFmt"))
            if fmt is not None:
                fmt.set("formatCode","yyyy" if span>365*5 else "yyyy-mm" if monthly or span>365 else "mm-dd")
                fmt.set("sourceLinked","0")
    # Let Office autoscale values, retaining displayUnits and primary/secondary axes.
    for axis in xml.findall(".//"+C("valAx")):
        scaling=axis.find(C("scaling"))
        for child in list(scaling):
            if child.tag in {C("min"),C("max")}: scaling.remove(child)
        for tag in ("majorUnit","minorUnit"):
            node=axis.find(C(tag))
            if node is not None: axis.remove(node)
    # Future blanks are gaps, never connect interpolation presented as facts.
    blanks=xml.find("./"+C("chart")+"/"+C("dispBlanksAs"))
    if blanks is not None: blanks.set("val","gap")
    if any(any(value is not None for value in s["forecast_values"]) for s in rebuilt["series"]):
        # Old two-row legend geometry cannot contain the additional forecast
        # series. Let Office lay it out; a visible page key is retained as well.
        for layout in xml.findall("./"+C("chart")+"/"+C("legend")+"/"+C("layout")):
            for manual in layout.findall(C("manualLayout")): layout.remove(manual)
    stream=io.BytesIO();workbook.save(stream);part._blob=stream.getvalue()
    rebuilt["formulas"]=[f.text for f in xml.findall(".//"+C("f"))]

def _target(report_month,frequency,cutoff):
    y,m=map(int,report_month.split("-"))
    target=month_end(y,m)
    if frequency=="quarterly":
        m=(m//3)*3
        target=month_end(y,m) if m else month_end(y-1,12)
    elif frequency in {"daily","weekly"}: target=min(target,cutoff)
    return target

def _forecast_for(request, obs, target, issues):
    points=normalize_series([o["date"] for o in obs],[o["value"] for o in obs],request["frequency"])
    if not points:
        issues.append({"code":"latest_actual_missing","request_id":request["id"]});return {},None,None
    last=points[-1][0]
    predicted={}
    receipt=None
    if last<target:
        try:
            receipt=forecast_series(points,target,request["frequency"],request["unit"],policy="LPR" in request["definition"])
            predicted={date.fromisoformat(v["period"]):v["value"] for v in receipt["values"]}
        except ValueError as exc:
            issues.append({"code":str(exc),"request_id":request["id"],"latest_actual":last.isoformat(),"target":target.isoformat(),"verified_history":len(points)})
    return predicted,last,receipt

def rebuild_chart(contract, observations, report_month, cutoff):
    """Rebuild one chart by reviewed semantics; return an auditable ledger."""
    semantic=contract["semantics"];freq=contract["frequency"]
    target=_target(report_month,freq,cutoff)
    requests={r["id"]:r for r in contract["requests"]}
    issues=[];series=[]
    def item(original,name,actual,forecast,unit,rids,projections,points):
        return {"original_name":original,"name":name,"actual_values":actual,"forecast_values":forecast,"unit":unit,
            "request_ids":rids,"frequency":requests[rids[0]]["frequency"] if rids else freq,"forecasts":projections,"verified_points":points}
    if semantic in {"time","mixed"}:
        # Order is retained, but all series share the same correctly typed axis.
        dates=[parse_period(x,freq) for x in contract["categories"]]
        ascending=dates[0]<=dates[-1]
        base=sorted(set(dates))
        if freq=="announcement_monthly":
            actual_dates={o["date"] for r in requests.values() for o in observations.get(r["id"],[])}
            proven_months={d.strftime("%Y-%m") for d in actual_dates}
            base=[d for d in base if d.strftime("%Y-%m") not in proven_months]+list(actual_dates)
            base=sorted(set(base))
        else:
            base=sorted(set(base)|{o["date"] for r in requests.values() for o in observations.get(r["id"],[]) if o["date"]<=target and r["frequency"]==freq})
        cursor=advance(base[-1],freq)
        while cursor<=target:
            base.append(cursor);cursor=advance(cursor,freq)
        base=base[-len(dates):]
        dates_out=base if ascending else list(reversed(base))
        cats=[(d-date(1899,12,30)).days for d in dates_out]
        for old in contract["series"]:
            name=old["name"]
            if static_series(name,old["values"]):
                value=next(v for v in old["values"] if v is not None)
                series.append(item(name,name,[value]*len(cats),[None]*len(cats),contract["raw_unit"],[],[],[]));continue
            rid=contract["id"]+"::"+name;r=requests[rid];obs=observations.get(rid,[])
            own_target=_target(report_month,r["frequency"],cutoff)
            pred,last,projection=_forecast_for(r,obs,own_target,issues)
            archive={parse_period(p,r["frequency"]):v for p,v in zip(contract["categories"],old["values"]) if v is not None}
            # Mixed frequency zero sentinels are NOT quarterly publications.
            if r["frequency"]=="quarterly" and freq!="quarterly":
                archive={parse_period(p,"quarterly"):v for p,v in zip(contract["categories"],old["values"]) if parse_period(p,"daily").month in {3,6,9,12} and v is not None}
            actual={d:v for d,v in archive.items() if last and d<=last}
            actual.update({o["date"]:o["value"] for o in obs})
            actual_values=[];forecasts=[]
            for d in dates_out:
                # Non-quarter cells are missing, not zeros or copied monthly GDP.
                relevant=r["frequency"]!="quarterly" or d.month in {3,6,9,12}
                actual_values.append(actual.get(d) if relevant else None)
                forecasts.append(pred.get(d) if relevant else None)
            series.append(item(name,name,actual_values,forecasts,r["unit"],[rid],[projection] if projection else [],obs))
    elif semantic in {"seasonal","seasonal_current"}:
        cats=list(contract["categories"]);year=int(report_month[:4])
        month=int(report_month[5:])
        target_index=target.isocalendar()[1]-1 if freq=="weekly" else month-1
        for old in contract["series"]:
            name=old["name"]
            if semantic=="seasonal" and str(year) not in str(name):
                series.append(item(name,name,list(old["values"]),[None]*len(cats),contract["raw_unit"],[],[],[]));continue
            rid=contract["id"]+"::current" if semantic=="seasonal" else contract["id"]+"::"+name
            r=requests[rid];obs=observations.get(rid,[]);pred,last,projection=_forecast_for(r,obs,target,issues)
            actual=list(old["values"]);future=[None]*len(cats)
            last_idx=(-1 if not last or last.year!=year else last.isocalendar()[1]-1 if freq=="weekly" else last.month-1)
            for i in range(len(actual)):
                if i>last_idx: actual[i]=None
            for o in obs:
                if o["date"].year==year:
                    idx=o["date"].isocalendar()[1]-1 if freq=="weekly" else o["date"].month-1
                    if idx<len(cats): actual[idx]=o["value"]
            for d,value in pred.items():
                idx=d.isocalendar()[1]-1 if freq=="weekly" else d.month-1
                if d.year==year and idx<len(cats) and idx<=target_index: future[idx]=value
            series.append(item(name,name,actual,future,r["unit"],[rid],[projection] if projection else [],obs))
        if semantic=="seasonal" and not any(str(year) in str(s["name"]) for s in contract["series"]):
            issues.append({"code":"seasonal_target_year_not_in_contract","chart_id":contract["id"]})
    else:
        # Fixed categories. Each cell's history is across periods for THAT category.
        cats=list(contract["categories"])
        for old_index,old in enumerate(contract["series"]):
            name=old["name"];actual=[];future=[];rids=[];projections=[];all_points=[]
            snapshot=semantic=="snapshot"
            display_target=target
            if snapshot and len(contract["series"])>1:
                # Preserve the relative date-snapshot order, comparison is previous month.
                original_dates=[parse_period(s["name"]) for s in contract["series"]]
                rank=sorted(original_dates).index(original_dates[old_index])
                if rank<len(original_dates)-1:
                    key=target.year*12+target.month-1-(len(original_dates)-1-rank)
                    display_target=month_end(key//12,key%12+1)
            for i in range(len(cats)):
                rid=contract["id"]+(f"::category{i}" if snapshot else "::"+name+f"::category{i}")
                r=requests[rid];obs=[o for o in observations.get(rid,[]) if o["date"]<=display_target]
                pred,last,projection=_forecast_for(r,obs,display_target,issues)
                point=next((o["value"] for o in obs if o["date"]==display_target),None)
                actual.append(point);future.append(pred.get(display_target));rids.append(rid)
                if projection: projections.append({"category_index":i,**projection})
                all_points.extend(obs)
            display_name=display_target.strftime("%Y-%m") if snapshot else name
            series.append(item(name,display_name,actual,future,contract["raw_unit"],rids,projections,all_points))
    # Dates in ledger are JSON strings; raw observations remain in source-package.
    for s in series:
        s["verified_points"]=[{**o,"date":o["date"].isoformat()} for o in s["verified_points"]]
    return {"chart_id":contract["id"],"semantics":semantic,"frequency":freq,"categories":cats,"target":target.isoformat(),
        "definition":contract["definition"],"series":series,"issues":issues,"archival_history":"未作为最新事实证明或预测训练样本；仅保留模板历史展示"}

def _shape(slide,shape_id):
    return next(s for s in all_shapes(slide.shapes) if s.shape_id==shape_id)

def set_text(shape,text):
    """Retain first paragraph/run formatting, delete stale remaining runs."""
    frame=shape.text_frame
    paragraph=frame.paragraphs[0]
    rpr=deepcopy(paragraph.runs[0]._r.find(A("rPr"))) if paragraph.runs else None
    ppr=deepcopy(paragraph._p.find(A("pPr")))
    frame.clear();paragraph=frame.paragraphs[0]
    if ppr is not None:
        existing=paragraph._p.find(A("pPr"))
        if existing is not None: paragraph._p.remove(existing)
        paragraph._p.insert(0,ppr)
    run=paragraph.add_run();run.text=text
    if rpr is not None:
        existing=run._r.find(A("rPr"))
        if existing is not None: run._r.remove(existing)
        run._r.insert(0,rpr)

def _fact(chart,keyword,period):
    candidates=[s for s in chart["series"] if keyword in s["name"] and s["request_ids"]]
    if not candidates: return None
    s=candidates[0]
    for point in s["verified_points"]:
        if point["date"][:7]==period: return {"value":point["value"],"status":"actual","unit":s["unit"],"source_url":point["source_url"]}
    for f in s["forecasts"]:
        for point in f.get("values",[]):
            if point["period"][:7]==period: return {"value":point["value"],"status":"forecast","unit":s["unit"],"method":f["method"]}
    return None

def collect_table_facts(charts, observations, report_month):
    byid={c["chart_id"]:c for c in charts};y,m=map(int,report_month.split("-"));periods=[]
    for offset in (2,1,0):
        key=y*12+m-1-offset;periods.append(f"{key//12:04d}-{key%12+1:02d}")
    rows=[]
    for label,cid,key,unit in OVERVIEW_ROWS:
        facts=[]
        for period in periods:
            if cid.startswith("overview::"):
                point=next((o for o in observations.get(cid,[]) if o["date"].strftime("%Y-%m")==period),None)
                fact={"value":point["value"],"status":"actual","unit":unit,"source_url":point["source_url"]} if point else None
                if fact is None:
                    history=[o for o in observations.get(cid,[]) if o["date"].strftime("%Y-%m")<period]
                    if history:
                        try:
                            projection=forecast_series(normalize_series([o["date"] for o in history],[o["value"] for o in history],"monthly"),parse_period(period),"monthly",unit)
                            predicted=next((v for v in projection["values"] if v["period"][:7]==period),None)
                            if predicted: fact={"value":predicted["value"],"status":"forecast","unit":unit,"method":projection["method"],"projection":projection}
                        except ValueError: pass
            else: fact=_fact(byid[cid],key,period)
            if fact and unit=="万亿元" and fact["unit"]=="亿元":
                fact={**fact,"value":fact["value"]/10000,"unit":unit}
            facts.append(fact)
        rows.append({"label":label,"unit":unit,"periods":periods,"facts":facts,"chart_id":cid})
    return rows

def _formatted(fact):
    if not fact: return "—"
    value=fact["value"]
    return f"{value:.2f}".rstrip("0").rstrip(".")+("（预测）" if fact["status"]=="forecast" else "")

def update_tables(deck, rows, report_month):
    receipts=[]
    slide=deck.slides[6]
    old=_shape(slide,24);geometry=(old.left,old.top,old.width,old.height)
    slide.shapes._spTree.remove(old._element)
    for sid in (2,4,5,6,8,10,11,13,14,15,16,17,18,19,20,21):
        try: shape=_shape(slide,sid);slide.shapes._spTree.remove(shape._element)
        except StopIteration: pass
    table_shape=slide.shapes.add_table(17,4,*geometry);table=table_shape.table
    table.columns[0].width=int(geometry[2]*.4)
    for col in range(1,4): table.columns[col].width=int(geometry[2]*.2)
    headers=["指标 / 单位"]+rows[0]["periods"]
    matrix=[headers]+[[r["label"]+"（"+r["unit"]+"）"]+[_formatted(f) for f in r["facts"]] for r in rows]
    for ri,row in enumerate(matrix):
        for ci,text in enumerate(row):
            cell=table.cell(ri,ci);cell.text=text
            for p in cell.text_frame.paragraphs:
                for run in p.runs: run.font.size=Pt(11 if ci==0 else 12)
    set_text(_shape(slide,12),"1.4 经济指标")
    set_text(_shape(slide,9),"信息截止日见各页；仅列有原始来源的实际值，预测单独标记；—表示未发布或未验收。")
    receipts.append({"slide":7,"shape_id":table_shape.shape_id,"cells":matrix,"facts":rows})
    # Slide 32 consumes the very same objects, not independently invented strings.
    forecast=_shape(deck.slides[31],9).table
    labels=["工业增加值当月同比","固定资产投资累计同比","社会消费品零售当月同比","出口金额当月同比","进口金额当月同比","CPI同比","PPI同比","新增人民币贷款"]
    forecast_matrix=[["指标","方向",report_month,rows[0]["periods"][1],rows[0]["periods"][0]]]
    for label in labels:
        row=next(r for r in rows if r["label"]==label);a,b=row["facts"][1:]
        direction="待核验" if not a or not b else "上行" if b["value"]>a["value"] else "下行" if b["value"]<a["value"] else "持平"
        forecast_matrix.append([label,direction,_formatted(b),_formatted(a),_formatted(row["facts"][0])])
    for ri,row in enumerate(forecast_matrix):
        for ci,text in enumerate(row):
            if ri<len(forecast.rows):
                cell=forecast.cell(ri,ci);set_text(cell,text)
                if ri and ci==1:
                    # Old red/green formatting is a stale direction signal too.
                    # Neutral text avoids implying that every rise is positive.
                    for paragraph in cell.text_frame.paragraphs:
                        for run in paragraph.runs: run.font.color.rgb=RGBColor(32,48,68)
    receipts.append({"slide":32,"shape_id":9,"cells":forecast_matrix,"shared_facts":"slide7"})
    return receipts

def update_narrative(deck, charts, rows, report_month, cutoff):
    updates=[]
    def record(slideno,sid,text):
        shape=_shape(deck.slides[slideno-1],sid);before=shape.text
        set_text(shape,text);updates.append({"slide":slideno,"shape_id":sid,"old":before,"new":text})
    # Publisher names, cutoff and forecast key need more room than the old
    # single-publisher footer. Leave the page-number strip intact.
    for slideno,(_,_,source_id) in TEXT_SLOTS.items():
        footer=_shape(deck.slides[slideno-1],source_id)
        footer.width=min(Pt(792),deck.slide_width-footer.left-Pt(54))
        footer.text_frame.margin_top=footer.text_frame.margin_bottom=Pt(0)
    for slideno,sid in ((7,9),(8,26)):
        footer=_shape(deck.slides[slideno-1],sid)
        footer.width=min(Pt(792),deck.slide_width-footer.left-Pt(54))
        footer.text_frame.margin_top=footer.text_frame.margin_bottom=Pt(0)
    for slideno,sid in ((4,19),(16,4),(31,13)):
        body=_shape(deck.slides[slideno-1],sid)
        body.text_frame.margin_left=body.text_frame.margin_right=Pt(0)
    y,m=map(int,report_month.split("-"))
    record(1,18,f"{y}年{m}月宏观经济月报")
    record(1,8,f"信息截止日：{cutoff.isoformat()}")
    record(4,6,"指数")
    record(4,7,"指数")
    for sid in (6,7):
        unit_shape=_shape(deck.slides[3],sid)
        unit_shape.width=Pt(40)
        unit_shape.text_frame.margin_left=unit_shape.text_frame.margin_right=Pt(0)
    record(17,8,"30大中城市商品房成交面积（万平方米）")
    byslide={}
    for chart in charts: byslide.setdefault(int(chart["chart_id"].split("-")[0][1:]),[]).append(chart)
    for slideno,slot in TEXT_SLOTS.items():
        if slideno==32: continue
        title_id,bodies,source_id=slot;pagecharts=byslide.get(slideno,[])
        facts=[];sources=[];latest=[];forecast=False;metrics=[]
        for chart in pagecharts:
            for s in chart["series"]:
                points=s["verified_points"]
                if not points: continue
                for rid in s["request_ids"]:
                    own=[p for p in points if p["request_id"]==rid]
                    if not own: continue
                    own=sorted(own,key=lambda p:p["date"]);point=own[-1]
                    latest.append(point["date"]);sources.append(point["source_url"])
                    label=chart["definition"] if chart["semantics"]=="seasonal" else s["name"]
                    category_index=None
                    if chart["semantics"] in {"snapshot","category_metrics"}:
                        category_index=int(rid.rsplit("category",1)[1])
                        label=str(chart["categories"][category_index])+("" if chart["semantics"]=="snapshot" else s["name"])
                    projections=[f for f in s["forecasts"] if category_index is None or f.get("category_index")==category_index]
                    predicted=[p for f in projections for p in f.get("values",[]) if p["period"]<=chart["target"]]
                    predicted=sorted(predicted,key=lambda p:p["period"])[-1:]
                    current=next((p for p in own if p["date"]==chart["target"]),None)
                    if predicted:
                        value=predicted[0]["value"];status="预测";period=predicted[0]["period"];forecast=True;prior=point
                    elif current:
                        value=current["value"];status="实际";period=current["date"];prior=own[-2] if len(own)>1 else None
                    else:
                        value=point["value"];status="实际";period=point["date"];prior=own[-2] if len(own)>1 else None
                    unit=s["unit"];factor=1
                    if unit=="亿元" and abs(value)>=10000: factor=10000;unit="万亿元"
                    if unit=="辆" and abs(value)>=10000: factor=10000;unit="万辆"
                    number=f"{value/factor:.2f}".rstrip("0").rstrip(".")
                    month=int(period[5:7]);periodlabel=f"{month}月" if s["frequency"]!="quarterly" else f"{(month-1)//3+1}季度"
                    if s["frequency"] in {"weekly","daily"}: periodlabel=period
                    clean=re.sub(r"\([^)]*\)|（[^）]*）","",label).replace("中国:","").replace("PMI:","")
                    delta=value-prior["value"] if prior else None
                    comparison=""
                    if delta is not None:
                        amount=f"{abs(delta)/factor:.2f}".rstrip("0").rstrip(".")
                        changeunit="个百分点" if unit in {"%","百分点"} else "点" if unit=="指数" else unit
                        comparison=f"，较上期{'上升' if delta>0 else '下降' if delta<0 else '持平'}"+(amount+changeunit if delta else "")
                    zone=""
                    if "PMI" in label or chart["chart_id"]=="s11-shape15": zone="，处于扩张区间" if value>50 else "，仍处收缩区间" if value<50 else "，处于荣枯线"
                    sentence=f"{clean}{periodlabel}{status}{number}{unit}"+comparison+zone
                    score=(10 if label in {"PMI","CPI同比","PPI同比"} or "GDP:不变价:当季" in label else 5 if unit in {"%","指数"} else 1)+(min(abs(delta),5) if delta is not None else 0)
                    metrics.append({"sentence":sentence,"short":clean+f"{'预测' if status=='预测' else ''}{number}{unit}"+zone,"score":score,"request_id":rid,"period":period,"value":value,"status":status,"prior":prior})
                    facts.append(sentence)
        # Choose material same-scope movements; preserve complete metric context.
        newest={}
        for metric in metrics:
            previous=newest.get(metric["request_id"])
            if previous is None or metric["period"]>previous["period"]:
                newest[metric["request_id"]]=metric
        ranked=sorted(newest.values(),key=lambda p:p["score"],reverse=True)
        distinct=[x["sentence"] for x in ranked[:3]]
        description="；".join(distinct) if distinct else "尚未取得该页精确口径的权威观测，当前为诊断稿，不形成业务结论"
        basis="未发布期为统计预测，非实际值。" if forecast else ""
        body="■ "+description+"。"+basis
        # Preserve the existing template's body font and box. Long metric names
        # live in notes; we keep at most ~three visual lines, not shrink font.
        if len(body)>190:
            description="；".join(distinct[:3]);body="■ "+description+"。"+basis
        record(slideno,bodies[0],body)
        record(slideno,title_id,f"{m}月："+(ranked[0]["short"] if ranked else "精确口径观测待补齐"))
        publishers={"stats.gov.cn":"国家统计局","pbc.gov.cn":"人民银行","mof.gov.cn":"财政部","customs.gov.cn":"海关总署","cpcaauto.com":"乘联分会","spglobal.com":"S&P Global","ismworld.org":"ISM","wind.com.cn":"Wind","mysteel.com":"Mysteel"}
        names=list(dict.fromkeys(name for domain,name in publishers.items() if any(domain in url for url in sources)))
        visual_key="；浅色斜纹柱/虚线菱形为预测" if forecast else ""
        record(slideno,source_id,f"来源：{'、'.join(names) or '待核验'}；截止{cutoff.isoformat()}{visual_key}；方法见备注。")
        notes=deck.slides[slideno-1].notes_slide.notes_text_frame
        notes.text="信息截止日："+cutoff.isoformat()+"\n"+"\n".join(facts)+"\n原始来源：\n"+"\n".join(dict.fromkeys(sources))
    # Replace the old July executive and policy prose, do not merely change dates.
    exec_shapes=[23,54,55,45,43,36,37]
    for sid,row in zip(exec_shapes,rows[:7]):
        record(2,sid,row["label"]+"："+_formatted(row["facts"][-1])+row["unit"]+"；实际与预测按同口径分列")
    record(2,2,f"{m}月宏观经济：以权威实际为基线，单独披露未发布期预测")
    def row_sentence(label):
        row=next(r for r in rows if r["label"]==label)
        return label+_formatted(row["facts"][-1])+row["unit"]
    fiscal=next(c for c in charts if c["chart_id"]=="s30-shape13")
    lpr=next(c for c in charts if c["chart_id"]=="s30-shape18")
    def chart_sentence(chart,keyword):
        fact=_fact(chart,keyword,report_month)
        return keyword+(_formatted(fact)+fact["unit"] if fact else "待核验")
    record(31,2,f"{m}月财政与利率：观察已发布事实，单列未发布期情景")
    record(31,5,f"信息截止{cutoff.isoformat()}。生产、消费、投资指标与财政收支、LPR按同口径核验。未发布指标标为预测；本页不以数据走势代替政策原文，不沿用旧月政策因果解释。")
    record(31,4,"指标状态与政策传导证据分开，不把预测当作政策效果")
    record(31,11,"生产、消费与投资")
    demand="；".join(row_sentence(x) for x in ["工业增加值当月同比","社会消费品零售当月同比","固定资产投资累计同比"])+"。"
    demand=demand.replace("工业增加值当月同比","工业同比").replace("社会消费品零售当月同比","社零同比").replace("固定资产投资累计同比","投资累计同比")
    record(31,13,demand)
    record(31,15,"财政累计收支同比")
    record(31,30,"；".join(chart_sentence(fiscal,x) for x in ["财政收入增速","财政支出增速"])+"。未据此推断专项债或项目落地效果。")
    record(31,32,"LPR实际与保持情景")
    record(31,34,"；".join(chart_sentence(lpr,x) for x in ["1年","5年"])+"。未发布期保持现行利率仅为情景假设，不是新公告。")
    record(31,35,"01 · 需求侧指标状态")
    record(31,36,"02 · 财政收支观测")
    record(31,38,"03 · 利率与情景边界")
    for sid in (35,36,38): _shape(deck.slides[30],sid).height=Pt(26)
    record(32,10,f"{m}月经济预测：与正文共用同一指标台账")
    record(32,6,"■ 已发布指标列实际值；尚未发布指标仅在核验历史充足时给出统计预测。方向按目标值与上期同口径比较，未取得观测或不能验收时保留空值，不沿用旧月数字。")
    record(32,7,f"信息截止日：{cutoff.isoformat()}；预测方法、回测和来源见台账；预测非实际。")
    for sid,cid in [(22,"s8-shape20"),(23,"s8-shape21"),(24,"s8-shape11"),(8,"s8-shape25")]:
        chart=next(c for c in charts if c["chart_id"]==cid)
        actuals=[p["date"] for s in chart["series"] for p in s["verified_points"]]
        forecasts=[p["period"] for s in chart["series"] for f in s["forecasts"] for p in f.get("values",[])]
        record(8,sid,chart["definition"]+"：实际至"+(max(actuals) if actuals else "待核验")+("；预测至"+max(forecasts) if forecasts else ""))
    record(8,26,f"各高频指标分别列示截止日；虚线菱形为预测；来源及训练记录见台账，信息截止{cutoff.isoformat()}。")
    for slideno,sid,cid in [(28,9,"s28-shape11"),(28,10,"s28-shape17"),(30,12,"s30-shape13"),(30,17,"s30-shape18")]:
        chart=next(c for c in charts if c["chart_id"]==cid)
        record(slideno,sid,chart["definition"])
    # Captions outside narrative slots use precise chart periods; data histories
    # themselves remain unchanged (no global July->September replacement).
    used={(u["slide"],u["shape_id"]) for u in updates}
    for slideno,pagecharts in byslide.items():
        for shape in all_shapes(deck.slides[slideno-1].shapes):
            if not getattr(shape,"has_text_frame",False) or (slideno,shape.shape_id) in used: continue
            text=shape.text
            if re.search(r"2026年[678]月|2026-[0678]\d?|[678]月|1[-—－–至][678]月|上半年",text):
                # Captions are labeled as observation/projection coverage, never
                # renamed 'actual September' by replacing an old month token.
                # Captions are regenerated by chart meaning, not old period-token
                # replacement that could leave stale narrative or range labels.
                chart_shapes=[(_shape(deck.slides[slideno-1],int(c["chart_id"].split("shape")[1])),c) for c in pagecharts]
                center=shape.left+shape.width/2
                _,closest=min(chart_shapes,key=lambda pair:abs(pair[0].left+pair[0].width/2-center))
                text=f"{m}月 {closest['definition']}"
                record(slideno,shape.shape_id,text)
    return updates

def build(reference, report_month, package, output, ledger_path, source_root=None):
    reference=Path(reference);output=Path(output)
    contract=inventory(reference)
    if package.get("report_month")!=report_month: raise ValueError("package_report_month_mismatch")
    if package.get("mode","forecast")!="forecast": raise ValueError("unsupported_macro_mode")
    cutoff=date.fromisoformat(package["cutoff_date"])
    if cutoff>date.today(): raise ValueError("cutoff_in_future")
    source_root=Path(source_root or Path(ledger_path).parent.parent)
    observations=verified_observations(package,contract,source_root)
    deck=Presentation(str(reference));charts=[]
    for slidecontract in contract["slides"]:
        for c in slidecontract["charts"]:
            rebuilt=rebuild_chart(c,observations,report_month,cutoff)
            update_native_chart(_shape(deck.slides[slidecontract["slide"]-1],c["shape_id"]).chart,rebuilt)
            charts.append(rebuilt)
    tablefacts=collect_table_facts(charts,observations,report_month)
    tables=update_tables(deck,tablefacts,report_month)
    text_updates=update_narrative(deck,charts,tablefacts,report_month,cutoff)
    issues=[i for c in charts for i in c["issues"]]
    issues.extend(validate_constraints(charts,observations))
    # Target table facts must be actual/forecast, not copied prior-month text.
    for row in tablefacts:
        if row["facts"][-1] is None and not (row["label"]=="GDP当季同比" and int(report_month[5:])%3):
            issues.append({"code":"overview_target_missing","indicator":row["label"]})
    required={r["id"] for r in contract["source_requests"]}
    missing=[rid for rid in required if not observations.get(rid)]
    issues.extend({"code":"source_required_missing","request_id":rid} for rid in sorted(missing))
    output.parent.mkdir(parents=True,exist_ok=True);deck.save(str(output))
    ledger={"schema_version":2,"contract_version":CONTRACT_VERSION,"report_month":report_month,"cutoff_date":cutoff.isoformat(),
        "run_id":source_root.name,"reference_sha256":digest(reference),"pptx_sha256":digest(output),"source_package_sha256":hashlib.sha256(json.dumps(package,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
        "summary":{"slides":33,"charts":37,"tables":2,"required_requests":len(required),"verified_requests":len(required)-len(missing)},
        "charts":charts,"slides":text_updates,"table_updates":tables,"issues":issues,
        "business_complete":not issues,"forecast_fit_policy":"仅拟合逐字验收的权威实际；模板历史不进入训练",
        "source_root":str(source_root),"observations":[{**o,"date":o["date"].isoformat()} for group in observations.values() for o in group]}
    dump(ledger_path,ledger)
    return {"pptx":str(output),"ledger":str(ledger_path),"business_complete":not issues,"issues":issues,"summary":ledger["summary"]}

def validate(pptx, ledger_path, *, _public_draft=False):
    """Independent artifact checks, including native caches against xlsx cells."""
    ledger=json.loads(Path(ledger_path).read_text(encoding="utf-8"));issues=[]
    if _public_draft:
        from macro_draft import rebuild_draft_chart, draft_table_facts, update_draft_tables, update_draft_narrative
        if ledger.get("delivery_mode")!="public_draft" or ledger.get("formal_delivery_allowed") is not False or ledger.get("business_complete") is not False:
            issues.append({"code":"draft_delivery_contract_invalid"})
        if not ledger.get("draft_content_complete"):
            issues.append({"code":"draft_content_not_validated"})
    else:
        rebuild_draft_chart = draft_table_facts = update_draft_tables = update_draft_narrative = None
    if ledger.get("contract_version")!=CONTRACT_VERSION: issues.append({"code":"contract_version_mismatch"})
    if digest(pptx)!=ledger.get("pptx_sha256"): issues.append({"code":"pptx_changed_after_build"})
    reference=Path(__file__).resolve().parents[1]/"assets/reference.pptx"
    contract=inventory(reference)
    if digest(reference)!=ledger.get("reference_sha256"): issues.append({"code":"reference_changed"})
    source_root=Path(ledger["source_root"])
    packagefile=source_root/"working/data-package.json"
    if not packagefile.is_file(): packagefile=source_root/"working/macro-sources/source-package.json"
    try:
        package=json.loads(packagefile.read_text(encoding="utf-8"))
        observations=verified_observations(package,contract,source_root)
        if hashlib.sha256(json.dumps(package,ensure_ascii=False,sort_keys=True).encode()).hexdigest()!=ledger.get("source_package_sha256"):
            issues.append({"code":"source_package_changed"})
        rebuilder=rebuild_draft_chart if _public_draft else rebuild_chart
        rebuilt=[rebuilder(c,observations,ledger["report_month"],date.fromisoformat(ledger["cutoff_date"])) for slide in contract["slides"] for c in slide["charts"]]
        constraints=validate_constraints(rebuilt,observations)
        if _public_draft:
            # A visibly blank unreleased quarter is not an identity claim.
            # Actual mismatches, units and partial decompositions still fail.
            constraints=[i for i in constraints if not (i.get("code")=="gdp_decomposition_incomplete" and i.get("series") and all(v is None for v in i["series"].values()))]
            required={r["id"] for r in contract["source_requests"]}
            missing=sorted(rid for rid in required if not observations.get(rid))
            if sorted(ledger.get("missing_requests",[]))!=missing or ledger.get("coverage")!={"required":len(required),"verified":len(required)-len(missing)}:
                issues.append({"code":"draft_coverage_replay_mismatch"})
            if len(missing)==len(required): issues.append({"code":"public_draft_has_no_verified_data"})
        issues.extend(constraints)
        for expected,actual in zip(rebuilt,ledger["charts"]):
            for key in ("chart_id","semantics","frequency","categories","series","issues"):
                if expected[key]!=actual[key]: issues.append({"code":"ledger_replay_mismatch","chart_id":expected["chart_id"],"field":key})
        tables=(draft_table_facts if _public_draft else collect_table_facts)(rebuilt,observations,ledger["report_month"])
        if tables!=ledger["table_updates"][0]["facts"]: issues.append({"code":"overview_facts_replay_mismatch"})
        replay_deck=Presentation(str(reference))
        replay_tables=(update_draft_tables if _public_draft else update_tables)(replay_deck,tables,ledger["report_month"])
        replay_text=(update_draft_narrative if _public_draft else update_narrative)(replay_deck,rebuilt,tables,ledger["report_month"],date.fromisoformat(ledger["cutoff_date"]))
        if replay_tables!=ledger.get("table_updates"): issues.append({"code":"table_content_replay_mismatch"})
        if replay_text!=ledger.get("slides"): issues.append({"code":"narrative_content_replay_mismatch"})
    except (ValueError,KeyError,OSError) as exc: issues.append({"code":"source_replay_failed","message":str(exc)})
    deck=Presentation(str(pptx));original_deck=Presentation(str(reference));chartcount=0;tablecount=0
    chartledgers={c["chart_id"]:c for c in ledger["charts"]}
    for slideno,slide in enumerate(deck.slides,1):
        for shape in all_shapes(slide.shapes):
            tablecount+=int(getattr(shape,"has_table",False))
            if not getattr(shape,"has_chart",False): continue
            chartcount+=1;chart=shape.chart;xml=chart._chartSpace;cid=f"s{slideno}-shape{shape.shape_id}"
            external=xml.find(C("externalData"));part=chart.part.related_part(external.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"))
            workbook=load_workbook(io.BytesIO(part.blob),data_only=True)
            for ser in xml.xpath(".//c:ser"):
                for ref in ser.xpath("./c:cat/c:numRef | ./c:cat/c:strRef | ./c:val/c:numRef"):
                    formula=ref.find(C("f")).text
                    cache=ref.find(C("numCache"))
                    if cache is None: cache=ref.find(C("strCache"))
                    if cache is None: continue
                    count=int(cache.find(C("ptCount")).get("val"));sheet,col,start,end,_=_range(formula,count)
                    if end-start+1!=count: issues.append({"code":"chart_formula_length_mismatch","chart_id":cid})
                    values={int(p.get("idx")):p.find(C("v")).text for p in cache.findall(C("pt"))}
                    for i in range(count):
                        value=workbook[sheet].cell(start+i,col).value;cached=values.get(i)
                        if isinstance(value,(date,datetime)) and ref.tag==C("numRef"):
                            value=to_excel(value,workbook.epoch)
                        equal=(value is None and cached is None) or (cached is not None and str(value)==cached)
                        if not equal and cached is not None:
                            try: equal=math.isclose(float(value),float(cached),rel_tol=1e-10,abs_tol=1e-8)
                            except (ValueError,TypeError): pass
                        if not equal: issues.append({"code":"cache_workbook_mismatch","chart_id":cid,"cell":f"{sheet}!{get_column_letter(col)}{start+i}"})
                name=_series_name(ser)
                expected=next((s for s in chartledgers[cid]["series"] if name==s["name"] or name==s["name"]+"（预测）"),None)
                if not expected: issues.append({"code":"unexpected_chart_series","chart_id":cid,"series":name});continue
                original_chart=_shape(original_deck.slides[slideno-1],shape.shape_id).chart
                original_ser=next(s for s in original_chart._chartSpace.xpath(".//c:ser") if _series_name(s)==expected["original_name"])
                if ser.getparent().tag!=original_ser.getparent().tag or [a.get("val") for a in ser.getparent().findall(C("axId"))]!=[a.get("val") for a in original_ser.getparent().findall(C("axId"))]:
                    issues.append({"code":"plot_axis_mapping_changed","chart_id":cid,"series":name})
                cat=ser.find(C("cat"))
                if cat is None:
                    issues.append({"code":"category_contract_missing","chart_id":cid,"series":name})
                elif cat.find(C("multiLvlStrRef")) is not None:
                    original_cat=original_ser.find(C("cat"))
                    expected_levels=[[p.find(C("v")).text for p in level.findall(C("pt"))] for level in original_cat.findall(".//"+C("lvl"))]
                    actual_levels=[[p.find(C("v")).text for p in level.findall(C("pt"))] for level in cat.findall(".//"+C("lvl"))]
                    if actual_levels!=expected_levels: issues.append({"code":"multilevel_category_changed","chart_id":cid})
                    original_ext=original_chart._chartSpace.find(C("externalData"))
                    original_part=original_chart.part.related_part(original_ext.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"))
                    original_workbook=load_workbook(io.BytesIO(original_part.blob),data_only=True)
                    formula=cat.find(".//"+C("f")).text;sheet,area=formula.rsplit("!",1);sheet=sheet.strip("'")
                    c1,r1,c2,r2=range_boundaries(area.replace("$",""))
                    if any(workbook[sheet].cell(row,col).value!=original_workbook[sheet].cell(row,col).value for row in range(r1,r2+1) for col in range(c1,c2+1)):
                        issues.append({"code":"multilevel_category_workbook_changed","chart_id":cid})
                else:
                    catref=cat.find(C("numRef"))
                    numeric=catref is not None
                    if catref is None: catref=cat.find(C("strRef"))
                    category_cache=catref.find(C("numCache") if numeric else C("strCache"))
                    actual_categories=[None]*int(category_cache.find(C("ptCount")).get("val"))
                    for p in category_cache.findall(C("pt")):
                        value=p.find(C("v")).text
                        actual_categories[int(p.get("idx"))]=float(value) if numeric else value
                    wanted=chartledgers[cid]["categories"]
                    if numeric: wanted=[float(value) for value in wanted]
                    else: wanted=[str(value) for value in wanted]
                    if actual_categories!=wanted: issues.append({"code":"category_ledger_mismatch","chart_id":cid,"series":name})
                ref=ser.find("./"+C("val")+"/"+C("numRef"));cache=ref.find(C("numCache"))
                count=int(cache.find(C("ptCount")).get("val"));values=[None]*count
                for p in cache.findall(C("pt")): values[int(p.get("idx"))]=float(p.find(C("v")).text)
                target=expected["forecast_values"] if name.endswith("（预测）") else expected["actual_values"]
                if values!=target: issues.append({"code":"native_values_ledger_mismatch","chart_id":cid,"series":name})
            if chartledgers[cid]["semantics"] in {"time","mixed"}:
                cats=chartledgers[cid]["categories"]
                for axis in xml.findall(".//"+C("dateAx")):
                    for key,value in (("min",min(cats)),("max",max(cats))):
                        bound=axis.find("./"+C("scaling")+"/"+C(key))
                        if bound is None or float(bound.get("val"))!=value: issues.append({"code":"stale_date_axis","chart_id":cid})
    for update in ledger.get("table_updates",[]):
        table=_shape(deck.slides[update["slide"]-1],update["shape_id"]).table
        cells=[[c.text for c in r.cells] for r in table.rows]
        if cells!=update["cells"]: issues.append({"code":"table_ledger_mismatch","slide":update["slide"]})
    for update in ledger.get("slides",[]):
        if _shape(deck.slides[update["slide"]-1],update["shape_id"]).text!=update["new"]:
            issues.append({"code":"text_ledger_mismatch","slide":update["slide"]})
    if len(deck.slides)!=33 or chartcount!=37 or tablecount!=2: issues.append({"code":"native_object_count_changed","slides":len(deck.slides),"charts":chartcount,"tables":tablecount})
    issues.extend(ledger.get("issues",[]))
    if not _public_draft and not ledger.get("business_complete"): issues.append({"code":"business_incomplete"})
    return {"passed":not issues,"gate":"macro_draft_business" if _public_draft else "macro_business","issues":issues,"slides":len(deck.slides),"charts":chartcount,"tables":tablecount,"report_month":ledger["report_month"],"cutoff_date":ledger["cutoff_date"],"artifact_sha256":digest(pptx),"formal_delivery_allowed":False if _public_draft else not issues}
