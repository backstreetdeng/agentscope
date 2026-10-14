"""Local, entity-bound argument selection for the rest of the monthly deck.

The model edits an already calculated argument, not a bag of flattened cells.
Every percentage has an entity, period, metric and denominator. Derived claims
keep their operands; missing ranking rows do not become a complete universe.
"""
from __future__ import annotations

from copy import deepcopy
import re
import unicodedata
from typing import Any

BUSINESS_PAGES = (4, 5, 7, 8, 12, 13, 14, 15, 16, 17, 18, 19)


def _width(text: str) -> float:
    return sum(1 if unicodedata.east_asian_width(c) in {'W', 'F', 'A'} else .55 for c in text)


def _count(value: float) -> str:
    return f'{value / 10000:.1f}万辆' if abs(value) >= 10000 else f'{value:g}辆'


def _change(value: float) -> str:
    if value == 0:
        return '持平'
    return f'{"增长" if value >= 0 else "下降"}{abs(value):.1f}%'


def _point(value: float) -> str:
    if value == 0:
        return '持平'
    return f'{"提高" if value >= 0 else "回落"}{abs(value):.1f}个百分点'


class _Argument:
    def __init__(self, page: int, packet: dict, month: str):
        self.page, self.packet, self.month = page, packet, month
        self.rows = packet['business_facts']
        self.claims: list[dict] = []
        self.guards: list[str] = []

    def row(self, entity: str, scope='single_month', code=None, period=None) -> dict:
        rows = [r for r in self.rows if r['entity'] == entity and r['scope'] == scope
                and r['period'] == (period or self.month) and (code is None or r['source_card_code'] == code)]
        if len(rows) != 1:
            raise ValueError(f'第{self.page}页{entity}/{scope}缺少唯一的具名事实，不能猜测。')
        return rows[0]

    def derive(self, entity: str, key: str, value: float, sources: list[dict], operands: dict,
               method: str, scope='single_month', **extra) -> dict:
        row = {'fact_id': f'CALC:{self.page}:{entity}:{key}:{scope}:{self.month}',
               'entity': entity, 'scope': scope, 'period': self.month, 'metric': key,
               key: value, 'source_card_code': 'CALC',
               'source_fact_ids': [r['fact_id'] for r in sources],
               'operands': operands, 'method': method, **extra}
        self.rows.append(row)
        return row

    def contribution(self, entity: dict, members: list[dict], field='delta_yoy') -> dict:
        numerator = entity[field]
        denominator = sum(r[field] for r in members)
        if not denominator or numerator * denominator <= 0:
            raise ValueError('增减贡献缺少同向、非零的净增减分母。')
        return self.derive(entity['entity'], 'net_change_share_pct', round(numerator / denominator * 100, 1),
                           members, {'numerator_delta': numerator, 'denominator_delta': denominator},
                           f'{field}: numerator_delta / sum(complete_group_delta) * 100',
                           scope=entity['scope'], comparison_metric=field)

    def claim(self, role: str, text: str, *rows: dict):
        self.claims.append({'role': role, 'claim': text, 'fact_ids': list(dict.fromkeys(r['fact_id'] for r in rows)),
                            'evidence_ids': [], 'certainty': 'unverified'})

    def guard(self, text: str) -> str:
        self.guards.append(text)
        return text

    def group(self, code: str, scope='single_month') -> list[dict]:
        group = next((g for g in self.packet['coverage']['groups']
                      if g['card_code'] == code and g['scope'] == scope), None)
        if not group or not group['comparison_complete']:
            raise ValueError(f'{code}没有完整比较集合，不能作全组比较。')
        return [r for r in self.rows if r['source_card_code'] == code and r['scope'] == scope and r['period'] == self.month]


def _current_pattern_supported(page: int, packet: dict, month: str) -> bool:
    """The selected argument is conditional, never a permanent negative story."""
    def row(entity, scope='single_month', code=None):
        return next(r for r in packet['business_facts'] if r['entity'] == entity and r['scope'] == scope
                    and r['period'] == month and (not code or r['source_card_code'] == code))
    def group(code, scope='single_month'):
        return [r for r in packet['business_facts'] if r['source_card_code'] == code and r['scope'] == scope and r['period'] == month]
    try:
        if page == 4:
            return row('整体市场')['yoy_pct'] < 0 and row('整体市场', 'year_to_date')['yoy_pct'] < 0 and row('整体市场')['mom_pct'] > 0
        if page == 5:
            trad, nev = row('传统车', 'stock'), row('新能源', 'stock')
            return (row('行业库存', 'stock')['mom_pct'] < 0 < row('整体市场')['mom_pct'] and
                    trad['mom_pct'] < 0 < nev['mom_pct'] and
                    trad['value'] / row('传统车', code='P1.2-2B')['value'] > nev['value'] / row('新能源', code='P1.2-2B')['value'])
        if page == 7:
            return all(r['delta_yoy'] < 0 for r in group('P2-1.1')) and row('轿车')['yoy_pct'] < row('SUV')['yoy_pct'] and row('轿车')['mom_pct'] > row('SUV')['mom_pct'] > 0
        if page == 8:
            return (sum(r['yoy_pct'] > 0 for r in group('P2-2.1')) == 1 and row('A0')['yoy_pct'] > 0 and
                    row('C+')['mom_pct'] < 0 and all(r['mom_pct'] > 0 for r in group('P2-2.1') if r['entity'] != 'C+'))
        if page == 12:
            return all(r['yoy_pct'] < 0 for r in group('P2-6.1')) and row('自主')['yoy_pct'] > row('日系')['yoy_pct'] and row('美系')['mom_pct'] > 0 > row('韩系')['mom_pct']
        if page == 13:
            return (all(r['yoy_pct'] < 0 for r in group('P2-7.1')) and row('20-25万')['mom_pct'] > 0 > row('15-20万')['mom_pct'] and row('35万以上')['mom_pct'] < 0 and
                    sum(r['yoy_pct'] > 0 for r in group('P2-7.2', 'year_to_date')) == 1 and row('25-35万', 'year_to_date')['yoy_pct'] > 0)
        if page == 14:
            return all(r['yoy_pct'] < 0 for r in group('P2-8.2')) and row('中部')['yoy_pct'] < row('西部')['yoy_pct']
        if page == 15:
            return row('三线城市')['mom_pct'] > row('一线城市')['mom_pct'] and all(r['delta_yoy'] < 0 for r in group('P2-9.1'))
        if page == 16:
            return row('比亚迪汽车')['yoy_pct'] < row('吉利汽车')['yoy_pct'] < 0 and row('比亚迪汽车', 'year_to_date')['yoy_pct'] < row('吉利汽车', 'year_to_date')['yoy_pct'] < 0
        if page == 17:
            return row('传统车')['yoy_pct'] < row('新能源')['yoy_pct'] < 0 and row('新能源', 'year_to_date')['yoy_pct'] < 0 and row('新能源')['share_change_pp'] > 0
        if page == 18:
            return row('PHEV', code='P2-12.1')['yoy_pct'] < row('BEV', code='P2-12.1')['yoy_pct'] < 0 and row('PHEV', code='P2-12.1')['mom_pct'] < 0 < row('BEV', code='P2-12.1')['mom_pct']
        if page == 19:
            return row('零跑汽车')['yoy_pct'] > 0 > row('比亚迪汽车')['yoy_pct'] and row('长安汽车')['mom_pct'] < 0 and row('零跑汽车', 'year_to_date')['yoy_pct'] > 0 > row('比亚迪汽车', 'year_to_date')['yoy_pct']
    except (StopIteration, KeyError, ZeroDivisionError):
        return False
    return False


