"""
scripts/test_evidence.py — 근거·출처 페이지 검증
================================================
이 페이지는 "우리 숫자의 근거를 보여준다"고 주장한다.
그 주장 자체가 검증되지 않으면 페이지가 오히려 위험하다.

검증 항목:
    1. 파라미터 출처가 YAML에서 실제로 읽히는가 (하드코딩이 아닌가)
    2. 위험한 status가 중립 배지로 새어나가지 않는가
    3. 등급 임계(55%)가 엔진 호출로 **재현**되는가 — 손으로 적은 값이 아닌가
    4. 절감률의 분모가 base(200)인가 — 현재 소요량(166.7)로 착각하지 않았는가
"""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.zeb_evaluator import get_base_energy  # noqa: E402
from modes.mode5_evidence import (  # noqa: E402
    collect_provenance, grade_sensitivity, status_badge,
)

fails = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)


def _raises(fn) -> bool:
    """fn이 예외를 내면 True. (조용한 실패를 잡기 위한 헬퍼)"""
    try:
        fn()
        return False
    except Exception:
        return True


print("① 파라미터 출처 — YAML 실시간 렌더")
rows = collect_provenance()
check("출처 행이 수집됨", len(rows) >= 15, f"{len(rows)}건")
check("3개 파라미터 세트 모두 포함",
      {r["set"] for r in rows} >= {"zeb_incentive", "gr_support", "energy_tariff"})
check("원문대조 항목에 원문 인용이 붙어 있음",
      all(r["원문근거"] for r in rows if r["status"] == "확인됨_원문대조"))

print("\n② status 배지 — 위험한 값이 안전해 보이면 안 됨")
danger, _ = status_badge("임시가정_근거없음")
check("임시가정_근거없음 → 경고 배지", "🔴" in danger, danger)
check("확인됨_원문대조가 '확인됨'에 먹히지 않음",
      status_badge("확인됨_원문대조")[0] == "✅ 원문대조")
check("모르는 status는 경고로 처리", status_badge("듣도보도못한값")[0].startswith("⚠️"))
check("폐지 → 폐지 배지", "⛔" in status_badge("폐지")[0])

print("\n③ 등급 민감도 — 임계를 엔진에서 재현")
s = grade_sensitivity(building_use="어린이집")
check("base가 엔진의 용도별 기본값(200)", s["base"] == float(get_base_energy("어린이집")),
      f"base={s['base']}")
cliff4 = next((c for c in s["cliffs"] if c["등급"] == "4"), None)
check("4등급 임계가 존재", cliff4 is not None)
if cliff4:
    check("4등급 임계 = 55.0% (사이트 표기와 일치)",
          abs(cliff4["임계_절감률_pct"] - 55.0) < 0.15,
          f"{cliff4['임계_절감률_pct']}%")
    check("67% 가정 대비 여유 12%p", abs((67.0 - cliff4["임계_절감률_pct"]) - 12.0) < 0.2,
          f"{round(67.0 - cliff4['임계_절감률_pct'], 1)}%p")

print("\n④ 분모 착각 방지 — base(200) vs 현재 소요량(166.7)")
wrong = grade_sensitivity(166.7, building_use="어린이집")
wrong4 = next((c for c in wrong["cliffs"] if c["등급"] == "4"), None)
check("분모를 166.7로 넣으면 임계가 46%로 어긋남 (착각 재현)",
      wrong4 is not None and abs(wrong4["임계_절감률_pct"] - 46.0) < 0.5,
      f"{wrong4['임계_절감률_pct']}%" if wrong4 else "—")
check("기본 호출은 166.7이 아닌 200을 씀", s["base"] != 166.7)

print("\n⑤ 절감률 결합 방식 — 단순합산은 물리적으로 성립하지 않는다")
from core.zeb_evaluator import GR_ENERGY_REDUCTION, combine_reductions  # noqa: E402

# 단순합산의 파탄을 재현: 10% 요소 11개 → 110% (에너지 음수)
absurd = [0.10] * 11
check("단순합산은 100%를 넘길 수 있다 (파탄 재현)",
      combine_reductions(absurd, "sum") > 1.0,
      f"{combine_reductions(absurd, 'sum')*100:.0f}%")
check("1−Π(1−rᵢ)는 100%를 넘지 않는다",
      0 < combine_reductions(absurd, "multiplicative") < 1.0,
      f"{combine_reductions(absurd, 'multiplicative')*100:.1f}%")
