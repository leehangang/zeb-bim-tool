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

# 제1호: 에너지자립률(%) 기준 ZEB 등급 (자립률_하한, 등급키, 라벨, rank).
# rank 클수록 상위 등급. ZEB 등급은 +등급·1~5등급 (ABCDE 아님).
ZEB_AUTONOMY_THRESHOLDS = [
    (120, "+", "ZEB 플러스등급", 6),
    (100, "1", "ZEB 1등급",     5),
    (80,  "2", "ZEB 2등급",     4),
    (60,  "3", "ZEB 3등급",     3),
    (40,  "4", "ZEB 4등급",     2),
    (20,  "5", "ZEB 5등급",     1),
]
NO_GRADE = {"grade": "-", "label": "등급 미달 (ZEB 인증 불가)", "rank": 0}

PV_YIELD_BY_REGION = {
    "중부1": 1250,
    "중부2": 1300,
    "남부":  1400,
    "제주":  1450,
}

# 1차에너지 환산계수 (ZEB 인증기준 고시 제10조 위임 · 건축물 에너지효율등급/ZEB 인증 공통)
# 소관부처 이관: 산업통상자원부 → 기후에너지환경부(2025.10.1). 계수값은 변동 없음.
# ZEB 에너지자립률 = 1차에너지 생산량 ÷ 1차에너지 소요량 → 전력 생산·소비 모두 ×2.75
PRIMARY_ENERGY_FACTORS = {
    "전력":     2.75,
    "지역난방": 0.728,
    "가스":     1.1,
    "기타연료": 1.1,
}
ELECTRICITY_PEF = PRIMARY_ENERGY_FACTORS["전력"]   # PV 발전(전력) 1차에너지 환산

# 제2호: 연간 단위면적당 1차에너지소요량(kWh/㎡·년) '미만' 기준 ZEB 등급.
# (PV 신재생 차감 후 순(net) 1차에너지소요량. 값이 작을수록(음수 포함) 상위 등급)
# (소요량_상한, 등급키, 라벨, rank).  출처: ZEB 인증기준 별표 제2호.
ZEB_PRIMARY_THRESHOLDS_NONRES = [   # 비주거용
    (-70, "+", "ZEB 플러스등급", 6),
    (-30, "1", "ZEB 1등급",     5),
    (10,  "2", "ZEB 2등급",     4),
    (50,  "3", "ZEB 3등급",     3),
    (90,  "4", "ZEB 4등급",     2),
    (130, "5", "ZEB 5등급",     1),
]
ZEB_PRIMARY_THRESHOLDS_RES = [      # 주거용
    (-10, "+", "ZEB 플러스등급", 6),
    (10,  "1", "ZEB 1등급",     5),
    (30,  "2", "ZEB 2등급",     4),
    (50,  "3", "ZEB 3등급",     3),
    (70,  "4", "ZEB 4등급",     2),
    (90,  "5", "ZEB 5등급",     1),
]
RESIDENTIAL_USES = {"공동주택", "주택", "기숙사", "아파트", "오피스텔"}


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


def autonomy_for_diagnosis(bim: dict) -> float:
    """
    진단(정량평가표)용 에너지자립률 — **비율(0~1)** 로 반환.

    ⚠️ 단일 소스 원칙: 자립률은 이 모듈에서만 계산한다.
    ZEB 고시 별표1 정식(순생산량 ÷ 총소요량, 양쪽 모두 1차에너지)을 그대로 쓴다.
    과거 core.bim_diagnoser가 '최종에너지 ÷ 100kWh/㎡ 어림'으로 따로 계산해
    진단 페이지 5.6% vs 홈 9.3%로 값이 갈리는 버그가 있었다.

    반환값은 RENEWABLE_BREAKPOINTS(비율 기준) 채점에 바로 쓰도록 0~1 스케일이다.
    """
    try:
        res = evaluate_zeb_from_bim(bim)
        return float(res.get("autonomy_pct", 0.0)) / 100.0
    except Exception:
        return 0.0


def determine_grade(autonomy_pct: float) -> dict:
    """제1호 — 에너지자립률(%) 기준 ZEB 등급."""
    for lo, g, label, rank in ZEB_AUTONOMY_THRESHOLDS:
        if autonomy_pct >= lo:
            return {"grade": g, "label": label, "rank": rank, "threshold": lo}
    return {**NO_GRADE, "threshold": 20}


def determine_grade_clause2(net_primary_kwh_m2: float,
                            is_residential: bool = False) -> dict:
    """제2호 — 연간 단위면적당 1차에너지소요량(PV 차감 후 net) 기준 ZEB 등급."""
    table = ZEB_PRIMARY_THRESHOLDS_RES if is_residential else ZEB_PRIMARY_THRESHOLDS_NONRES
    for upper, g, label, rank in table:
        if net_primary_kwh_m2 < upper:
            return {"grade": g, "label": label, "rank": rank, "threshold": upper}
    return {**NO_GRADE, "threshold": table[-1][0]}


