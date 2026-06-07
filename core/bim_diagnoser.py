"""
core/bim_diagnoser.py — BIM 진단 엔진
=====================================
Dynamo 추출 JSON을 받아 11개 GR 기술요소에 매핑하고 자동 채점.

데이터 소스:
    - 01 GR 가이드라인 표1 (종합형 정량평가표)
    - 02 GR 기술요소 — 매핑 룰
    - 06 에너지절약설계기준 별표1 — 지역별 부위별 열관류율

11개 GR 기술요소:
    [패시브-건축]
    1. 고성능창호
    2. 고기밀성 단열문
    3. 내·외부 단열보강
    4. 바닥 단열 및 난방
    5. 쿨루프

    [액티브-기계]
    6. 폐열회수형 환기장치
    7. 고효율 냉·난방장치
    8. 고효율 보일러

    [액티브-전기]
    9. 고효율 LED 조명
    10. 신재생에너지 (태양광)
    11. BEMS / 원격검침전자식계량기
"""

import json
from pathlib import Path
from typing import Optional


# ====================================================================
# 06 에너지절약설계기준 별표1 - 지역별 부위별 열관류율 기준 (W/㎡K)
# ====================================================================
# 출처: 국토교통부 고시 (2025.12 개정)
# 주의: 본 dict의 값은 업계 공개 기준에 따른 표준 값이며,
#       실제 06 PDF [별표1] 값과 비교 검증 후 사용 권장.
# --------------------------------------------------------------------
U_VALUE_LIMITS = {
    "중부1": {
        "외벽_직접": 0.150,
        "외벽_간접": 0.210,
        "지붕_직접": 0.130,
        "지붕_간접": 0.180,
        "바닥_직접": 0.150,
        "바닥_간접": 0.210,
        "창_직접": 0.900,
        "창_간접": 1.300,
        "문_직접": 0.900,
        "문_간접": 1.300,
    },
    "중부2": {
        "외벽_직접": 0.170,
        "외벽_간접": 0.240,
        "지붕_직접": 0.150,
        "지붕_간접": 0.210,
        "바닥_직접": 0.170,
        "바닥_간접": 0.240,
        "창_직접": 1.000,
        "창_간접": 1.500,
        "문_직접": 1.000,
        "문_간접": 1.500,
    },
    "남부": {
        "외벽_직접": 0.220,
        "외벽_간접": 0.310,
        "지붕_직접": 0.180,
        "지붕_간접": 0.260,
        "바닥_직접": 0.220,
        "바닥_간접": 0.310,
        "창_직접": 1.200,
        "창_간접": 1.600,
        "문_직접": 1.200,
        "문_간접": 1.600,
    },
    "제주": {
        "외벽_직접": 0.290,
        "외벽_간접": 0.410,
        "지붕_직접": 0.250,
        "지붕_간접": 0.350,
        "바닥_직접": 0.290,
        "바닥_간접": 0.410,
        "창_직접": 1.600,
        "창_간접": 1.900,
        "문_직접": 1.600,
        "문_간접": 1.900,
    },
}


# ====================================================================
# 01 GR 가이드라인 표1 - 종합형 정량평가표 (배점 기준)
# ====================================================================
# 100점 만점 = 그린리모델링 요소 80점 + 사업여건 20점
# + 가점 13점, 감점 10점
# --------------------------------------------------------------------

# 단열 (20점): 벽 10 + 지붕 7 + 바닥 3 — 적용 면적 비율 기준
WALL_INSULATION_BREAKPOINTS = [
    (1.00, 10), (0.80, 8), (0.60, 6), (0.40, 4), (0.30, 2),
]
ROOF_INSULATION_BREAKPOINTS = [
    (1.00, 7), (0.75, 5), (0.50, 3), (0.25, 1),
]
FLOOR_INSULATION_BREAKPOINTS = [
    (1.00, 3), (0.60, 2), (0.30, 1),
]

# 창호 (16점): 창 10 + 문 3 + 일사조절 3
WINDOW_BREAKPOINTS = [
    (1.00, 10), (0.80, 8), (0.60, 6), (0.40, 4), (0.20, 2),
]
DOOR_BREAKPOINTS = [
    (1.00, 3), (0.60, 2), (0.30, 1),
]

# 설비 (15점): 냉방 5 + 난방 5 + 급탕 5 (각각 동일 배점 룰)
HVAC_BREAKPOINTS = [
    (1.00, 5), (0.80, 4), (0.60, 3), (0.40, 2), (0.30, 1),
]

# 환기 (5점): 폐열회수형 환기장치 적용 면적
VENTILATION_BREAKPOINTS = [
    (1.00, 5), (0.80, 4), (0.60, 3), (0.40, 2), (0.20, 1),
]

# 신재생 (5점): 자립률
RENEWABLE_BREAKPOINTS = [
    (0.20, 5), (0.15, 4), (0.10, 3), (0.05, 2), (0.0001, 1),
]

# LED (2점): 적용 여부
# BEMS (2점): 적용 여부

# 에너지 절감률 (10점)
ENERGY_SAVING_BREAKPOINTS = [
    (0.35, 10), (0.30, 8), (0.25, 6), (0.20, 4), (0.00, 2),
]


def _score_by_ratio(ratio: float, breakpoints: list) -> int:
    """
    적용 비율 -> 점수.
    breakpoints는 [(임계값, 점수), ...] 내림차순.
    """
    for threshold, score in breakpoints:
        if ratio >= threshold:
            return score
    return 0


# ====================================================================
# Phase 1 — JSON 파싱
# ====================================================================

def parse_bim_json(json_path: str) -> dict:
    """
    Dynamo 추출 JSON 파일 읽기.

    기대 스키마:
        {
          "region": "중부2",
          "building_year": 2014,
          "total_area_m2": 1251,
          "walls": [
            {"id": "W001", "area": 683.75, "facing": "exterior_direct",
             "insulated": true, "u_value": 0.156},
            {"id": "W002", "area": 887.50, "facing": "exterior_direct",
             "insulated": false, "u_value": null}
          ],
          "windows": [
            {"id": "Win01", "area": 100.0, "facing": "exterior_direct",
             "u_value": 3.6}
          ],
          "doors": [
            {"id": "D01", "area": 28.85, "count": 13,
             "facing": "exterior_direct", "insulated": false}
          ],
          "roofs": [
            {"id": "R001", "area": 600.0, "insulated": true,
             "u_value": 0.18, "cool_roof_applied": false}
          ],
          "floors": [
            {"id": "F001", "area": 600.0, "insulated": true,
             "underfloor_heating": true, "u_value": 0.17}
          ],
          "pv_panels": [
            {"id": "PV001", "area": 27.0, "capacity_kw": 5.4}
          ],
          "hvac": {
            "heating": {"type": "EHP", "units": 23, "efficient": true},
            "cooling": {"type": "EHP", "units": 23, "efficient": true},
            "boiler": null,
            "ventilation": {"type": "ERV", "units": 9, "efficient": true,
                            "covered_area_m2": 800}
          },
          "lighting": {"led_count": 0, "total_count": 439},
          "bems_installed": false
        }
    """
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


# ====================================================================
# Phase 2 — 11개 GR 기술요소 매핑
# ====================================================================

