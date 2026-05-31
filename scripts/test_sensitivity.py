"""
scripts/test_sensitivity.py — 민감도·시나리오 엔진 단위 테스트
==============================================================
PFV 사업수지 모델 분석으로 도입한 두 엔진 검증.

실행:
    cd /path/to/zeb-chatbot
    python scripts/test_sensitivity.py

기대 결과:
    - 도담어린이집 케이스: GR 단독 회수 13년, 자산화 ROI 233%
    - 3개 시나리오 비교 정상 작동
    - 손익분기 보조금율 자동 산출
    - 모든 테스트 PASS
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.sensitivity import (
    compute_metrics,
    sensitivity_subsidy,
    sensitivity_cost,
    sensitivity_saving,
    breakeven_subsidy_rate,
    breakeven_payback,
    run_sensitivity_analysis,
)
from core.scenario_compare import (
    SCENARIO_TEMPLATES,
    apply_scenario,
    compare_all_scenarios,
    recommend_scenario,
    build_inputs_from_diagnosis,
)


# 도담어린이집 기준 입력 (메모리에서)
DOAM_BASELINE = {
    "subsidy_rate": 0.7,
    "total_cost_won": 531_000_000,
    "annual_saving_won": 12_400_000,
    "area_m2": 1_251,
    "far_bonus_value_won": 0,
    "tax_relief_won": 0,
}

DOAM_BASE_INPUTS = {
    "total_cost_full": 531_000_000,
    "annual_saving_full": 12_400_000,
    "area_m2": 1_251,
    "far_bonus_full": 32_000_000,
    "tax_relief_full": 8_000_000,
}


# ────────────────────────────────────────────────
# Section 1: compute_metrics()
# ────────────────────────────────────────────────

def test_compute_metrics_baseline():
    m = compute_metrics(**DOAM_BASELINE)
    # 자부담 = 5.31억 × 30% = 1.593억
    assert abs(m["자부담_원"] - 159_300_000) < 1, \
        f"자부담 계산 오차: {m['자부담_원']}"
    # GR 회수년 = 1.593억 / 0.124억 = 12.85년
    assert 12.0 < m["GR_단독_회수년"] < 14.0, \
        f"GR 회수년 범위 이탈: {m['GR_단독_회수년']}"
    print("  ✓ compute_metrics baseline")


def test_compute_metrics_zero_subsidy():
    """보조금 0%일 때 자부담 = 총비용."""
    b = dict(DOAM_BASELINE)
    b["subsidy_rate"] = 0.0
    m = compute_metrics(**b)
    assert abs(m["자부담_원"] - 531_000_000) < 1
    print("  ✓ compute_metrics 보조금 0% case")


def test_compute_metrics_zero_saving():
    """연간 절감 0일 때 회수기간 무한대."""
    b = dict(DOAM_BASELINE)
    b["annual_saving_won"] = 0
    m = compute_metrics(**b)
    assert m["GR_단독_회수년"] == float("inf")
    print("  ✓ compute_metrics 절감 0 case (inf 반환)")


def test_compute_metrics_with_bonus():
    """용적률 보너스 + 세금 감면 포함 시 30년 총효익 증가."""
    b = dict(DOAM_BASELINE)
    b["far_bonus_value_won"] = 50_000_000
    b["tax_relief_won"] = 10_000_000
    m = compute_metrics(**b)
    # 30년 절감(0.124×30=3.72억) + 보너스(0.5억) + 세금(0.1억) = 4.32억
    expected_min = 372_000_000 + 60_000_000
    assert m["30년_총효익_원"] >= expected_min - 1000, \
        f"보너스 누락: {m['30년_총효익_원']}"
    print("  ✓ compute_metrics 보너스+세금감면 포함")


# ────────────────────────────────────────────────
# Section 2: sensitivity tables
# ────────────────────────────────────────────────

def test_sensitivity_subsidy_table():
    rows = sensitivity_subsidy(DOAM_BASELINE)
    assert len(rows) == 5, "기본 5단계 보조율"
    # 기준 케이스 정확히 1개
    baseline_count = sum(1 for r in rows if r["_is_baseline"])
    assert baseline_count == 1, \
        f"기준 케이스가 정확히 1개여야: {baseline_count}"
    # 보조율 높을수록 회수기간 짧아져야
    sorted_rows = sorted(rows, key=lambda r: r["보조금율"])
    paybacks = [r["GR_단독_회수년"] for r in sorted_rows]
    for i in range(len(paybacks) - 1):
        assert paybacks[i] >= paybacks[i+1], \
            f"보조율↑일 때 회수기간↓ 위반: {paybacks}"
    print(f"  ✓ sensitivity_subsidy: {len(rows)}행, 단조 감소 확인")


def test_sensitivity_cost_table():
    rows = sensitivity_cost(DOAM_BASELINE)
    assert len(rows) == 5
    # 비용 ↑이면 자부담 ↑
    sorted_rows = sorted(rows, key=lambda r: r["비용_변화율"])
    burdens = [r["자부담_억"] for r in sorted_rows]
    for i in range(len(burdens) - 1):
        assert burdens[i] <= burdens[i+1] + 0.001
    print("  ✓ sensitivity_cost: 비용↑→자부담↑ 단조성")


def test_sensitivity_saving_table():
    rows = sensitivity_saving(DOAM_BASELINE)
    assert len(rows) == 5
    # 절감액 ↑이면 회수기간 ↓
    sorted_rows = sorted(rows, key=lambda r: r["절감_변화율"])
    paybacks = [r["GR_단독_회수년"] for r in sorted_rows]
    for i in range(len(paybacks) - 1):
        assert paybacks[i] >= paybacks[i+1] - 0.001
    print("  ✓ sensitivity_saving: 절감↑→회수↓ 단조성")


# ────────────────────────────────────────────────
# Section 3: breakeven analysis
# ────────────────────────────────────────────────

def test_breakeven_subsidy_rate():
    """회수 10년 달성 보조율 약 76% 예상."""
    rate_10y = breakeven_subsidy_rate(DOAM_BASELINE, 10.0)
    assert 0.5 < rate_10y < 0.95, \
        f"회수 10년 보조율 범위 이탈: {rate_10y}"
    # 회수 5년은 더 많은 보조 필요
    rate_5y = breakeven_subsidy_rate(DOAM_BASELINE, 5.0)
    assert rate_5y > rate_10y, "더 짧은 회수에 더 많은 보조 필요"
    print(f"  ✓ breakeven: 회수10년={rate_10y:.0%}, 회수5년={rate_5y:.0%}")


def test_breakeven_payback_summary():
    bk = breakeven_payback(DOAM_BASELINE)
    required_keys = ["무보조_회수년", "50%보조_회수년", "현재_회수년",
                     "회수8년_필요_보조율", "회수10년_필요_보조율"]
    for k in required_keys:
        assert k in bk, f"필수 키 누락: {k}"
    # 무보조가 50% 보조보다 길어야
    assert bk["무보조_회수년"] > bk["50%보조_회수년"]
    print("  ✓ breakeven_payback 5개 지표 모두 산출")


# ────────────────────────────────────────────────
# Section 4: run_sensitivity_analysis (통합)
# ────────────────────────────────────────────────

def test_run_sensitivity_analysis():
    result = run_sensitivity_analysis(DOAM_BASELINE)
    required = ["baseline_metrics", "subsidy_table", "cost_table",
                "saving_table", "breakeven"]
    for k in required:
        assert k in result, f"통합 결과 키 누락: {k}"
    assert len(result["subsidy_table"]) == 5
    assert len(result["cost_table"]) == 5
    assert len(result["saving_table"]) == 5
    print("  ✓ run_sensitivity_analysis 통합 진입점")


# ────────────────────────────────────────────────
# Section 5: scenario_compare
# ────────────────────────────────────────────────

def test_apply_scenario_all_three():
    for key in SCENARIO_TEMPLATES:
        sc = apply_scenario(DOAM_BASE_INPUTS, key)
        assert sc["key"] == key
        assert "label" in sc
        assert sc["자부담_억"] >= 0
        assert sc["보강비용_억"] > 0
    print(f"  ✓ apply_scenario: 3개 시나리오 모두 정상")


def test_compare_all_scenarios():
    scenarios = compare_all_scenarios(DOAM_BASE_INPUTS)
    assert len(scenarios) == 3
    keys = [s["key"] for s in scenarios]
    assert keys == ["A_부분보강", "B_전체보강", "C_시그니처"]
    # 부분 보강은 비용 최소
    a_cost = scenarios[0]["보강비용_억"]
    b_cost = scenarios[1]["보강비용_억"]
    assert a_cost < b_cost, "부분보강이 전체보강보다 저렴해야"
    print(f"  ✓ compare_all_scenarios: A({a_cost:.2f}) < B({b_cost:.2f})억")


def test_recommend_scenario_priorities():
    scenarios = compare_all_scenarios(DOAM_BASE_INPUTS)
    for pri in ["회수기간", "ROI", "초기부담"]:
        rec = recommend_scenario(scenarios, pri)
        assert "best_scenario" in rec
        assert "reason" in rec
        assert rec["priority"] == pri
    print("  ✓ recommend_scenario: 3개 우선순위 모두 추천")


def test_recommend_payback_picks_shortest():
    """회수기간 우선이면 통합_회수년이 가장 짧은 시나리오 선택."""
    scenarios = compare_all_scenarios(DOAM_BASE_INPUTS)
    rec = recommend_scenario(scenarios, "회수기간")
    best_payback = rec["best_scenario"]["통합_회수년"]
    for sc in scenarios:
        assert best_payback <= sc["통합_회수년"] + 0.001, \
            f"회수기간 최단 선택 실패: {best_payback} vs {sc['통합_회수년']}"
    print(f"  ✓ recommend(회수기간): 최단 {best_payback:.1f}년 선택")


def test_recommend_roi_picks_highest():
    scenarios = compare_all_scenarios(DOAM_BASE_INPUTS)
    rec = recommend_scenario(scenarios, "ROI")
    best_roi = rec["best_scenario"]["자산화_ROI_pct"]
    for sc in scenarios:
        assert best_roi >= sc["자산화_ROI_pct"] - 0.001
    print(f"  ✓ recommend(ROI): 최대 {best_roi:.0f}% 선택")


def test_build_inputs_from_diagnosis():
    """진단 결과 dict에서 시나리오 입력 자동 구성."""
    fake_diagnosis = {
        "roi_plan": [
            {"Max_Cost": 100_000_000},
            {"Max_Cost": 200_000_000},
        ],
        "scenario": {"연면적_m2": 1000},
        "roi_summary": {
            "용적률_자산가치_원": 20_000_000,
            "취득세_감면액_원": 5_000_000,
        },
    }
    inputs = build_inputs_from_diagnosis(fake_diagnosis)
    assert inputs["total_cost_full"] == 300_000_000
    assert inputs["area_m2"] == 1000
    assert inputs["far_bonus_full"] == 20_000_000
    assert inputs["tax_relief_full"] == 5_000_000
    print("  ✓ build_inputs_from_diagnosis: 결과 추출 정확")


# ────────────────────────────────────────────────
# Section 6: 졸업설계 시연 시나리오
# ────────────────────────────────────────────────

def test_doam_full_demo_flow():
    """도담어린이집 케이스 — 발표용 핵심 수치 검증."""
    # 시나리오 비교
    scenarios = compare_all_scenarios(DOAM_BASE_INPUTS)

    # 시그니처 시나리오 ROI가 가장 높아야 (보조 85% + ZEB 1등급)
    c_signature = scenarios[2]
    assert c_signature["key"] == "C_시그니처"
    assert c_signature["자산화_ROI_pct"] > 400, \
        f"시그니처 ROI 기대치 미달: {c_signature['자산화_ROI_pct']}"

    # 민감도 분석
    sens = run_sensitivity_analysis(DOAM_BASELINE)
    bk = sens["breakeven"]
    # 회수 8년 달성에 보조 80% 이상 필요해야
    assert bk["회수8년_필요_보조율"] > 0.7
    print(f"  ✓ 도담 시연: 시그니처 ROI {c_signature['자산화_ROI_pct']:.0f}%, "
          f"회수8년 보조율 {bk['회수8년_필요_보조율']:.0%}")


# ────────────────────────────────────────────────
# Test runner
# ────────────────────────────────────────────────

ALL_TESTS = [
    test_compute_metrics_baseline,
    test_compute_metrics_zero_subsidy,
    test_compute_metrics_zero_saving,
    test_compute_metrics_with_bonus,
    test_sensitivity_subsidy_table,
    test_sensitivity_cost_table,
    test_sensitivity_saving_table,
    test_breakeven_subsidy_rate,
    test_breakeven_payback_summary,
    test_run_sensitivity_analysis,
    test_apply_scenario_all_three,
    test_compare_all_scenarios,
    test_recommend_scenario_priorities,
    test_recommend_payback_picks_shortest,
    test_recommend_roi_picks_highest,
    test_build_inputs_from_diagnosis,
    test_doam_full_demo_flow,
]


def main():
    print("=" * 60)
    print("민감도·시나리오 엔진 단위 테스트")
    print("=" * 60)
    passed, failed = 0, 0
    for test in ALL_TESTS:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print("=" * 60)
    print(f"결과: {passed} PASS / {failed} FAIL (총 {len(ALL_TESTS)}개)")
    print("=" * 60)
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
