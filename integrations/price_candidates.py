"""Local candidate inventory, not a validated monthly price series.

Keep price, cash, replacement and finance descriptions separate. Blank values
mean unknown; no numeric amount, eligibility or date is inferred.
"""
from __future__ import annotations

from datetime import date, datetime


def text(value):
    if value is None: return None
    if isinstance(value, (date, datetime)): return value.isoformat()
    result = str(value).strip()
    return result or None


def monitor_candidate(record, *, sheet, row, source):
    fields = {'old_price':text(record.get('原指导价')), 'new_price':text(record.get('现指导价')),
              'cash_discount':text(record.get('现金优惠')), 'replacement':text(record.get('置换及增购补贴')),
              'finance':text(record.get('金融政策')), 'restrictions':text(record.get('叠加及限制条件'))}
    if not any(fields.values()): return None
    return {'source':source, 'sheet':sheet, 'row':row, 'record_id':text(record.get('记录编号')),
            'brand':text(record.get('车企/品牌')), 'vehicle':text(record.get('车型')),
            'energy':text(record.get('动力类型')), 'region_channel':text(record.get('适用地区及渠道')),
            'observed_or_published':text(record.get('监测日期/发布日期')),
            'monitor_target_at':text(record.get('监测目标日期')),
            'article_published_at':text(record.get('文章发布日期')),
            'captured_at':text(record.get('采集日期')), 'starts_at':text(record.get('活动开始日期')),
            'ends_at':text(record.get('活动结束日期')), 'source_link':text(record.get('信息来源链接')),
            'fields':fields, 'review':'未核验：日期含义、金额、适用条件及叠加规则均需核对'}


def historical_candidate(record, *, sheet, row, source):
    # Historical sheets mix price changes and other benefits. Preserve source
    # text without guessing year, filling merged cells, or inferring cash.
    descriptions = [text(record.get(k)) for k in ('降幅（万元）','涨幅（万元）','优惠幅度','一口价/降价优惠','详情','备注','变化情况')]
    descriptions = [x for x in descriptions if x]
    if not descriptions: return None
    return {'source':source, 'sheet':sheet, 'row':row, 'brand':text(record.get('车企') or record.get('企业')),
            'vehicle':text(record.get('车型')), 'date_raw':text(record.get('降价时间') or record.get('涨价时间') or record.get('时间')),
            'source_link':text(record.get('链接')), 'descriptions':descriptions,
            'review':'未分类：可能包含价格、现金或条件性权益；日期、合并单元格及原始来源需核对'}