def map_to_gr_elements(bim: dict) -> dict:
    """
    BIM 객체를 11개 GR 기술요소로 매핑.
    각 항목에 대해 status, applied_ratio, details 산출.
    """
    out = {}

    # ---------------------------------------------------------------
    # 1. 고성능창호
    # ---------------------------------------------------------------
    windows = bim.get("windows", [])
    total_win = sum(w["area"] for w in windows)
    # 고성능 판정: 외기 직접 면 + u_value <= 한 기준
    region = bim.get("region", "중부2")
    win_u_limit = U_VALUE_LIMITS[region]["창_직접"]
    high_perf_win = sum(
        w["area"] for w in windows
        if w.get("u_value") is not None and w["u_value"] <= win_u_limit
    )
    out["1_고성능창호"] = {
        "status": _classify(high_perf_win, total_win),
        "총면적_m2": total_win,
        "기적용_m2": high_perf_win,
        "미적용_m2": total_win - high_perf_win,
        "적용비율": (high_perf_win / total_win) if total_win > 0 else 0,
        "기준_U값": win_u_limit,
    }

    # ---------------------------------------------------------------
    # 2. 고기밀성 단열문
    # ---------------------------------------------------------------
    doors = bim.get("doors", [])
    total_door = sum(d["area"] for d in doors)
    insulated_door = sum(d["area"] for d in doors if d.get("insulated"))
    out["2_고기밀성단열문"] = {
        "status": _classify(insulated_door, total_door),
        "총면적_m2": total_door,
        "기적용_m2": insulated_door,
        "미적용_m2": total_door - insulated_door,
        "적용비율": (insulated_door / total_door) if total_door > 0 else 0,
    }

    # ---------------------------------------------------------------
    # 3. 내·외부 단열보강 (외벽)
    # ---------------------------------------------------------------
    walls = bim.get("walls", [])
    total_wall = sum(w["area"] for w in walls)
    insulated_wall = sum(w["area"] for w in walls if w.get("insulated"))
    out["3_외벽단열보강"] = {
        "status": _classify(insulated_wall, total_wall),
        "총면적_m2": total_wall,
        "기적용_m2": insulated_wall,
        "미적용_m2": total_wall - insulated_wall,
        "적용비율": (insulated_wall / total_wall) if total_wall > 0 else 0,
    }

    # ---------------------------------------------------------------
    # 4. 바닥 단열 및 난방
    # ---------------------------------------------------------------
    floors = bim.get("floors", [])
    total_floor = sum(f["area"] for f in floors)
    insulated_floor = sum(
        f["area"] for f in floors
        if f.get("insulated") or f.get("underfloor_heating")
    )
    out["4_바닥단열난방"] = {
        "status": _classify(insulated_floor, total_floor),
        "총면적_m2": total_floor,
        "기적용_m2": insulated_floor,
        "미적용_m2": total_floor - insulated_floor,
        "적용비율": (insulated_floor / total_floor) if total_floor > 0 else 0,
    }

    # ---------------------------------------------------------------
    # 5. 쿨루프
    # ---------------------------------------------------------------
    roofs = bim.get("roofs", [])
    total_roof = sum(r["area"] for r in roofs)
    cool_roof_area = sum(r["area"] for r in roofs if r.get("cool_roof_applied"))
    out["5_쿨루프"] = {
        "status": _classify(cool_roof_area, total_roof),
        "총면적_m2": total_roof,
        "기적용_m2": cool_roof_area,
        "미적용_m2": total_roof - cool_roof_area,
        "적용비율": (cool_roof_area / total_roof) if total_roof > 0 else 0,
    }

    # ---------------------------------------------------------------
    # 6. 폐열회수형 환기장치
    # ---------------------------------------------------------------
    vent = bim.get("hvac", {}).get("ventilation")
    if vent and vent.get("efficient"):
        covered = vent.get("covered_area_m2", 0)
        total = bim.get("total_area_m2", 1)
        ratio = covered / total if total else 0
        out["6_폐열회수환기"] = {
            "status": _classify(covered, total),
            "기적용_m2": covered,
            "적용비율": ratio,
            "장비_수": vent.get("units", 0),
        }
    else:
        out["6_폐열회수환기"] = {
            "status": "미적용", "기적용_m2": 0, "적용비율": 0, "장비_수": 0,
        }

    # ---------------------------------------------------------------
    # 7. 고효율 냉·난방장치
    # ---------------------------------------------------------------
    hvac = bim.get("hvac", {})
    heating = hvac.get("heating")
    cooling = hvac.get("cooling")
    heating_ok = bool(heating and heating.get("efficient"))
    cooling_ok = bool(cooling and cooling.get("efficient"))
    out["7_고효율냉난방"] = {
        "status": (
            "적용" if heating_ok and cooling_ok else
            "부분적용" if heating_ok or cooling_ok else
            "미적용"
        ),
        "냉방": heating,
        "난방": cooling,
    }

    # ---------------------------------------------------------------
    # 8. 고효율 보일러
    # ---------------------------------------------------------------
    boiler = hvac.get("boiler")
    out["8_고효율보일러"] = {
        "status": "적용" if (boiler and boiler.get("efficient")) else "미적용",
        "설비": boiler,
    }

    # ---------------------------------------------------------------
    # 9. 고효율 LED 조명
    # ---------------------------------------------------------------
    lighting = bim.get("lighting", {})
    led_count = lighting.get("led_count", 0)
    total_count = lighting.get("total_count", 1)
    led_ratio = led_count / total_count if total_count else 0
    out["9_고효율LED"] = {
        "status": _classify(led_count, total_count),
        "LED_개수": led_count,
        "전체_개수": total_count,
        "적용비율": led_ratio,
    }

    # ---------------------------------------------------------------
    # 10. 신재생에너지 (태양광)
    # ---------------------------------------------------------------
    pv = bim.get("pv_panels", [])
    total_pv_area = sum(p["area"] for p in pv)
    total_kw = sum(p.get("capacity_kw", 0) for p in pv)
    # 자립률 추정: 1kW PV ≈ 연간 1,300 kWh 발전, 건물 연간 소비 가정 100kWh/㎡
    building_area = bim.get("total_area_m2", 1)
    annual_demand = building_area * 100   # kWh/년 (어림)
    annual_gen = total_kw * 1300          # kWh/년
    autonomy_ratio = annual_gen / annual_demand if annual_demand > 0 else 0
    out["10_신재생태양광"] = {
        "status": "적용" if total_pv_area > 0 else "미적용",
        "PV_면적_m2": total_pv_area,
        "용량_kW": total_kw,
        "자립률_추정": round(autonomy_ratio, 3),
    }

    # ---------------------------------------------------------------
    # 11. BEMS / 원격검침
    # ---------------------------------------------------------------
    out["11_BEMS"] = {
        "status": "적용" if bim.get("bems_installed") else "미적용",
    }

    return out


def _classify(applied: float, total: float) -> str:
    """적용 면적 / 전체 면적 -> 상태 분류."""
    if total <= 0:
        return "해당없음"
    ratio = applied / total
    if ratio >= 0.95:
        return "적용"
    elif ratio >= 0.05:
        return "부분적용"
    return "미적용"


# ====================================================================
# Phase 3 — 정량평가표 채점
# ====================================================================

