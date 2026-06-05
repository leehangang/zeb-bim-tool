"""
core/zeb_evaluator.py — ZEB 인증 평가 엔진
"""

from typing import Dict, Optional


BASE_ENERGY_BY_USE = {
    "어린이집": 200,
    "유치원": 200,
    "도서관": 220,
    "보건소": 280,
    "지역아동센터": 200,
    "복지시설": 250,
    "학교": 180,
    "사무소": 350,
    "업무시설": 350,
    "공공청사": 350,
    "기타": 250,
}

GR_ENERGY_REDUCTION = {
    "1_고성능창호":     0.08,
    "2_고기밀성단열문": 0.02,
    "3_외벽단열보강":   0.15,
    "4_바닥단열난방":   0.05,
    "5_쿨루프":         0.04,
    "6_폐열회수환기":   0.08,
    "7_고효율냉난방":   0.12,
    "8_고효율보일러":   0.05,
    "9_고효율LED":      0.03,
    "10_신재생태양광":  0.00,
    "11_BEMS":          0.05,
}

ZEB_GRADE_THRESHOLDS = [
    (100, 1, "ZEB 1등급 (Net Zero)"),
    (80,  2, "ZEB 2등급"),
    (60,  3, "ZEB 3등급"),
    (40,  4, "ZEB 4등급"),
    (20,  5, "ZEB 5등급"),
]

PV_YIELD_BY_REGION = {
    "중부1": 1250,
    "중부2": 1300,
    "남부":  1400,
    "제주":  1450,
}


def get_base_energy(building_use: str = "어린이집") -> float:
    return BASE_ENERGY_BY_USE.get(building_use, BASE_ENERGY_BY_USE["기타"])


def detect_building_use(bim: dict) -> str:
    desc = (bim.get("_meta", {}).get("description", "") + " "
            + bim.get("_meta", {}).get("extracted_for", ""))
    for use in BASE_ENERGY_BY_USE:
        if use in desc:
            return use
    return "어린이집"


def calculate_reduction_ratio(gr_mapping: dict) -> dict:
    breakdown = {}
    total_reduction = 0.0

    for key, ratio_max in GR_ENERGY_REDUCTION.items():
        if key not in gr_mapping:
            continue
        item = gr_mapping[key]

        status = item.get("status", "미적용")
        if status == "적용":
            applied = 1.0
        elif status == "부분적용":
            applied = item.get("적용비율", 0.5)
        else:
            applied = 0.0

        actual = applied * ratio_max
        total_reduction += actual

        breakdown[key] = {
            "이론최대_pct": round(ratio_max * 100, 1),
            "적용도_pct": round(applied * 100, 1),
            "실제절감_pct": round(actual * 100, 2),
        }

    return {
        "total_reduction_ratio": round(total_reduction, 4),
        "total_reduction_pct": round(total_reduction * 100, 1),
        "breakdown": breakdown,
    }


def calculate_pv_generation(bim: dict) -> dict:
    pv_list = bim.get("pv_panels", []) or []
    region = bim.get("region", "중부2")
    yield_per_kw = PV_YIELD_BY_REGION.get(region, 1300)

    total_kw = sum(p.get("capacity_kw", 0) for p in pv_list)
    annual_kwh = total_kw * yield_per_kw

    area_m2 = bim.get("total_area_m2", 1)
    yield_per_m2 = annual_kwh / area_m2 if area_m2 > 0 else 0

    return {
        "total_capacity_kw": total_kw,
        "annual_generation_kwh": round(annual_kwh, 1),
        "yield_per_m2_kwh": round(yield_per_m2, 2),
        "region_yield_per_kw": yield_per_kw,
        "region": region,
    }


def determine_grade(autonomy_pct: float) -> dict:
    for threshold, grade, label in ZEB_GRADE_THRESHOLDS:
        if autonomy_pct >= threshold:
            return {
                "grade": grade,
                "label": label,
                "threshold_pct": threshold,
            }
    return {
        "grade": 0,
        "label": "등급 미달 (ZEB 인증 불가)",
        "threshold_pct": 20,
    }


def evaluate_zeb(
    bim: dict,
    gr_mapping: dict,
    building_use: Optional[str] = None,
    manual_overrides: Optional[dict] = None,
) -> dict:
    overrides = manual_overrides or {}
    use_db = bool(overrides.get("annual_saving_pct"))

    use = building_use or detect_building_use(bim)
    base_kwh = overrides.get("base_energy_kwh_m2") or get_base_energy(use)

    if use_db:
        reduction_ratio = overrides["annual_saving_pct"] / 100.0
        reduction = {
            "total_reduction_ratio": reduction_ratio,
            "total_reduction_pct": round(reduction_ratio * 100, 1),
            "breakdown": {},
            "_source": "DesignBuilder 입력",
        }
    else:
        reduction = calculate_reduction_ratio(gr_mapping)
        reduction["_source"] = "11개 GR 요소 적용도 기반 추정"

    post_energy = base_kwh * (1 - reduction["total_reduction_ratio"])

    if overrides.get("pv_generation_kwh"):
        area_m2 = bim.get("total_area_m2", 1)
        pv_kwh = overrides["pv_generation_kwh"]
        pv = {
            "total_capacity_kw": None,
            "annual_generation_kwh": pv_kwh,
            "yield_per_m2_kwh": round(pv_kwh / area_m2 if area_m2 else 0, 2),
            "region_yield_per_kw": None,
            "region": bim.get("region", "중부2"),
            "_source": "사용자 입력",
        }
    else:
        pv = calculate_pv_generation(bim)
        pv["_source"] = "BIM PV 패널 자동 산정"

    if post_energy > 0:
        autonomy_pct = (pv["yield_per_m2_kwh"] / post_energy) * 100
    else:
        autonomy_pct = 0

    grade = determine_grade(autonomy_pct)

    return {
        "building_use": use,
        "area_m2": bim.get("total_area_m2", 0),
        "base_energy_kwh_m2": round(base_kwh, 1),
        "reduction": reduction,
        "post_energy_kwh_m2": round(post_energy, 2),
        "pv": pv,
        "autonomy_pct": round(autonomy_pct, 1),
        "grade": grade,
        "mode": "designbuilder" if use_db else "estimated",
    }


def evaluate_zeb_from_bim(bim: dict, manual_overrides: Optional[dict] = None) -> dict:
    from core.bim_diagnoser import map_to_gr_elements
    gr_mapping = map_to_gr_elements(bim)
    return evaluate_zeb(bim, gr_mapping, manual_overrides=manual_overrides)
