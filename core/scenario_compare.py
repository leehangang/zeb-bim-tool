"""
core/scenario_compare.py — 그린리모델링 시나리오 비교 엔진
=====================================================
한 건물에 대해 여러 사업 전략을 동시에 분석.

성수동 PFV 모델의 "1안 선매각 / 2안 임대 후 매각" 비교에서 영감.
졸업설계 발표에서 "이 건물엔 어떤 전략이 최선인가?" 답하는 도구.

3가지 표준 시나리오:
    A. 부분 보강 (Top 3 우선순위 항목만)
    B. 전체 보강 (11개 항목 모두)
    C. 시그니처 (전체 보강 + ZEB 1등급 목표)

각각 자부담, 회수기간, ROI 비교.
"""

from typing import Dict, List, Optional
from .sensitivity import compute_metrics


# ────────────────────────────────────────────────────
# 시나리오 정의
# ────────────────────────────────────────────────────

SCENARIO_TEMPLATES = {
    "A_부분보강": {
        "label": "A. 부분 보강 (Top 3)",
        "desc": "효율 가장 좋은 3개 항목만 시공",
        "scope_ratio": 0.35,        # 11개 중 효율 좋은 3개 = 비용 ~35%
        "subsidy_rate": 0.5,        # 일반 보조 50%
        "is_signature": False,
        "annual_saving_ratio": 0.45, # 절감의 45% 달성 (보강 비례)
        "far_bonus_apply": False,    # 부분 보강은 용적률 X
        "tax_relief_apply": False,
        "zeb_target": 5,
    },
    "B_전체보강": {
        "label": "B. 전체 보강 (11개)",
        "desc": "11개 GR 기술요소 모두 적용",
        "scope_ratio": 1.0,
        "subsidy_rate": 0.7,        # 공공 보조 70%
        "is_signature": False,
        "annual_saving_ratio": 1.0,
        "far_bonus_apply": True,
        "tax_relief_apply": True,
        "zeb_target": 3,
    },
    "C_시그니처": {
        "label": "C. 시그니처 (ZEB 1등급)",
        "desc": "전체 보강 + ZEB 1등급 + 시그니처 보조",
        "scope_ratio": 1.0,
        "subsidy_rate": 0.85,       # 시그니처 + ZEB 1급 추가 보조
        "is_signature": True,
        "annual_saving_ratio": 1.15, # 1등급은 절감 폭 더 큼
        "far_bonus_apply": True,
        "tax_relief_apply": True,
        "zeb_target": 1,
    },
}


# ────────────────────────────────────────────────────
# 시나리오 적용
# ────────────────────────────────────────────────────

def apply_scenario(
    base_inputs: Dict,
    scenario_key: str,
) -> Dict:
    """
    기준 입력에 시나리오 옵션을 적용해 ROI 산출.

    Args:
        base_inputs: {
            "total_cost_full": 531_000_000,   # 전체 보강 시 비용
            "annual_saving_full": 12_400_000, # 전체 보강 시 절감액
            "area_m2": 1_251,
            "far_bonus_full": 32_000_000,     # 용적률 전체 보너스
            "tax_relief_full": 8_000_000,     # 세금 감면 전체
        }
        scenario_key: "A_부분보강" | "B_전체보강" | "C_시그니처"

    Returns:
        시나리오 카드용 dict
    """
    template = SCENARIO_TEMPLATES[scenario_key]

    # 비용 / 절감 / 보너스 시나리오별 조정
    cost = base_inputs["total_cost_full"] * template["scope_ratio"]
    saving = base_inputs["annual_saving_full"] * template["annual_saving_ratio"]
    far_bonus = (
        base_inputs.get("far_bonus_full", 0)
        if template["far_bonus_apply"] else 0
    )
    tax_relief = (
        base_inputs.get("tax_relief_full", 0)
        if template["tax_relief_apply"] else 0
    )

    # ROI 계산
    metrics = compute_metrics(
        subsidy_rate=template["subsidy_rate"],
        total_cost_won=cost,
        annual_saving_won=saving,
        area_m2=base_inputs["area_m2"],
        far_bonus_value_won=far_bonus,
        tax_relief_won=tax_relief,
    )

    return {
        "key": scenario_key,
        "label": template["label"],
        "desc": template["desc"],
        "scope_pct": template["scope_ratio"] * 100,
        "subsidy_pct": template["subsidy_rate"] * 100,
        "is_signature": template["is_signature"],
        "zeb_target": template["zeb_target"],
        "보강비용_억": cost / 1e8,
        "자부담_억": metrics["자부담_원"] / 1e8,
        "연간절감_만원": saving / 1e4,
        "용적률보너스_억": far_bonus / 1e8,
        "세금감면_만원": tax_relief / 1e4,
        "GR_단독_회수년": metrics["GR_단독_회수년"],
        "통합_회수년": metrics["통합_회수년"],
        "할인회수년": metrics["할인회수_년"],
        "NPV_억": metrics["NPV_원"] / 1e8,
        "IRR": metrics["IRR"],
        "BC_ratio": metrics["BC_ratio"],
        "자산가치_수익환원_억": metrics["자산가치_수익환원_원"] / 1e8,
        "자산화_ROI_pct": metrics["자산화_ROI_pct"],
        "30년_총효익_억": metrics["30년_총효익_원"] / 1e8,
    }


