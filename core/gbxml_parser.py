# -*- coding: utf-8 -*-
"""
gbXML → 우리 BIM 스키마 파서.

왜 gbXML인가 (2026-07-16 조사 결과)
-----------------------------------
사용자가 "Revit에서 .rvt를 IDF로 빼서 올리자"고 제안했는데, 확인해보니 전제가 틀렸다:

  · **Revit은 IDF를 export하지 않는다.** Revit 2026 Export 목록에 IDF가 없다.
    2014~2016엔 있었고, Insight/Green Building Studio 경로가 있었으나
    **2025-07-01부로 폐지**됐다(Autodesk 공식 공지). 웹에 튜토리얼만 남아 오도된다.
  · Autodesk가 지원하는 유일한 에너지 해석 export는 **gbXML**이다.
    Revit 2026 공식: "To perform energy analysis using other software,
    export the model to gbXML."
  · Revit 2020+ Systems Analysis가 내부적으로 EnergyPlus를 돌려 temp 폴더에 .idf를
    남기지만, Autodesk 공식 문서가 보장하는 건 eplusout.err까지다(비문서화 부산물).

→ 그래서 입력은 **gbXML**로 받는다. 이 파서는 표준 라이브러리(xml.etree)만 쓴다.
   openstudio 패키지(78.7MB)도 검토했으나 wheel이 cp313까지라 우리(3.14)에 설치 불가고,
   OpenStudio의 gbXML 임포트 자체가 Construction을 조용히 누락시키는 알려진 결함이 있다.

한계 (숨기지 않는다)
--------------------
  · gbXML이 U-value를 안 담고 Layer/Material만 담는 경우가 흔하다 → 그때는 u_value=None.
    화면에서 '확인 필요'로 뜨고 사용자가 채워야 한다. 지어내지 않는다.
  · HVAC·신재생은 gbXML 지오메트리 export에 대개 없다 → 사용자 입력으로 보완.
  · 면적은 RectangularGeometry(Width×Height)를 우선 쓰고, 없으면 PolyLoop 3D 폴리곤
    넓이를 뉴웰(Newell) 법으로 계산한다.
"""

import xml.etree.ElementTree as ET
from typing import Optional

# gbXML 표준 네임스페이스. Revit export는 이걸 붙여 나온다.
_NS = {"g": "http://www.gbxml.org/schema"}

# gbXML surfaceType → 우리 스키마 버킷
# (gbXML 스펙 surfaceTypeEnum 기준)
_SURFACE_MAP = {
    "ExteriorWall": ("walls", "exterior_direct"),
    "UndergroundWall": ("walls", "exterior_indirect"),
    "Roof": ("roofs", "exterior_direct"),
    "Ceiling": ("roofs", "exterior_indirect"),
    "UndergroundCeiling": ("roofs", "exterior_indirect"),
    "SlabOnGrade": ("floors", "exterior_indirect"),
    "UndergroundSlab": ("floors", "exterior_indirect"),
    "RaisedFloor": ("floors", "exterior_direct"),
    "ExposedFloor": ("floors", "exterior_direct"),
    # 아래는 외피가 아니라 제외 — 열관류율 판정 대상이 아니다
    "InteriorWall": (None, None),
    "InteriorFloor": (None, None),
    "Shade": (None, None),
    "Air": (None, None),
    "FreestandingColumn": (None, None),
    "EmbeddedColumn": (None, None),
}

# openingType → 창 / 문
_OPENING_WINDOW = {
    "FixedWindow", "OperableWindow", "FixedSkylight", "OperableSkylight",
    "SlidingDoor",          # 유리 슬라이딩 도어는 창호로 본다 (열관류율 기준이 창)
}
_OPENING_DOOR = {"NonSlidingDoor", "Door"}


def _text(el, path: str) -> Optional[str]:
    found = el.find(path, _NS)
    return found.text.strip() if found is not None and found.text else None


