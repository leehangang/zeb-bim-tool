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

print("\n⑥-b 존(Space)을 버리지 않는가")
# 🔴 gbXML은 <Space spaceType>과 면의 <AdjacentSpaceId>로 **존 분할**을 준다.
#    파서가 이걸 통째로 버리고 IDF를 단일 존으로 만들고 있었다. 두 번 손해다:
#    ① E+는 존별로 온도·부하를 따로 푸는데 하나로 뭉치면 그 해상도가 사라진다
#    ② ECO2 용도프로필(운영규정 별표2)이 **바로 이 space 단위**로 배정된다 —
#       gbXML spaceType이 그 배정의 단서인데 버리면 다시 못 만든다
check("Space를 읽는다", len(bim.get("spaces") or []) == 1, str(bim.get("spaces")))
check("spaceType을 보존한다 (ECO2 용도프로필 배정 단서)",
      bim["spaces"][0].get("spaceType") == "DayCare")
check("면이 소속 존을 안다 (AdjacentSpaceId)",
      walls["su-wall-1"].get("space") == "sp-1", str(walls["su-wall-1"].get("space")))

from core.idf_writer import write_idf  # noqa: E402

# 존이 **여럿일 때**가 진짜 관건 — 단일 존이면 버그가 안 드러난다
_multi = {
    "_meta": {}, "spaces": [{"id": "A", "spaceType": "Classroom"},
                            {"id": "B", "spaceType": "Office"}],
    "walls": [
        {"id": "wA", "area": 10, "u_value": 0.24, "space": "A",
         "surface_type": "ExteriorWall", "vertices": [(0, 0, 0), (5, 0, 0), (5, 0, 2), (0, 0, 2)]},
        {"id": "wB", "area": 10, "u_value": 0.24, "space": "B",
         "surface_type": "ExteriorWall", "vertices": [(0, 5, 0), (5, 5, 0), (5, 5, 2), (0, 5, 2)]},
    ],
    "roofs": [], "floors": [], "windows": [], "doors": [],
}
_rm = write_idf(_multi)
_i = _rm["idf"]
check("존 2개가 각각 Zone으로 나감", _i.count("\nZone,\n") == 2, f'{_i.count(chr(10)+"Zone,"+chr(10))}개')
check("각 면이 자기 존에 붙는다", "    A,   !- Zone Name" in _i and "    B,   !- Zone Name" in _i)
# 존이 여럿인데 설비를 하나만 쓰면, 빠진 존은 온도제어가 없어 E+가 부하를 0으로 낸다
check("존마다 IdealLoads가 있다", "IDEAL_A" in _i and "IDEAL_B" in _i)
check("존마다 온도제어가 있다", "TSTAT_A" in _i and "TSTAT_B" in _i)
check("존마다 내부부하가 있다", "LGT_A" in _i and "LGT_B" in _i)
check("spaceType을 IDF 주석에 남긴다", "spaceType: Classroom" in _i)


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

print("\n⑧ 좌표 보존 (IDF 생성의 전제)")
# 면적만 뽑고 좌표를 버리면 IDF를 못 쓴다 — BuildingSurface:Detailed가 꼭짓점을 요구한다.
check("벽에 꼭짓점이 남는다", len(walls["su-wall-1"].get("vertices") or []) == 4)
check("창에 꼭짓점이 남는다", len(bim["windows"][0].get("vertices") or []) == 4)
check("창이 어느 벽에 붙었는지(host) 남는다",
      bim["windows"][0].get("host") == "su-wall-1", str(bim["windows"][0].get("host")))
check("RectangularGeometry가 있어도 면적은 Rect, 좌표는 PolyLoop에서",
      abs(walls["su-wall-1"]["area"] - 345.0) < 0.01
      and len(walls["su-wall-1"]["vertices"]) == 4)

print("\n⑨ IDF 생성 (EnergyPlus = GR 센터 지정 프로그램)")
from core.idf_writer import EP_VERSION, _material_r, write_idf  # noqa: E402

# U → 재료 R 역산이 왕복해야 한다. 표면열저항을 안 빼면 단열이 실제보다 좋게 나온다.
for u, kind, rsurf in ((0.24, "wall", 0.17), (0.15, "roof", 0.14)):
    r = _material_r(u, kind)
    check(f"U={u} {kind} → R 역산 왕복 (표면열저항 {rsurf} 차감)",
          abs(1.0 / (r + rsurf) - u) < 1e-6, f"R={r:.4f} → U={1/(r+rsurf):.4f}")
