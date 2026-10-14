"""Read-only, transaction-consistent access to the two existing raw source tables."""
from datetime import date
from enum import Enum
import re
from pydantic import Field
from .shared import PageInput, pg_connect


class SourceName(str, Enum):
    AUTOHOME = 'autohome'
    DONGCHEDI = 'dongchedi'


class SourceReviewInput(PageInput):
    model: str = Field(default='', max_length=100, description='Exact source model/input name; no fuzzy competitor-text attribution.')
    source: SourceName | None = None
    keyword: str = Field(default='', max_length=200, description='Filter original review text.')
    published_from: date | None = None
    published_to: date | None = None


RAW = """
SELECT 'autohome'::text AS source, dedupe_key AS review_key,
       COALESCE(NULLIF(btrim(car_name_input),''),NULLIF(btrim(carname),''),'') AS model,
       carname, series_id_input AS series_id, posttime AS published_date,
       updated_at, collected_at, detail_url, average_score,
       satisfied, dissatisfied,
       concat_ws(E'\n',NULLIF(feeling_summary,''),NULLIF(satisfied,''),NULLIF(dissatisfied,''),NULLIF(lastappend,'')) AS review_text
FROM public.autohome_koubei
UNION ALL
SELECT 'dongchedi'::text, dedupe_key,
       COALESCE(NULLIF(btrim(car_name_input),''),NULLIF(btrim(carname),''),''),
       carname, series_id_input, posttime, updated_at, collected_at, detail_url,
       average_score, NULL::text, NULL::text, content
FROM public.dongchedi_koubei
"""


def _dicts(cursor):
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _revision(cursor):
    cursor.execute('WITH raw AS ('+RAW+") SELECT md5(COALESCE(string_agg(source||':'||review_key||':'||COALESCE(updated_at::text,''),',' ORDER BY source,review_key),'')) AS version FROM raw")
    return cursor.fetchone()[0]


def source_status():
    connection = pg_connect()
    try:
        connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            version = _revision(cursor)
            cursor.execute('WITH raw AS ('+RAW+''')
                SELECT source, COUNT(*) AS review_count, COUNT(DISTINCT series_id) AS series_count,
                       MAX(published_date) AS latest_published_date, MAX(updated_at) AS last_record_update
                FROM raw GROUP BY source ORDER BY source''')
            sources = _dicts(cursor)
            cursor.execute('WITH raw AS ('+RAW+''')
                SELECT COUNT(*) AS review_count, COUNT(DISTINCT NULLIF(model,'')) AS source_model_count,
                       MAX(published_date) AS latest_published_date, MAX(updated_at) AS last_record_update,
                       COUNT(DISTINCT model) FILTER (WHERE EXISTS
                         (SELECT 1 FROM public.new_car_model n WHERE btrim(n.model)=raw.model)) AS matched_new_car_model_count
                FROM raw''')
            result = _dicts(cursor)[0]
            cursor.execute('''SELECT COUNT(*) AS tagged_review_count,COUNT(DISTINCT model) AS model_count,
                              COUNT(DISTINCT (source,review_key)) AS opinion_review_count,
                              MAX(import_batch) AS latest_batch FROM public.new_car_reputation_review_tag''')
            analysis = _dicts(cursor)[0]
            cursor.execute('''SELECT MAX(taxonomy_version) AS taxonomy_version FROM public.new_car_reputation_taxonomy_summary
                              WHERE import_batch=(SELECT MAX(import_batch) FROM public.new_car_reputation_taxonomy_summary)''')
            taxonomy_version=cursor.fetchone()[0] or ''
            match=re.search(r'/raw-([0-9a-f]{32})/',taxonomy_version)
            analysis_source_version=match.group(1) if match else None
            current=bool(analysis_source_version and analysis_source_version==version)
            analysis.update(taxonomy_version=taxonomy_version,analysis_batch=analysis['latest_batch'],
                            analysis_model_count=analysis['model_count'],analysis_source_version=analysis_source_version,
                            analysis_current=current,analysis_method='explicit_evidence_rules' if match else 'legacy_poc',
                            analysis_processed_review_count=result['review_count'] if current else None,
                            analysis_processed_model_count=result['source_model_count'] if current else None,
                            analysis_without_tag_review_count=result['review_count']-analysis['opinion_review_count'] if current else None)
            return {'success': True, 'data_source': 'reputation', 'status': 'ready',
                    'storage_backend': 'postgres', 'storage_tables': ['autohome_koubei','dongchedi_koubei'],
                    'sources': sources, 'data_version': version, **result, **analysis,
                    'source_name': '汽车之家＋懂车帝原始口碑',
                    'matching_method': '来源车型/采集输入名称精确匹配；不依据竞品正文归属',
                    'last_successful_import': None}
    finally:
        connection.rollback()
        connection.close()


def search_source_reviews(params: SourceReviewInput):
    clauses, values = ['TRUE'], []
    if params.model:
        clauses.append('(model=%s OR btrim(carname)=%s)')
        values.extend([params.model, params.model])
    if params.source:
        clauses.append('source=%s')
        values.append(params.source.value)
    if params.keyword:
        clauses.append('review_text ILIKE %s')
        values.append('%'+params.keyword+'%')
    if params.published_from:
        clauses.append('published_date >= %s')
        values.append(params.published_from)
    if params.published_to:
        clauses.append('published_date <= %s')
        values.append(params.published_to)
    where = ' AND '.join(clauses)
    connection = pg_connect()
    try:
        connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            version = _revision(cursor)
            cursor.execute('WITH raw AS ('+RAW+') SELECT source,COUNT(*) AS review_count FROM raw WHERE '+where+' GROUP BY source',tuple(values))
            counts = _dicts(cursor)
            total = sum(row['review_count'] for row in counts)
            cursor.execute('WITH raw AS ('+RAW+') SELECT * FROM raw WHERE '+where+
                           ' ORDER BY published_date DESC NULLS LAST,source,review_key LIMIT %s OFFSET %s',tuple(values+[params.limit,params.offset]))
            items = _dicts(cursor)
            has_more = params.offset+len(items)<total
            return {'success':True,'data_source':'reputation_raw','data_version':version,
                    'total_count':total,'count':len(items),'offset':params.offset,'has_more':has_more,
                    'next_offset':params.offset+len(items) if has_more else None,
                    'sources':counts,'items':items,
                    'warnings':['原始口碑不等同于已完成标签分析；评分来自平台，不是统一情感分。']}
    finally:
        connection.rollback()
        connection.close()