def _polygon_area_3d(points: list) -> float:
    """
    3D 폴리곤 넓이 — 뉴웰(Newell) 법.

    gbXML PolyLoop는 임의 평면 위의 점열이라 2D 공식을 못 쓴다.
    법선 벡터를 누적해 그 크기의 절반이 넓이다. 비평면이어도 근사값을 준다
    (OpenStudio는 비평면을 만나면 아예 실패한다 — 우리는 근사하고 넘어간다).
    """
    if len(points) < 3:
        return 0.0
    nx = ny = nz = 0.0
    n = len(points)
    for i in range(n):
        x1, y1, z1 = points[i]
        x2, y2, z2 = points[(i + 1) % n]
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    return (nx * nx + ny * ny + nz * nz) ** 0.5 / 2.0


def _vertices(el) -> list:
    """
    Surface/Opening의 3D 꼭짓점 목록. 없으면 [].

    ⚠️ 면적만 뽑고 좌표를 버리면 **IDF를 쓸 수 없다** — EnergyPlus의
       BuildingSurface:Detailed는 꼭짓점을 요구한다. RectangularGeometry(W×H)만 있는
       면은 좌표가 없으므로 IDF export 대상에서 빠진다(core/idf_writer.py 참고).
    """
    for loop in el.iter():
        if not loop.tag.endswith("PolyLoop"):
            continue
        pts = []
        for cp in loop.findall("g:CartesianPoint", _NS):
            coords = [c.text for c in cp.findall("g:Coordinate", _NS)]
            if len(coords) >= 3:
                try:
                    pts.append(tuple(float(c) for c in coords[:3]))
                except (ValueError, TypeError):
                    pass
        if len(pts) >= 3:
            return pts
    return []


def _geometry_area(el) -> float:
    """Surface/Opening의 면적. RectangularGeometry 우선, 없으면 PolyLoop."""
    rect = el.find("g:RectangularGeometry", _NS)
    if rect is not None:
        w, h = _text(rect, "g:Width"), _text(rect, "g:Height")
        if w and h:
            try:
                return float(w) * float(h)
            except ValueError:
                pass
    pts = _vertices(el)
    return _polygon_area_3d(pts) if pts else 0.0


def _collect_u_values(root) -> dict:
    """
    Construction / WindowType id → U-value(W/㎡·K).

    ⚠️ gbXML이 U-value를 안 담고 Layer/Material만 담는 경우가 흔하다.
       그러면 여기 안 잡히고 u_value=None이 된다 — **추정해서 채우지 않는다.**
       (OpenStudio의 gbXML 임포트가 Construction을 조용히 누락시켜 E+ fatal error를
        내는 알려진 결함과 같은 뿌리다. 우리는 '없음'을 '없음'이라 말한다.)
    """
    out = {}
    for tag in ("Construction", "WindowType", "Layer"):
        for el in root.iter():
            if not el.tag.endswith(tag):
                continue
            cid = el.get("id")
            if not cid:
                continue
            u = _text(el, "g:U-value")
            if u:
                try:
                    out[cid] = float(u)
                except ValueError:
                    pass
    return out


def _DEFAULT_LOCATIONS_HIT(root) -> bool:
    """Revit이 프로젝트 위치를 안 잡았을 때 넣는 기본 좌표(보스턴)인가."""
    loc = root.find(".//g:Location", _NS)
    if loc is None:
        return False
    try:
        lat = float(loc.findtext("g:Latitude", default="", namespaces=_NS))
        lon = float(loc.findtext("g:Longitude", default="", namespaces=_NS))
    except ValueError:
        return False
    return abs(lat - 42.3584) < 0.01 and abs(lon + 71.0598) < 0.01


