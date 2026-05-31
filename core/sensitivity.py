"""
core/sensitivity.py — 민감도 분석 엔진
=====================================
주요 변수(보조금율, 보강비용, 에너지절감액 등)를 ±N% 흔들었을 때 
핵심 지표(자산화 ROI, 회수기간, 자부담)가 어떻게 변하는지 자동 계산.

성수동 PFV 사업수지 모델의 민감도 분석 시트에서 영감.
졸업설계 발표용 임팩트 시각화를 위해 설계.

용법:
    from core.sensitivity import run_sensitivity_analysis
    
    baseline = {
        "subsidy_rate": 0.7,          # 70% 보조
        "total_cost_won": 531_000_000, # 5.31억
        "annual_saving_won": 12_400_000,
        "area_m2": 1_251,
    }
    
    result = run_sensitivity_analysis(baseline)
    # → {"subsidy_rate": [...], "total_cost": [...], ...}
"""

from typing import Dict, List, Optional


# ────────────────────────────────────────────────────
# 핵심 ROI 계산 (단순화 버전)
# ────────────────────────────────────────────────────

def compute_metrics(
    subsidy_rate: float,
    total_cost_won: float,
    annual_saving_won: float,
    area_m2: float,
    far_bonus_value_won: float = 0,
    tax_relief_won: float = 0,
    lifespan_years: int = 30,
) -> Dict[str, float]:
    """
    단일 시나리오의 핵심 ROI 지표 계산.

    Returns:
        {
            "자부담_원": 자기부담금,
            "GR_단독_회수년": 자부담 / 연간절감,
            "통합_회수년": 자부담 / (절감 + 보너스 분할),
            "자산화_ROI_pct": 30년 누적 효익 / 자부담 × 100,
            "30년_총효익_원": 절감×30 + 보너스 + 세금감면,
        }
    """
    own_burden = total_cost_won * (1 - subsidy_rate)

    if annual_saving_won <= 0:
        gr_payback = float("inf")
    else:
        gr_payback = own_burden / annual_saving_won

    # 통합 회수기간: 보너스를 30년 동안 분할 환산
    annual_bonus = (far_bonus_value_won + tax_relief_won) / lifespan_years
    total_annual = annual_saving_won + annual_bonus
    if total_annual <= 0:
        combined_payback = float("inf")
    else:
        combined_payback = own_burden / total_annual

    total_benefit_30y = (
        annual_saving_won * lifespan_years
        + far_bonus_value_won
        + tax_relief_won
    )
    asset_roi_pct = (
        (total_benefit_30y / own_burden * 100) if own_burden > 0 else float("inf")
    )

    return {
        "자부담_원": own_burden,
        "GR_단독_회수년": gr_payback,
        "통합_회수년": combined_payback,
        "자산화_ROI_pct": asset_roi_pct,
        "30년_총효익_원": total_benefit_30y,
    }


# ────────────────────────────────────────────────────
# 민감도 분석 (한 변수씩 흔들기)
# ────────────────────────────────────────────────────

def sensitivity_subsidy(
    baseline: Dict,
    rates: Optional[List[float]] = None,
) -> List[Dict]:
    """
    보조금율을 흔들어가며 ROI 변화 측정.

    Args:
        baseline: compute_metrics()의 입력 dict
        rates: 보조금율 리스트 (기본 [0.0, 0.3, 0.5, 0.7, 0.9])
    """
    if rates is None:
        rates = [0.0, 0.3, 0.5, 0.7, 0.9]

    out = []
    for r in rates:
        b = dict(baseline)
        b["subsidy_rate"] = r
        m = compute_metrics(**b)
        out.append({
            "보조금율": r,
            "보조금율_pct": f"{r*100:.0f}%",
            "자부담_억": m["자부담_원"] / 1e8,
            "GR_단독_회수년": m["GR_단독_회수년"],
            "통합_회수년": m["통합_회수년"],
            "자산화_ROI_pct": m["자산화_ROI_pct"],
            "_is_baseline": abs(r - baseline["subsidy_rate"]) < 0.001,
        })
    return out