check("결합은 순서에 무관하다",
      abs(combine_reductions([0.1, 0.3, 0.2], "multiplicative")
          - combine_reductions([0.3, 0.2, 0.1], "multiplicative")) < 1e-12)

_rs = list(GR_ENERGY_REDUCTION.values())
_sum, _mul = combine_reductions(_rs, "sum"), combine_reductions(_rs, "multiplicative")
check("도담 단순합산 = 67.0%", abs(_sum * 100 - 67.0) < 0.1, f"{_sum*100:.1f}%")
check("도담 상호작용 = 50.5%", abs(_mul * 100 - 50.5) < 0.2, f"{_mul*100:.1f}%")
check("상호작용 값이 4등급 임계(55%) 아래 — 즉 등급이 뒤집힌다",
      _mul * 100 < 55.0,
      f"{_mul*100:.1f}% < 55% → 4등급 아님")
check("엔진이 두 값을 모두 노출한다",
      "total_reduction_ratio_multiplicative" in
      __import__("core.zeb_evaluator", fromlist=["x"]).calculate_reduction_ratio(
          {k: {"status": "적용"} for k in GR_ENERGY_REDUCTION}))
check("알 수 없는 결합 방식은 조용히 넘어가지 않는다",
      _raises(lambda: combine_reductions([0.1], "평균내기")))

print("\n⑥ 도담 케이스 회귀 고정 — 엔진의 실제 판정")
# 왜: 홈 화면의 등급·소요량은 하드코딩 문자열이라, 엔진 결론이 바뀌어도 아무것도 깨지지
#     않았다(4등급 → 5등급이 조용히 통과). 엔진의 실제 판정을 여기서 고정한다.
import json  # noqa: E402
from core.bim_diagnoser import map_to_gr_elements  # noqa: E402
from core.zeb_evaluator import evaluate_zeb  # noqa: E402

_bim = json.load(open("data/sample_bim/doam_archi_sample.json", encoding="utf-8"))
_gr = map_to_gr_elements(_bim)
_full = evaluate_zeb(_bim, _gr, assume_full_reinforcement=True, assume_bems=True)

check("결합 기본값 = multiplicative", _full["reduction"]["_결합방식"] == "multiplicative")
check("전체보강 절감률 = 50.5%", abs(_full["reduction"]["total_reduction_pct"] - 50.5) < 0.2,
      f"{_full['reduction']['total_reduction_pct']}%")
check("전체보강 1차E 소요량 ≈ 99.1", abs(_full["post_energy_kwh_m2"] - 99.1) < 0.3,
      f"{_full['post_energy_kwh_m2']}")
check("자립률 0% (태양광 없음 — 태양열 27㎡는 급탕)", _full["autonomy_pct"] == 0.0,
      f"{_full['autonomy_pct']}%")
check("제1호(자립률)로는 등급 미달", _full["grade_clause1"]["rank"] == 0)
check("최종 등급 = ZEB 5등급 (제2호 근거)", _full["grade"]["grade"] == "5",
      _full["grade"]["label"])
check("등급 근거는 제2호", _full["grade"]["rank"] == _full["grade_clause2"]["rank"])

# 과거 기본값(sum)이었다면 4등급이 나온다 — 결론이 산정 방식에 달렸음을 고정
from core.zeb_evaluator import calculate_reduction_ratio, determine_grade_clause2  # noqa: E402
_sum_r = calculate_reduction_ratio(
    {k: {"status": "적용"} for k in GR_ENERGY_REDUCTION}, combine="sum",
)["total_reduction_ratio"]
_sum_grade = determine_grade_clause2(200 * (1 - _sum_r), is_residential=False)
check("단순합산이면 4등급이 나온다 (방식 의존성 고정)", _sum_grade["grade"] == "4",
      f"sum {_sum_r*100:.1f}% → {_sum_grade['label']}")

print("\n⑦ 단일 소스 원칙 — 매직넘버가 코드로 다시 스며들지 않는가")
# 왜: 9,900원/㎡는 energy_tariff.yaml에 '임시가정_근거없음'으로 등록돼 있는데도
#     roi_calculator·roi_tools·scenario_compare·mode3_bim 5곳이 각자 하드코딩하고 있었다.
#     우리가 내세우는 P2("숫자는 테이블에서 결정론적 조회")를 최대 가정치에서 어긴 셈.
import re as _re  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_ROOT = _Path(__file__).resolve().parent.parent
_SRC = ["core/roi_calculator.py", "core/roi_tools.py", "core/scenario_compare.py",
        "modes/mode3_bim.py"]
