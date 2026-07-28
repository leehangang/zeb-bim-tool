"""
core/gr_evaluator.py — Track B · 그린리모델링 사업 자격 판정
============================================================
설계 원칙 P4 (docs/ARCHITECTURE.md): **ZEB ≠ 그린리모델링**.
    ZEB  = 녹색건축법 §17 · 절대성능(1차E 소요량/자립률) → 등급 (+~5등급)
    GR   = 녹색건축법 §27 · **상대 개선율**(개선 전 대비) → 등급 없음, 자격 충족/미달
두 트랙은 판정을 분리하고 BIM 파싱·에너지 해석·단가DB·법령 RAG는 공유한다.
그래서 ZEB는 core.zeb_evaluator, GR 자격은 이 모듈이 맡는다.

⚠️ 분모를 절대 헷갈리지 말 것 — 두 트랙의 분모가 다르다:
    ZEB 절감률        = (base − 개선후) ÷ **base**       ← 용도별 기준 에너지요구량
    GR 성능개선비율    = (개선전 − 개선후) ÷ **개선전**    ← 실제 현재 상태
  도담 기준 50.5% vs 41.2%로 9%p 갈린다. 섞으면 조용히 틀린다(silent error).

근거 (2026-07 자체 RAG로 원문 확인 — 딥리서치는 이 쟁점을 '못 찾음'으로 종결했었다):
  · 2026년 민간건축물 GR 이자지원 사업 공고 p.3:
      "비주거 ➊ : 에너지 성능개선 비율 20% 이상(센터 지정 프로그램 활용)"
      "➊ (에너지성능[프로그램]) 센터가 지정한 프로그램으로 산출한
        **그린리모델링 공사 이전 대비** 에너지 성능개선 비율 20% 이상"
      "** 에너지 성능개선 비율은 **개선공사 이전 대비** '에너지 요구량' 또는
        '에너지 소요량' 또는 '1차에너지 소요량'의 성능개선"
      → 분모 = 개선공사 이전. 지표는 요구량/소요량/1차E소요량 중 택1.
  · GR 지원사업 운영 고시 제9조①:
      "이자지원의 기준은 에너지 시뮬레이션에 따른 성능개선비율이 20퍼센트 이상일 경우 등으로 한다."
  · 지정 프로그램 6종: ECO2, ECO2-OD, GR-E, EnergyStudio, EnergyPlus, IES-VE
      → **우리 엔진의 간이 추정은 지정 프로그램이 아니다.** 자격 판정은 참고용이며
        실제 신청은 지정 프로그램 결과를 제출해야 한다.
  · 비주거는 간이평가표 경로가 없다(간이평가표는 단독주택 전용) → 시뮬레이션 필수.
"""

from typing import Optional

from core import params as _P

# 성능개선비율 산정에 쓸 수 있는 지표 (공고 p.3 각주)
# 🔑 '에너지요구량'이 명시적으로 허용된다 — 설비 효율 없이 부하만으로도 성립한다.
#    우리 EnergyPlus IDF는 IdealLoads라 정확히 이 요구량을 낸다.
ALLOWED_METRICS = ("에너지요구량", "에너지소요량", "1차에너지소요량")

# 센터 지정 에너지 시뮬레이션 프로그램 (공고 p.3·p.16 각주 — 같은 목록이 두 곳에 있다)
DESIGNATED_TOOLS = ("ECO2", "ECO2-OD", "GR-E", "EnergyStudio", "EnergyPlus", "IES-VE")

# 🔴 프로그램만 맞으면 되는 게 아니다. 공고 p.3 각주 축자:
#     "계산에 필요한 '용도프로필'과 '기상데이터'는 「제로에너지건축물 인증 제도 운영규정」
#      별표2, 별표6을 준용함"
#    → EnergyPlus를 써도 **입력이 별표2·별표6이 아니면 요건 미충족**이다.
#    우리 IDF는 둘 다 안 지킨다:
#      · 용도프로필: 어린이집 표준 가정(0.1인/㎡·10W/㎡·5W/㎡) — 별표2가 아니다.
#        (게다가 별표2 23개 용도에 어린이집이 없다 → zeb_incentive.yaml 용도별보정계수_제2호)
#      · 기상데이터: 추풍령 TMYx .epw(시간별) — 별표6은 66지역 **월평균**이다.
#        시간별 엔진에 월평균을 어떻게 '준용'하는지는 공고가 안 알려준다 → 센터 확인 필요.
REQUIRED_INPUTS = {
    "용도프로필": "ZEB 인증 제도 운영규정 [별표2]",
    "기상데이터": "ZEB 인증 제도 운영규정 [별표6]",
    "근거": "2026 민간 GR 이자지원 공고 p.3 각주",
    "우리_준수여부": "미준수 — 표준가정 프로필 + 추풍령 .epw",
}


