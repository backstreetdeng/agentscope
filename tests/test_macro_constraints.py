# -*- coding: utf-8 -*-
"""Independent, explicitly synthetic tests for reviewed economic identities."""
from copy import deepcopy
from datetime import date
import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/"skills/macro-monthly-report/scripts"
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location("tested_macro_constraints",SCRIPTS/"macro_constraints.py")
constraints=importlib.util.module_from_spec(spec);spec.loader.exec_module(constraints)


def gdp_chart(values=(2.3,1.5,1.0,4.8), statuses=None, period="2026-06-30"):
    statuses=statuses or ["actual"]*4
    chart={"chart_id":"s10-shape28","target":period,"categories":[period],"series":[]}
    observations={}
    for (role,name,unit),value,status in zip(constraints.GDP_ROLES,values,statuses):
        rid="GDP-SYNTHETIC::"+role
        chart["series"].append({"original_name":name,"name":name,"unit":unit,"request_ids":[rid],
            "actual_values":[value if status in {"actual","archival","overlap"} else None],
            "forecast_values":[value if status in {"forecast","overlap"} else None]})
        observations[rid]=([{"request_id":rid,"date":date.fromisoformat(period),"value":value,"synthetic":True}]
                           if status in {"actual","overlap"} and value is not None else [])
    return chart,observations


def cumulative_chart(cid="s14-shape15", name="固定资产投资累计值", periods=None,
                     actuals=None, forecasts=None, verified=None):
    periods=periods or ["2026-07-31","2026-08-31","2026-09-30"]
    actuals=actuals if actuals is not None else [100,110,None]
    forecasts=forecasts if forecasts is not None else [None,None,120]
    rid="CUMULATIVE-SYNTHETIC::"+name
    chart={"chart_id":cid,"target":periods[-1],"categories":periods,"series":[
        {"original_name":name,"name":name,"unit":"亿元","request_ids":[rid],
         "actual_values":actuals,"forecast_values":forecasts}]}
    verified=verified if verified is not None else {
        period:value for period,value in zip(periods,actuals) if value is not None}
    observations={rid:[{"request_id":rid,"date":period,"value":value,"synthetic":True}
                       for period,value in verified.items()]}
    return chart,observations


def add_gdp_actual_history(chart,observations,period,values):
    chart["categories"].insert(0,period)
    for series,value in zip(chart["series"],values):
        series["actual_values"].insert(0,value)
        series["forecast_values"].insert(0,None)
        rid=series["request_ids"][0]
        observations[rid].append({"date":period,"value":value,"synthetic":True})


