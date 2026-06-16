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

# 1차에너지 환산계수 (산업통상자원부 고시 · 건축물 에너지효율등급/ZEB 인증 공통)
# ZEB 에너지자립률 = 1차에너지 생산량 ÷ 1차에너지 소요량 → 전력 생산·소비 모두 ×2.75
PRIMARY_ENERGY_FACTORS = {
    "전력":     2.75,
    "지역난방": 0.728,
    "가스":     1.1,
    "기타연료": 1.1,
}
ELECTRICITY_PEF = PRIMARY_ENERGY_FACTORS["전력"]   # PV 발전(전력) 1차에너지 환산

# 비주거 건축물 에너지효율등급 — 보강 후 단위면적당 1차에너지소요량(kWh/㎡·년) 상한.
# (국토부·산업부 「건축물 에너지효율등급 인증 및 ZEB 인증 기준」 별표 표준값)
NONRES_EFFICIENCY_GRADES = [
    ("1+++",  80),
    ("1++",  140),
    ("1+",   200),
    ("1",    260),
    ("2",    320),
    ("3",    380),
    ("4",    450),
    ("5",    520),
    ("6",    610),
    ("7",    700),
]
# ZEB 인증 의무요건: 에너지효율 1++ 이상이어야 함 (1차에너지소요량 < 140)
ZEB_REQUIRED_EFFICIENCY_GRADES = {"1+++", "1++"}
ZEB_MIN_AUTONOMY_PCT = 20.0   # 자립률 최소 20% (ZEB 5등급)


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


def determine_efficiency_grade(primary_energy_req: float) -> dict:
    """보강 후 단위면적당 1차에너지소요량(kWh/㎡·년) → 비주거 에너지효율등급."""
    for grade, upper in NONRES_EFFICIENCY_GRADES:
        if primary_energy_req < upper:
            return {
                "grade": grade,
                "upper_limit": upper,
                "meets_zeb_min": grade in ZEB_REQUIRED_EFFICIENCY_GRADES,
            }
    return {"grade": "등급외", "upper_limit": None, "meets_zeb_min": False}


def check_zeb_requirements(
    efficiency_grade: dict,
    autonomy_pct: float,
    bems_installed: bool,
) -> dict:
    """ZEB 인증 3대 의무요건 판정.

    ① 건축물 에너지효율등급 1++ 이상
    ② 에너지자립률 20% 이상
    ③ BEMS 또는 전자식 원격검침계량기 설치
    셋 다 충족해야 ZEB 인증 가능.
    """
    eff_ok = bool(efficiency_grade.get("meets_zeb_min"))
    autonomy_ok = autonomy_pct >= ZEB_MIN_AUTONOMY_PCT
    bems_ok = bool(bems_installed)
    return {
        "효율등급_충족": eff_ok,
        "자립률_충족": autonomy_ok,
        "BEMS_충족": bems_ok,
        "인증가능": eff_ok and autonomy_ok and bems_ok,
        "items": [
            {"요건": "건축물 에너지효율등급 1++ 이상",
             "현재": efficiency_grade.get("grade", "-"), "충족": eff_ok},
            {"요건": "에너지자립률 20% 이상",
             "현재": f"{autonomy_pct:.1f}%", "충족": autonomy_ok},
            {"요건": "BEMS·원격검침 설치",
             "현재": "설치" if bems_ok else "미설치", "충족": bems_ok},
        ],
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

    # PV 발전(전력)을 1차에너지로 환산(×2.75) 후 자립률 산정
    # — ZEB 고시: 자립률 = 1차에너지 생산량 ÷ 1차에너지 소요량 (양쪽 모두 1차에너지)
    pv_primary_per_m2 = pv["yield_per_m2_kwh"] * ELECTRICITY_PEF
    pv["yield_per_m2_primary_kwh"] = round(pv_primary_per_m2, 2)
    pv["primary_energy_factor"] = ELECTRICITY_PEF

    if post_energy > 0:
        autonomy_pct = (pv_primary_per_m2 / post_energy) * 100
    else:
        autonomy_pct = 0

    grade = determine_grade(autonomy_pct)
    efficiency = determine_efficiency_grade(post_energy)
    requirements = check_zeb_requirements(
        efficiency, autonomy_pct, bim.get("bems_installed", False)
    )

    return {
        "building_use": use,
        "area_m2": bim.get("total_area_m2", 0),
        "base_energy_kwh_m2": round(base_kwh, 1),
        "reduction": reduction,
        "post_energy_kwh_m2": round(post_energy, 2),
        "pv": pv,
        "autonomy_pct": round(autonomy_pct, 1),
        "grade": grade,
        "efficiency_grade": efficiency,
        "zeb_requirements": requirements,
        "primary_energy_factor": ELECTRICITY_PEF,
        "mode": "designbuilder" if use_db else "estimated",
    }


def evaluate_zeb_from_bim(bim: dict, manual_overrides: Optional[dict] = None) -> dict:
    from core.bim_diagnoser import map_to_gr_elements
    gr_mapping = map_to_gr_elements(bim)
    return evaluate_zeb(bim, gr_mapping, manual_overrides=manual_overrides)