_offenders = []
for _rel in _SRC:
    for _i, _line in enumerate(( _ROOT / _rel).read_text(encoding="utf-8").splitlines(), 1):
        if _re.search(r"(?<![\w.])9[_,]?900(?![\d])", _line) and not _line.lstrip().startswith("#"):
            _offenders.append(f"{_rel}:{_i}")
check("9,900 매직넘버가 코드에 없다 (params 경유)", not _offenders,
      "위반: " + ", ".join(_offenders) if _offenders else "5곳 → 0곳")

from core import params as _PP  # noqa: E402
check("params.annual_saving_per_m2()가 YAML 값을 돌려준다",
      _PP.annual_saving_per_m2() == 9900.0, f"{_PP.annual_saving_per_m2()}")
check("단가가 '가정치'로 표시된다", _PP.annual_saving_is_assumption() is True)

# 자립률 등급표도 엔진 단일 소스여야 한다
_m3 = (_ROOT / "modes/mode3_bim.py").read_text(encoding="utf-8")
check("mode3가 자립률 등급표를 재정의하지 않는다",
      '("3등급", 60)' not in _m3 and "ZEB_AUTONOMY_THRESHOLDS" in _m3)

print("\n⑧ Track B · GR 자격 판정 — ZEB와 분모가 다르다")
from core.gr_evaluator import (  # noqa: E402
    ALLOWED_METRICS, evaluate_gr, improvement_ratio, judge_improvement,
)

# 분모 = 개선 전 (공고 p.3 "개선공사 이전 대비") — base가 아니다
check("성능개선비율 = (전−후)÷전", abs(improvement_ratio(168.52, 99.08) - 0.412) < 0.002,
      f"{improvement_ratio(168.52, 99.08)*100:.1f}%")
check("분모가 0이면 조용히 넘어가지 않는다", _raises(lambda: improvement_ratio(0, 10)))
check("허용되지 않는 지표는 거부한다",
      _raises(lambda: judge_improvement(100, 50, metric="아무거나")))
check("공고 별지6의 3개 지표를 허용",
      set(ALLOWED_METRICS) == {"에너지요구량", "에너지소요량", "1차에너지소요량"})

_grres = evaluate_gr(_bim, _gr)
_imp = _grres["성능개선"]
check("도담 성능개선비율 = 41.2%", abs(_imp["성능개선비율_pct"] - 41.2) < 0.2,
      f"{_imp['성능개선비율_pct']}%")
check("기준 20% 충족", _imp["충족"] is True, f"{_imp['성능개선비율_pct']}% ≥ {_imp['기준_pct']}%")
check("대상공사 7종 중 1건 이상 충족", _grres["대상공사"]["충족"] is True,
      f"{len(_grres['대상공사']['해당공사'])}개 분야")
check("GR 자격 = 충족", _grres["자격충족"] is True)
check("지정 프로그램이 아님을 명시", "지정 프로그램" in _grres["_주의"])

# 🔴 두 트랙의 분모를 섞으면 안 된다 — 값이 실제로 다름을 고정
_zeb_ratio = _full["reduction"]["total_reduction_pct"]          # base 분모 → 50.5%
check("ZEB 절감률(base 분모) ≠ GR 성능개선비율(개선전 분모)",
      abs(_zeb_ratio - _imp["성능개선비율_pct"]) > 5.0,
      f"ZEB {_zeb_ratio}% vs GR {_imp['성능개선비율_pct']}% — {abs(_zeb_ratio-_imp['성능개선비율_pct']):.1f}%p 차이")

print("\n⑨ GR 정량평가표 — 원문 정합 (2026 공공 GR 2.0 가이드라인 p.18~20)")
from core.bim_diagnoser import score_compliance  # noqa: E402

_sc = score_compliance(_gr, _bim)
check("등급을 반환하지 않는다 (제도에 없음)", "grade" not in _sc)
check("평가 성격이 '선정 랭킹 점수'로 명시", "랭킹" in _sc["_평가성격"])
check("도담 기본점수 = 24 (사업효율성 원문정합 반영)",
      _sc["total_score"] == 24, f"{_sc['total_score']}")