class GDPDemandIdentityTest(unittest.TestCase):
    def test_equal_actual_and_equal_forecast_are_accepted_with_explicit_roles(self):
        for statuses in (["actual"]*4,["forecast"]*4,["actual","forecast","forecast","forecast"]):
            chart,obs=gdp_chart(statuses=statuses)
            self.assertEqual(constraints.validate_constraints([chart],obs),[])

    def test_one_decimal_publisher_rounding_tolerance_is_exactly_point_two(self):
        chart,obs=gdp_chart(values=(2.3,1.5,1.0,4.6))
        self.assertEqual(constraints.validate_constraints([chart],obs),[])
        chart,obs=gdp_chart(values=(2.3,1.5,1.0,4.59))
        issues=constraints.validate_constraints([chart],obs)
        mismatch=next(i for i in issues if i["code"]=="gdp_decomposition_mismatch")
        self.assertAlmostEqual(mismatch["component_sum"],4.8)
        self.assertAlmostEqual(mismatch["delta"],0.21)
        self.assertEqual(mismatch["date"],"2026-06-30")

    def test_missing_component_or_total_never_presents_partial_sum_as_complete(self):
        for values in ((None,1.5,1.0,4.8),(2.3,1.5,1.0,None)):
            chart,obs=gdp_chart(values=values)
            issue=next(i for i in constraints.validate_constraints([chart],obs)
                       if i["code"]=="gdp_decomposition_incomplete")
            self.assertIsNone(issue["component_sum"])
            self.assertIsNone(issue["delta"])
            self.assertTrue(issue["missing"])

    def test_archival_cells_are_not_source_proof_and_quarterly_yoy_chart_is_outside_identity(self):
        chart,obs=gdp_chart(statuses=["archival"]*4)
        self.assertTrue(any(i["code"]=="gdp_decomposition_incomplete"
                            for i in constraints.validate_constraints([chart],obs)))
        chart["chart_id"]="s10-shape7"
        self.assertEqual(constraints.validate_constraints([chart],obs),[])

    def test_percent_growth_and_percentage_point_contributions_cannot_be_swapped(self):
        chart,obs=gdp_chart()
        chart["series"][0]["unit"]="%"
        self.assertTrue(any(i["code"]=="gdp_decomposition_unit_mismatch"
                            for i in constraints.validate_constraints([chart],obs)))

    def test_forecast_actual_overlap_is_not_silently_double_counted(self):
        chart,obs=gdp_chart(statuses=["overlap","actual","actual","actual"])
        self.assertTrue(any(i["code"]=="gdp_actual_forecast_overlap"
                            for i in constraints.validate_constraints([chart],obs)))

    def test_target_quarter_absent_from_axis_is_rejected(self):
        chart,obs=gdp_chart()
        chart["target"]="2026-09-30"
        self.assertTrue(any(i["code"]=="gdp_decomposition_target_missing"
                            for i in constraints.validate_constraints([chart],obs)))

    def test_gdp_longer_history_than_components_does_not_block_complete_latest_baseline(self):
        chart,obs=gdp_chart()
        older=date(2026,3,31)
        chart["categories"].insert(0,older)
        for series in chart["series"]:
            series["actual_values"].insert(0,1234)  # visibly archival, not source evidence
            series["forecast_values"].insert(0,None)
        gdp_rid=chart["series"][-1]["request_ids"][0]
        obs[gdp_rid].insert(0,{"date":older,"value":4.1,"synthetic":True})
        self.assertEqual(constraints.validate_constraints([chart],obs),[])

    def test_latest_actual_baseline_missing_component_still_blocks_future_target(self):
        chart,obs=gdp_chart(statuses=["forecast"]*4,period="2026-09-30")
        chart["categories"].insert(0,"2026-06-30")
        for series in chart["series"]:
            series["actual_values"].insert(0,1234)
            series["forecast_values"].insert(0,None)
        gdp_rid=chart["series"][-1]["request_ids"][0]
        obs[gdp_rid]=[{"date":"2026-06-30","value":4.1,"synthetic":True}]
        issue=next(i for i in constraints.validate_constraints([chart],obs)
                   if i["code"]=="gdp_decomposition_incomplete")
        self.assertEqual(issue["date"],"2026-06-30")
        self.assertEqual(set(issue["missing"]),{"consumption","capital","net_exports"})

    def test_separate_complete_actual_baseline_and_forecast_target_both_pass(self):
        chart,obs=gdp_chart(statuses=["forecast"]*4,period="2026-09-30")
        add_gdp_actual_history(chart,obs,"2026-06-30",(2.0,1.5,1.1,4.6))
        self.assertEqual(constraints.validate_constraints([chart],obs),[])

    def test_baseline_and_target_mismatches_are_attributed_to_their_own_quarter(self):
        for period in ("2026-06-30","2026-09-30"):
            chart,obs=gdp_chart(statuses=["forecast"]*4,period="2026-09-30")
            baseline=(2.0,1.5,1.1,6.6) if period=="2026-06-30" else (2.0,1.5,1.1,4.6)
            add_gdp_actual_history(chart,obs,"2026-06-30",baseline)
            if period=="2026-09-30":chart["series"][-1]["forecast_values"][-1]=6.8
            original=deepcopy((chart,obs))
            mismatches=[i for i in constraints.validate_constraints([chart],obs)
                        if i["code"]=="gdp_decomposition_mismatch"]
            self.assertEqual(len(mismatches),1)
            self.assertEqual(mismatches[0]["date"],period)
            self.assertAlmostEqual(mismatches[0]["delta"],-2.0)
            status="actual" if period=="2026-06-30" else "forecast"
            self.assertEqual(set(mismatches[0]["actual_vs_forecast"].values()),{status})
            self.assertEqual((chart,obs),original)

    def test_complete_verified_old_history_mismatch_still_blocks(self):
        chart,obs=gdp_chart(statuses=["forecast"]*4,period="2026-09-30")
        add_gdp_actual_history(chart,obs,"2026-06-30",(2.0,1.5,1.1,4.6))
        add_gdp_actual_history(chart,obs,"2026-03-31",(2.0,1.5,1.0,7.0))
        mismatches=[i for i in constraints.validate_constraints([chart],obs)
                    if i["code"]=="gdp_decomposition_mismatch"]
        self.assertEqual([i["date"] for i in mismatches],["2026-03-31"])

    def test_verified_latest_actual_baseline_missing_from_axis_is_explicit(self):
        chart,obs=gdp_chart(statuses=["forecast"]*4,period="2026-09-30")
        for series,value in zip(chart["series"],(2.0,1.5,1.1,4.6)):
            obs[series["request_ids"][0]].append({"date":"2026-06-30","value":value,"synthetic":True})
        issues=constraints.validate_constraints([chart],obs)
        self.assertEqual([i["code"] for i in issues],["gdp_decomposition_baseline_missing"])
        self.assertEqual(issues[0]["date"],"2026-06-30")


