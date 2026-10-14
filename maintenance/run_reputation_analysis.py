"""Maintenance-only full snapshot / incremental computation / guarded publication."""
import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

from dotenv import dotenv_values
import psycopg2
from psycopg2.extras import execute_values

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'mcp'))
from maintenance.reputation_analysis import METHOD, analyze_review, aggregate, compile_patterns
from market_data.reputation_sources import RAW, _revision, _dicts

SUMMARY=['model','direction','rank','primary_label','tertiary_labels','mention_count','mention_share',
         'dongchedi_count','autohome_count','source_mentions','taxonomy_version','import_batch']
DETAIL=['model','direction','source','review_key','primary_label','secondary_label','tertiary_label',
        'taxonomy_code','is_custom','excerpt','review_text','import_batch']
TABLES={'new_car_reputation_taxonomy_summary':SUMMARY,'new_car_reputation_review_tag':DETAIL}
OUT=ROOT/'outputs/reputation-full-analysis'


def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,default=str,separators=(',',':'))
def digest(value):return hashlib.sha256(encode(value).encode()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')


def connect():
    env=dotenv_values(ROOT/'.env.new-car')
    if env['NEW_CAR_PG_HOST']!='192.168.3.146' or env['NEW_CAR_PG_DATABASE']!='vectordb':
        raise ValueError('Unexpected formal database target')
    return psycopg2.connect(host=env['NEW_CAR_PG_HOST'],port=env.get('NEW_CAR_PG_PORT','5432'),
        dbname=env['NEW_CAR_PG_DATABASE'],user=env['NEW_CAR_PG_USER'],password=env['NEW_CAR_PG_PASSWORD'],
        connect_timeout=5,application_name='maintenance-evidence-reputation-analysis')


def ordered(rows):return sorted(rows,key=encode)


def current_analysis(cursor):
    result={}
    for table,columns in TABLES.items():
        cursor.execute('SELECT '+','.join(columns)+' FROM public.'+table)
        result[table]=ordered(_dicts(cursor))
    return result


def normalized(rows):
    output=[]
    for row in rows:
        item=dict(row)
        if 'mention_share' in item:item['mention_share']=str(Decimal(str(item['mention_share'])).quantize(Decimal('0.0001')))
        output.append(item)
    return ordered(output)


def equivalent(left,right):
    return digest(normalized([{k:v for k,v in r.items() if k!='import_batch'} for r in left]))==digest(normalized([{k:v for k,v in r.items() if k!='import_batch'} for r in right]))


def prepare():
    bundle=json.loads((ROOT/'maintenance/reputation-taxonomy.json').read_text(encoding='utf-8'))
    taxonomy=bundle['taxonomy']
    patterns=compile_patterns(bundle['patterns'])
    connection=connect()
    try:
        connection.set_session(readonly=True,isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            revision=_revision(cursor)
            cursor.execute('WITH raw AS ('+RAW+') SELECT * FROM raw ORDER BY source,review_key')
            rows=_dicts(cursor)
            cursor.execute('SELECT DISTINCT btrim(model) AS model FROM public.new_car_model WHERE model IS NOT NULL')
            new_car_names={r['model'] for r in _dicts(cursor)}
            before=current_analysis(cursor)
    finally:
        connection.rollback()
        connection.close()
    keys={(r['source'],r['review_key']) for r in rows}
    if len(keys)!=len(rows):raise ValueError('Duplicate raw source+review_key')
    names=sorted({r['model'] for r in rows if r['model']})
    all_names=sorted(set(names)|new_car_names,key=lambda s:(-len(s),s))
    own_names={s for s in all_names if len(s)>=4}
    competitor_pattern=re.compile('|'.join(re.escape(s) for s in sorted(own_names,key=lambda s:(-len(s),s))))
    engine_hash=digest({'method':METHOD,'bundle':bundle,'engine':hashlib.sha256((ROOT/'maintenance/reputation_analysis.py').read_bytes()).hexdigest(),'known_names':all_names})
    version=f'{METHOD}/raw-{revision}/rules-{engine_hash[:16]}'
    batch=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S')
    run=OUT/batch
    run.mkdir(parents=True,exist_ok=False)
    cache=sqlite3.connect(OUT/'maintenance-checkpoints.sqlite')
    cache.execute('CREATE TABLE IF NOT EXISTS review_checkpoint (source TEXT, review_key TEXT, input_hash TEXT, engine_hash TEXT, result_json TEXT, PRIMARY KEY(source,review_key))')
    tags=[]
    new_or_changed=0
    reused=0
    model_stats={name:{'model':name,'raw':0,'tagged':0,'without_explicit_tags':0,'matches_new_car':name in new_car_names} for name in names}
    sample=[]
    for index,row in enumerate(rows,1):
        fingerprint=digest({k:row.get(k) for k in ['source','review_key','model','review_text','satisfied','dissatisfied']})
        cached=cache.execute('SELECT input_hash,engine_hash,result_json FROM review_checkpoint WHERE source=? AND review_key=?',(row['source'],row['review_key'])).fetchone()
        if cached and cached[:2]==(fingerprint,engine_hash):
            decisions=json.loads(cached[2]);reused+=1
        else:
            decisions=analyze_review(row,taxonomy,patterns,competitor_pattern)
            cache.execute('INSERT INTO review_checkpoint VALUES (?,?,?,?,?) ON CONFLICT(source,review_key) DO UPDATE SET input_hash=excluded.input_hash,engine_hash=excluded.engine_hash,result_json=excluded.result_json',
                (row['source'],row['review_key'],fingerprint,engine_hash,encode(decisions)))
            new_or_changed+=1
        if row['model']:
            model_stats[row['model']]['raw']+=1
            model_stats[row['model']]['tagged' if decisions else 'without_explicit_tags']+=1
        for decision in decisions:
            if decision['excerpt'] not in (row['review_text'] or ''):raise ValueError('Evidence not in original text')
            if decision['direction'] not in {'positive','negative'}:raise ValueError('Invalid sentiment direction')
            tags.append({'model':row['model'],'source':row['source'],'review_key':row['source']+':'+row['review_key'],
                         'review_text':row['review_text'],'import_batch':batch,**decision})
            if len(sample)<60:sample.append({'model':row['model'],'source':row['source'],**decision})
        if index%2000==0:
            cache.commit()
            print(encode({'phase':'analysis','read':index,'total':len(rows),'tag_rows':len(tags)}),flush=True)
    cache.commit();cache.close()
    summaries,counts=aggregate(rows,tags,taxonomy,batch,version)
    for row in summaries:row['mention_share']=f"{row['mention_share']:.4f}"
    if len({(t['model'],t['direction'],t['source'],t['review_key'],t['tertiary_label']) for t in tags})!=len(tags):
        raise ValueError('Duplicate tag primary key')
    tagged_keys={(r['source'],r['review_key'].split(':',1)[1]) for r in tags}
    report={'status':'prepared','batch':batch,'method':METHOD,'source_version':revision,'taxonomy_version':version,
            'review_count':len(rows),'source_model_count':len(names),'named_reviews':sum(s['raw'] for s in model_stats.values()),
            'processed_new_or_changed':new_or_changed,'reused_checkpoints':reused,'reviews_with_tags':len(tagged_keys),
            'reviews_without_explicit_tags':len(rows)-len(tagged_keys),'models_with_tags':len({t['model'] for t in tags}),
            'matched_new_car_model_names':len(set(names)&new_car_names),'tag_rows':len(tags),'summary_rows':len(summaries),
            'raw_tables_modified':False,'schema_changed':False,'before_analysis_hash':digest(before),
            'dictionary_sha256':bundle['dictionary_sha256']}
    payload={'new_car_reputation_taxonomy_summary':summaries,'new_car_reputation_review_tag':tags}
    save(run/'model-coverage.json',list(model_stats.values()))
    save(run/'evidence-sample.json',sample)
    save(run/'before-analysis.json',before)
    save(run/'analysis-payload.json',payload)
    report['payload_sha256']=hashlib.sha256((run/'analysis-payload.json').read_bytes()).hexdigest()
    save(run/'report.json',report)
    print(encode({'phase':'prepared','run':str(run),**report}),flush=True)


def publish(run:Path):
    run=run.resolve()
    if OUT.resolve() not in run.parents:raise ValueError('Run must be a verified maintenance output directory')
    report=json.loads((run/'report.json').read_text(encoding='utf-8'))
    raw=(run/'analysis-payload.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=report['payload_sha256']:raise ValueError('Prepared payload changed')
    payload=json.loads(raw)
    connection=connect()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout='10s'")
                cursor.execute("SET LOCAL statement_timeout='180s'")
                cursor.execute('LOCK TABLE public.autohome_koubei, public.dongchedi_koubei IN SHARE MODE')
                cursor.execute('LOCK TABLE public.new_car_reputation_taxonomy_summary, public.new_car_reputation_review_tag IN SHARE ROW EXCLUSIVE MODE')
                if _revision(cursor)!=report['source_version']:raise ValueError('Source changed; re-prepare using checkpoints before publication')
                current=current_analysis(cursor)
                if all(equivalent(current[t],payload[t]) for t in TABLES):
                    report.update(status='already_current',inserted=0,updated=0)
                else:
                    if digest(current)!=report['before_analysis_hash']:raise ValueError('Analysis tables changed since prepare; stop without overwrite')
                    save(run/'publication-backup.json',current)
                    for table,columns in TABLES.items():
                        cursor.execute('DELETE FROM public.'+table)
                        values=[tuple(encode(r[c]) if c in {'tertiary_labels','source_mentions'} else r[c] for c in columns) for r in payload[table]]
                        if values:execute_values(cursor,'INSERT INTO public.'+table+' ('+','.join(columns)+') VALUES %s',values,page_size=500)
                    actual=current_analysis(cursor)
                    if not all(equivalent(actual[t],payload[t]) for t in TABLES):raise ValueError('Publication verification failed; rollback')
                    report.update(status='transaction_validated',published_models=report['models_with_tags'],
                                  published_tag_rows=report['tag_rows'],published_summary_rows=report['summary_rows'])
        if report['status']=='transaction_validated':report['status']='committed'
        save(run/'report.json',report)
        print(encode({'run':str(run),**report}),flush=True)
    finally:connection.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--publish',type=Path)
    args=parser.parse_args()
    publish(args.publish) if args.publish else prepare()