def score_compliance(gr_mapping: dict, bim: dict) -> dict:
    """
    01 가이드라인 표1 기반 자동 채점.
    100점 만점 (기본 80 + 사업여건 20).
    """
    breakdown = {}

    # ---------------------------------------------------------------
    # 그린리모델링 요소 (80점)
    # ---------------------------------------------------------------

    # 1) 단열 (벽 10 + 지붕 7 + 바닥 3 = 20점)
    wall_ratio = gr_mapping["3_외벽단열보강"]["적용비율"]
    wall_score = _score_by_ratio(wall_ratio, WALL_INSULATION_BREAKPOINTS)

    # 지붕 단열 비율
    roofs = bim.get("roofs", [])
    total_roof = sum(r["area"] for r in roofs)
    insul_roof = sum(r["area"] for r in roofs if r.get("insulated"))
    roof_ratio = insul_roof / total_roof if total_roof > 0 else 0
    roof_score = _score_by_ratio(roof_ratio, ROOF_INSULATION_BREAKPOINTS)

    floor_ratio = gr_mapping["4_바닥단열난방"]["적용비율"]
    floor_score = _score_by_ratio(floor_ratio, FLOOR_INSULATION_BREAKPOINTS)

    breakdown["단열"] = {
        "벽": {"비율": wall_ratio, "점수": wall_score, "만점": 10},
        "지붕": {"비율": roof_ratio, "점수": roof_score, "만점": 7},
        "바닥": {"비율": floor_ratio, "점수": floor_score, "만점": 3},
        "소계": wall_score + roof_score + floor_score,
    }

    # 2) 창호 (창 10 + 문 3 + 일사조절 3 = 16점)
    win_ratio = gr_mapping["1_고성능창호"]["적용비율"]
    win_score = _score_by_ratio(win_ratio, WINDOW_BREAKPOINTS)
    door_ratio = gr_mapping["2_고기밀성단열문"]["적용비율"]
    door_score = _score_by_ratio(door_ratio, DOOR_BREAKPOINTS)
    # 일사조절은 별도 데이터 필요. 기본 0
    shading_score = bim.get("shading_score", 0)

    breakdown["창호"] = {
        "창": {"비율": win_ratio, "점수": win_score, "만점": 10},
        "문": {"비율": door_ratio, "점수": door_score, "만점": 3},
        "일사조절": {"점수": shading_score, "만점": 3},
        "소계": win_score + door_score + shading_score,
    }

    # 3) 설비 (냉방 5 + 난방 5 + 급탕 5 = 15점)
    hvac = bim.get("hvac", {})

    def _hvac_ratio(category):
        info = hvac.get(category)
        if not info:
            return 0
        units_old = info.get("units", 0)
        replaced = info.get("replaced_units", units_old if info.get("efficient") else 0)
        return replaced / units_old if units_old > 0 else 0

    cool_ratio = _hvac_ratio("cooling")
    heat_ratio = _hvac_ratio("heating")
    dhw_ratio = _hvac_ratio("dhw")   # 급탕

    cool_score = _score_by_ratio(cool_ratio, HVAC_BREAKPOINTS)
    heat_score = _score_by_ratio(heat_ratio, HVAC_BREAKPOINTS)
    dhw_score = _score_by_ratio(dhw_ratio, HVAC_BREAKPOINTS)

    breakdown["설비"] = {
        "냉방": {"비율": cool_ratio, "점수": cool_score, "만점": 5},
        "난방": {"비율": heat_ratio, "점수": heat_score, "만점": 5},
        "급탕": {"비율": dhw_ratio, "점수": dhw_score, "만점": 5},
        "소계": cool_score + heat_score + dhw_score,
    }

    # 4) 신재생 (5점) - 자립률 기반
    auto = gr_mapping["10_신재생태양광"]["자립률_추정"]
    renew_score = _score_by_ratio(auto, RENEWABLE_BREAKPOINTS)
    breakdown["신재생"] = {"자립률": auto, "점수": renew_score, "만점": 5}

    # 5) 환기 (5점)
    vent_ratio = gr_mapping["6_폐열회수환기"]["적용비율"]
    vent_score = _score_by_ratio(vent_ratio, VENTILATION_BREAKPOINTS)
    breakdown["환기"] = {"비율": vent_ratio, "점수": vent_score, "만점": 5}

    # 6) 전기 LED (2점)
    led_applied = gr_mapping["9_고효율LED"]["적용비율"] >= 1.0
    led_score = 2 if led_applied else 0
    breakdown["LED"] = {"적용": led_applied, "점수": led_score, "만점": 2}

    # 7) BEMS (2점)
    bems_applied = gr_mapping["11_BEMS"]["status"] == "적용"
    bems_score = 2 if bems_applied else 0
    breakdown["BEMS"] = {"적용": bems_applied, "점수": bems_score, "만점": 2}

    # 8) 에너지 절감률 (10점)
    energy_saving = bim.get("energy_saving_ratio", 0)
    energy_score = _score_by_ratio(energy_saving, ENERGY_SAVING_BREAKPOINTS)
    breakdown["에너지절감률"] = {
        "비율": energy_saving, "점수": energy_score, "만점": 10,
    }

    # 9) 녹색건축물 전환 인정 (5점) — 기본 0, 추후 입력
    breakdown["녹색건축물전환"] = {"점수": bim.get("green_cert_score", 0), "만점": 5}

    # 그린리모델링 요소 소계
    gr_total = sum(v["소계"] if "소계" in v else v["점수"] for v in [
        breakdown["단열"], breakdown["창호"], breakdown["설비"],
        breakdown["신재생"], breakdown["환기"], breakdown["LED"],
        breakdown["BEMS"], breakdown["에너지절감률"], breakdown["녹색건축물전환"],
    ])

    # ---------------------------------------------------------------
    # 사업여건 (20점) - 노후도 + 소유 + 사업효율성
    # ---------------------------------------------------------------
    year = bim.get("building_year", 2025)
    if year <= 1993:
        age_score = 10
    elif year <= 2000:
        age_score = 8
    elif year <= 2008:
        age_score = 6
    elif year <= 2010:
        age_score = 4
    else:
        age_score = 2

    ownership_score = 5 if bim.get("directly_owned", True) else 3

    # 사업효율성: 절감량(kWh/년) / 사업비(백만원), 5점 만점
    saving_kwh = bim.get("annual_saving_kwh", 0)
    project_cost_mil = bim.get("project_cost_million_won", 1)
    efficiency = saving_kwh / project_cost_mil if project_cost_mil > 0 else 0
    if efficiency >= 120:
        efficiency_score = 5
    elif efficiency >= 90:
        efficiency_score = 4
    elif efficiency >= 60:
        efficiency_score = 3
    elif efficiency >= 30:
        efficiency_score = 2
    elif efficiency > 0:
        efficiency_score = 1
    else:
        efficiency_score = 0

    breakdown["사업여건"] = {
        "노후도": {"건축년도": year, "점수": age_score, "만점": 10},
        "소유": {"직접소유": bim.get("directly_owned", True),
                 "점수": ownership_score, "만점": 5},
        "사업효율성": {"효율": efficiency, "점수": efficiency_score, "만점": 5},
        "소계": age_score + ownership_score + efficiency_score,
    }

    # ---------------------------------------------------------------
    # 총점
    # ---------------------------------------------------------------
    total_score = gr_total + breakdown["사업여건"]["소계"]

    # 등급
    if total_score >= 85:
        grade = "A+"
    elif total_score >= 75:
        grade = "A"
    elif total_score >= 65:
        grade = "B"
    elif total_score >= 50:
        grade = "C"
    else:
        grade = "D"

    return {
        "total_score": total_score,
        "max_score": 100,
        "grade": grade,
        "gr_subtotal": gr_total,
        "site_subtotal": breakdown["사업여건"]["소계"],
        "breakdown": breakdown,
    }


# ====================================================================
# Phase 4 — 열관류율 적합성 검증
# ====================================================================

def check_u_value(
    part: str,
    actual_u: Optional[float],
    region: str = "중부2",
    facing: str = "direct",
) -> dict:
    """
    부위별 열관류율 기준 적합성 판정.

    Args:
        part: "외벽", "지붕", "바닥", "창", "문"
        actual_u: 측정·계산된 열관류율
        region: 중부1/중부2/남부/제주
        facing: "direct" (직접) / "indirect" (간접)

    Returns:
        {"compliant": True/False, "limit": ..., "actual": ..., "margin_pct": ...}
    """
    if actual_u is None:
        return {
            "compliant": None,
            "limit": None,
            "actual": None,
            "message": "측정값 없음",
        }

    facing_kr = "직접" if facing == "direct" else "간접"
    key = f"{part}_{facing_kr}"

    if region not in U_VALUE_LIMITS or key not in U_VALUE_LIMITS[region]:
        return {
            "compliant": None,
            "limit": None,
            "actual": actual_u,
            "message": f"기준 없음: {region}/{key}",
        }

    limit = U_VALUE_LIMITS[region][key]
    compliant = actual_u <= limit
    margin = ((limit - actual_u) / limit * 100) if limit > 0 else 0

    return {
        "compliant": compliant,
        "limit": limit,
        "actual": actual_u,
        "margin_pct": round(margin, 1),
    }


