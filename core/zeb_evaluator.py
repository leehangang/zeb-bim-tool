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
# 주거용 판정 (ZEB 인증기준 별표2 **주5**)
#   "주거용 = 단독주택 + 공동주택(**기숙사 제외**)"  → 그 외는 전부 비주거용
#
# 🔴 2026-07 정정 — 기숙사가 여기 들어 있었다(주거로 분류). 별표2 주5는 기숙사를
#    명시적으로 **제외**하므로 기숙사는 **비주거용**이다. 주거 기준이 더 엄격해서
#    (5등급 90 vs 130) 기숙사를 주거로 재면 등급이 과소평가된다 —
#    예: net 100 → 주거로 재면 '인증 미달', 비주거로 재면 'ZEB 5등급'.
#    근거: 팀 학습문서 v4 §3-5 / 경계 케이스 "기숙사 주거 아님 → 비주거용으로 분류"
#
# ⚠️ 오피스텔도 뺐다 — 건축법상 **업무시설**이라 별표2 주5의 '공동주택'이 아니다.
#    (주택법상 준주택이지만 ZEB 인증의 용도 구분은 건축법을 따른다)
RESIDENTIAL_USES = {"공동주택", "주택", "단독주택", "아파트", "연립주택", "다세대주택"}


def get_base_energy(building_use: str = "어린이집") -> float:
    return BASE_ENERGY_BY_USE.get(building_use, BASE_ENERGY_BY_USE["기타"])


def detect_building_use(bim: dict) -> str:
    desc = (bim.get("_meta", {}).get("description", "") + " "
            + bim.get("_meta", {}).get("extracted_for", ""))
    for use in BASE_ENERGY_BY_USE:
        if use in desc:
            return use
    return "어린이집"


def combine_reductions(ratios: list, mode: str = "multiplicative") -> float:
    """
    개별 요소 절감률들을 하나의 총 절감률로 결합한다.

    mode="multiplicative" — 1 − Π(1−rᵢ).  **기본값.** 각 요소가 '남은' 에너지를 줄인다고 본다.
                            상한이 100%로 수렴하고 적용 순서에 무관하다.
    mode="sum"            — 단순합산 Σrᵢ.  ⚠️ 물리적으로 성립하지 않는다:
                            10% 요소 11개면 110%가 되어 에너지가 음수가 된다.
                            (과거 기본값 — 비교 표시용으로만 남긴다)

    ⚠️ multiplicative도 근사다. 두 방식의 참값은 요소들이 같은 부하를 건드리는지에 달렸다:
       · 겹치는 경우(외벽단열 ↔ 고효율보일러: 단열하면 보일러가 줄일 난방부하가 이미 줄어듦)
         → 단순합산은 과대. multiplicative가 가깝다.
       · 겹치지 않는 경우(LED(조명) ↔ 외벽단열(난방)) → 실제로는 거의 가산적이라
         multiplicative가 다소 **과소**추정한다.
       우리 11개 요소는 외피·설비·조명·환기·제어가 섞여 있어 참값은 두 값 사이에 있다.
       그럼에도 multiplicative를 기본으로 삼는 이유:
         (1) 단순합산은 100%를 넘길 수 있어 **정의상 틀렸다** — 방어 불가.
         (2) 아래 실측 근거가 '보수적으로 잡는 쪽'을 지지한다.
       정확한 값은 ECO2/EnergyPlus 정식 해석으로만 얻는다.

       실증 근거: KEEI 기본연구보고서 2025-14 (보도자료 2026-06-22) — GR 시행 공공건축물
       522동(어린이집 358동 = 68.6%) 실측 결과 연간 20.4 kWh/㎡ 절감으로,
       엔지니어링 사전 예측 33 kWh/㎡의 약 60% 수준. 설계단계 예측에 약 1.6배
       과대추정 편의가 실측으로 확인됐다.
    """
    if mode == "sum":
        return float(sum(ratios))
    if mode != "multiplicative":
        raise ValueError(f"알 수 없는 결합 방식: {mode} (sum|multiplicative)")
    remaining = 1.0
    for r in ratios:
        remaining *= (1.0 - float(r))
    return 1.0 - remaining