def comparison_headline(x: dict, y: dict, name, metric: str) -> str:
    """State a measured pairwise relationship rather than a reading instruction."""
    label = '同比' if metric == 'yoy_pct' else '环比'
    fast, slow = sorted((x, y), key=lambda row: row[metric], reverse=True)
    if fast[metric] < 0 and fast[metric] != slow[metric]:
        return f'{name(fast)}{label}降幅小于{name(slow)}，两者仍收缩'
    if slow[metric] > 0 and fast[metric] != slow[metric]:
        return f'{name(fast)}{label}增长快于{name(slow)}，增量恢复不均'
    if slow[metric] < 0 < fast[metric]:
        return f'{name(fast)}{label}增长与{name(slow)}收缩并存'
    relation = '均下降' if fast[metric] < 0 else '均增长' if slow[metric] > 0 else '方向存在差异'
    return f'{name(x)}与{name(y)}{label}{relation}'


def _adaptive_draft(page: int, packet: dict, month: str) -> dict:
    """An opposite-direction month gets a new factual comparison, not old prose."""
    a = _Argument(page, packet, month)
    if page == 4:
        r, y = a.row('整体市场'), a.row('整体市场', 'year_to_date')
        a.claim('core', f'{int(month[5:])}月整体市场零售{_count(r["value"])}，同比{_change(r["yoy_pct"])}、环比{_change(r["mom_pct"])}；两类增速分别衡量同期表现和最近变化，不以单一增速替代整体走势。',r)
        a.claim('structure', f'整体市场同比净{"增" if r["delta_yoy"] >= 0 else "减"}{_count(abs(r["delta_yoy"]))}，环比净{"增" if r["delta_mom"] >= 0 else "减"}{_count(abs(r["delta_mom"]))}；增减量与增速的基数不同，应结合规模观察。',r)
        a.claim('support', f'1—{int(month[5:])}月整体市场累计零售{_count(y["value"])}、同比{_change(y["yoy_pct"])}；累计反映阶段规模，单月反映最新变化，结合判断。',y)
        packet['business_guards'] = []
        return {'slide':page,'headline':f'整体市场同比{_change(r["yoy_pct"])}，单月与累计口径分别观察',
                'anomaly':{'type':'ordinary_change','priority':7,'fact_ids':[r['fact_id'],y['fact_id']]},'headline_evidence_ids':[],'body_claims':a.claims}
    scope = 'stock' if page == 5 else 'single_month'
    current = sorted([r for r in a.rows if r['period'] == month and r['scope'] == scope and
                      'value' in r and ('yoy_pct' in r or 'mom_pct' in r)], key=lambda r: -r['value'])
    # P18 has two denominator-specific versions of the same quantities.
    current = list({r['entity']: r for r in reversed(current)}.values())
    current.sort(key=lambda r: -r['value'])
    if page == 5:
        current = [a.row('新能源','stock'),a.row('传统车','stock')]
    if not current:
        raise ValueError(f'第{page}页没有足以形成分析的目标月份具名事实。')
    x, y = current[0], current[min(1, len(current)-1)]
    name = lambda r: r['entity'] + ('级' if page == 8 else '')
    metric = 'yoy_pct' if all('yoy_pct' in r for r in (x,y)) else 'mom_pct'
    title_metric = '同比' if metric == 'yoy_pct' else '环比'
    relation = '一增一减' if x[metric] * y[metric] < 0 else '均增长' if min(x[metric],y[metric]) > 0 else '均下降' if max(x[metric],y[metric]) < 0 else '方向存在差异'
    noun = '库存' if scope == 'stock' else '单月零售'
    stronger, weaker = sorted((x,y), key=lambda r:r[metric], reverse=True)
    interpretation = (f'{name(stronger)}同期收缩较小' if max(x[metric],y[metric]) < 0
                      else f'{name(stronger)}同期增长较快' if min(x[metric],y[metric]) > 0
                      else '两者同期增长方向分化')
    a.claim('core', f'{int(month[5:])}月{name(x)}{noun}{_count(x["value"])}、{title_metric}{_change(x[metric])}，{name(y)}{title_metric}{_change(y[metric])}；两者{relation}，{interpretation}。', x,y)
    a.guard(f'两者{relation}')
    if 'mom_pct' in x and 'mom_pct' in y:
        faster, slower = sorted((x,y), key=lambda r:r['mom_pct'], reverse=True)
        comparison = ('两者环比增速相同，近期变化方向一致' if x['mom_pct'] == y['mom_pct']
                      else f'{name(faster)}环比增速高于{name(slower)}，恢复不均')
        a.claim('structure', f'{name(x)}环比{_change(x["mom_pct"])}，{name(y)}环比{_change(y["mom_pct"])}；{comparison}。', x,y)
    else:
        a.claim('structure', f'{name(x)}当月份额{x["share_pct"]:.1f}%，{name(y)}当月份额{y["share_pct"]:.1f}%；份额只表示该口径的相对位置，不能替代销量增速或据此判断全部对象的排名。', x,y)
    cum = [r for r in a.rows if r['scope'] == 'year_to_date' and r['period'] == month and 'yoy_pct' in r]
    if cum:
        z = max(cum, key=lambda r:r['value'])
        single = next((r for r in current if r['entity'] == z['entity']), None)
        if single is not None and 'yoy_pct' in single:
            if single['yoy_pct'] < 0 and z['yoy_pct'] < 0:
                context = '累计与当月同比方向一致，阶段规模尚未恢复至去年同期'
            elif single['yoy_pct'] > 0 and z['yoy_pct'] > 0:
                context = '累计与当月同比方向一致，最新恢复与阶段扩张相互印证'
            elif single['yoy_pct'] < 0 < z['yoy_pct']:
                context = '累计同比增长而单月下降，最新变化与阶段走势出现分化'
            else:
                context = '单月与累计同比方向分化，最新表现与阶段规模不同步'
            a.claim('support', f'1—{int(month[5:])}月{name(z)}累计零售{_count(z["value"])}、同比{_change(z["yoy_pct"])}；{context}。', z,single)
        else:
            a.claim('support', f'1—{int(month[5:])}月{name(z)}累计零售{_count(z["value"])}、同比{_change(z["yoy_pct"])}；累计规模与单月变化结合判断，不沿用历史趋势。',z)
    elif scope == 'stock':
        total = a.row('行业库存','stock')
        a.claim('support', f'行业库存合计{_count(total["value"])}、环比{_change(total["mom_pct"])}；新能源与传统车分别比较库存规模和环比变化，总量增减不代表各类型变化幅度相同。',total)
    else:
        z = current[min(2,len(current)-1)]
        a.claim('support', f'{name(z)}单月零售{_count(z["value"])}、同比{_change(z[metric])}，当月份额{z["share_pct"]:.1f}%；规模、增速和份额分别观察，结论落实到具体对象。',z)
    packet['business_guards'] = a.guards
    return {'slide':page,'headline':comparison_headline(x, y, name, metric),
            'anomaly':{'type':'structural_divergence','priority':7,'fact_ids':list(dict.fromkeys(v for c in a.claims for v in c['fact_ids']))},
            'headline_evidence_ids':[],'body_claims':a.claims}