# ====================================================================
# Phase 5 — 자연어 진단 리포트
# ====================================================================

def generate_diagnosis_report(
    gr_mapping: dict,
    score: dict,
    bim: dict,
    roi_plan: Optional[list] = None,
) -> str:
    """
    11개 매핑 + 점수 → 마크다운 진단 리포트.

    roi_plan이 주어지면 "보강 권장 사항" 섹션을 ROI 정보로 확장
    (예상 보강비용, 점수 상승, 우선순위).
    """
    region = bim.get("region", "중부2")
    lines = []

    # 헤더
    lines.append(f"# BIM 진단 리포트")
    lines.append("")
    lines.append(f"**총점**: {score['total_score']}/{score['max_score']}점  ")
    lines.append(f"**등급**: {score['grade']}  ")
    lines.append(f"**권역**: {region}  ")
    lines.append("")

    # 11개 항목 요약
    lines.append("## 11개 GR 기술요소 현황")
    lines.append("")
    lines.append("| # | 기술요소 | 상태 | 적용 비율 | 비고 |")
    lines.append("|---|---|---|---|---|")

    items = [
        ("1", "고성능창호", gr_mapping["1_고성능창호"]),
        ("2", "고기밀성단열문", gr_mapping["2_고기밀성단열문"]),
        ("3", "외벽단열보강", gr_mapping["3_외벽단열보강"]),
        ("4", "바닥단열·난방", gr_mapping["4_바닥단열난방"]),
        ("5", "쿨루프", gr_mapping["5_쿨루프"]),
        ("6", "폐열회수환기", gr_mapping["6_폐열회수환기"]),
        ("7", "고효율 냉난방", gr_mapping["7_고효율냉난방"]),
        ("8", "고효율 보일러", gr_mapping["8_고효율보일러"]),
        ("9", "고효율 LED", gr_mapping["9_고효율LED"]),
        ("10", "신재생(태양광)", gr_mapping["10_신재생태양광"]),
        ("11", "BEMS", gr_mapping["11_BEMS"]),
    ]

    icon_map = {"적용": "✅", "부분적용": "⚠️", "미적용": "❌", "해당없음": "—"}

    for num, name, info in items:
        status = info["status"]
        icon = icon_map.get(status, "—")
        ratio = info.get("적용비율", None)
        ratio_str = f"{ratio*100:.0f}%" if ratio is not None else "-"
        note = ""
        if "미적용_m2" in info and info["미적용_m2"] > 0:
            note = f"미적용 {info['미적용_m2']:.1f}㎡"
        elif "용량_kW" in info:
            note = f"{info['용량_kW']}kW, 자립률 {info['자립률_추정']*100:.1f}%"
        lines.append(f"| {num} | {name} | {icon} {status} | {ratio_str} | {note} |")

    lines.append("")

    # 점수 분해
    lines.append("## 점수 분해")
    lines.append("")
    bd = score["breakdown"]
    lines.append(f"- 단열: {bd['단열']['소계']}/20점 (벽 {bd['단열']['벽']['점수']}, 지붕 {bd['단열']['지붕']['점수']}, 바닥 {bd['단열']['바닥']['점수']})")
    lines.append(f"- 창호: {bd['창호']['소계']}/16점")
    lines.append(f"- 설비: {bd['설비']['소계']}/15점")
    lines.append(f"- 신재생: {bd['신재생']['점수']}/5점 (자립률 {bd['신재생']['자립률']*100:.1f}%)")
    lines.append(f"- 환기: {bd['환기']['점수']}/5점")
    lines.append(f"- LED: {bd['LED']['점수']}/2점")
    lines.append(f"- BEMS: {bd['BEMS']['점수']}/2점")
    lines.append(f"- 에너지절감률: {bd['에너지절감률']['점수']}/10점")
    lines.append(f"- 사업여건: {bd['사업여건']['소계']}/20점")
    lines.append("")
    lines.append(f"**GR 요소 합계**: {score['gr_subtotal']}/80점")
    lines.append(f"**사업여건**: {score['site_subtotal']}/20점")
    lines.append("")

    # 보강 권장 (미적용/부분적용 항목)
    lines.append("## 보강 권장 사항")
    lines.append("")
    recommendations = []
    for num, name, info in items:
        if info["status"] in ("미적용", "부분적용"):
            if "미적용_m2" in info and info["미적용_m2"] > 0:
                recommendations.append(
                    f"- **{name}**: {info['미적용_m2']:.1f}㎡ 추가 보강 필요"
                )
            elif info["status"] == "미적용":
                recommendations.append(f"- **{name}**: 신규 설치 검토")

    if recommendations:
        lines.extend(recommendations)
    else:
        lines.append("모든 GR 기술요소가 충족되었습니다 ✅")

    # ---------------------------------------------------------------
    # ROI 연계 보강 계획 (옵션)
    # ---------------------------------------------------------------
    if roi_plan:
        lines.append("")
        lines.append("## 보강 계획 ROI 분석")
        lines.append("")
        lines.append(
            "*아래 비용은 07 조달청 단가DB + 08 간접공사비 매트릭스 기반 자동 산정 결과입니다. "
            "실시설계 단계에선 견적사·시공사 검토 필수.*"
        )
        lines.append("")
        lines.append("| 우선순위 | 항목 | 수량 | 예상 비용(원) | 현재→보강 점수 | Δ점수 | 효율(점/억) |")
        lines.append("|---|---|---|---|---|---|---|")
        cumulative_cost = 0
        cumulative_uplift = 0
        excluded_cost = 0
        excluded_labels = []
        for i, p in enumerate(roi_plan, 1):
            qty_str = f"{p['수량']:.1f} {p['단위']}" if p.get("수량") else "-"
            cost_str = f"{p['Max_Cost']:,}" if p.get("Max_Cost") else "산정불가"
            cur = p["현재점수"]
            new = p["보강후점수"]
            delta = p["점수상승"]
            eff = p.get("효율_점수당억", 0)
            if delta > 0:
                cumulative_cost += p.get("Max_Cost", 0)
                cumulative_uplift += delta
                mark = ""
            else:
                # 점수표에 반영되지 않는 항목(예: 쿨루프)은 누적 총액에서 제외
                excluded_cost += p.get("Max_Cost", 0)
                excluded_labels.append(p["label"])
                mark = " ※"
            lines.append(
                f"| {i} | {p['label']}{mark} | {qty_str} | {cost_str} | "
                f"{cur} → {new} | +{delta} | {eff:.2f} |"
            )

        lines.append("")
        lines.append(f"**누적 보강 비용(점수 기여 항목)**: {cumulative_cost:,}원 "
                     f"({cumulative_cost/100_000_000:.2f}억)")
        lines.append(f"**누적 점수 상승**: +{cumulative_uplift}점 "
                     f"({score['total_score']}점 → {score['total_score']+cumulative_uplift}점)")
        if excluded_labels:
            lines.append(
                f"※ {', '.join(excluded_labels)}: 점수표 미반영(에너지 보조수단)으로 "
                f"위 총액에서 제외 (별도 {excluded_cost:,}원)"
            )
        lines.append("")
        lines.append("*효율 = 점수상승 ÷ (보강비용/억). 높을수록 가성비 좋음.*")

    lines.append("")
    lines.append("---")
    lines.append("*본 진단은 자동 산출 결과이며, 실제 사업 신청 시에는 그린리모델링 창조센터(1588-8788)의 공식 컨설팅이 필요합니다.*")

    return "\n".join(lines)


# ====================================================================
# 통합 진입점
# ====================================================================