def calculate_reduction_ratio(gr_mapping: dict, combine: str = "multiplicative") -> dict:
    """
    11개 GR 요소의 적용 상태 → 총 에너지 절감률.

    total_reduction_ratio = combine 방식으로 결합한 값 (기본 multiplicative).
    비교용으로 두 방식 값을 모두 반환해 모드 5(근거·출처)에서 격차를 공개한다.

    이력 (2026-07): 기본값이 'sum'이었으나 단순합산은 100%를 넘길 수 있어 정의상 틀렸다.
      대상 건물 기준 sum 67.0%(→4등급) vs multiplicative 50.5%(→5등급)로 등급 결론이 바뀐다.
      "숫자를 지키려고 틀린 산식을 남겨두지 않는다"는 판단으로 multiplicative로 전환.
    """
    breakdown = {}
    actuals = []

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
        actuals.append(actual)

        breakdown[key] = {
            "이론최대_pct": round(ratio_max * 100, 1),
            "적용도_pct": round(applied * 100, 1),
            "실제절감_pct": round(actual * 100, 2),
        }

    total_sum = combine_reductions(actuals, "sum")
    total_mult = combine_reductions(actuals, "multiplicative")
    total = combine_reductions(actuals, combine)

    return {
        "total_reduction_ratio": round(total, 4),
        "total_reduction_pct": round(total * 100, 1),
        # 비교용 — 화면에서 두 방식의 격차를 그대로 보여준다
        "total_reduction_ratio_multiplicative": round(total_mult, 4),
        "total_reduction_pct_multiplicative": round(total_mult * 100, 1),
        "total_reduction_ratio_sum": round(total_sum, 4),
        "total_reduction_pct_sum": round(total_sum * 100, 1),
        "_결합방식": combine,
        "breakdown": breakdown,
    }


def offsite_correction_factor(onsite_autonomy_pct: float) -> float:
    """
    대지 **외** 신재생 생산량에 곱하는 보정계수 (ZEB 인증기준 별표1).

    대지 내 자립률이 낮을수록 대지 외 생산을 덜 인정한다:
        대지 내 자립률 <10% → 0.7 / 10~15% → 0.8 / 15~20% → 0.9 / ≥20% → 1.0

    ⚠️ 인자는 **대지 내 자립률**이지 전체 자립률이 아니다.
       별표1 제2호 나목 3) ※ — "대지 내 에너지자립률 산정 시 … 대지 내 순생산량만을 고려한다."

    2026-07-16 공동고시 별표1 원문 확보로 확정 (data/policy_docs/19_ZEB_인증기준_공동고시.txt).
    그전까지 근거는 팀 학습문서 v4 §3-1뿐이었고, 원문을 못 구한 이유를 "03 고시가
    이미지 스캔본이라"고 적어뒀으나 둘 다 틀렸다 — 03은 12(인증규칙)의 중복본이었고,
    고시 링크는 팀이 준 'ZEB GR 법령.pdf'에 처음부터 있었다. 원문 값은 학습문서와 일치했다.
    """
    from core import params as _P
    try:
        table = _P.get("zeb_incentive", "등급판정.보정계수_대지외생산.구간")
    except Exception:
        table = [[10, 0.7], [15, 0.8], [20, 0.9], [float("inf"), 1.0]]
    for upper, factor in table:
        if onsite_autonomy_pct < float(upper):
            return float(factor)
    return 1.0