check("GR요소 80 + 사업여건 20 = 100 만점", _sc["max_score"] == 100)

# '0점'과 '미평가'는 다르다
check("미평가 항목을 0점과 구분해 노출", len(_sc["_미평가"]) > 0,
      f"{len(_sc['_미평가'])}건")
check("채점가능최대 = 92 (일사조절3 + 인정5는 데이터 없음)",
      _sc["_채점가능최대"] == 92, f"{_sc['_채점가능최대']}")
_names = {u["항목"] for u in _sc["_미평가"]}
check("일사조절·인정이 '미평가'로 잡힌다",
      any("일사조절" in n for n in _names) and any("녹색건축물" in n for n in _names))

# 가점 14 / 감점 -10 (원문 p.20)
check("가점 만점 = 14", _sc["breakdown"]["가점"]["만점"] == 14)
check("감점 한도 = -10", _sc["breakdown"]["감점"]["한도"] == -10)
check("가점 항목이 미평가로 잡힌다 (BIM에서 산출 불가)",
      any(n.startswith("가점") for n in _names))

# 사업효율성 원문 구간: "30미만~0이상 = 1점" — 0도 1점이다
_b0 = {**_bim, "annual_saving_kwh": 0, "project_cost_million_won": 100}
check("사업효율성 효율 0 → 1점 (원문 '30미만~0이상')",
      score_compliance(_gr, _b0)["breakdown"]["사업여건"]["사업효율성"]["점수"] == 1)
_b5 = {**_bim, "annual_saving_kwh": 12000, "project_cost_million_won": 100}   # 120
check("사업효율성 효율 120 → 5점",
      score_compliance(_gr, _b5)["breakdown"]["사업여건"]["사업효율성"]["점수"] == 5)

# 가점 입력 시 실제 선정 점수에 반영
_bb = {**_bim, "bonus_safety": 5, "bonus_meter": 2, "penalty_mgmt": 3}
_scb = score_compliance(_gr, _bb)
check("가점·감점이 final_score에 반영",
      _scb["final_score"] == _scb["total_score"] + 7 - 3,
      f"기본 {_scb['total_score']} +{_scb['bonus']} {_scb['penalty']} = {_scb['final_score']}")
check("가점은 항목별 상한을 넘지 않는다",
      score_compliance(_gr, {**_bim, "bonus_meter": 99})["bonus"] == 2)

print("\n⑩ 용어사전 — 세 제도 구분 · 엔진 연동")
from modes.mode6_glossary import confusions, glossary, three_systems  # noqa: E402

_sys = three_systems()
check("세 제도(ZEB §17 / G-SEED §16 / GR §27)를 구분", len(_sys) == 3)
check("근거 조항이 셋 다 다르다", len({s["근거"] for s in _sys}) == 3,
      " · ".join(s["근거"].split("§")[-1] for s in _sys))
check("G-SEED는 '평가하지 않음'으로 명시",
      any("평가하지 않음" in s["우리"] for s in _sys))
check("GR 지원사업은 '등급 없음'으로 명시",
      any("등급 없음" in s["결과"] for s in _sys))

_conf = confusions()
check("우리가 틀렸던 혼동을 기록", len(_conf) >= 4, f"{len(_conf)}건")
check("모든 혼동에 '우리 사고 기록'이 있다", all(c["우리사고"] for c in _conf))

# 용어사전은 엔진에서 값을 읽어야 한다 — 하드코딩이면 기준표가 바뀔 때 갈라진다
_g = glossary()
check("용어 카테고리 3분야", len(_g) == 3)
_flat = [t for v in _g.values() for t in v]
check("용어 13개 이상", len(_flat) >= 13, f"{len(_flat)}개")
check("모든 용어에 뜻이 있다", all(t.get("뜻") for t in _flat))

_a = next(t for t in _g["Track A · ZEB 인증"] if t["용어"] == "1차에너지소요량")
check("전력 환산계수를 엔진에서 읽는다 (×2.75)", "2.75" in _a["함정"])
check("비주거 등급 구간을 엔진에서 읽는다 (<90)", "<90" in _a["우리도구"])
_b = next(t for t in _g["Track B · 그린리모델링 사업"] if t["용어"] == "성능개선비율")
check("GR 기준 20%를 params에서 읽는다", "20% 이상" in _b["우리도구"])
check("정량평가표 용어가 '등급이 아니다'라고 경고",
      any("등급이 아니다" in (t.get("함정") or "")
          for t in _g["Track B · 그린리모델링 사업"]))