def business_fact_draft(page: int, packet: dict[str, Any], month: str) -> dict:
    """Select page-specific relationships, not a fixed one-line summary."""
    if not _current_pattern_supported(page, packet, month):
        return _adaptive_draft(page, packet, month)
    a = _Argument(page, packet, month)
    label = f'{int(month[5:])}月'
    end = int(month[5:])
    previous = f'{int(month[:4]) - 1}-12' if end == 1 else f'{month[:4]}-{end - 1:02d}'
    headline = ''
    if page == 4:
        r, y = a.row('整体市场'), a.row('整体市场', 'year_to_date')
        p = a.row('整体市场', period=previous)
        diff = a.derive('整体市场', 'yoy_change_pp', round(r['yoy_pct'] - p['yoy_pct'], 1), [r, p],
                        {'current_yoy': r['yoy_pct'], 'previous_yoy': p['yoy_pct']}, 'current_yoy-previous_yoy')
        history = [v for v in a.rows if v['entity'] == '整体市场' and v['scope'] == 'single_month' and v.get('source_card_code') == 'P1.1-1'
                   and v['period'].startswith(month[:4]) and v['period'] <= month]
        complete = len({v['period'] for v in history if 'yoy_pct' in v}) == end
        extreme = a.guard('同比降幅为年内已披露月份最大') if complete and r['yoy_pct'] == min(v['yoy_pct'] for v in history) else '同比表现仍弱于去年同期'
        headline = '环比回升未抵消同比缺口，累计市场仍承压'
        a.claim('core', f'{label}整体市场零售{_count(r["value"])}，同比{_change(r["yoy_pct"])}、环比{_change(r["mom_pct"])}，{extreme}。', r, *history)
        gap = '扩大' if diff['yoy_change_pp'] < 0 else '收窄'
        a.claim('structure', f'整体市场同比净减{_count(abs(r["delta_yoy"]))}，同比降幅较上月{gap}{abs(diff["yoy_change_pp"]):.1f}个百分点，环比回升尚未弥合去年同期销量缺口。', r, diff)
        a.claim('support', f'1—{end}月整体市场累计零售{_count(y["value"])}，同比{_change(y["yoy_pct"])}，单月与累计均低于去年同期，市场压力并非单月波动。', y)
    elif page == 5:
        stock, sale = a.row('行业库存', 'stock'), a.row('整体市场')
        trad, nev = a.row('传统车', 'stock'), a.row('新能源', 'stock')
        def ratio(s, v, entity):
            return a.derive(entity, 'inventory_sales_ratio', round(s['value'] / v['value'], 1), [s, v],
                            {'stock': s['value'], 'retail': v['value']}, 'stock/retail', scope='stock')
        total_ratio = ratio(stock, sale, '行业库存')
        t = ratio(trad, a.row('传统车', code='P1.2-2B'), '传统车')
        n = ratio(nev, a.row('新能源', code='P1.2-2B'), '新能源')
        headline = f'{label}行业库存{_count(stock["value"])}，存销比{total_ratio["inventory_sales_ratio"]:.1f}'
        a.claim('core', f'{label}行业库存{_count(stock["value"])}，环比{_change(stock["mom_pct"])}；整体市场零售环比{_change(sale["mom_pct"])}，库存与销量一降一升，行业库存存销比{total_ratio["inventory_sales_ratio"]:.1f}。', stock, sale, total_ratio)
        a.claim('structure', f'传统车库存{_count(trad["value"])}、环比{_change(trad["mom_pct"])}，新能源库存{_count(nev["value"])}、环比{_change(nev["mom_pct"])}，能源类型一降一升。', trad, nev)
        a.claim('support', f'传统车存销比{t["inventory_sales_ratio"]:.1f}，新能源存销比{n["inventory_sales_ratio"]:.1f}；传统车去化更快，但相对销量的库存负担仍较重，不能只看总库存下降。', t, n, trad, nev)
    elif page == 7:
        rows = a.group('P2-1.1'); sedan, suv, mpv = (a.row(v) for v in ('轿车', 'SUV', 'MPV'))
        contrib = a.contribution(sedan, rows)
        headline = '轿车环比回升但仍是同比减量主因，SUV相对抗跌'
        a.claim('core', f'{label}SUV零售{_count(suv["value"])}、同比{_change(suv["yoy_pct"])}，降幅小于轿车同比{_change(sedan["yoy_pct"])}及MPV同比{_change(mpv["yoy_pct"])}，SUV相对抗跌。', suv, sedan, mpv)
        a.claim('structure', f'轿车环比{_change(sedan["mom_pct"])}，快于SUV环比{_change(suv["mom_pct"])}；轿车单月份额较上月{_point(sedan["share_change_pp"])}至{sedan["share_pct"]:.1f}%，修复集中于轿车。', sedan, suv)
        a.claim('support', f'轿车同比净减{_count(abs(sedan["delta_yoy"]))}，占全类别净减{contrib["net_change_share_pct"]:.1f}%，是同比主要拖累；环比改善与同比压力并存，份额回升不等于规模增长。', sedan, contrib)
    elif page == 8:
        rows = a.group('P2-2.1'); a0, a00, b, c = (a.row(v) for v in ('A0', 'A00', 'B', 'C+'))
        prevc = a.row('C+', period=previous)
        group_delta = a0['delta_mom'] + b['delta_mom']; total_delta = sum(r['delta_mom'] for r in rows)
        g = a.derive('B与A0', 'delta_mom', group_delta, [b, a0], {'B_delta': b['delta_mom'], 'A0_delta': a0['delta_mom']}, 'B_delta+A0_delta')
        share = a.derive('B与A0', 'net_change_share_pct', round(group_delta / total_delta * 100, 1), rows,
                         {'group_delta': group_delta, 'total_delta': total_delta}, 'group_delta/total_delta*100')
        only = a.guard('A0级唯一同比增长') if sum(r['yoy_pct'] > 0 for r in rows) == 1 and a0['yoy_pct'] > 0 else 'A0级同比增长'
        headline = f'{only}，环比增量主要来自B级与A0级'
        a.claim('core', f'{label}{only}{a0["yoy_pct"]:.1f}%，其余级别同比下降；A00级环比{_change(a00["mom_pct"])}，A0级环比{_change(a0["mom_pct"])}，小型级别恢复更快。', *rows)
        a.claim('structure', f'B与A0合计环比净增{_count(group_delta)}，占全级别环比净增{share["net_change_share_pct"]:.1f}%；B级单月份额{b["share_pct"]:.1f}%，增量贡献不同于增速排名。', g, share, b)
        narrow = '收窄' if c['mom_pct'] < 0 and prevc['mom_pct'] < c['mom_pct'] else '变化'
        a.guard(f'C+级环比降幅{narrow}')
        a.claim('support', f'C+级单月零售{_count(c["value"])}、环比{_change(c["mom_pct"])}，C+级环比降幅{narrow}，仍与其他级别方向相反；环比修复尚未扩展至全部级别。', c, prevc)
    elif page == 12:
        rows = a.group('P2-6.1'); own, us, jp, kr = (a.row(v) for v in ('自主', '美系', '日系', '韩系'))
        all_down = a.guard('各系别单月同比均下降') if all(r['yoy_pct'] < 0 for r in rows) else '系别同比表现分化'
        headline = '自主相对抗跌，美系环比反弹但同比仍下降'
        a.claim('core', f'{label}{all_down}；自主同比{_change(own["yoy_pct"])}，日系同比{_change(jp["yoy_pct"])}，自主降幅较小，份额优势不等于销量增长。', own, jp, *rows)
        a.claim('structure', f'美系单月零售{_count(us["value"])}、环比{_change(us["mom_pct"])}，但同比{_change(us["yoy_pct"])}；韩系环比{_change(kr["mom_pct"])}，恢复方向并不一致。', us, kr)
        a.claim('support', f'美系单月份额较上月{_point(us["share_change_pp"])}至{us["share_pct"]:.1f}%，自主份额较上月{_point(own["share_change_pp"])}至{own["share_pct"]:.1f}%，增速差异改变当月结构。', us, own)
    elif page == 13:
        rows = a.group('P2-7.1'); mid, high, hot = (a.row(v) for v in ('15-20万', '35万以上', '20-25万'))
        ytd = a.group('P2-7.2', 'year_to_date'); grow = a.row('25-35万', 'year_to_date')
        a.guard('各价格段单月同比均下降') if all(r['yoy_pct'] < 0 for r in rows) else None
        only = a.guard('累计仅25-35万同比增长') if sum(r['yoy_pct'] > 0 for r in ytd) == 1 and grow['yoy_pct'] > 0 else '累计25-35万同比增长'
        headline = '单月同比普降，累计25-35万逆势扩张'
        a.claim('core', f'{label}各价格段单月同比均下降；15-20万同比{_change(mid["yoy_pct"])}，35万以上同比{_change(high["yoy_pct"])}，两档收缩明显，同比恢复并不普遍。', *rows)
        a.claim('structure', f'20-25万环比{_change(hot["mom_pct"])}，15-20万环比{_change(mid["mom_pct"])}，35万以上环比{_change(high["mom_pct"])}，单月恢复集中于部分价格段。', hot, mid, high)
        a.claim('support', f'1—{end}月{only}{grow["yoy_pct"]:.1f}%，累计份额{grow["share_pct"]:.1f}%、较去年同期{_point(grow["share_change_pp"])}，累计增长集中于该价段。', *ytd)
    elif page == 14:
        rows = a.group('P2-8.2'); center, west, east, ne = (a.row(v, code='P2-8.2') for v in ('中部', '西部', '东部', '东北'))
        headline = '中部收缩较深、西部相对抗跌，区域结构继续分化'
        a.claim('core', f'{label}中部同比{_change(center["yoy_pct"])}，西部同比{_change(west["yoy_pct"])}；东部零售{_count(east["value"])}，各区域均低于去年同期，收缩幅度不同。', *rows)
        a.claim('structure', f'西部单月份额较去年同期{_point(west["share_change_pp"])}至{west["share_pct"]:.1f}%，中部份额较去年同期{_point(center["share_change_pp"])}至{center["share_pct"]:.1f}%。', west, center)
        provinces = [r for r in a.rows if r['source_card_code'] == 'P2-8.1' and r['period'] == month and r.get('region') == '东北']
        if {r['entity'] for r in provinces} == {'辽宁', '吉林', '黑龙江'} and sum(r['value'] for r in provinces) == ne['value']:
            h = a.row('黑龙江', code='P2-8.1'); con = a.contribution(h, provinces)
            a.claim('support', f'黑龙江零售{_count(h["value"])}、同比{_change(h["yoy_pct"])}，占东北同比净减{con["net_change_share_pct"]:.1f}%；省份表现不同，黑龙江减量影响较大。', h, con)
        else:
            a.claim('support', f'东北单月零售{_count(ne["value"])}、同比{_change(ne["yoy_pct"])}，弱于西部；现有省份明细不完整，只对已核验区域比较，不据此推断全国省份排名。', ne, west)
    elif page == 15:
        rows = a.group('P2-9.1'); first, third, second = (a.row(v) for v in ('一线城市', '三线城市', '二线城市'))
        con = a.contribution(second, rows)
        headline = '三线环比回升快于一线，二线仍贡献较大同比减量'
        a.claim('core', f'{label}三线城市零售{_count(third["value"])}、环比{_change(third["mom_pct"])}，一线城市环比{_change(first["mom_pct"])}，线级之间回升并不均衡。', third, first)
        a.claim('structure', f'一线城市份额较上月{_point(first["share_change_pp"])}至{first["share_pct"]:.1f}%，三线城市份额较上月{_point(third["share_change_pp"])}至{third["share_pct"]:.1f}%，结构向三线倾斜。', first, third)
        a.claim('support', f'二线城市同比净减{_count(abs(second["delta_yoy"]))}，占全线级净减{con["net_change_share_pct"]:.1f}%，是重要同比减量来源；环比回升尚不足抵补去年同期规模缺口。', second, con)
    elif page == 16:
        byd, geely, changan, chery = (a.row(v) for v in ('比亚迪汽车', '吉利汽车', '长安汽车', '奇瑞汽车'))
        yb, yg = a.row('比亚迪汽车', 'year_to_date'), a.row('吉利汽车', 'year_to_date')
        headline = '比亚迪与吉利均收缩，比亚迪累计同比压力更大'
        a.claim('core', f'{label}比亚迪汽车零售{_count(byd["value"])}、同比{_change(byd["yoy_pct"])}，吉利汽车同比{_change(geely["yoy_pct"])}；两家均收缩，比亚迪同比压力更大。', byd, geely)
        a.claim('structure', f'比亚迪汽车单月份额{byd["share_pct"]:.1f}%，吉利汽车份额{geely["share_pct"]:.1f}%；奇瑞汽车环比{_change(chery["mom_pct"])}，长安汽车环比{_change(changan["mom_pct"])}，恢复有差异。', byd, geely, chery, changan)
        a.claim('support', f'1—{end}月比亚迪汽车累计同比{_change(yb["yoy_pct"])}，吉利汽车累计同比{_change(yg["yoy_pct"])}；单月环比回升与累计同比收缩并存。', yb, yg)
    elif page == 17:
        nev, trad = a.row('新能源'), a.row('传统车'); y = a.row('新能源', 'year_to_date')
        ty = a.row('传统车', 'year_to_date')
        p = a.row('新能源', period=previous)
        diff = a.derive('新能源', 'yoy_change_pp', round(nev['yoy_pct'] - p['yoy_pct'], 1), [nev, p],
                        {'current_yoy': nev['yoy_pct'], 'previous_yoy': p['yoy_pct']}, 'current_yoy-previous_yoy')
        headline = '新能源渗透率提高，但自身同比压力仍未缓解'
        a.claim('core', f'{label}新能源零售{_count(nev["value"])}，同比{_change(nev["yoy_pct"])}、环比{_change(nev["mom_pct"])}；传统车同比{_change(trad["yoy_pct"])}，抗跌不等于规模增长。', nev, trad)
        a.claim('structure', f'新能源占整体市场{nev["share_pct"]:.1f}%，较上月{_point(nev["share_change_pp"])}；新能源同比降幅较上月{"扩大" if diff["yoy_change_pp"] < 0 else "收窄"}{abs(diff["yoy_change_pp"]):.1f}个百分点，渗透率上升而降幅扩大。', nev, diff)
        a.claim('support', f'1—{end}月新能源累计{_count(y["value"])}、同比{_change(y["yoy_pct"])}，传统车累计同比{_change(ty["yoy_pct"])}；累计相对抗跌仍未转为增长。', y, ty)
    elif page == 18:
        phev, bev = a.row('PHEV', code='P2-12.1'), a.row('BEV', code='P2-12.1')
        prev = a.row('BEV', code='P2-12.1', period=previous)
        overall = a.row('BEV', code='P2-12.2')
        con = a.contribution(phev, [phev, bev])
        reversal = a.guard('BEV同比由上月增长转为下降') if prev.get('yoy_pct', 0) > 0 > bev['yoy_pct'] else 'BEV同比仍低于去年同期'
        headline = f'{reversal}，PHEV为新能源同比减量主因'
        a.claim('core', f'{label}BEV零售{_count(bev["value"])}、同比{_change(bev["yoy_pct"])}，{reversal}；PHEV同比{_change(phev["yoy_pct"])}，两类动力均低于去年同期。', bev, phev, prev)
        a.claim('structure', f'BEV环比{_change(bev["mom_pct"])}，PHEV环比{_change(phev["mom_pct"])}；PHEV同比净减{_count(abs(phev["delta_yoy"]))}，占新能源同比净减{con["net_change_share_pct"]:.1f}%，是主要拖累。', bev, phev, con)
        a.claim('support', f'BEV占新能源内部{bev["share_pct"]:.1f}%，BEV占整体市场{overall["share_pct"]:.1f}%；内部结构向BEV集中与新能源同比下降并存，份额与规模背离。', bev, overall)
    elif page == 19:
        byd, leap, ca = (a.row(v) for v in ('比亚迪汽车', '零跑汽车', '长安汽车'))
        ly, by = a.row('零跑汽车', 'year_to_date'), a.row('比亚迪汽车', 'year_to_date')
        headline = '零跑同比扩张与比亚迪收缩并存，新能源企业分化'
        a.claim('core', f'{label}零跑汽车零售{_count(leap["value"])}、同比{_change(leap["yoy_pct"])}，比亚迪汽车同比{_change(byd["yoy_pct"])}，新能源整体承压下，两家企业一增一减。', leap, byd)
        a.claim('structure', f'比亚迪汽车占新能源市场{byd["share_pct"]:.1f}%，零跑汽车份额{leap["share_pct"]:.1f}%；长安汽车零售{_count(ca["value"])}、环比{_change(ca["mom_pct"])}，恢复不均。', byd, leap, ca)
        a.claim('support', f'1—{end}月零跑汽车累计零售{_count(ly["value"])}、同比{_change(ly["yoy_pct"])}，比亚迪汽车累计同比{_change(by["yoy_pct"])}；累计同样分化。', ly, by)
    else:
        raise ValueError(f'unsupported page {page}')
    all_ids = list(dict.fromkeys(v for claim in a.claims for v in claim['fact_ids']))
    packet['business_guards'] = a.guards
    return {'slide': page, 'headline': headline, 'headline_evidence_ids': [],
            'anomaly': {'type': 'contribution_concentration' if any(r.get('net_change_share_pct') for r in a.rows) else 'structural_divergence',
                        'priority': 8, 'fact_ids': all_ids}, 'body_claims': a.claims}


