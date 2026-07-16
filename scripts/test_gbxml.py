"""
scripts/test_gbxml.py — gbXML 파서 검증
========================================
사용자가 "JSON 말고 Revit에서 뽑은 파일을 직접 받자"고 해서 만든 경로다.

조사 결과 Revit이 실제로 내보내는 건 **gbXML**이다 (IDF 아님 — Revit 2026 Export 목록에
IDF가 없고, Insight/GBS 경로는 2025-07-01 폐지). 그래서 gbXML을 받는다.

여기서 지키는 것:
  · 면적 산출이 맞는가 (창·문을 벽에서 빼는가, PolyLoop를 3D로 재는가)
  · 외피가 아닌 면(내벽·차양)을 걸러내는가 — 걸러야 열관류율 판정이 안 오염된다
  · **U-value가 없으면 None으로 두는가** — 지어내면 진단이 조용히 틀린다
  · 무엇이 안 채워졌는지 드러내는가
"""

import io
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from core.gbxml_parser import parse_gbxml, _polygon_area_3d  # noqa: E402

fails = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)


FIXTURE = PROJECT_ROOT / "data" / "sample_bim" / "doam_sample.gbxml"

print("=" * 70)
print("gbXML 파서")
print("=" * 70)

print("\n① 3D 폴리곤 넓이 (뉴웰 법)")
# 수직 평면 10x10 — 2D 공식으로는 못 푸는 형태
check("수직 사각형 10×10 = 100",
      abs(_polygon_area_3d([(0, 0, 0), (10, 0, 0), (10, 0, 10), (0, 0, 10)]) - 100.0) < 1e-6)
# 수평 삼각형
check("수평 삼각형 = 0.5",
      abs(_polygon_area_3d([(0, 0, 0), (1, 0, 0), (0, 1, 0)]) - 0.5) < 1e-6)
check("점 2개면 0 (파탄 방지)", _polygon_area_3d([(0, 0, 0), (1, 1, 1)]) == 0.0)

print("\n② 픽스처 파싱")
bim = parse_gbxml(FIXTURE)
check("연면적 = Building/Area", bim.get("total_area_m2") == 1251.0, str(bim.get("total_area_m2")))

walls = {w["id"]: w for w in bim["walls"]}
check("외벽 2개", len(walls) == 2, f"{len(walls)}개")
# 40×10=400에서 창 50(20×2.5)·문 5(2×2.5)를 빼야 345
check("창·문 면적을 벽에서 뺀다 (400−50−5=345)",
      abs(walls["su-wall-1"]["area"] - 345.0) < 0.01, f'{walls["su-wall-1"]["area"]}㎡')
check("PolyLoop 벽 = 100㎡ (RectangularGeometry 없이)",
      abs(walls["su-wall-2"]["area"] - 100.0) < 0.01, f'{walls["su-wall-2"]["area"]}㎡')

check("창 1개 · 50㎡ · U=1.5",
      len(bim["windows"]) == 1 and abs(bim["windows"][0]["area"] - 50.0) < 0.01
      and bim["windows"][0]["u_value"] == 1.5)
check("문은 창과 분리 (U=2.4)",
      len(bim["doors"]) == 1 and bim["doors"][0]["u_value"] == 2.4)
check("지붕 600㎡ · U=0.15",
      len(bim["roofs"]) == 1 and abs(bim["roofs"][0]["area"] - 600.0) < 0.01
      and bim["roofs"][0]["u_value"] == 0.15)

print("\n③ 외피가 아닌 면은 걸러진다")
# 내벽을 벽으로 세면 열관류율 판정이 오염되고, 내벽에 붙은 창이 창호 면적을 부풀린다
check("내벽이 walls에 안 들어감", "su-int-1" not in walls)
check("내벽에 붙은 창이 windows에 안 들어감",
      all(w["id"] != "op-int-win" for w in bim["windows"]),
      f'{[w["id"] for w in bim["windows"]]}')
check("차양(Shade)이 안 들어감",
      not any("shade" in s["id"] for k in ("walls", "roofs", "floors") for s in bim[k]))