def improvement_ratio(pre: float, post: float) -> float:
    """
    성능개선비율 = (개선 전 − 개선 후) ÷ **개선 전**.

    ⚠️ 분모는 '개선 전'이지 용도별 기준요구량(base)이 아니다 (모듈 docstring 참고).

    >>> round(improvement_ratio(168.52, 99.08), 3)
    0.412
    """
    pre = float(pre)
    if pre <= 0:
        raise ValueError(f"개선 전 값이 0 이하다: {pre} — 분모가 될 수 없다")
    return (pre - float(post)) / pre


def judge_improvement(pre: float, post: float,
                      metric: str = "1차에너지소요량") -> dict:
    """
    성능개선비율 20% 기준 충족 여부.

    Args:
        pre/post: 개선 전/후 값 (같은 지표·같은 단위여야 한다)
        metric: 어떤 지표로 쟀는지 (ALLOWED_METRICS 중 하나)
    """
    if metric not in ALLOWED_METRICS:
        raise ValueError(
            f"허용되지 않는 지표: {metric} (가능: {ALLOWED_METRICS}) — 공고 별지6"
        )
    ratio = improvement_ratio(pre, post)
    minimum = _P.gr_min_improvement_ratio()
    return {
        "지표": metric,
        "개선전": round(float(pre), 2),
        "개선후": round(float(post), 2),
        "성능개선비율": round(ratio, 4),
        "성능개선비율_pct": round(ratio * 100, 1),
        "기준": minimum,
        "기준_pct": round(minimum * 100, 1),
        "충족": ratio >= minimum,
        "_분모": "개선 전 (공고 p.3 '개선공사 이전 대비')",
        "_근거": "GR 고시 §9① / 2026년 민간 GR 이자지원 공고 p.3·별지6",
    }


def check_target_works(gr_mapping: dict) -> dict:
    """
    대상공사 7종 중 1건 이상 포함 여부 (GR 고시 §7①).

    gr_mapping은 core.bim_diagnoser.map_to_gr_elements() 결과.
    '적용'/'부분적용'인 항목을 개선 대상으로 본다.
    """
    # 7종 ↔ 우리 11개 기술요소 키 매핑
    GROUPS = {
        "1_외벽단열공사": ["3_외벽단열보강", "4_바닥단열난방", "5_쿨루프"],
        "2_고성능창호공사": ["1_고성능창호", "2_고기밀성단열문"],
        "3_고효율기기": ["7_고효율냉난방", "8_고효율보일러", "9_고효율LED"],
        "4_폐열회수환기": ["6_폐열회수환기"],
        "5_BEMS_원격검침": ["11_BEMS"],
        "6_신재생에너지": ["10_신재생태양광", "6-나_신재생태양열"],
        "7_기타외피성능": [],
    }
    hit = {}
    for group, keys in GROUPS.items():
        applied = [
            k for k in keys
            if str((gr_mapping.get(k) or {}).get("status", "")) in ("적용", "부분적용")
        ]
        if applied:
            hit[group] = applied
    return {
        "충족": bool(hit),
        "해당공사": hit,
        "_근거": "GR 고시 제7조 제1항 (대상공사 7종 중 1건 이상)",
    }


def evaluate_gr(bim: dict, gr_mapping: dict,
                pre_primary: Optional[float] = None,
                post_primary: Optional[float] = None,
                metric: str = "1차에너지소요량") -> dict:
    """
    Track B 종합 자격 판정.

    pre/post를 주지 않으면 ZEB 엔진(공유 코어)에서 현재/전체보강 소요량을 가져온다.
    ⚠️ 그 값은 **간이 추정**이며 센터 지정 프로그램(ECO2 등) 결과가 아니다.
    """
    if pre_primary is None or post_primary is None:
        from core.zeb_evaluator import evaluate_zeb
        now = evaluate_zeb(bim, gr_mapping)
        full = evaluate_zeb(bim, gr_mapping,
                            assume_full_reinforcement=True, assume_bems=True)
        pre_primary = now["post_energy_kwh_m2"]
        post_primary = full["post_energy_kwh_m2"]
        source = "core.zeb_evaluator 간이 추정 (⚠️ 지정 프로그램 아님)"
    else:
        source = "사용자 입력 (지정 프로그램 결과 권장)"

    imp = judge_improvement(pre_primary, post_primary, metric=metric)
    works = check_target_works(gr_mapping)
    owner = _P.get("gr_support", "사업유형판정.대상건물판정", "공공지원사업")

    eligible = imp["충족"] and works["충족"]
    return {
        "성능개선": imp,
        "대상공사": works,
        "사업유형": owner,
        "자격충족": eligible,
        "_산정출처": source,
        "_지정프로그램": list(DESIGNATED_TOOLS),
        "_주의": (
            "우리 엔진의 간이 추정은 센터 지정 프로그램이 아니다. "
            "실제 신청은 ECO2·EnergyPlus 등 지정 프로그램 결과를 제출해야 하며, "
            "비주거는 간이평가표 경로가 없어 시뮬레이션이 필수다."
        ),
    }
