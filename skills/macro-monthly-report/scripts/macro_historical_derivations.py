"""Replay PBC monthly loan flows as differences of explicit YTD flow prose.

Never difference loan balances. Rounded cumulative releases imply rounded
monthly estimates, with uncertainty bounds and both original input receipts.
"""
from datetime import date
from decimal import Decimal
import re
from urllib.parse import urlparse
from macro_contract import month_end

NUMBER=r'\d+(?:\.\d+)?'
NAMES={'1':'一','2':'二','3':'三','4':'四','5':'五','6':'六','7':'七','8':'八','9':'九','10':'十','11':'十一','12':'十二'}
FIELDS={'s24-shape9::current':('total','人民币贷款'),
        's24-shape17::category0':('household_short','住户短期贷款'),
        's24-shape17::category1':('household_long','住户中长期贷款'),
        's24-shape17::category2':('corporate_short','企事业单位短期贷款'),
        's24-shape17::category3':('corporate_long','企事业单位中长期贷款'),
        's24-shape17::category4':('bill','票据融资')}


def _number(match,page,year,month):
    value=Decimal(match['number']);scale=Decimal(10000) if match['unit']=='万亿元' else Decimal(1)
    step=Decimal(1).scaleb(-len(match['number'].partition('.')[2]))*scale
    sign=-1 if match['verb']=='减少' else 1
    return {'period':f'{year}-{month:02d}','value':float(sign*value*scale),'half_rounding':float(step/2),
            'quote':match.group(0),'receipt_id':page['receipt_id'],'source_url':page['url'],
            'published_at':page['published_at'],'original_unit':match['unit'],'original_number':match['number']}


def cumulative_inputs(pages,cutoff):
    result={}
    for page in pages.values():
        parsed=urlparse(page.get('url',''))
        if parsed.scheme!='https' or (parsed.hostname or '').lower() not in {'pbc.gov.cn','www.pbc.gov.cn'}:continue
        text=page.get('text','');title=re.match(r'\s*(20\d{2})年(\d{1,2})月金融统计数据报告',text)
        try:published=date.fromisoformat(page.get('published_at','')[:10])
        except ValueError:continue
        if not title or published.isoformat()>cutoff:continue
        year,month=int(title[1]),int(title[2]);prefix='前'+NAMES[str(month)]+'个月人民币贷款'
        # The exact own section terminates before bank interbank-rate data.
        section=re.search(re.escape(prefix)+r'(?:增加|减少).*?(?=[六七八九十]、\d+月份银行间|\Z)',text,re.S)
        if not section:continue
        block=section.group(0)
        pat=r'(?P<verb>增加|减少)(?P<number>'+NUMBER+r')(?P<unit>万亿元|亿元)'
        matches={}
        total=re.search(re.escape(prefix)+pat,block)
        if total:matches['total']=total
        household=re.search(r'住户贷款(?:增加|减少).*?(?=企（事）业单位贷款|企\(事\)业单位贷款|企事业单位贷款)',block,re.S)
        corporate=re.search(r'(?:企（事）业单位|企\(事\)业单位|企事业单位)贷款(?:增加|减少).*?(?=非银行业金融机构贷款|\Z)',block,re.S)
        for source,short,long in [(household,'household_short','household_long'),(corporate,'corporate_short','corporate_long')]:
            if source:
                for label,key in [('短期贷款',short),('中长期贷款',long)]:
                    hit=re.search(label+pat,source.group(0))
                    if hit:matches[key]=hit
        if corporate:
            hit=re.search('票据融资'+pat,corporate.group(0))
            if hit:matches['bill']=hit
        for kind,match in matches.items():
            result.setdefault((year,month,kind),[]).append(_number(match,page,year,month))
    # Conflicting original inputs cannot be silently averaged/selected.
    clean={}
    for key,variants in result.items():
        if len({v['value'] for v in variants})==1:clean[key]=variants[-1]
    return clean


def replay(pages,report_month,cutoff):
    inputs=cumulative_inputs(pages,cutoff);targetyear,targetmonth=map(int,report_month.split('-'));out=[]
    for rid,(kind,label) in FIELDS.items():
        for month in range(2,targetmonth+1):
            current=inputs.get((targetyear,month,kind));prior=inputs.get((targetyear,month-1,kind))
            if not current or not prior:continue
            value=Decimal(str(current['value']))-Decimal(str(prior['value']))
            error=current['half_rounding']+prior['half_rounding']
            out.append({'request_id':rid,'period':month_end(targetyear,month).isoformat(),'value':float(value),
                        'unit':'亿元','frequency':'monthly','definition':label+'当月增量（累计差推算）',
                        'provenance':'official_derived','approximate':True,'uncertainty_half_width':error,
                        'source_url':current['source_url'],'published_at':current['published_at'],
                        'derivation':{'formula':'pbc_ytd_flow_difference_v1','inputs':[current,prior],
                            'boundary':'累计新增流量差，不是余额差；保留发布舍入与统计版本差异'},
                        'lower':float(value)-error,'upper':float(value)+error})
    return out
