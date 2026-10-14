"""Actual monthly sales, with explicit energy boundaries and legacy continuity."""
import re
import unicodedata
from collections import defaultdict

ENERGY={'纯电动':'纯电动','插电式混合动力':'插电式混合动力','插电式':'插电式混合动力',
        '增程式':'插电式混合动力','常规混合动力':'常规混合动力','传统燃料':'传统燃料',
        '燃料电池':'燃料电池','氢燃料':'燃料电池'}

def key(model):return ''.join(unicodedata.normalize('NFKC',str(model)).split()).casefold()

def model_candidates(model,brand='',ambiguous=False):
    candidates=[] if ambiguous else [key(model)]
    if brand:
        candidates.append(key(brand+model))
        # Avoid repeating brand suffixes: 上汽大通 + 大通G10 -> 上汽大通G10.
        for size in range(min(len(brand),len(model)),1,-1):
            if brand[-size:]==model[:size]:
                candidates.append(key(brand+model[size:]));break
        if brand.startswith('东风') and model.startswith('eπ'):
            candidates.append(key('东风'+model))
    return list(dict.fromkeys(candidates))

def combine(excel,legacy,legacy_energy,wanted=()):
    facts={}
    if legacy_energy and (not wanted or legacy_energy in wanted):
        for r in legacy:
            facts[(str(r['month'])[:10],legacy_energy)]={**r,'energy_type':legacy_energy,'provenance':'existing_business_sales'}
    revisions=[]
    for r in excel:
        if wanted and r['energy_type'] not in wanted:continue
        identity=(str(r['month'])[:10],r['energy_type'])
        old=facts.get(identity)
        if old and old['sales']!=r['sales']:revisions.append({'month':identity[0],'energy_type':identity[1],'old':old['sales'],'new':r['sales']})
        facts[identity]={**r,'month':identity[0],'provenance':'business_excel'}
    groups=defaultdict(list);totals=defaultdict(int)
    for (month,energy),r in sorted(facts.items()):
        groups[energy].append(r);totals[month]+=int(r['sales'])
    rows=[{'month':month,'sales':sales,'month_index':index+1} for index,(month,sales) in enumerate(sorted(totals.items()))]
    return dict(success=True,source='api',items=rows,total_sales=sum(totals.values()),peak_sales=max(totals.values(),default=0),
        energy_types=sorted(groups),series=[{'energy_type':energy,'items':items} for energy,items in sorted(groups.items())],
        revisions=revisions,legacy_months_retained=sum(r['provenance']=='existing_business_sales' for r in facts.values()),
        batch=' / '.join(sorted({str(r.get('import_batch') or '') for r in facts.values()}- {''})))

def read_sales(cursor,values):
    model=str(values.get('model') or '').strip();brand=str(values.get('brand') or '').strip()
    if not model or len(model)>100 or len(brand)>100:raise ValueError('Invalid model')
    raw_energy=str(values.get('energy_type') or '').strip()
    wanted=[]
    if raw_energy:
        for e in re.split(r'\s*[/、,|]\s*',raw_energy):
            if e not in ENERGY:raise ValueError('Unknown energy type')
            if ENERGY[e] not in wanted:wanted.append(ENERGY[e])
    cursor.execute('SELECT DISTINCT brand,energy_type FROM new_car_model WHERE model=%s',(model,))
    catalog=cursor.fetchall();brands={r[0] for r in catalog}
    energies={ENERGY[r[1]] for r in catalog if r[1] in ENERGY and (not brand or r[0]==brand)}
    legacy_energy=next(iter(energies)) if len(energies)==1 and len(brands)<=1 else None
    cursor.execute('SELECT to_regclass(\'public.new_car_monthly_sales_by_energy\')')
    excel=[]
    if cursor.fetchone()[0]:
        candidates=model_candidates(model,brand,len(brands)>1)
        for candidate in dict.fromkeys(candidates):
            cursor.execute('''SELECT model,energy_type,sales_month,sales_volume,import_batch,source_sha256
                FROM new_car_monthly_sales_by_energy WHERE model_key=%s ORDER BY sales_month,energy_type''',(candidate,))
            fetched=cursor.fetchall()
            if fetched:
                excel=[dict(model=r[0],energy_type=r[1],month=r[2],sales=r[3],import_batch=r[4],source_sha256=r[5]) for r in fetched]
                break
    cursor.execute('SELECT sales_month,sales_volume,import_batch FROM new_car_monthly_sales WHERE model=%s ORDER BY sales_month',(model,))
    legacy=[dict(month=r[0],sales=r[1],import_batch=r[2]) for r in cursor.fetchall()]
    result=combine(excel,legacy,legacy_energy,wanted)
    result.update(model=model,matched_model=excel[0]['model'] if excel else model,requested_energy_types=wanted)
    return result