print("\n⑪ 별표1 열관류율 · 별표2 주5 — 팀 학습문서 v4 대조 (2026-07)")
from core.bim_diagnoser import U_VALUE_LIMITS, U_VALUE_LIMITS_RES, check_u_value, u_limits  # noqa: E402
from core.zeb_evaluator import RESIDENTIAL_USES  # noqa: E402

# 별표2 주5: "주거용 = 단독주택 + 공동주택(**기숙사 제외**)"
check("기숙사는 비주거다 (별표2 주5)", "기숙사" not in RESIDENTIAL_USES)
check("오피스텔은 비주거다 (건축법상 업무시설)", "오피스텔" not in RESIDENTIAL_USES)
check("단독·공동주택은 주거다",
      {"단독주택", "공동주택"} <= RESIDENTIAL_USES)

# 별표1 원문 (06 PDF p.19 파싱) — 외기 직접, 공동주택 외 vs 공동주택
_ORIG = {  # 지역: (비주거외벽, 주거외벽, 비주거창, 주거창, 지붕, 바닥난방)
    "중부1": (0.170, 0.150, 1.300, 0.900, 0.150, 0.150),
    "중부2": (0.240, 0.170, 1.500, 1.000, 0.180, 0.170),
    "남부":  (0.320, 0.220, 1.800, 1.200, 0.250, 0.220),
    "제주":  (0.410, 0.290, 2.200, 1.600, 0.290, 0.290),
}
_bad = []
for _r, (_wn, _wr, _gn, _gr_, _rf, _fl) in _ORIG.items():
    _n, _s = u_limits(_r, False), u_limits(_r, True)
    for _lbl, _exp, _got in [
        ("비주거외벽", _wn, _n["외벽_직접"]), ("주거외벽", _wr, _s["외벽_직접"]),
        ("비주거창", _gn, _n["창_직접"]), ("주거창", _gr_, _s["창_직접"]),
        ("지붕", _rf, _n["지붕_직접"]), ("바닥", _fl, _n["바닥_직접"]),
    ]:
        if abs(_exp - _got) > 1e-9:
            _bad.append(f"{_r}/{_lbl} {_exp}≠{_got}")
check("별표1 원문과 완전 일치 (4지역 × 6부위)", not _bad, "; ".join(_bad) or "24/24")

# 🔴 과거 버그: 비주거에 공동주택(주거) 기준을 쓰고 있었다
check("비주거 기준이 주거보다 완화적 (별표1 구조)",
      u_limits("중부2", False)["외벽_직접"] > u_limits("중부2", True)["외벽_직접"],
      f"비주거 {u_limits('중부2', False)['외벽_직접']} > 주거 {u_limits('중부2', True)['외벽_직접']}")
check("U_VALUE_LIMITS 기본값 = 비주거 (도담 등 공공 비주거가 대부분)",
      U_VALUE_LIMITS["중부2"]["외벽_직접"] == 0.240)

# check_u_value가 용도를 실제로 분기하는가 — 경계값으로 확인
_bnd = 1.2   # 중부2: 비주거 창 1.5 → 적합 / 주거 창 1.0 → 부적합
check("check_u_value가 용도로 갈린다 (창 u=1.2)",
      check_u_value("창", _bnd, "중부2", "direct", is_residential=False)["compliant"] is True
      and check_u_value("창", _bnd, "중부2", "direct", is_residential=True)["compliant"] is False,
      "비주거 적합 / 주거 부적합")
check("알 수 없는 지역은 조용히 넘어가지 않는다", _raises(lambda: u_limits("화성", False)))

print("\n⑫ 대지 외 보정계수 · 완화용 자립률 분리 (별표1 / 별표1 주4)")
import copy as _copy  # noqa: E402
from core.zeb_evaluator import offsite_correction_factor  # noqa: E402

# 보정계수 구간 — 경계값 포함
for _a, _exp in [(5, 0.7), (9.99, 0.7), (10, 0.8), (14.99, 0.8),
                 (15, 0.9), (19.99, 0.9), (20, 1.0), (200, 1.0)]:
    if offsite_correction_factor(_a) != _exp:
        check(f"보정계수 {_a}% → {_exp}", False, f"{offsite_correction_factor(_a)}")
        break