def sensitivity_cost(
    baseline: Dict,
    deltas: Optional[List[float]] = None,
) -> List[Dict]:
    """
    보강 비용(±30%)을 흔들었을 때 ROI 변화.

    Args:
        deltas: [-0.3, -0.15, 0, 0.15, 0.3] 같은 변화율 리스트
    """
    if deltas is None:
        deltas = [-0.3, -0.15, 0.0, 0.15, 0.3]

    base_cost = baseline["total_cost_won"]
    out = []
    for d in deltas:
        b = dict(baseline)
        b["total_cost_won"] = base_cost * (1 + d)
        m = compute_metrics(**b)
        out.append({
            "비용_변화율": d,
            "비용_변화_pct": f"{d*100:+.0f}%",
            "보강비용_억": b["total_cost_won"] / 1e8,
            "자부담_억": m["자부담_원"] / 1e8,
            "GR_단독_회수년": m["GR_단독_회수년"],
            "자산화_ROI_pct": m["자산화_ROI_pct"],
            "_is_baseline": abs(d) < 0.001,
        })
    return out


def sensitivity_saving(
    baseline: Dict,
    deltas: Optional[List[float]] = None,
) -> List[Dict]:
    """
    에너지 절감액(±20%)을 흔들었을 때.

    실제 절감은 BIM 진단 후 예측이라 오차 범위 있음. 그래서 민감도 측정.
    """
    if deltas is None:
        deltas = [-0.2, -0.1, 0.0, 0.1, 0.2]

    base_saving = baseline["annual_saving_won"]
    out = []
    for d in deltas:
        b = dict(baseline)
        b["annual_saving_won"] = base_saving * (1 + d)
        m = compute_metrics(**b)
        out.append({
            "절감_변화율": d,
            "절감_변화_pct": f"{d*100:+.0f}%",
            "연간절감_만원": b["annual_saving_won"] / 1e4,
            "GR_단독_회수년": m["GR_단독_회수년"],
            "통합_회수년": m["통합_회수년"],
            "자산화_ROI_pct": m["자산화_ROI_pct"],
            "_is_baseline": abs(d) < 0.001,
        })
    return out


# ────────────────────────────────────────────────────
# 손익분기 분석 (Breakeven)
# ────────────────────────────────────────────────────

def breakeven_subsidy_rate(
    baseline: Dict,
    target_payback_years: float = 10.0,
) -> Optional[float]:
    """
    회수기간 = 목표 년수가 되는 손익분기 보조금율.

    이진 탐색으로 0~99% 범위에서 찾기.
    """
    low, high = 0.0, 0.99
    for _ in range(50):  # 50회면 1e-15 정밀도
        mid = (low + high) / 2
        b = dict(baseline)
        b["subsidy_rate"] = mid
        m = compute_metrics(**b)
        if m["통합_회수년"] > target_payback_years:
            low = mid  # 회수기간 더 짧게 → 보조금 더
        else:
            high = mid
    return (low + high) / 2


def breakeven_payback(baseline: Dict) -> Dict:
    """
    실용적 손익분기 지표 모음.

    Returns:
        - 무보조 회수년: 보조금 0% 일 때
        - 50% 보조 회수년
        - 현재 보조율 회수년 (baseline)
        - 회수 8년 달성 필요 보조율
        - 회수 10년 달성 필요 보조율
    """
    def with_rate(r):
        b = dict(baseline)
        b["subsidy_rate"] = r
        return compute_metrics(**b)["통합_회수년"]

    return {
        "무보조_회수년": with_rate(0.0),
        "50%보조_회수년": with_rate(0.5),
        "현재_회수년": with_rate(baseline["subsidy_rate"]),
        "회수8년_필요_보조율": breakeven_subsidy_rate(baseline, 8.0),
        "회수10년_필요_보조율": breakeven_subsidy_rate(baseline, 10.0),
    }


# ────────────────────────────────────────────────────
# 통합 진입점 (한 번에 모든 민감도 분석)
# ────────────────────────────────────────────────────

def run_sensitivity_analysis(baseline: Dict) -> Dict:
    """
    Mode 3 / Mode 2 에서 호출할 통합 민감도 분석.

    Args:
        baseline: {
            "subsidy_rate": 0.7,           # 0~1
            "total_cost_won": 531_000_000,
            "annual_saving_won": 12_400_000,
            "area_m2": 1_251,
            "far_bonus_value_won": 0,      # 옵션
            "tax_relief_won": 0,           # 옵션
        }

    Returns:
        {
            "baseline_metrics": {...},
            "subsidy_table": [...],
            "cost_table": [...],
            "saving_table": [...],
            "breakeven": {...},
        }
    """
    baseline_metrics = compute_metrics(**baseline)
    return {
        "baseline_metrics": baseline_metrics,
        "subsidy_table": sensitivity_subsidy(baseline),
        "cost_table": sensitivity_cost(baseline),
        "saving_table": sensitivity_saving(baseline),
        "breakeven": breakeven_payback(baseline),
    }