def diagnose_from_json(
    json_path: str,
    with_roi: bool = False,
    duration_months: int = 8,
) -> dict:
    """
    JSON 파일 경로 -> 진단 결과 통합 반환.

    Args:
        json_path: Dynamo 추출 BIM JSON 경로
        with_roi: True면 ROI 연계 보강 계획 산출 (단가DB 로드 필요, 약 1~2초 소요)
        duration_months: ROI 산정 시 예상 공사 기간 (개월)

    Returns:
        {
          "gr_mapping": ...,
          "score": ...,
          "report": ... (markdown),
          "roi_plan": [...]  # with_roi=True일 때만
        }
    """
    bim = parse_bim_json(json_path)
    gr_mapping = map_to_gr_elements(bim)
    score = score_compliance(gr_mapping, bim)

    roi_plan = None
    if with_roi:
        roi_plan = build_reinforcement_plan(
            gr_mapping, score, bim,
            duration_months=duration_months,
        )

    report = generate_diagnosis_report(gr_mapping, score, bim, roi_plan=roi_plan)

    return {
        "bim_data": bim,
        "gr_mapping": gr_mapping,
        "score": score,
        "report": report,
        "roi_plan": roi_plan,
    }


# ====================================================================
# Phase 6 — ROI 연계 보강 계획
# ====================================================================
"""
진단 결과의 미적용/부분적용 항목에 대해 ROI 계산기를 호출하여
예상 보강 비용 + 점수 상승 효과를 자동 산정한다.

데이터 흐름:
    gr_mapping (미적용 면적/수량)
        → GR 항목별 보강 시나리오 정의 (자재 카테고리, 두께, 단위)
        → roi_calculator.lookup_material_price + CONSTRUCTION_FACTOR
        → 직접공사비 산정 → apply_indirect_cost → Max Cost (부가세 포함)
        → 동시에 점수 상승 추정 (_score_by_ratio 룰 재적용)
        → 효율 = Δ점수 ÷ (Δ비용/억) → 우선순위 정렬

설비/전기 항목(EHP, ERV, LED, PV, BEMS, 보일러)은 단가DB에 없을 수 있어
ESTIMATED_UNIT_COSTS 추정 단가를 사용. 실시설계 시 갱신 필요.
"""


# --------------------------------------------------------------------
# 단가DB에 등록되지 않은 설비/전기 항목의 추정 단가 (졸업설계 보수 추정)
# 출처: KEPCO·LH 표준 견적 + 시중 견적 평균
# 실제 사업 시엔 견적사·시공사 의견 반영 필수
# --------------------------------------------------------------------
ESTIMATED_UNIT_COSTS = {
    "EHP_실외기_대당": 3_000_000,    # 10kW급 EHP 1대 교체비 (자재+시공)
    "ERV_대당": 5_000_000,            # 폐열회수형 환기장치 1대 (자재+시공+덕트)
    "보일러_고효율_일식": 8_000_000,  # 콘덴싱 보일러 1식 (소형 건물 기준)
    "LED_등기구_개당": 50_000,         # 평균 등기구 교체 단가
    "PV_kW당": 1_500_000,             # 태양광 1kW 설치비 (모듈+인버터+공사)
    "BEMS_일식": 30_000_000,          # 1,000~2,000㎡ 건물 BEMS 일식
    "쿨루프_m2": 30_000,              # 차열도료 ㎡당 (자재+시공)
}


# --------------------------------------------------------------------
# 단가DB 캐시 (price_db 인자가 None일 때 첫 호출에 로드)
# --------------------------------------------------------------------
_PRICE_DB_CACHE = None
_INDIRECT_MATRIX_CACHE = None


def _get_price_db():
    """ROI calculator의 단가DB 캐시 로딩."""
    global _PRICE_DB_CACHE
    if _PRICE_DB_CACHE is None:
        from core.roi_calculator import load_price_db
        _PRICE_DB_CACHE = load_price_db()
    return _PRICE_DB_CACHE


def _get_indirect_matrix():
    """ROI calculator의 간접공사비 매트릭스 캐시 로딩."""
    global _INDIRECT_MATRIX_CACHE
    if _INDIRECT_MATRIX_CACHE is None:
        from core.roi_calculator import load_indirect_cost_matrix
        _INDIRECT_MATRIX_CACHE = load_indirect_cost_matrix()
    return _INDIRECT_MATRIX_CACHE


def _delta_score(current_ratio: float, target_ratio: float, breakpoints: list) -> tuple:
    """비율 변화 → (현재 점수, 보강 후 점수, 상승치)."""
    cur = _score_by_ratio(current_ratio, breakpoints)
    new = _score_by_ratio(target_ratio, breakpoints)
    return cur, new, max(0, new - cur)


def _envelope_cost(
    quantity_m2: float,
    gr_category: str,
    min_thickness_mm: Optional[float],
    construction_factor_key: str,
) -> Optional[dict]:
    """
    외피 항목 (외벽·지붕·바닥·창·문) 직접공사비 산정.
    ROI calculator의 lookup_material_price + CONSTRUCTION_FACTOR 활용.
    """
    if quantity_m2 <= 0:
        return None
    try:
        from core.roi_calculator import lookup_material_price, CONSTRUCTION_FACTOR
        mat = lookup_material_price(
            _get_price_db(),
            gr_category=gr_category,
            min_thickness_mm=min_thickness_mm,
        )
        factor = CONSTRUCTION_FACTOR.get(construction_factor_key, 1.0)
        unit_price = int(mat["단가"] * factor)
        direct = int(quantity_m2 * unit_price)
        return {
            "자재": f"{mat['품명']} {mat['규격']}",
            "자재단가": int(mat["단가"]),
            "시공계수": factor,
            "종합단가": unit_price,
            "수량": quantity_m2,
            "단위": "㎡",
            "직접공사비": direct,
        }
    except (ValueError, FileNotFoundError, ImportError) as e:
        return {
            "자재": "단가DB 조회 실패",
            "수량": quantity_m2,
            "단위": "㎡",
            "직접공사비": 0,
            "_error": str(e),
        }


def _equipment_cost(
    quantity: float,
    unit_cost_key: str,
    unit_label: str,
) -> dict:
    """설비/전기 항목 직접공사비 산정 (ESTIMATED_UNIT_COSTS 기반)."""
    unit_price = ESTIMATED_UNIT_COSTS[unit_cost_key]
    direct = int(quantity * unit_price)
    return {
        "자재": f"추정단가 {unit_price:,}원/{unit_label}",
        "수량": quantity,
        "단위": unit_label,
        "종합단가": unit_price,
        "직접공사비": direct,
    }


def _apply_indirect(direct_cost: float, duration_months: int = 8) -> dict:
    """ROI calculator의 apply_indirect_cost 위임."""
    if direct_cost <= 0:
        return {
            "직접공사비": 0,
            "간접노무비": 0,
            "기타경비": 0,
            "일반관리비": 0,
            "이윤": 0,
            "공급가액": 0,
            "부가세": 0,
            "Max_Cost": 0,
        }
    try:
        from core.roi_calculator import apply_indirect_cost
        return apply_indirect_cost(
            direct_cost,
            project_duration_months=duration_months,
            matrix=_get_indirect_matrix(),
        )
    except Exception:
        # 간접비 매트릭스 로드 실패 시 단순 보정 (×1.4)
        max_cost = int(direct_cost * 1.4)
        return {
            "직접공사비": int(direct_cost),
            "_fallback": True,
            "Max_Cost": max_cost,
        }


# ====================================================================
# 항목별 보강 시나리오 산정 함수들
# 각 함수는 단일 GR 항목에 대해 {label, quantity, cost_info, score_delta} 반환
# ====================================================================

def _plan_wall(gr_mapping: dict, bim: dict, duration_months: int) -> Optional[dict]:
    """3_외벽단열보강 — 미적용 면적을 전부 보강 가정."""
    info = gr_mapping["3_외벽단열보강"]
    qty = info.get("미적용_m2", 0)
    if qty <= 0:
        return None

    cost_info = _envelope_cost(qty, "GR_단열_PF", 130, "외벽_외단열")
    indirect = _apply_indirect(cost_info["직접공사비"], duration_months)
    cur, new, delta = _delta_score(
        info["적용비율"], 1.0, WALL_INSULATION_BREAKPOINTS,
    )

    return {
        "key": "3_외벽단열보강",
        "label": "외벽 단열보강",
        "수량": qty,
        "단위": "㎡",
        "자재": cost_info["자재"],
        "직접공사비": cost_info["직접공사비"],
        "Max_Cost": indirect["Max_Cost"],
        "현재점수": cur,
        "보강후점수": new,
        "점수상승": delta,
        "점수만점": 10,
    }