def calculate_pv_generation(bim: dict) -> dict:
    """
    PV 발전량 산정 — **대지 내/외를 분리**한다 (별표1 주4 / §3-1).

    BIM의 각 PV 패널은 `onsite: false`로 대지 외임을 표시한다(기본 true = 대지 내).
    대지 외 생산은 보정계수(0.7~1.0)를 곱해 인정하며, 그 계수는 **대지 내 자립률**에
    따라 정해진다 — 그래서 대지 내를 먼저 계산해야 한다.

    두 자립률이 나온다:
      · 등급용   = (대지 내 + 대지 외×보정계수) 기준  ← 인증등급 판정
      · 완화용   = **대지 내만** 기준 (별표1 주4)      ← 용적률·높이 완화 판정
    값이 다르므로 절대 섞으면 안 된다.
    """
    pv_list = bim.get("pv_panels", []) or []
    region = bim.get("region", "중부2")
    yield_per_kw = PV_YIELD_BY_REGION.get(region, 1300)
    area_m2 = bim.get("total_area_m2", 1) or 1

    def _kw(items):
        return sum(p.get("capacity_kw", 0) for p in items)

    # onsite 미표기는 대지 내로 본다 (기존 BIM 호환)
    onsite = [p for p in pv_list if p.get("onsite", True)]
    offsite = [p for p in pv_list if not p.get("onsite", True)]

    onsite_kw, offsite_kw = _kw(onsite), _kw(offsite)
    onsite_kwh = onsite_kw * yield_per_kw
    offsite_kwh_raw = offsite_kw * yield_per_kw

    return {
        # 대지 내
        "onsite_capacity_kw": onsite_kw,
        "onsite_generation_kwh": round(onsite_kwh, 1),
        "onsite_yield_per_m2_kwh": round(onsite_kwh / area_m2, 2),
        # 대지 외 (보정 전 — 보정계수는 대지 내 자립률을 알아야 정해지므로 evaluate_zeb에서 적용)
        "offsite_capacity_kw": offsite_kw,
        "offsite_generation_kwh_raw": round(offsite_kwh_raw, 1),
        # 합계 (보정 전)
        "total_capacity_kw": onsite_kw + offsite_kw,
        "annual_generation_kwh": round(onsite_kwh + offsite_kwh_raw, 1),
        "yield_per_m2_kwh": round((onsite_kwh + offsite_kwh_raw) / area_m2, 2),
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
    # ── 대지 내/외 분리 + 보정계수 (별표1 / 별표1 주4) ─────────────
    # ⚠️ 순서가 중요하다: 보정계수는 **대지 내 자립률**로 정해지므로 대지 내를 먼저 푼다.
    area_m2 = bim.get("total_area_m2", 1) or 1
    onsite_primary = pv.get("onsite_yield_per_m2_kwh", pv["yield_per_m2_kwh"]) * ELECTRICITY_PEF
    offsite_primary_raw = (pv.get("offsite_generation_kwh_raw", 0) / area_m2) * ELECTRICITY_PEF

    # ① 완화용 자립률 = **대지 내만** (별표1 주4) — 용적률·높이 완화 판정용
    onsite_autonomy_pct = (onsite_primary / post_energy * 100) if post_energy > 0 else 0.0

    # ② 대지 외 보정계수는 ①에 따라 정해진다
    corr = offsite_correction_factor(onsite_autonomy_pct) if offsite_primary_raw > 0 else 1.0
    offsite_primary = offsite_primary_raw * corr

    # ③ 등급용 자립률 = 대지 내 + 대지 외×보정계수
    pv_primary_per_m2 = onsite_primary + offsite_primary
    pv["yield_per_m2_primary_kwh"] = round(pv_primary_per_m2, 2)
    pv["primary_energy_factor"] = ELECTRICITY_PEF
    pv["onsite_primary_per_m2"] = round(onsite_primary, 2)
    pv["offsite_primary_per_m2_raw"] = round(offsite_primary_raw, 2)
    pv["offsite_correction_factor"] = corr
    pv["offsite_primary_per_m2_corrected"] = round(offsite_primary, 2)

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
        # 등급 판정용 자립률 — 대지 내 + 대지 외×보정계수
        "autonomy_pct": round(autonomy_pct, 1),
        # ⚠️ 완화(용적률·높이) 판정용 자립률 — **대지 내만** (별표1 주4).
        #    등급용과 값이 다르다. 완화 계산에 autonomy_pct를 쓰면 과대 인정된다.
        "autonomy_pct_onsite_only": round(onsite_autonomy_pct, 1),
        "offsite_correction_factor": corr,
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
