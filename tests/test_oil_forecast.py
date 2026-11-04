"""As-of and fair-window checks; synthetic inputs, no network or weights."""
import unittest
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from integrations.gd_oil import audit, DETAIL, END, AVG
from integrations.oil_forecast import inputs, calculate, START
from integrations.chronos2_forecast import next_month
from integrations.sarimax_forecast import validate


class OilTests(unittest.TestCase):
    def test_month_end_midnight_and_independent_arithmetic(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            def write(name,rows):
                with (root/name).open('w',encoding='utf-8',newline='') as stream:
                    w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            events=[]
            for when,announce,old,new in [('2019-12-31','2019-12-30',7,8),('2020-02-01','2020-01-31',8,9)]:
                y,m,d=map(int,announce.split('-'))
                events.append({'生效日期':when,'公告日期':announce,'生效时刻':'00:00',
                    '92号汽油_元每升':old,'95号汽油_元每升':new,'公告原文链接':'https://example.test/source',
                    '采集时间':'2026-11-03','原文生效表述':f'{y}年{m}月{d}日24时'})
            write(DETAIL,events)
            write(END,[{'月份':'2020-01','92号_月末有效价_元每升':7,'95号_月末有效价_元每升':8}])
            avg={'月份':'2020-01','92号_月均价_按生效天数加权':7,'95号_月均价_按生效天数加权':8,'覆盖天数':31,'当月天数':31}
            write(AVG,[avg]);self.assertEqual(audit(root)['monthly'][0]['value'],7)
            avg['92号_月均价_按生效天数加权']=8;write(AVG,[avg])
            with self.assertRaisesRegex(ValueError,'重算不一致'):audit(root)

    def fixture(self):
        monthly=[dict(period=next_month('2019-12',i+1),value=5+i*.01,available_at=next_month('2019-12',i+1)+'-28') for i in range(96)]
        history=[(r['period'],1000+i) for i,r in enumerate(monthly[:81])]
        return history,monthly

    def test_future_real_and_revision_not_used(self):
        history,m=self.fixture(); before=inputs(history,m,12)
        for row in m:
            if row['period']>history[-1][0]:row['value']=99999
        m.append(dict(period=history[-1][0],value=99999,available_at='2030-01-01'))
        self.assertEqual(inputs(history,m,12),before)
        self.assertTrue(all(r[0]<10 for r in before['future_features']))

    def test_both_lags_share_history(self):
        h,m=self.fixture()
        self.assertEqual(inputs(h,m,12,1)['history'],inputs(h,m,12,3)['history'])
        self.assertEqual(inputs(h,m,12)['history'][0][0],START)

    def test_missing_oil_blocks(self):
        h,m=self.fixture()
        with self.assertRaises(ValueError):inputs(h,m[5:],12)

    def test_scope_and_arbitrary_payload_rejected(self):
        base=dict(operation='forecast',province='广东',energy='插电式混合动力',horizon=6,profile='gd_oil')
        self.assertEqual(validate(base)['profile'],'gd_oil')
        for extra in ({'province':'31省份合计'},{'horizon':24},{'history':[123]},{'profile':'other'}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):validate(dict(base,**extra))

    def test_failed_origins_are_reported_and_all_scores_use_same_intersection(self):
        h,m=self.fixture()
        class Workbook:
            source_hash='synthetic'
            def series(self,*_):return h
        def fit(p):
            if p['origin']=='2024-10' and p['variables'][0]['lag']==3:raise ValueError('synthetic failure')
            return dict(forecast=[dict(mean=1000,lower=900,upper=1100)]*12)
        class Chronos:
            def predict(self,values,n):return {.1:[900]*n,.5:[1000]*n,.9:[1100]*n}
        result=calculate(Workbook(),dict(operation='backtest',province='广东',energy='插电式混合动力',horizon=6),
            snapshot=dict(monthly=m,hashes={},limitation='snapshot'),fitter=fit,
            baseline=lambda v,n:[dict(p10=900,p50=1000,p90=1100)]*n,chronos=Chronos())
        self.assertFalse(result['stability_passed'])
        self.assertEqual(result['backtest']['origins'],11)
        for b in result['benchmark'].values():
            self.assertEqual(b['by_horizon']['12']['observations'],11)
            self.assertNotIn('2024-10',{r['origin'] for r in b['records']})


if __name__=='__main__':unittest.main()