def _plan_roof_insulation(gr_mapping: dict, bim: dict, duration_months: int) -> Optional[dict]:
    """지붕 단열 (gr_mapping엔 별도 없음, bim.roofs 직접 사용)."""
    roofs = bim.get("roofs", [])
    total = sum(r["area"] for r in roofs)
    insulated = sum(r["area"] for r in roofs if r.get("insulated"))
    qty = total - insulated
    if qty <= 0 or total <= 0:
        return None

    cost_info = _envelope_cost(qty, "GR_단열_PF", 150, "지붕_단열")
    indirect = _apply_indirect(cost_info["직접공사비"], duration_months)
    current_ratio = insulated / total
    cur, new, delta = _delta_score(
        current_ratio, 1.0, ROOF_INSULATION_BREAKPOINTS,
    )

    return {
        "key": "_지붕단열",
        "label": "지붕 단열보강",
        "수량": qty,
        "단위": "㎡",
        "자재": cost_info["자재"],
        "직접공사비": cost_info["직접공사비"],
        "Max_Cost": indirect["Max_Cost"],
        "현재점수": cur,
        "보강후점수": new,
        "점수상승": delta,
        "점수만점": 7,
    }


def _plan_floor(gr_mapping: dict, bim: dict, duration_months: int) -> Optional[dict]:
    """4_바닥단열난방 — 미적용 면적에 단열 보강."""
    info = gr_mapping["4_바닥단열난방"]
    qty = info.get("미적용_m2", 0)
    if qty <= 0:
        return None

    cost_info = _envelope_cost(qty, "GR_단열_PF", 100, "바닥_단열")
    indirect = _apply_indirect(cost_info["직접공사비"], duration_months)
    cur, new, delta = _delta_score(
        info["적용비율"], 1.0, FLOOR_INSULATION_BREAKPOINTS,
    )

    return {
        "key": "4_바닥단열난방",
        "label": "바닥 단열·난방 보강",
        "수량": qty,
        "단위": "㎡",
        "자재": cost_info["자재"],
        "직접공사비": cost_info["직접공사비"],
        "Max_Cost": indirect["Max_Cost"],
        "현재점수": cur,
        "보강후점수": new,
        "점수상승": delta,
        "점수만점": 3,
    }


def _plan_window(gr_mapping: dict, bim: dict, duration_months: int) -> Optional[dict]:
    """1_고성능창호 — 미적용 면적 교체."""
    info = gr_mapping["1_고성능창호"]
    qty = info.get("미적용_m2", 0)
    if qty <= 0:
        return None

    cost_info = _envelope_cost(qty, "GR_창호_복층유리", 24, "창호")
    indirect = _apply_indirect(cost_info["직접공사비"], duration_months)
    cur, new, delta = _delta_score(
        info["적용비율"], 1.0, WINDOW_BREAKPOINTS,
    )

    return {
        "key": "1_고성능창호",
        "label": "고성능 창호 교체",
        "수량": qty,
        "단위": "㎡",
        "자재": cost_info["자재"],
        "직접공사비": cost_info["직접공사비"],
        "Max_Cost": indirect["Max_Cost"],
        "현재점수": cur,
        "보강후점수": new,
        "점수상승": delta,
        "점수만점": 10,
    }


def _plan_door(gr_mapping: dict, bim: dict, duration_months: int) -> Optional[dict]:
    """2_고기밀성단열문 — 미적용 면적 교체."""
    info = gr_mapping["2_고기밀성단열문"]
    qty = info.get("미적용_m2", 0)
    if qty <= 0:
        return None

    # 07 단가DB는 'GR_문_금속문' 카테고리로 등록되어 있음
    cost_info = _envelope_cost(qty, "GR_문_금속문", None, "단열문")
    indirect = _apply_indirect(cost_info["직접공사비"], duration_months)
    cur, new, delta = _delta_score(
        info["적용비율"], 1.0, DOOR_BREAKPOINTS,
    )

    return {
        "key": "2_고기밀성단열문",
        "label": "고기밀성 단열문 교체",
        "수량": qty,
        "단위": "㎡",
        "자재": cost_info["자재"],
        "직접공사비": cost_info["직접공사비"],
        "Max_Cost": indirect["Max_Cost"],
        "현재점수": cur,
        "보강후점수": new,
        "점수상승": delta,
        "점수만점": 3,
    }


def _plan_cool_roof(gr_mapping: dict, bim: dict, duration_months: int) -> Optional[dict]:
    """5_쿨루프 — 미적용 지붕 면적에 차열도료 도포 (정량평가표엔 가점 0)."""
    info = gr_mapping["5_쿨루프"]
    qty = info.get("미적용_m2", 0)
    if qty <= 0:
        return None

    cost = _equipment_cost(qty, "쿨루프_m2", "㎡")
    indirect = _apply_indirect(cost["직접공사비"], duration_months)

    # 쿨루프는 01 정량평가표엔 별도 점수 없음(가점)
    return {
        "key": "5_쿨루프",
        "label": "쿨루프 (차열도료)",
        "수량": qty,
        "단위": "㎡",
        "자재": cost["자재"],
        "직접공사비": cost["직접공사비"],
        "Max_Cost": indirect["Max_Cost"],
        "현재점수": 0,
        "보강후점수": 0,
        "점수상승": 0,
        "점수만점": 0,
        "_note": "정량평가 점수 없음 (가점 사항)",
    }


def _plan_ventilation(gr_mapping: dict, bim: dict, duration_months: int) -> Optional[dict]:
    """6_폐열회수환기 — 미커버 면적에 ERV 추가 설치."""
    info = gr_mapping["6_폐열회수환기"]
    if info["status"] == "적용":
        return None

    total = bim.get("total_area_m2", 0)
    covered = info.get("기적용_m2", 0)
    missing_area = max(0, total - covered)
    if missing_area <= 0:
        return None

    # ERV 1대당 100㎡ 커버 가정 (대략)
    units_needed = max(1, round(missing_area / 100))
    cost = _equipment_cost(units_needed, "ERV_대당", "대")
    indirect = _apply_indirect(cost["직접공사비"], duration_months)

    new_ratio = (covered + units_needed * 100) / total if total > 0 else 0
    new_ratio = min(new_ratio, 1.0)
    cur, new, delta = _delta_score(
        info["적용비율"], new_ratio, VENTILATION_BREAKPOINTS,
    )

    return {
        "key": "6_폐열회수환기",
        "label": f"폐열회수환기장치(ERV) {units_needed}대 추가",
        "수량": units_needed,
        "단위": "대",
        "자재": cost["자재"],
        "직접공사비": cost["직접공사비"],
        "Max_Cost": indirect["Max_Cost"],
        "현재점수": cur,
        "보강후점수": new,
        "점수상승": delta,
        "점수만점": 5,
    }