skipped = bim["_meta"]["gbxml"]["skipped_surface_types"]
check("건너뛴 타입을 기록한다", skipped.get("InteriorWall") == 1 and skipped.get("Shade") == 1,
      str(skipped))

print("\n④ 없는 값은 지어내지 않는다")
# 🔴 이게 핵심이다. gbXML은 U-value 없이 Layer/Material만 담는 경우가 흔하다.
#    거기서 기본값을 넣으면 '측정한 값'처럼 보이면서 진단이 조용히 틀린다.
floor = bim["floors"][0]
check("U-value 없는 Construction → u_value=None (기본값 주입 금지)",
      floor["u_value"] is None, f'{floor["u_value"]}')
check("단열 여부는 gbXML에 없다 → None",
      all(w.get("insulated") is None for w in bim["walls"]))
missing = bim["_meta"]["gbxml"]["missing"]
check("gbXML에 없는 정보를 missing에 드러낸다",
      any("region" in m for m in missing) and any("hvac" in m for m in missing),
      f"{len(missing)}건")

print("\n⑤ 입력 형태 (경로·bytes·str)")
raw = FIXTURE.read_bytes()
check("bytes 입력", parse_gbxml(raw).get("total_area_m2") == 1251.0)
check("str 입력", parse_gbxml(raw.decode("utf-8")).get("total_area_m2") == 1251.0)
check("파일객체 입력", parse_gbxml(io.BytesIO(raw)).get("total_area_m2") == 1251.0)

print("\n⑥ 엔진이 이 dict를 그대로 먹는가")
# 파서가 아무리 정확해도 엔진이 못 먹으면 의미 없다
from core.bim_diagnoser import map_to_gr_elements  # noqa: E402
try:
    el = map_to_gr_elements(bim)
    check("bim_diagnoser.map_to_gr_elements() 통과", isinstance(el, dict))
except Exception as e:
    check("bim_diagnoser.map_to_gr_elements() 통과", False, f"{type(e).__name__}: {e}")

print("\n⑦ 업로드 → 진단 완주 (UI 경로 그대로)")
# 파서만 맞고 업로드 경계에서 끊기면 사용자에겐 아무 소용이 없다.
# Streamlit UploadedFile을 흉내내 save_uploaded_to_temp → 진단까지 실제로 돌린다.


class _FakeUpload:
    def __init__(self, path):
        self.name = Path(path).name
        self._b = Path(path).read_bytes()

    def getvalue(self):
        return self._b


from modes.mode3_bim import GBXML_SUFFIXES, save_uploaded_to_temp  # noqa: E402

tmp = save_uploaded_to_temp(_FakeUpload(FIXTURE))
check("gbXML 업로드가 JSON으로 변환돼 저장됨", Path(tmp).suffix == ".json", Path(tmp).suffix)
check(".gbxml·.xml 둘 다 gbXML로 취급", set(GBXML_SUFFIXES) == {".gbxml", ".xml"})

from modes.mode3_bim import run_bim_diagnosis  # noqa: E402

try:
    res = run_bim_diagnosis(tmp, with_roi=True, duration_months=8)
    check("진단이 끝까지 완주 (score·roi_plan 산출)",
          "score" in res and "roi_plan" in res, str(list(res))[:60])
    _sc = res.get("score") or {}
    # gbXML엔 HVAC·신재생이 없으니 JSON 케이스보다 미평가가 많아야 정상이다.
    # 0건이면 오히려 어딘가에서 기본값을 지어내고 있다는 뜻이다.
    check("gbXML에 없는 항목이 '미평가'로 잡힌다 (기본값 주입 안 함)",
          len(_sc.get("_미평가") or []) > 0, f'미평가 {len(_sc.get("_미평가") or [])}건')
except Exception as e:
    check("진단이 끝까지 완주", False, f"{type(e).__name__}: {e}")

print()
if fails:
    print(f"❌ 실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("✅ 전부 통과 — gbXML → 우리 스키마 변환이 재현됨")
