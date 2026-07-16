"""
core/params.py — 버전드 파라미터 테이블 로더
============================================
설계 원칙 (docs/ARCHITECTURE.md P2):
    · 제도 파라미터(요율·한도·단가)는 코드에 하드코딩하지 않는다.
    · 값은 data/params/*.yaml에 source/effective_from/status와 함께 둔다.
    · 엔진은 이 표를 **결정론적으로 조회**한다. LLM을 경유시키지 않는다.

왜 RAG가 아니라 테이블인가:
    RAG는 "문장을 찾아 인용"하는 도구다. 전기요금표처럼
    계절×시간대×계약종별 매트릭스에서 셀 하나를 고르게 하면
    (1) 계산을 LLM에게 시키는 셈이라 P2 위반이고
    (2) 틀려도 그럴싸해서 조용히 틀린다(silent error).
    → 숫자는 테이블에서 조회하고, RAG는 "그 근거가 뭐냐"에 답하는 데 쓴다.

제공:
    load(name)            — 파라미터 파일 로드 (캐시)
    get(path, default)    — 점 경로 조회 ("취득세감면.등급별감면율.4")
    provenance(path)      — 해당 값의 출처·시행일·상태 반환 (근거 제시용)
    missing()             — status가 확인필요/미완성인 항목 목록 (값 고정 금지 대상)
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

PARAM_DIR = Path(__file__).resolve().parent.parent / "data" / "params"

# 파일명 → 트랙
FILES = {
    "zeb_incentive": "zeb_incentive.yaml",
    "gr_support": "gr_support.yaml",
    "energy_tariff": "energy_tariff.yaml",
}

_UNSET = object()


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    """파라미터 파일 로드 (캐시). name은 FILES의 키."""
    if name not in FILES:
        raise KeyError(f"알 수 없는 파라미터 세트: {name} (가능: {list(FILES)})")
    path = PARAM_DIR / FILES[name]
    if not path.exists():
        raise FileNotFoundError(f"파라미터 파일 없음: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get(name: str, path: str, default: Any = _UNSET) -> Any:
    """
    점 경로로 값 조회.

    >>> get("zeb_incentive", "취득세감면.등급별감면율.4")
    0.18
    """
    node: Any = load(name)
    for key in path.split("."):
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            if default is _UNSET:
                raise KeyError(f"{name}: 경로 없음 — {path}")
            return default
    return node


def provenance(name: str, section: str) -> dict:
    """
    해당 섹션의 출처·시행일·상태. 결과 화면에 근거를 함께 표시할 때 쓴다.

    >>> provenance("zeb_incentive", "취득세감면")["source"]
    '지방세특례제한법 제47조의2 제2항 / 시행령 제24조'
    """
    node = get(name, section, {})
    if not isinstance(node, dict):
        return {}
    return {
        k: node.get(k)
        for k in ("source", "url", "effective_from", "effective_until", "status", "year", "note")
        if node.get(k) is not None
    }


def missing() -> list:
    """
    status가 '확인필요' 또는 '미완성'인 항목 목록.
    이 목록의 값은 **고정하지 않고** 화면에 '확인 필요'로 표기한다.
    (팀 학습문서 v4 부록 B 원칙)
    """
    out = []

    def walk(name: str, node: Any, trail: str):
        if not isinstance(node, dict):
            return
        status = node.get("status")
        if isinstance(status, str) and ("확인필요" in status or "미완성" in status):
            out.append({
                "set": name,
                "section": trail or "(root)",
                "status": status,
                "source": node.get("source"),
                "확인필요": node.get("확인필요"),
            })
        for k, v in node.items():
            if isinstance(v, dict):
                walk(name, v, f"{trail}.{k}" if trail else str(k))

    for name in FILES:
        try:
            walk(name, load(name), "")
        except Exception:
            continue
    return out


# ── 편의 조회 (엔진에서 자주 쓰는 값) ────────────────────────────

def zeb_tax_relief_rate(grade: str, has_extension: bool) -> float:
    """
    ZEB 취득세 감면율.

    ⚠️ 신축·증축·개축한 '부분'만 대상이다. 기존 건축물 단순 리모델링(증축 없음)은 0.
    (지방세특례제한법 §47의2 제2항 — 학습문서 v4 1-4-1)
    """
    if not has_extension:
        return 0.0
    return float(get("zeb_incentive", f"취득세감면.등급별감면율.{grade}", 0.0))


def zeb_far_bonus(grade: str) -> float:
    """ZEB 용적률·높이 최대 완화율 (에너지절약설계기준 별표9)."""
    return float(get("zeb_incentive", f"용적률높이완화.등급별최대완화율.{grade}", 0.0))


def zeb_cert_fee(exclusive_area_m2: float) -> int:
    """ZEB 인증 수수료 (비주거, 별표4, 부가세 별도)."""
    for limit, fee in get("zeb_incentive", "인증수수료.전용면적구간_원"):
        if exclusive_area_m2 < float(limit):
            return int(fee)
    return 0


def zeb_fee_refund_rate(grade: str, is_mandatory: bool) -> float:
    """
    ZEB 인증 수수료 환불율.
    ⚠️ '의무 대상이 아닌' 건물이 자율 인증한 경우에만 적용 (고시 제6조제3항제5호 나목).
    """
    if is_mandatory:
        return 0.0
    return float(get("zeb_incentive", f"수수료환불.등급별환불율.{grade}", 0.0))


def gr_subsidy_rate(owner_type: str) -> float:
    """GR 공공지원 보조율. owner_type: '서울_중앙_공공기관' | '그외_지자체'."""
    return float(get("gr_support", f"공공지원.보조율.{owner_type}", 0.0))


def gr_min_improvement_ratio() -> float:
    """GR 지원 자격 — 성능개선비율 최소치 (고시 제9조 제1항)."""
    return float(get("gr_support", "공통자격.성능개선비율_최소", 0.20))


def electricity_tariff_won_per_kwh() -> float:
    """
    전기 세후 실효단가 (원/kWh) — 한전 기본공급약관 [별표1] 2026.7.1 시행판.

    계절별 전력량요금을 **월수로 가중평균**(여름3·봄가을5·겨울4)한 뒤
    기후환경요금·연료비조정요금을 더하고 부가세·전력산업기반기금을 적용한다.

    ⚠️ 월수 가중은 '월별 사용량이 균등하다'는 단순화다. 실제로는 냉난방으로
       여름·겨울에 사용량이 몰리므로 실효단가가 이보다 높을 수 있다.
       ECO2 월간 kWh가 나오면 사용량 가중으로 교체할 것.
    """
    e = get("energy_tariff", "전기")
    u, b, t = e["단가_원_per_kWh"], e["부과금_원_per_kWh"], e["세금_요율"]
    # 여름 6~8월(3) · 봄가을 3~5,9~10월(5) · 겨울 11~2월(4) — 약관 제67조⑧
    seasonal = (u["여름철"] * 3 + u["봄가을철"] * 5 + u["겨울철"] * 4) / 12
    subtotal = seasonal + b["기후환경요금"] + b["연료비조정요금"]
    return subtotal * (1 + t["부가가치세"] + t["전력산업기반기금"])


def annual_saving_per_m2(reduction_primary_kwh_m2: Optional[float] = None) -> float:
    """
    연간 에너지 절감 단가 (원/㎡·년) = 절감 site kWh × 전기 실효단가.

    2026-07-16까지 이 함수는 `9,900원/㎡`라는 **근거 없는 매직넘버**를 돌려줬다.
    kWh 절감량과 연결이 끊겨 있어 ZEB 엔진이 절감률을 고쳐도 ROI는 꿈쩍하지 않았다.

    리서치로 한전 약관 원문 단가를 확보해 계산식으로 교체했다:
        절감 1차E(kWh/㎡·년) ÷ 2.75  →  절감 site 전기(kWh/㎡·년)
        × 전기 세후 실효단가(원/kWh)  →  원/㎡·년
    도담 기준 100.9 ÷ 2.75 × 140.9 ≈ **5,172원/㎡** — 옛 매직넘버는 **1.91배 과대**였다.
    (연간 1,238만원 → 647만원. 방향은 KEEI 실측연구 '예측의 60%'와 독립적으로 일치한다.)

    Args:
        reduction_primary_kwh_m2: 1차에너지 절감량. None이면 params의 도담 기본값.

    ⚠️ 남은 가정 — **전량 전기**로 본다. 도담의 실제 연료 구성(전기/가스)은 미확인이며,
       경북 노유자시설 전기 비중은 82.2%다(건물에너지사용량통계 2024). 가스분이 있으면
       환산계수가 1.1이라 site kWh가 커져 절감액은 이보다 **커진다** → 이 값은 보수적이다.
    """
    if reduction_primary_kwh_m2 is None:
        try:
            reduction_primary_kwh_m2 = float(
                get("energy_tariff", "절감액산정.도담_1차E_절감_kWh_per_m2")
            )
        except Exception:
            return 5_172.0          # YAML 없어도 import가 깨지지 않게 방어
    try:
        factor = float(get("energy_tariff", "1차에너지환산계수.전력", 2.75))
        site_kwh = float(reduction_primary_kwh_m2) / factor
        return site_kwh * electricity_tariff_won_per_kwh()
    except Exception:
        return 5_172.0


def annual_saving_is_assumption() -> bool:
    """
    위 단가가 아직 근거 미확보 상태인가 — 화면 표기 판단용.

    이제 **단가**는 약관 원문 근거가 있다. 그러나 **절감 kWh**(base 200·절감률 11개 값)는
    아직 문헌 근거가 없고 ECO2 해석 전이므로, 곱해서 나온 절감액도 여전히 추정치다.
    → 절감액 산정에 들어가는 값 중 하나라도 미확정이면 True.
    """
    try:
        return "확인됨" not in str(get("energy_tariff", "절감액산정.status", ""))
    except Exception:
        return True      # 확인 못 하면 '가정치'로 본다 (안전한 쪽)
