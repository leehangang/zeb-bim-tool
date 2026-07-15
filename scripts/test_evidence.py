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

print("\n⑤ 주거/비주거 기준표 분기")
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