def parse_gbxml(source) -> dict:
    """
    gbXML(파일 경로·파일객체·bytes·str) → 우리 BIM 스키마 dict.

    Returns:
        core.bim_diagnoser / zeb_evaluator가 그대로 먹는 dict.
        `_meta.gbxml`에 파싱 경위와 **비어 있는 항목**을 남긴다.
    """
    if isinstance(source, bytes):
        root = ET.fromstring(source)
    elif isinstance(source, str) and source.lstrip().startswith("<"):
        root = ET.fromstring(source)
    else:
        root = ET.parse(source).getroot()

    u_by_id = _collect_u_values(root)

    bim = {
        "_meta": {"source": "gbXML", "gbxml": {}},
        "walls": [], "windows": [], "doors": [], "roofs": [], "floors": [],
        "pv_panels": [], "spaces": [],
    }
    skipped = {}

    # 공간(Space) — gbXML이 주는 **존 분할**이다. 예전엔 이걸 통째로 버리고 IDF를
    # 단일 존으로 만들었다. 두 번 손해다:
    #   ① EnergyPlus는 존별 온도·부하를 따로 푸는데 하나로 뭉치면 그 해상도가 사라진다.
    #   ② ECO2의 용도프로필(운영규정 별표2)이 **바로 이 space 단위**로 배정된다.
    #      gbXML의 spaceType이 그 배정의 단서인데 버리면 다시 못 만든다.
    for sp in root.iter():
        if not sp.tag.endswith("Space"):
            continue
        sid = sp.get("id")
        if not sid:
            continue
        area = _text(sp, "g:Area")
        vol = _text(sp, "g:Volume")

        def _f(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        bim["spaces"].append({
            "id": sid,
            "spaceType": sp.get("spaceType"),   # ECO2 용도프로필 배정의 단서
            "area": _f(area),
            "volume": _f(vol),
        })

    for surf in root.iter():
        if not surf.tag.endswith("Surface"):
            continue
        stype = surf.get("surfaceType") or ""
        bucket, facing = _SURFACE_MAP.get(stype, (None, None))

        # 개구부는 surfaceType과 무관하게 먼저 훑는다 (내벽에 붙은 창은 제외)
        if bucket is not None:
            for op in surf.findall("g:Opening", _NS):
                otype = op.get("openingType") or ""
                area = _geometry_area(op)
                if area <= 0:
                    continue
                uid = op.get("windowTypeIdRef") or op.get("constructionIdRef")
                item = {
                    "id": op.get("id") or f"OP{len(bim['windows'])+1}",
                    "area": round(area, 2),
                    "facing": facing,
                    "u_value": u_by_id.get(uid),
                    "type": otype or None,
                    "vertices": _vertices(op),      # IDF 생성용 — 없으면 []
                    "host": surf.get("id"),         # 창이 붙은 벽 (IDF 부모면)
                }
                if otype in _OPENING_DOOR:
                    bim["doors"].append(item)
                else:
                    bim["windows"].append(item)

        if bucket is None:
            if stype:
                skipped[stype] = skipped.get(stype, 0) + 1
            continue

        area = _geometry_area(surf)
        # 개구부 면적은 벽 면적에서 뺀다 (gbXML Surface는 창을 포함한 총면적)
        op_area = sum(_geometry_area(o) for o in surf.findall("g:Opening", _NS))
        net = max(area - op_area, 0.0)
        if net <= 0:
            continue

        adj = surf.find("g:AdjacentSpaceId", _NS)
        entry = {
            "id": surf.get("id") or f"S{len(bim[bucket])+1}",
            "area": round(net, 2),
            "u_value": u_by_id.get(surf.get("constructionIdRef")),
            "vertices": _vertices(surf),        # IDF 생성용 — 없으면 []
            "surface_type": stype,              # IDF BuildingSurface 종류 매핑용
            "space": adj.get("spaceIdRef") if adj is not None else None,   # 소속 존
        }
        if bucket == "walls":
            entry["facing"] = facing
            entry["insulated"] = None      # gbXML은 '단열 여부'를 안 담는다 → 사용자 확인
        elif bucket == "roofs":
            entry["insulated"] = None
        elif bucket == "floors":
            entry["insulated"] = None
        bim[bucket].append(entry)

    # 건물 정보
    for b in root.iter():
        if b.tag.endswith("Building"):
            a = _text(b, "g:Area")
            if a:
                try:
                    bim["total_area_m2"] = float(a)
                except ValueError:
                    pass
            if b.get("buildingType"):
                bim["_meta"]["gbxml"]["buildingType"] = b.get("buildingType")
            break

    # ── Revit 해석 모델이 만들어졌는가 ──────────────────────────────
    # 2026-07-17 실제 도담 Revit export(1,251㎡)를 넣었더니 해석 공간이 **15㎡**뿐이었고
    # 나머지 99%가 Shade 377개로 빠졌다. 그런데 화면엔 "walls 6개"라고만 떠서 멀쩡해 보였다.
    # 세어만 놓고 판단을 안 하면 사용자는 쓰레기를 받아들고 모른다.
    _envelope = sum(len(bim[k]) for k in ("walls", "roofs", "floors"))
    _shade = int(skipped.get("Shade", 0))
    blockers = []
    if _envelope and _shade > _envelope * 3:
        blockers.append(
            f"외피 {_envelope}면 대비 **차양(Shade) {_shade}면** — Revit이 건물을 "
            f"닫힌 공간으로 인식하지 못하고 대부분을 차양으로 내보냈습니다. "
            f"Revit [해석] 탭 > 에너지 설정에서 해석 모델을 먼저 만드세요."
        )
    _sp_area = sum(float(s.get("area") or 0) for s in bim["spaces"])
    if bim["spaces"] and _sp_area < 50:
        blockers.append(
            f"해석 공간 총 면적이 **{_sp_area:,.1f}㎡** ({len(bim['spaces'])}개)뿐입니다 — "
            f"건물 전체가 아니라 일부만 인식된 export입니다."
        )
    if _DEFAULT_LOCATIONS_HIT(root):
        blockers.append(
            "Location이 Revit 기본값(미국 보스턴 42.36°N / -71.06°E)입니다 — "
            "프로젝트 위치가 설정되지 않았습니다. (우리는 .epw를 따로 쓰므로 해석 자체엔 "
            "영향이 없지만, 이 export가 기본 설정 그대로라는 신호입니다.)"
        )

    # 무엇이 안 채워졌는지 드러낸다 — 조용히 0으로 두면 진단이 조용히 틀린다
    missing = []
    if not bim.get("total_area_m2"):
        missing.append("total_area_m2 (Building/Area 없음)")
    if not any(x["u_value"] is not None for x in bim["walls"] + bim["roofs"] + bim["floors"]):
        missing.append("열관류율 (Construction에 U-value 없음 — Layer/Material만 담긴 gbXML)")
    if not bim["windows"]:
        missing.append("창호 (Opening 없음)")
    for key in ("region", "building_year", "directly_owned"):
        missing.append(f"{key} (gbXML에 없는 정보 — 사용자 입력 필요)")
    missing.append("hvac·pv_panels (지오메트리 export엔 대개 없음 — 사용자 입력 필요)")

    bim["_meta"]["gbxml"].update({
        "surfaces": {k: len(bim[k]) for k in ("walls", "windows", "doors", "roofs", "floors")},
        "skipped_surface_types": skipped,
        "missing": missing,
        # 🔴 '값이 없다'가 아니라 **'이 export를 쓰면 안 된다'** — 성격이 다르다.
        "blockers": blockers,
        "space_area_m2": round(_sp_area, 2),
        "note": (
            "Revit → File > Export > gbXML 로 내보낸 파일입니다. "
            "Revit은 IDF를 직접 export하지 않으며(2026 기준), Insight/GBS 경로는 2025-07-01 폐지."
        ),
    })
    return bim
