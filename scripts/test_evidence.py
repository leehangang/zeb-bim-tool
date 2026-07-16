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

print("\n⑨ 주거/비주거 기준표 분기")
res = grade_sensitivity(200.0, building_use="공동주택")
nonres = grade_sensitivity(200.0, building_use="어린이집")
check("주거와 비주거의 임계가 다름",
      [c["임계_절감률_pct"] for c in res["cliffs"]]
      != [c["임계_절감률_pct"] for c in nonres["cliffs"]])

print()
if fails:
    print(f"❌ 실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("✅ 전부 통과 — 근거·출처 페이지의 주장이 재현됨")