def _plan_hvac(gr_mapping: dict, bim: dict, duration_months: int) -> Optional[dict]:
    """7_고효율냉난방 — 기존 EHP 전체 교체."""
    info = gr_mapping["7_고효율냉난방"]
    if info["status"] == "적용":
        return None

    hvac = bim.get("hvac", {})
    heating = hvac.get("heating", {}) or {}
    cooling = hvac.get("cooling", {}) or {}
    # 가장 많은 대수 (보통 EHP는 냉난방 공용)
    units = max(
        heating.get("units", 0) - heating.get("replaced_units", 0),
        cooling.get("units", 0) - cooling.get("replaced_units", 0),
    )
    if units <= 0:
        return None

    cost = _equipment_cost(units, "EHP_실외기_대당", "대")
    indirect = _apply_indirect(cost["직접공사비"], duration_months)

    # 냉방 5 + 난방 5 = 10점 만점 가정 (전체 교체)
    delta = 10  # 0% → 100% breakpoint = 5+5

    return {
        "key": "7_고효율냉난방",
        "label": f"고효율 EHP {units}대 교체",
        "수량": units,
        "단위": "대",
        "자재": cost["자재"],
        "직접공사비": cost["직접공사비"],
        "Max_Cost": indirect["Max_Cost"],
        "현재점수": 0,
        "보강후점수": delta,
        "점수상승": delta,
        "점수만점": 10,
    }


def _plan_boiler(gr_mapping: dict, bim: dict, duration_months: int) -> Optional[dict]:
    """8_고효율보일러 — 보일러 미적용 시 1식 신규."""
    info = gr_mapping["8_고효율보일러"]
    if info["status"] == "적용":
        return None
    # 보일러 미설치 건물은 굳이 신규 안 함 (EHP/난방으로 충당 가능)
    # 단, 급탕 점수(5점)에 기여하므로 옵션으로 표시
    cost = _equipment_cost(1, "보일러_고효율_일식", "식")
    indirect = _apply_indirect(cost["직접공사비"], duration_months)

    return {
        "key": "8_고효율보일러",
        "label": "고효율 콘덴싱 보일러 1식 (급탕)",
        "수량": 1,
        "단위": "식",
        "자재": cost["자재"],
        "직접공사비": cost["직접공사비"],
        "Max_Cost": indirect["Max_Cost"],
        "현재점수": 0,
        "보강후점수": 5,   # 급탕 항목 5점
        "점수상승": 5,
        "점수만점": 5,
        "_note": "선택 사항 (EHP로 난방 충당 시 미필요)",
    }


def _plan_led(gr_mapping: dict, bim: dict, duration_months: int) -> Optional[dict]:
    """9_고효율LED — 미적용 등기구 전부 교체."""
    info = gr_mapping["9_고효율LED"]
    led = info["LED_개수"]
    total = info["전체_개수"]
    qty = total - led
    if qty <= 0:
        return None

    cost = _equipment_cost(qty, "LED_등기구_개당", "개")
    indirect = _apply_indirect(cost["직접공사비"], duration_months)
    # LED: 100% 적용 시 2점 가산
    cur = 2 if (led / total >= 1.0) else 0
    new = 2
    delta = new - cur

    return {
        "key": "9_고효율LED",
        "label": f"고효율 LED {qty}개 교체",
        "수량": qty,
        "단위": "개",
        "자재": cost["자재"],
        "직접공사비": cost["직접공사비"],
        "Max_Cost": indirect["Max_Cost"],
        "현재점수": cur,
        "보강후점수": new,
        "점수상승": delta,
        "점수만점": 2,
    }


def _plan_pv(gr_mapping: dict, bim: dict, duration_months: int) -> Optional[dict]:
    """10_신재생태양광 — 자립률 20% 목표 추가 설치."""
    info = gr_mapping["10_신재생태양광"]
    current_kw = sum(p.get("capacity_kw", 0) for p in bim.get("pv_panels", []))
    building_area = bim.get("total_area_m2", 1)
    annual_demand = building_area * 100   # kWh/년 어림

    # 자립률 20% 도달 위한 추가 용량
    target_autonomy = 0.20
    target_kw = (annual_demand * target_autonomy) / 1300
    add_kw = max(0, target_kw - current_kw)
    if add_kw <= 0.1:
        return None

    cost = _equipment_cost(add_kw, "PV_kW당", "kW")
    indirect = _apply_indirect(cost["직접공사비"], duration_months)
    cur, new, delta = _delta_score(
        info["자립률_추정"], target_autonomy, RENEWABLE_BREAKPOINTS,
    )

    return {
        "key": "10_신재생태양광",
        "label": f"태양광 +{add_kw:.1f}kW (자립률 20% 도달)",
        "수량": round(add_kw, 1),
        "단위": "kW",
        "자재": cost["자재"],
        "직접공사비": cost["직접공사비"],
        "Max_Cost": indirect["Max_Cost"],
        "현재점수": cur,
        "보강후점수": new,
        "점수상승": delta,
        "점수만점": 5,
    }


def _plan_bems(gr_mapping: dict, bim: dict, duration_months: int) -> Optional[dict]:
    """11_BEMS — 미설치 시 1식 신규."""
    info = gr_mapping["11_BEMS"]
    if info["status"] == "적용":
        return None

    cost = _equipment_cost(1, "BEMS_일식", "식")
    indirect = _apply_indirect(cost["직접공사비"], duration_months)

    return {
        "key": "11_BEMS",
        "label": "BEMS / 원격검침 1식",
        "수량": 1,
        "단위": "식",
        "자재": cost["자재"],
        "직접공사비": cost["직접공사비"],
        "Max_Cost": indirect["Max_Cost"],
        "현재점수": 0,
        "보강후점수": 2,
        "점수상승": 2,
        "점수만점": 2,
    }


# 항목별 보강 함수 레지스트리
_REINFORCEMENT_FUNCS = [
    _plan_wall,
    _plan_roof_insulation,
    _plan_floor,
    _plan_window,
    _plan_door,
    _plan_cool_roof,
    _plan_ventilation,
    _plan_hvac,
    _plan_boiler,
    _plan_led,
    _plan_pv,
    _plan_bems,
]


# ====================================================================
# 통합 보강 계획 빌더
# ====================================================================

def build_reinforcement_plan(
    gr_mapping: dict,
    score: dict,
    bim: dict,
    duration_months: int = 8,
) -> list:
    """
    11개 GR 항목 전체를 순회하며 미적용/부분적용 항목에 대해
    예상 보강 비용 + 점수 상승 산정.

    Returns:
        보강 계획 list, 효율(점수/억) 내림차순 정렬.
        각 element: {
            key, label, 수량, 단위, 자재,
            직접공사비, Max_Cost,
            현재점수, 보강후점수, 점수상승, 점수만점,
            효율_점수당억,
        }
    """
    plans = []
    for func in _REINFORCEMENT_FUNCS:
        try:
            plan = func(gr_mapping, bim, duration_months)
        except Exception as e:
            # 한 항목이 실패해도 전체 진단은 계속
            plan = None
            print(f"[WARN] {func.__name__} 실패: {type(e).__name__}: {e}")
        if plan is not None:
            # 효율 = Δ점수 ÷ (Max_Cost / 1억)
            max_cost_eok = plan.get("Max_Cost", 0) / 100_000_000
            if max_cost_eok > 0:
                plan["효율_점수당억"] = plan["점수상승"] / max_cost_eok
            else:
                plan["효율_점수당억"] = 0.0
            plans.append(plan)

    # 효율 내림차순 (가성비 좋은 순)
    plans.sort(key=lambda p: p["효율_점수당억"], reverse=True)
    return plans


# ====================================================================
# Phase 7 — 보강 조합 최적화 (예산/등급 목표 기반)
# ====================================================================
"""
build_reinforcement_plan 결과(전체 11개 항목)에서 사용자 제약을 만족하는
보강 조합을 자동 선택한다.

전략:
    A. 예산 상한 모드 (optimize_within_budget):
       - 그리디: 효율(점수/억) 내림차순 누적 선택
       - 누적 Max_Cost ≤ 예산이면 채택, 초과 시 skip
       - 보강 후 누적 점수 + 등급 산출

    B. 목표 등급 모드 (optimize_for_target_grade):
       - 효율 내림차순으로 누적 선택
       - 누적 점수가 목표 점수 도달하면 종료
       - 최소 비용 조합 + 도달 가능 여부 반환

졸업설계 단계엔 그리디로 충분하다. 0/1 knapsack DP는 항목 수가 늘어나면 도입.
"""