def validate_business_slide(slide: dict, payload: dict) -> None:
    """Bind each number to its cited entity/metric/scope; fail closed on prose.

This intentionally uses explicit business grammar. When an editor rewrites a
pairing ambiguously, retry that page rather than treating an arbitrary number
elsewhere in the card as evidence. Format-valid is not business-valid.
"""
    page, month = int(slide['slide']), payload['coverage']['period']
    # Repair the known instruction-like legacy heading using the same local
    # fact selection as generation. Record the change and still validate it.
    if '结构比较需区分口径' in slide.get('headline', ''):
        original = slide['headline']
        repaired = business_fact_draft(page, deepcopy(payload), month)['headline']
        prefix = original.split('：', 1)[0] + '：' if '：' in original else ''
        slide['headline'] = prefix + repaired
        slide['headline_repair'] = {'original': original, 'method': 'typed_pairwise_comparison'}
    rows = {r['fact_id']: r for r in payload['business_facts']}
    claims = slide.get('body_claims', [])
    if len(claims) != 3 or {c.get('role') for c in claims} != {'core', 'structure', 'support'}:
        raise ValueError(f'第{page}页应保留core/structure/support三层事实关系。')
    all_refs = [*slide.get('anomaly', {}).get('fact_ids', []), *(v for c in claims for v in c.get('fact_ids', []))]
    bad = [v for v in all_refs if v not in rows]
    if bad:
        raise ValueError(f'第{page}页引用未具名或非本页事实：{bad}')
    slide['coverage_requirement'] = {'minimum_layers': 3, 'entity_metric_bound': True}
    text_parts = [(slide.get('headline', ''), all_refs), *((c['claim'], c['fact_ids']) for c in claims)]
    names = {r['entity'] for r in rows.values()} | {'B与A0'}
    aliases = {v: v for v in names}
    if page == 4:
        aliases['零售量'] = '整体市场'  # fixed title explicitly names the market metric
    for v in ('A00', 'A0', 'A', 'B', 'C+'):
        if v in names:
            aliases[v + '级'] = v
            aliases.pop(v, None)
    pattern = '|'.join(re.escape(v) for v in sorted(aliases, key=len, reverse=True))
    measurement = re.compile(r'\d[\d,]*(?:\.\d+)?(?:(?:亿|万)?辆|%|个百分点)')
    for part_index, (text, refs) in enumerate(text_parts):
        assertion_count = 0
        stock_assertions = [m for m in re.finditer(r'同步去化|同步下降|双双下降|均去化', text)
                            if not re.search(r'不能|不可|不宜|并非|不代表', text[max(0, text.rfind('；', 0, m.start()) + 1):m.start()])]
        if page == 5 and stock_assertions:
            stock = [r for r in rows.values() if r['scope'] == 'stock' and r['period'] == month and r['entity'] in ('新能源', '传统车')]
            if len(stock) != 2 or not all(r.get('mom_pct', 0) < 0 for r in stock):
                raise ValueError('库存不同方向，不能写新能源与传统车同步去化。')
        # No annual/monthly or incomplete-ranking assertions introduced by an editor.
        if re.search(r'全年|需求转强|需求增长|集中交付|估算|预计', text):
            raise ValueError(f'第{page}页引入未核验口径或原因。')
        if re.search(r'大头|形势喜人|全面向好', text):
            raise ValueError(f'第{page}页表达过于笼统或口语化，需落实到具名对象和比较口径。')
        for phrase in re.findall(r'[^，；。]*?(?:唯一|领先|领涨|领跌|创新高|最深|最大|连续|均下降|全线(?:增长|回升|下降))[^，；。]*', text):
            if not any(guard in phrase for guard in payload.get('business_guards', [])):
                # A named pair declining is a directional claim, not a rank or
                # a statement about every member of the comparison universe.
                # Verify its cited current-period rows instead of requiring
                # the editor to repeat the literal phrase "两者均下降".
                if ('均下降' in phrase and not re.search(r'唯一|领先|领涨|领跌|创新高|最深|最大|连续|全线|全部|各(?:个|价格|系别|区域|线级)', phrase)):
                    entities = {aliases[m[0]] for m in re.finditer(pattern, phrase)}
                    metric = 'yoy_pct' if '同比' in phrase else 'mom_pct' if '环比' in phrase else ''
                    scope = 'year_to_date' if '累计' in phrase else 'single_month'
                    cited_rows = [rows[value] for value in refs if value in rows]
                    if (len(entities) >= 2 and metric and all(
                            any(row['entity'] == entity and row['period'] == month and row['scope'] == scope
                                and row.get(metric) is not None and row[metric] < 0 for row in cited_rows)
                            for entity in entities)):
                        continue
                # A negative boundary statement is not an assertion of an incomplete rank.
                if re.search(r'不能|不泛化|不据此|不宜', phrase):
                    continue
                raise ValueError(f'第{page}页比较集合未支持该极值/连续表述：{phrase}')
        cited = [rows[v] for v in refs if v in rows]
        found = [m for m in re.finditer(pattern, text) if not re.search(r'占(?:全部|全国)?$', text[:m.start()])]
        prefix = text[:found[0].start()] if found else text
        if measurement.search(prefix):
            raise ValueError(f'第{page}页数字前缺少具名对象，不能借用后文事实。')
        for i, match in enumerate(found):
            checked_spans = []
            entity = aliases[match[0]]
            clause = text[match.end():found[i + 1].start() if i + 1 < len(found) else len(text)]
            # A generic conclusion after a sentence boundary is not a metric
            # assertion about the preceding entity (e.g. 吉利累计...；单月回升).
            local_clause = re.split(r'[；。]', clause, maxsplit=1)[0]
            scope_markers = list(re.finditer(r'累计|单月|当月|库存', text[:match.end()]))
            scope = 'year_to_date' if scope_markers and scope_markers[-1][0] == '累计' else 'stock' if scope_markers and scope_markers[-1][0] == '库存' else 'stock' if page == 5 and all(r['scope'] == 'stock' for r in cited if r['entity'] == entity) else 'single_month'
            local_scope = list(re.finditer(r'累计|单月|当月|库存', clause[:8]))
            if local_scope:
                scope = 'year_to_date' if local_scope[-1][0] == '累计' else 'stock' if local_scope[-1][0] == '库存' else 'single_month'
            elif '零售' in clause[:8] and '累计' not in text[max(0, text.rfind('；', 0, match.start()) + 1):match.start()]:
                scope = 'single_month'
            candidates = [r for r in cited if r['entity'] == entity and r['scope'] == scope and r['period'] == month]
            # A ratio retains stock scope even when its name omits the word 库存.
            if '存销比' in clause[:8]:
                candidates = [r for r in cited if r['entity'] == entity and r['scope'] == 'stock' and r['period'] == month]
            if not candidates:
                if re.search(r'\d+(?:\.\d+)?(?:%|万?辆|个百分点)', clause):
                    raise ValueError(f'第{page}页{entity}的{scope}数值缺少对应引用。')
                continue
            def check(key, value, magnitude=False, unit=''):
                expected = [r[key] for r in candidates if key in r]
                if magnitude:
                    expected = [abs(v) for v in expected]
                if unit == '万':
                    expected = [round(v / 10000, 1) for v in expected]
                if not any(abs(value - v) < .051 for v in expected):
                    raise ValueError(f'第{page}页{entity}/{scope}/{key}错配：{value}，应为{expected}。')
            # Unnamed numbers after punctuation still belong to the last
            # explicit subject and must be checked, not merely whitelisted.
            # Only generic, nonnumeric concluding directions are bounded here.
            qualitative_clause = re.split(r'其余|两者|各级别|各类型', local_clause, maxsplit=1)[0]
            for qualitative in re.finditer(r'(同比|环比)(增长|下降|下滑|回升|持平)', qualitative_clause):
                key = 'yoy_pct' if qualitative[1] == '同比' else 'mom_pct'
                values = [r[key] for r in candidates if key in r]
                expected_sign = 0 if qualitative[2] == '持平' else -1 if qualitative[2] in ('下降','下滑') else 1
                if not any((0 if v == 0 else 1 if v > 0 else -1) == expected_sign for v in values):
                    raise ValueError(f'第{page}页{entity}/{scope}/{key}定性方向不符。')
            for growth in re.finditer(r'(同比|环比)(增长|下降|下滑|回升|\+|−|-)?\s*(\d+(?:\.\d+)?)%', clause):
                value = float(growth[3]) * (-1 if growth[2] in ('下降', '下滑', '−', '-') else 1)
                check('yoy_pct' if growth[1] == '同比' else 'mom_pct', value)
                checked_spans.append(growth.span())
            for count in re.finditer(r'(\d[\d,]*(?:\.\d+)?)(亿|万)?辆', clause):
                if count[2] == '亿':
                    raise ValueError(f'第{page}页销量单位超出本报告允许口径。')
                prefix = clause[:count.start()]
                delta = re.search(r'(同比|环比)?(净减|净增)\s*$', prefix)
                if delta:
                    value = float(count[1].replace(',', '')) * (-1 if delta[2] == '净减' else 1)
                    check('delta_mom' if delta[1] == '环比' else 'delta_yoy', value, unit=count[2] or '')
                else:
                    check('value', float(count[1].replace(',', '')), unit=count[2] or '')
                checked_spans.append(count.span())
            for share in re.finditer(r'(?:份额|占比|渗透率|占(?:整体市场|新能源内部|新能源市场|(?:全国)?乘用车(?:市场|零售|销量)|(?:全部)?新能源销量))(?:较(?:上月|去年同期)(?:提高|回落)\d+(?:\.\d+)?个百分点)?(?:为|达|至|升至|降至)?\s*(\d+(?:\.\d+)?)%', clause):
                key = 'share_pct'
                check(key, float(share[1]))
                denominator = 'nev_market' if re.search(r'新能源(?:内部|市场|销量)', share[0]) else 'passenger_market' if '整体市场' in share[0] or '乘用车' in share[0] or '渗透率' in share[0] else None
                if denominator and not any(r.get('share_scope') == denominator and r.get('share_pct') == float(share[1]) for r in candidates):
                    raise ValueError(f'第{page}页{entity}份额分母错配。')
                checked_spans.append(share.span())
            # Bare comparative magnitudes must not pass the old absolute-number
            # whitelist (e.g. negative share delta rewritten as '较上月高0.6').
            for comparative in re.finditer(r'较(?:上月|去年同期)(?:提高|提升|上升|增加|增长|回落|下降|降低|减少|高|低|扩大|收窄)\s*[+-]?\d+(?:\.\d+)?', clause):
                if not re.match(r'\s*个百分点', clause[comparative.end():]):
                    raise ValueError(f'第{page}页{entity}比较差值缺少明确百分点单位，不能只核验绝对数字。')
            for point in re.finditer(r'(提高|提升|上升|增加|增长|回落|下降|降低|减少|高|低|扩大|收窄)\s*(\d+(?:\.\d+)?)个百分点', clause):
                prefix = clause[:point.start()]
                if not re.search(r'较(?:上月|去年同期)', prefix):
                    raise ValueError(f'第{page}页百分点缺少明确比较基期。')
                key = 'yoy_change_pp' if '同比降幅' in prefix else 'share_change_pp'
                if key == 'share_change_pp':
                    if point[1] in ('扩大', '收窄'):
                        raise ValueError(f'第{page}页{entity}份额差值需明确提高或下降，不能套用同比降幅扩大/收窄。')
                    marker = list(re.finditer(r'较(上月|去年同期)',prefix))[-1][1]
                    expected_scope = 'previous_month' if marker == '上月' else 'prior_year_same_period' if scope == 'year_to_date' else 'prior_year_same_month'
                    if not any(r.get('share_comparison_scope') == expected_scope for r in candidates if 'share_change_pp' in r):
                        raise ValueError(f'第{page}页{entity}份额变化比较基期与测算记录不符。')
                sign = -1 if point[1] in ('回落', '下降', '降低', '减少', '低', '扩大') else 1
                check(key, sign * float(point[2]))
                checked_spans.append(point.span())
            for contribution in re.finditer(r'占[^，；。%]*?净(?:减|增)(\d+(?:\.\d+)?)%', clause):
                check('net_change_share_pct', float(contribution[1]))
                checked_spans.append(contribution.span())
            for contribution in re.finditer(r'(同比|环比)(?:净(?:增|减)|减量|增量)贡献(\d+(?:\.\d+)?)%|贡献(\d+(?:\.\d+)?)%(同比|环比)(?:增量|减量)', clause):
                basis = contribution[1] or contribution[4]
                value = float(contribution[2] or contribution[3])
                if not any(r.get('comparison_metric') == ('delta_yoy' if basis == '同比' else 'delta_mom')
                           and r.get('net_change_share_pct') == value for r in candidates):
                    raise ValueError(f'第{page}页{entity}增减贡献比较基期不符。')
                check('net_change_share_pct', value)
                checked_spans.append(contribution.span())
            for ratio in re.finditer(r'存销比(?:降至|升至|为)?(\d+(?:\.\d+)?)', clause):
                check('inventory_sales_ratio', float(ratio[1]))
                checked_spans.append(ratio.span())
            for metric_token in measurement.finditer(clause):
                if not any(start <= metric_token.start() and end >= metric_token.end() for start, end in checked_spans):
                    raise ValueError(f'第{page}页{entity}指标语义未绑定：{metric_token[0]}；需写明同比、环比、份额分母或数量。')
            assertion_count += len(checked_spans)
        if part_index and not assertion_count:
            claim = claims[part_index - 1]
            if not (claim.get('evidence_ids') and claim.get('certainty') == 'supported'):
                raise ValueError(f'第{page}页{claim.get("role")}层只有泛论，缺少实际指标或已验证据支撑。')
        # Even a missed linguistic form cannot borrow a number from another claim.
        allowed = {float(v) for v in re.findall(r'\d+(?:\.\d+)?', payload.get('required_prefix', ''))}
        allowed |= {float(int(month[5:])), 1.0}
        # Digits in entity names / price bands are labels, not metric assertions.
        for name in names:
            allowed |= {float(v) for v in re.findall(r'\d+', name)}
        for row in cited:
            for key, value in row.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    allowed |= {round(float(value), 1), round(abs(float(value)), 1)}
                    if abs(value) >= 10000:
                        allowed |= {round(value / 10000, 1), round(abs(value) / 10000, 1)}
        for token in re.findall(r'(?<![A-Za-z])\d+(?:\.\d+)?', text):
            if round(float(token), 1) not in allowed:
                raise ValueError(f'第{page}页当前论点出现不可回溯数字：{token}')
    body = '；'.join(c['claim'].rstrip('；。 ') for c in claims)
    if not 120 <= _width(body) <= 150:
        raise ValueError(f'第{page}页正文显示宽度{_width(body):.1f}，需保留三层有效信息并排入三行。')
    slide['business_validation'] = {'entity_metric_scope_checked': True,
                                    'fact_ids': list(dict.fromkeys(all_refs)), 'rule': 'typed-pages-v5'}