else:
    check("보정계수 4구간 (0.7/0.8/0.9/1.0) 경계 정확", True, "8개 경계값 통과")

# 도담(PV 없음) 회귀 — 보정계수 도입이 기존 결과를 바꾸면 안 된다
check("도담 회귀: 등급용·완화용 자립률 모두 0%",
      _full["autonomy_pct"] == 0.0 and _full["autonomy_pct_onsite_only"] == 0.0)
check("도담 회귀: 여전히 5등급 · 소요량 99.1",
      _full["grade"]["grade"] == "5" and abs(_full["post_energy_kwh_m2"] - 99.08) < 0.1)

# 🔴 대지 외는 보정계수만큼 덜 인정 + 완화용에는 아예 안 잡힌다
_on = _copy.deepcopy(_bim); _on["pv_panels"] = [{"capacity_kw": 20, "onsite": True}]
_off = _copy.deepcopy(_bim); _off["pv_panels"] = [{"capacity_kw": 20, "onsite": False}]
_ron = evaluate_zeb(_on, map_to_gr_elements(_on), assume_full_reinforcement=True, assume_bems=True)
_roff = evaluate_zeb(_off, map_to_gr_elements(_off), assume_full_reinforcement=True, assume_bems=True)

check("같은 20kW라도 대지 외가 자립률이 낮다 (보정계수)",
      _roff["autonomy_pct"] < _ron["autonomy_pct"],
      f"대지내 {_ron['autonomy_pct']}% vs 대지외 {_roff['autonomy_pct']}%")
check("대지 외만 있으면 보정계수 0.7 (대지내 자립률 0%)",
      _roff["offsite_correction_factor"] == 0.7)
check("🔴 완화용 자립률은 대지 외를 빼고 센다 (별표1 주4)",
      _roff["autonomy_pct_onsite_only"] == 0.0 and _roff["autonomy_pct"] > 0,
      f"완화용 {_roff['autonomy_pct_onsite_only']}% vs 등급용 {_roff['autonomy_pct']}%")
check("대지 외면 등급이 실제로 내려간다",
      _roff["grade"]["rank"] < _ron["grade"]["rank"],
      f"{_ron['grade']['label']} → {_roff['grade']['label']}")
check("대지 내는 등급용 = 완화용 (보정 없음)",
      _ron["autonomy_pct"] == _ron["autonomy_pct_onsite_only"]
      and _ron["offsite_correction_factor"] == 1.0)

# onsite 미표기는 대지 내로 (기존 BIM 호환)
_legacy = _copy.deepcopy(_bim); _legacy["pv_panels"] = [{"capacity_kw": 20}]
_rleg = evaluate_zeb(_legacy, map_to_gr_elements(_legacy),
                     assume_full_reinforcement=True, assume_bems=True)
check("onsite 미표기 PV는 대지 내로 간주 (구 BIM 호환)",
      _rleg["autonomy_pct"] == _ron["autonomy_pct"])

print("\n⑬ 주거/비주거 기준표 분기")
res = grade_sensitivity(200.0, building_use="공동주택")
nonres = grade_sensitivity(200.0, building_use="어린이집")
check("주거와 비주거의 임계가 다름",
      [c["임계_절감률_pct"] for c in res["cliffs"]]
      != [c["임계_절감률_pct"] for c in nonres["cliffs"]])

print("\n⑭ ZEB 인증기준 공동고시 원문 ↔ 엔진·params 대조")
# 2026-07-16 원문 확보 전까지 보정계수·등급표의 근거는 팀 학습문서뿐이었다.
# 이제 원문이 있으니, 우리 숫자가 원문과 일치하는지 **원문 파일을 읽어** 검증한다.
_gaz = (Path(__file__).resolve().parent.parent
        / "data" / "policy_docs" / "19_ZEB_인증기준_공동고시.txt")
if not _gaz.exists():
    check("공동고시 원문 파일 존재", False, str(_gaz))