def pick_higher_grade(g1: dict, g2: dict) -> dict:
    """제1호·제2호 중 더 높은 등급을 ZEB 인증등급으로."""
    return g1 if g1.get("rank", 0) >= g2.get("rank", 0) else g2


def check_zeb_requirements(
    grade_clause1: dict,
    grade_clause2: dict,
    bems_installed: bool,
    autonomy_pct: float,
    net_primary_kwh_m2: float,
) -> dict:
    """ZEB 인증요건 판정 — (제1호 또는 제2호) 그리고 제3호.

    제1호: 에너지자립률 20% 이상 (= 자립률로 5등급 이상 산정)
    제2호: 연간 단위면적당 1차에너지소요량 기준 충족 (= 소요량으로 5등급 이상)
    제3호: BEMS·전자식 원격검침 설치
    → (제1호 OR 제2호) AND 제3호 이면 인증 가능. 세 개 모두 충족할 필요는 없음.
    """
    c1_ok = grade_clause1.get("rank", 0) >= 1     # 제1호로 5등급 이상
    c2_ok = grade_clause2.get("rank", 0) >= 1     # 제2호로 5등급 이상
    bems_ok = bool(bems_installed)
    certifiable = (c1_ok or c2_ok) and bems_ok
    return {
        "제1호_충족": c1_ok,
        "제2호_충족": c2_ok,
        "제3호_BEMS_충족": bems_ok,
        "인증가능": certifiable,
        "items": [
            {"요건": "제1호 · 에너지자립률 20% 이상",
             "현재": f"{autonomy_pct:.1f}%", "충족": c1_ok},
            {"요건": "제2호 · 1차에너지소요량 기준",
             "현재": (grade_clause2.get("label", "-") if c2_ok else
                      f"{net_primary_kwh_m2:.0f} kWh/㎡ (미달)"),
             "충족": c2_ok},
            {"요건": "제3호 · BEMS·원격검침 설치",
             "현재": "설치" if bems_ok else "미설치", "충족": bems_ok},
        ],
        "note": "제1호 또는 제2호 중 하나 + 제3호(BEMS)를 충족하면 인증 가능",
    }


def apply_full_reinforcement(gr_mapping: dict) -> dict:
    """모든 GR 기술요소를 '적용'(100%)으로 만든 가상 매핑 — 보강 후 시나리오용."""
    out = {}
    for k, v in gr_mapping.items():
        nv = dict(v)
        nv["status"] = "적용"
        nv["적용비율"] = 1.0
        out[k] = nv
    return out


def evaluate_zeb(
    bim: dict,
    gr_mapping: dict,
    building_use: Optional[str] = None,
    manual_overrides: Optional[dict] = None,
    assume_full_reinforcement: bool = False,
    assume_bems: bool = False,
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
    elif assume_full_reinforcement:
        reduction = calculate_reduction_ratio(apply_full_reinforcement(gr_mapping))
        reduction["_source"] = "권장 전체 GR 보강 적용 가정"
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

    # 자립률(제1호) = 1차에너지 생산 ÷ 1차에너지 소비(보강 후 gross)
    if post_energy > 0:
        autonomy_pct = (pv_primary_per_m2 / post_energy) * 100
    else:
        autonomy_pct = 0

    # 제2호용 순(net) 1차에너지소요량 = gross 소요량 − 신재생(PV) 생산
    net_primary = post_energy - pv_primary_per_m2
    is_residential = use in RESIDENTIAL_USES

    grade_c1 = determine_grade(autonomy_pct)                          # 제1호 (자립률)
    grade_c2 = determine_grade_clause2(net_primary, is_residential)   # 제2호 (소요량)
    grade = pick_higher_grade(grade_c1, grade_c2)                     # 인증등급 = 더 높은 등급
    bems = bool(bim.get("bems_installed", False)) or assume_bems
    requirements = check_zeb_requirements(
        grade_c1, grade_c2, bems, autonomy_pct, net_primary,
    )

    return {
        "building_use": use,
        "is_residential": is_residential,
        "area_m2": bim.get("total_area_m2", 0),
        "base_energy_kwh_m2": round(base_kwh, 1),
        "reduction": reduction,
        "post_energy_kwh_m2": round(post_energy, 2),
        "net_primary_kwh_m2": round(net_primary, 2),
        "pv": pv,
        "autonomy_pct": round(autonomy_pct, 1),
        "grade": grade,                 # 최종 ZEB 인증등급 (제1호·제2호 중 상위)
        "grade_clause1": grade_c1,      # 제1호 (자립률 기준)
        "grade_clause2": grade_c2,      # 제2호 (1차에너지소요량 기준)
        "zeb_requirements": requirements,
        "primary_energy_factor": ELECTRICITY_PEF,
        "mode": "designbuilder" if use_db else "estimated",
    }


def evaluate_zeb_from_bim(bim: dict, manual_overrides: Optional[dict] = None) -> dict:
    from core.bim_diagnoser import map_to_gr_elements
    gr_mapping = map_to_gr_elements(bim)
    return evaluate_zeb(bim, gr_mapping, manual_overrides=manual_overrides)