def overview_business_packet(packets: list[dict], approved: list[dict], month: str) -> dict | None:
    """The final overview may only reuse facts already cited by accepted pages."""
    accepted = {v for slide in approved for claim in slide.get('body_claims', []) for v in claim.get('fact_ids', [])}
    facts = {r['fact_id']: r for packet in packets for r in packet.get('business_facts', [])
             if r['fact_id'] in accepted and r['period'] == month}
    def get(code, entity, scope):
        return facts[f'{code}:{entity}:{scope}:{month}']
    try:
        market = get('P1.1-1', '整体市场', 'single_month')
        ytd = get('P1.1-3', '整体市场', 'year_to_date')
        stock = get('P1.2-1', '行业库存', 'stock')
        nev, trad = (get('P2-11.1', name, 'single_month') for name in ('新能源', '传统车'))
    except KeyError:
        return None
    packet = {'slide':3, 'required_prefix':'概述', 'business_facts':list(facts.values()),
              'coverage':{'period':month, 'groups':[]}, 'business_guards':[]}
    a = _Argument(3, packet, month)
    relationship = ('环比回升与同比收缩并存' if market['yoy_pct'] < 0 < market['mom_pct'] else
                    '同比环比方向一致' if market['yoy_pct'] * market['mom_pct'] > 0 else '同比与环比表现分化')
    a.claim('core', f'{int(month[5:])}月整体市场零售{_count(market["value"])}，同比{_change(market["yoy_pct"])}、环比{_change(market["mom_pct"])}；{relationship}。',market)
    energy_relation = '收缩幅度不同' if max(nev['yoy_pct'],trad['yoy_pct']) < 0 else '增长表现不同'
    a.claim('structure', f'新能源占整体市场{nev["share_pct"]:.1f}%，同比{_change(nev["yoy_pct"])}；传统车同比{_change(trad["yoy_pct"])}，两类能源{energy_relation}，份额提升不代表规模增长。',nev,trad)
    a.claim('support', f'1—{int(month[5:])}月整体市场累计零售{_count(ytd["value"])}、同比{_change(ytd["yoy_pct"])}；行业库存{_count(stock["value"])}、环比{_change(stock["mom_pct"])}，累计与库存共同观察。',ytd,stock)
    refs = [v for claim in a.claims for v in claim['fact_ids']]
    packet['fact_grounded_draft'] = {'slide':3, 'headline':f'概述：{relationship}，新能源与传统车走势分化',
                                    'anomaly':{'type':'structural_divergence','priority':9,'fact_ids':refs},
                                    'headline_evidence_ids':[],'body_claims':a.claims}
    return packet