def compare_all_scenarios(base_inputs: Dict) -> List[Dict]:
    """3개 표준 시나리오 한 번에 비교."""
    return [
        apply_scenario(base_inputs, key)
        for key in ("A_부분보강", "B_전체보강", "C_시그니처")
    ]


# ────────────────────────────────────────────────────
# 최적 시나리오 추천
# ────────────────────────────────────────────────────

def recommend_scenario(
    scenarios: List[Dict],
    user_priority: str = "회수기간",
) -> Dict:
    """
    사용자 우선순위에 따라 최적 시나리오 자동 추천.

    Args:
        scenarios: compare_all_scenarios() 결과
        user_priority: "회수기간" | "ROI" | "초기부담"

    Returns:
        추천 시나리오 dict + 이유
    """
    if user_priority == "회수기간":
        # 통합 회수기간이 가장 짧은 시나리오
        best = min(scenarios, key=lambda s: s["통합_회수년"])
        reason = (
            f"통합 회수기간이 가장 짧음 ({best['통합_회수년']:.1f}년). "
            "보조금과 인센티브를 다 챙길 때 가장 빨리 본전 회수."
        )
    elif user_priority == "ROI":
        # 편익/비용(B-C)이 가장 높은 시나리오
        best = max(scenarios, key=lambda s: s["BC_ratio"])
        reason = (
            f"편익/비용(B-C)이 가장 높음 ({best['BC_ratio']:.2f}배). "
            "투입 1원당 할인편익이 가장 큼 (장기 경제성 최고)."
        )
    elif user_priority == "초기부담":
        # 자부담이 가장 적은 시나리오
        best = min(scenarios, key=lambda s: s["자부담_억"])
        reason = (
            f"초기 자부담이 가장 적음 ({best['자부담_억']:.2f}억). "
            "예산 제약이 큰 케이스에 적합."
        )
    else:
        # 기본: 균형 (회수기간 + B-C 조합 점수)
        def balance_score(s):
            payback = s["할인회수년"] if s["할인회수년"] else 99
            payback_score = max(0, 30 - payback) / 30 * 100
            roi_score = min(s["BC_ratio"], 4) / 4 * 100  # 최대 100
            return payback_score + roi_score
        best = max(scenarios, key=balance_score)
        reason = "할인회수기간과 B-C의 균형이 가장 좋음."

    return {
        "best_scenario": best,
        "reason": reason,
        "priority": user_priority,
    }


# ────────────────────────────────────────────────────
# Mode 3 진단 결과에서 시나리오 입력 자동 구성
# ────────────────────────────────────────────────────

def build_inputs_from_diagnosis(diagnosis_result: dict) -> Dict:
    """
    Mode 3 진단 결과(`run_bim_diagnosis()`의 출력)에서 
    시나리오 비교 입력을 자동 구성.

    Args:
        diagnosis_result: bim_diagnoser.run_bim_diagnosis() 결과

    Returns:
        compare_all_scenarios() 에 넣을 base_inputs
    """
    plan = diagnosis_result.get("roi_plan", []) or []
    total_cost = sum(p.get("Max_Cost", 0) for p in plan)
    scenario = diagnosis_result.get("scenario", {})

    # 연면적 (BIM 진단 결과에서)
    area_m2 = scenario.get("연면적_m2", 1000)

    # 연간 절감액 추정 (단가DB 기반 보강 시 평균 12,400원/m2/year 적용)
    annual_saving_per_m2 = 9900  # 보수적
    annual_saving = area_m2 * annual_saving_per_m2

    # 용적률 자산가치 + 취득세 감면 추정 (전체 보강 시)
    roi_summary = diagnosis_result.get("roi_summary", {})
    far_bonus = roi_summary.get("용적률_자산가치_원", 0)
    tax_relief = roi_summary.get("취득세_감면액_원", 0)

    return {
        "total_cost_full": total_cost,
        "annual_saving_full": annual_saving,
        "area_m2": area_m2,
        "far_bonus_full": far_bonus,
        "tax_relief_full": tax_relief,
    }