else:
    _t = _gaz.read_text(encoding="utf-8")
    _flat = _t.replace(" ", "")

    # (1) 보정계수 — 원문 별표1 제2호 나목 3)의 네 구간이 그대로 있는가
    check("별표1 보정계수 표 원문에 존재",
          "0.7" in _flat and "0.8" in _flat and "0.9" in _flat
          and "대지외생산량가중치" in _flat)
    from core.zeb_evaluator import offsite_correction_factor as _f
    check("엔진 보정계수 = 원문 구간 (0/10/15/20% 경계)",
          (_f(0), _f(9.99), _f(10), _f(14.9), _f(15), _f(19.9), _f(20), _f(50))
          == (0.7, 0.7, 0.8, 0.8, 0.9, 0.9, 1.0, 1.0))

    # (2) 별표2 등급표 — 비주거 경계 12개가 원문대로 재현되는가
    from core.zeb_evaluator import determine_grade_clause2 as _g
    _boundaries = [(-71, "+"), (-70, "1"), (-31, "1"), (-30, "2"), (9, "2"),
                   (10, "3"), (49, "3"), (50, "4"), (89, "4"), (90, "5"),
                   (129, "5"), (130, "-")]
    _bad = [(n, e, _g(n, is_residential=False)["grade"])
            for n, e in _boundaries if _g(n, is_residential=False)["grade"] != e]
    check("별표2 비주거 등급 경계 12개 일치", not _bad, f"불일치: {_bad}" if _bad else "")
    check("별표2 등급표 원문에 존재", "130미만" in _flat and "-70미만" in _flat)

    # (3) 별표2 주5 — 주거용 정의(기숙사 제외). 기숙사를 주거로 재면 등급이 과소평가된다.
    check("별표2 주5 '기숙사 제외' 원문에 존재", "공동주택(기숙사제외)" in _flat)
    from core.zeb_evaluator import RESIDENTIAL_USES
    check("엔진 주거 목록에 기숙사·오피스텔 없음",
          "기숙사" not in RESIDENTIAL_USES and "오피스텔" not in RESIDENTIAL_USES)

    # (4) 별표1 주4 — 완화 판정용 자립률은 대지 내만
    check("별표1 주4 '건축기준 완화 시 대지 내…만을' 원문에 존재",
          "건축기준완화시대지내" in _flat and "순생산량만을고려" in _flat)

    # (5) 별표1의2 BEMS — 13개 항목이 원문에 모두 있는가
    _bems = ["일반사항", "시스템설치", "데이터수집및표시", "정보감시", "데이터조회",
             "에너지소비현황분석", "설비의성능및효율분석", "실내외환경정보제공",
             "에너지소비예측", "에너지비용조회및분석", "제어시스템연동",
             "종합유지관리", "시스템확장성"]
    _miss = [b for b in _bems if b not in _flat]
    check("별표1의2 BEMS 13항목 전부 원문에 존재", not _miss, f"누락: {_miss}" if _miss else "")

    # (6) 별표4 수수료 — 도담(1,251㎡ 비주거) = 390만원
    from core import params as _PP
    _fee = _PP.get("zeb_incentive", "인증수수료.전용면적구간_원")
    _doam = next(v for u, v in _fee if 1251 < float(u))
    check("도담 인증수수료 = 별표4 원문 390만원", _doam == 3_900_000, f"{_doam:,}원")

    # (7) 원문을 읽고 새로 생긴 숙제가 params에 기록됐는가 (조용히 넘어가지 않았는가)
    _yaml = (Path(__file__).resolve().parent.parent
             / "data" / "params" / "zeb_incentive.yaml").read_text(encoding="utf-8")
    check("별표2 주7 '용도별 보정계수' 미구현이 params에 기록됨",
          "용도별보정계수_제2호" in _yaml and "확인필요_운영세칙미확보" in _yaml)
    check("수수료 환불 적용례 쟁점(2024.12.31)이 params에 기록됨",
          "확인필요_적용례쟁점" in _yaml and "2024.12.31" in _yaml)
    # status: 값만 본다. 본문 산문에는 과거 경위로 '확인필요_원문미확보'가 언급된다.
    import re as _re
    _statuses = _re.findall(r"^\s*status:\s*(\S+)", _yaml, _re.M)
    check("보정계수 status가 원문대조로 승격됨 (원문미확보 status 잔존 없음)",
          "확인필요_원문미확보" not in _statuses, f"현재 status들: {sorted(set(_statuses))}")

print()
if fails:
    print(f"❌ 실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("✅ 전부 통과 — 근거·출처 페이지의 주장이 재현됨")