check("U가 커도 R이 음수로 안 감 (E+ 거부 방지)", _material_r(50.0, "wall") > 0)

res = write_idf(bim)
idf = res["idf"]
check("IDF 텍스트 생성", len(idf) > 1000 and idf.lstrip().startswith("!-"))
# 존 이름은 이제 gbXML space id다 (예전엔 ZONE_1 하드코딩) — 그래야 ECO2 용도프로필과
# 대응이 붙는다. ZONE_1 fallback은 AdjacentSpaceId가 없는 gbXML에만 쓴다.
# 버전은 EP_VERSION에서 끌어온다 — "26.1;"로 박아뒀다가 서비스(25.1)와 어긋난 걸
# 놓쳤다. 이미지 태그와의 일치는 test_eplus가 지킨다.
check("Version·Zone·GlobalGeometryRules 포함",
      f"Version, {EP_VERSION};" in idf and "Zone,\n    sp-1" in idf
      and "GlobalGeometryRules" in idf)
check("외피가 BuildingSurface:Detailed로 나감",
      idf.count("BuildingSurface:Detailed") == 3, f'{idf.count("BuildingSurface:Detailed")}개')
check("창·문이 FenestrationSurface:Detailed로 나감 (2개)",
      idf.count("FenestrationSurface:Detailed") == 2,
      f'{idf.count("FenestrationSurface:Detailed")}개')
check("개구부가 부모 벽에 붙는다 (Building Surface Name = host)",
      "su-wall-1," in idf.split("FenestrationSurface:Detailed")[1][:200])
check("창호는 SimpleGlazingSystem으로 U를 그대로 (역산 안 함)",
      "WindowMaterial:SimpleGlazingSystem" in idf and "1.5," in idf)
check("설정온도가 ZEB 별표3과 같다 (냉방26·난방20)",
      "20.0" in idf and "26.0" in idf)

# 🔑 U를 모르는 면은 IDF에서 빠져야 한다. 기본값을 넣으면 E+가 '측정된 것처럼' 답한다.
check("U-value 미상 면은 IDF에서 제외 + skipped에 기록",
      any("su-floor-1" in s for s in res["skipped"]) and "su-floor-1" not in idf,
      f'skipped={res["skipped"]}')
check("빠진 면을 조용히 버리지 않는다", len(res["skipped"]) > 0)
check("SHGC 가정을 warnings에 남긴다",
      any("SHGC" in w for w in res["warnings"]), f'{res["warnings"]}')

# 🔑 바닥이 빠지면 존 면적이 0 → 조명·기기·재실 부하가 전부 0인데 해석은 '성공'한다.
# 2026-07-17 첫 성공 실행이 정확히 이 상태였다 (Electricity:Facility = 0.0 kWh).
check("바닥 없는 존을 경고한다 (해석 성공 ≠ 맞는 값)",
      any("존 면적이 0" in w for w in res["warnings"]), f'{res["warnings"]}')

# 🔴 만들어놓고 화면이 안 그리면 없는 것과 같다 — 실제로 warnings를 한 번도 안 그리고
#    있었다. skipped만 그리고 warnings는 통째로 빠져 있었다.
import re  # noqa: E402

_ui = (PROJECT_ROOT / "modes" / "mode3_bim.py").read_text(encoding="utf-8")
check("화면이 _idf['warnings']를 실제로 그린다", '_idf["warnings"]' in _ui)

# 화면 안내가 낡으면 기능이 있어도 못 찾는다. 실제로 gbXML·에너지해석을 붙여놓고
# 상단 안내는 "Dynamo로 추출한 BIM JSON 업로드"에 멈춰 있어 사용자가 헤맸다.
# (표시 문자열은 사용자가 읽는 유일한 계약이다 — 소스만 맞으면 되는 게 아니다.)
_intro = _ui.split("st.expander(", 1)[0]     # 헤더 영역만
check("상단 안내가 gbXML을 첫 입력으로 말한다",
      "gbXML" in _intro and "Dynamo로 추출한 BIM JSON 업로드" not in _intro)
check("상단 안내가 EnergyPlus 해석까지 한다고 말한다", "EnergyPlus" in _intro)
check("업로더 라벨이 gbXML을 권장으로 표시", "gbXML**(권장)" in _ui or "gbXML**(권장" in _ui)
check("두 입력이 다른 결과를 준다는 걸 화면이 설명한다",
      "에너지 해석 불가" in _ui or "에너지 해석은 안 됩니다" in _ui)