class CumulativeAmountPredictionTest(unittest.TestCase):
    def test_same_year_increasing_forecast_is_accepted(self):
        chart,obs=cumulative_chart()
        self.assertEqual(constraints.validate_constraints([chart],obs),[])

    def test_same_year_decreasing_forecast_records_baseline_and_delta_without_mutation(self):
        chart,obs=cumulative_chart(forecasts=[None,None,105])
        originals=deepcopy((chart,obs))
        issue=next(i for i in constraints.validate_constraints([chart],obs)
                   if i["code"]=="cumulative_forecast_decrease")
        self.assertEqual(issue["previous_date"],"2026-08-31")
        self.assertEqual(issue["previous_status"],"actual")
        self.assertEqual(issue["delta"],-5)
        self.assertEqual(issue["actual_vs_forecast"],"forecast")
        self.assertEqual((chart,obs),originals)

    def test_descending_native_axis_still_compares_forecasts_chronologically(self):
        chart,obs=cumulative_chart(periods=["2026-09-30","2026-08-31","2026-07-31"],
                                   actuals=[None,None,100],forecasts=[105,110,None])
        issues=constraints.validate_constraints([chart],obs)
        decrease=next(i for i in issues if i["code"]=="cumulative_forecast_decrease")
        self.assertEqual(decrease["date"],"2026-09-30")
        self.assertEqual(decrease["previous_status"],"forecast")

    def test_authoritative_downward_revision_is_not_monotonicity_rejected(self):
        chart,obs=cumulative_chart(actuals=[120,110,108],forecasts=[None,None,None])
        self.assertEqual(constraints.validate_constraints([chart],obs),[])

    def test_archival_amount_is_not_forecast_baseline_and_unrelated_net_flows_are_untouched(self):
        chart,obs=cumulative_chart(verified={})
        self.assertTrue(any(i["code"]=="cumulative_forecast_baseline_missing"
                            for i in constraints.validate_constraints([chart],obs)))
        chart["chart_id"]="s25-shape10"
        chart["series"][0]["forecast_values"]=[None,None,-100]
        self.assertEqual(constraints.validate_constraints([chart],obs),[])

    def test_cross_year_extrapolation_of_cumulative_amount_requires_reviewed_reset_model(self):
        chart,obs=cumulative_chart(periods=["2026-12-31","2027-01-31","2027-02-28"],
                                   actuals=[200,None,None],forecasts=[None,210,220])
        issues=[i for i in constraints.validate_constraints([chart],obs)
                if i["code"]=="cumulative_forecast_cross_year_unmodeled"]
        self.assertEqual(len(issues),2)
        self.assertTrue(all(i["baseline_date"]=="2026-12-31" for i in issues))

    def test_publisher_actual_new_year_reset_is_valid_baseline_for_later_forecast(self):
        chart,obs=cumulative_chart(periods=["2026-12-31","2027-01-31","2027-02-28"],
                                   actuals=[200,15,None],forecasts=[None,None,30])
        self.assertEqual(constraints.validate_constraints([chart],obs),[])

    def test_fiscal_raw_yi_yuan_amounts_are_scoped_but_percentage_series_are_not(self):
        chart,obs=cumulative_chart(cid="s30-shape13",name="财政支出(万亿)",forecasts=[None,None,100])
        self.assertTrue(any(i["code"]=="cumulative_forecast_decrease"
                            for i in constraints.validate_constraints([chart],obs)))
        chart["series"][0]["name"]="财政支出增速（右轴）"
        chart["series"][0]["original_name"]="财政支出增速（右轴）"
        chart["series"][0]["unit"]="%"
        self.assertEqual(constraints.validate_constraints([chart],obs),[])

    def test_nonfinite_forecast_and_actual_prediction_overlap_are_rejected(self):
        chart,obs=cumulative_chart(forecasts=[None,None,float("nan")])
        self.assertTrue(any(i["code"]=="cumulative_forecast_nonfinite"
                            for i in constraints.validate_constraints([chart],obs)))
        chart,obs=cumulative_chart(actuals=[100,110,120],forecasts=[None,None,120])
        self.assertTrue(any(i["code"]=="cumulative_actual_forecast_overlap"
                            for i in constraints.validate_constraints([chart],obs)))


if __name__=="__main__":unittest.main()