# 등급 -> 최소 점수 매핑 (score_compliance와 동일 룰)
GRADE_THRESHOLDS = {
    "A+": 85,
    "A":  75,
    "B":  65,
    "C":  50,
    "D":  0,
}


def _score_to_grade(score: int) -> str:
    """점수 -> 등급 (score_compliance의 룰과 동일)."""
    if score >= 85:
        return "A+"
    elif score >= 75:
        return "A"
    elif score >= 65:
        return "B"
    elif score >= 50:
        return "C"
    return "D"


def optimize_within_budget(
    plan: list,
    budget_won: int,
    current_score: int,
) -> dict:
    """
    예산 상한 내에서 점수를 최대화하는 보강 조합 그리디 선택.

    Args:
        plan: build_reinforcement_plan() 결과 (효율 내림차순 정렬됨)
        budget_won: 사용자 지정 예산 (원 단위, Max_Cost 기준)
        current_score: 현재 진단 총점

    Returns:
        {
            "selected": [...],         # 선택된 보강 항목들
            "skipped":  [...],         # 예산 초과로 제외된 항목들
            "사용예산": int,
            "잔여예산": int,
            "누적점수상승": int,
            "예상총점": int,
            "현재등급": str,
            "예상등급": str,
        }
    """
    if budget_won <= 0:
        return {
            "selected": [], "skipped": list(plan),
            "사용예산": 0, "잔여예산": 0,
            "누적점수상승": 0,
            "예상총점": current_score,
            "현재등급": _score_to_grade(current_score),
            "예상등급": _score_to_grade(current_score),
        }

    selected = []
    skipped = []
    used = 0

    for p in plan:
        cost = p.get("Max_Cost", 0)
        if cost <= 0:
            # 비용 산정 실패한 항목 skip
            skipped.append({**p, "_skip_reason": "비용 산정 실패"})
            continue
        if used + cost <= budget_won:
            selected.append(p)
            used += cost
        else:
            skipped.append({**p, "_skip_reason": f"예산 초과 (잔여 {budget_won-used:,}원)"})

    uplift = sum(p["점수상승"] for p in selected)
    new_score = current_score + uplift

    return {
        "selected": selected,
        "skipped": skipped,
        "사용예산": used,
        "잔여예산": budget_won - used,
        "누적점수상승": uplift,
        "예상총점": new_score,
        "현재등급": _score_to_grade(current_score),
        "예상등급": _score_to_grade(new_score),
    }


def optimize_for_target_grade(
    plan: list,
    target_grade: str,
    current_score: int,
) -> dict:
    """
    목표 등급 달성에 필요한 최소 비용 조합 (그리디).

    Args:
        plan: build_reinforcement_plan() 결과 (효율 내림차순)
        target_grade: "A+", "A", "B", "C" 중 하나
        current_score: 현재 진단 총점

    Returns:
        {
            "achievable": bool,        # 모든 보강 합쳐도 목표 미달이면 False
            "selected": [...],
            "필요비용": int,
            "목표점수": int,
            "달성점수": int,
            "현재등급": str,
            "목표등급": str,
        }
    """
    if target_grade not in GRADE_THRESHOLDS:
        raise ValueError(
            f"target_grade는 {list(GRADE_THRESHOLDS.keys())} 중 하나여야 함: {target_grade}"
        )

    target_score = GRADE_THRESHOLDS[target_grade]
    deficit = target_score - current_score

    if deficit <= 0:
        return {
            "achievable": True,
            "selected": [],
            "필요비용": 0,
            "목표점수": target_score,
            "달성점수": current_score,
            "현재등급": _score_to_grade(current_score),
            "목표등급": target_grade,
            "_note": "이미 목표 등급 달성 상태",
        }

    selected = []
    accumulated_uplift = 0
    accumulated_cost = 0

    for p in plan:
        if p["점수상승"] <= 0:
            continue
        if p.get("Max_Cost", 0) <= 0:
            continue
        selected.append(p)
        accumulated_uplift += p["점수상승"]
        accumulated_cost += p["Max_Cost"]
        if accumulated_uplift >= deficit:
            break

    achieved_score = current_score + accumulated_uplift
    achievable = achieved_score >= target_score

    return {
        "achievable": achievable,
        "selected": selected,
        "필요비용": accumulated_cost,
        "목표점수": target_score,
        "달성점수": achieved_score,
        "현재등급": _score_to_grade(current_score),
        "목표등급": target_grade,
    }


# ====================================================================
# 최적화 결과 리포트
# ====================================================================

def format_optimization_report(opt_result: dict, mode: str = "budget") -> str:
    """
    optimize_within_budget 또는 optimize_for_target_grade 결과를
    마크다운 리포트로 포맷.

    Args:
        opt_result: 최적화 함수 반환 dict
        mode: "budget" 또는 "target"
    """
    lines = []

    if mode == "budget":
        lines.append("## 예산 상한 보강 조합")
        lines.append("")
        lines.append(
            f"**사용 예산**: {opt_result['사용예산']:,}원 "
            f"({opt_result['사용예산']/1e8:.2f}억)  "
        )
        lines.append(
            f"**잔여 예산**: {opt_result['잔여예산']:,}원  "
        )
        lines.append(
            f"**점수 변화**: {opt_result['예상총점']-opt_result['누적점수상승']}점 → "
            f"{opt_result['예상총점']}점 (+{opt_result['누적점수상승']})  "
        )
        lines.append(
            f"**등급 변화**: {opt_result['현재등급']} → {opt_result['예상등급']}  "
        )
    elif mode == "target":
        if opt_result["achievable"]:
            lines.append(f"## 목표 등급 {opt_result['목표등급']} 달성 보강 조합")
        else:
            lines.append(f"## 목표 등급 {opt_result['목표등급']} 달성 불가")
            lines.append("")
            lines.append(
                f"⚠️ 11개 항목 전체 보강 시에도 목표 점수 "
                f"{opt_result['목표점수']}점에 도달 불가 "
                f"(최대 달성 {opt_result['달성점수']}점)"
            )
        lines.append("")
        lines.append(
            f"**필요 비용**: {opt_result['필요비용']:,}원 "
            f"({opt_result['필요비용']/1e8:.2f}억)  "
        )
        lines.append(
            f"**점수 변화**: {opt_result['달성점수']-sum(p['점수상승'] for p in opt_result['selected'])}점 → "
            f"{opt_result['달성점수']}점  "
        )
        lines.append(
            f"**등급 변화**: {opt_result['현재등급']} → "
            f"{_score_to_grade(opt_result['달성점수'])}"
        )

    lines.append("")
    selected = opt_result.get("selected", [])
    if not selected:
        lines.append("*선택된 보강 항목이 없습니다.*")
        return "\n".join(lines)

    lines.append("### 채택 항목")
    lines.append("")
    lines.append("| 순위 | 항목 | 수량 | 비용(원) | Δ점수 | 효율 |")
    lines.append("|---|---|---|---|---|---|")
    for i, p in enumerate(selected, 1):
        qty_str = f"{p['수량']:.1f} {p['단위']}"
        lines.append(
            f"| {i} | {p['label']} | {qty_str} | {p['Max_Cost']:,} | "
            f"+{p['점수상승']} | {p['효율_점수당억']:.2f} |"
        )

    # budget 모드일 때 skipped 항목도 출력
    if mode == "budget":
        skipped = opt_result.get("skipped", [])
        skipped_with_cost = [s for s in skipped if s.get("Max_Cost", 0) > 0]
        if skipped_with_cost:
            lines.append("")
            lines.append("### 예산 초과로 제외된 항목")
            lines.append("")
            for s in skipped_with_cost:
                lines.append(
                    f"- {s['label']} ({s['Max_Cost']:,}원, +{s['점수상승']}점) "
                    f"— {s.get('_skip_reason', '')}"
                )

    return "\n".join(lines)
    return "\n".join(lines)