# 데모 버튼에 걸린 파일이 실제로 있어야 한다. 없으면 클릭하는 순간 죽는다.
# (칸 수를 넘겨 데모를 조용히 밀어낸 적이 있어 개수도 같이 지킨다.)
_samples = re.findall(r'\("([\w.]+\.(?:json|gbxml))",', _ui)
check(f"데모 케이스 {len(_samples)}개가 전부 실재하는 파일",
      all((PROJECT_ROOT / "data" / "sample_bim" / f).exists() for f in _samples),
      f'{[f for f in _samples if not (PROJECT_ROOT / "data" / "sample_bim" / f).exists()]}')
check("gbXML 데모가 최소 1개 있다 (에너지 해석을 눌러볼 수 있어야 한다)",
      any(f.endswith(".gbxml") for f in _samples), f'{_samples}')
check("데모 칸 수를 하드코딩하지 않는다 (st.columns(3)에 4개 넣다 하나 잃었다)",
      "st.columns(len(samples))" in _ui)

# ── 쓸 수 없는 export를 '쓸 수 없다'고 말하는가 ──────────────────────────
# 2026-07-17 실제 도담 Revit export: 1,251㎡ 건물인데 해석 공간이 15㎡, 나머지 99%가
# Shade 377면. 그런데 화면엔 "walls 6개"만 떠서 멀쩡해 보였다. 세어놓고 판단을 안 했다.
_BAD = """<gbXML xmlns="http://www.gbxml.org/schema" version="7.03">
  <Campus id="c">
    <Location><Latitude>42.358429</Latitude><Longitude>-71.0597763</Longitude></Location>
    <Building id="b" buildingType="Office"><Area>14.96</Area>
      <Space id="s1"><Area>5.25</Area></Space>
    </Building>
    <Surface id="w1" surfaceType="ExteriorWall" constructionIdRef="c1">
      <AdjacentSpaceId spaceIdRef="s1"/>
      <RectangularGeometry><Width>2</Width><Height>2</Height></RectangularGeometry>
    </Surface>
    {shades}
  </Campus>
  <Construction id="c1"><U-value unit="WPerSquareMeterK">0.81</U-value></Construction>
</gbXML>"""
_shade_xml = "".join(
    f'<Surface id="sh{i}" surfaceType="Shade">'
    f"<RectangularGeometry><Width>1</Width><Height>1</Height></RectangularGeometry></Surface>"
    for i in range(30)
)
_bad = parse_gbxml(_BAD.format(shades=_shade_xml))["_meta"]["gbxml"]
check("차양이 외피를 압도하면 막는다 (해석 모델 미생성)",
      any("차양" in b for b in _bad["blockers"]), f'{len(_bad["blockers"])}건')
check("해석 공간이 건물이라 하기엔 너무 작으면 막는다",
      any("일부만 인식" in b for b in _bad["blockers"]))
check("Revit 기본 위치(보스턴)를 알아챈다",
      any("보스턴" in b for b in _bad["blockers"]))
check("blockers를 화면이 접지 않고 st.error로 띄운다",
      '_g.get("blockers")' in _ui and "st.error(" in _ui)

# 🔑 오탐이 나면 정상 파일도 막혀 아무도 못 쓴다
check("정상 gbXML엔 blockers가 없다 (오탐 금지)",
      parse_gbxml(FIXTURE)["_meta"]["gbxml"]["blockers"] == [],
      f'{parse_gbxml(FIXTURE)["_meta"]["gbxml"]["blockers"]}')
_full = PROJECT_ROOT / "data" / "sample_bim" / "demo_daycare_full.gbxml"
check("데모 gbXML에도 blockers가 없다",
      parse_gbxml(str(_full))["_meta"]["gbxml"]["blockers"] == [])
check("바닥 누락 경고는 접지 않고 본문에 띄운다 (조용한 실패라서)",
      '"존 면적이 0" in w' in _ui and "st.warning(" in _ui)

# 좌표 없는 면은 IDF에 못 넣는다 — 우리 JSON 스키마(면적만)로 IDF를 만들면 안 되는 이유
_no_geom = {"walls": [{"id": "X1", "area": 10.0, "u_value": 0.2, "vertices": []}],
            "roofs": [], "floors": [], "windows": [], "doors": [], "_meta": {}}
_r2 = write_idf(_no_geom)
check("좌표 없는 면은 IDF 제외 (지오메트리 지어내지 않음)",
      "BuildingSurface:Detailed,\n    X1" not in _r2["idf"]
      and any("좌표 없음" in s for s in _r2["skipped"]))

print()
if fails:
    print(f"❌ 실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("✅ 전부 통과 — gbXML → 우리 스키마 → IDF 생성이 재현됨")
