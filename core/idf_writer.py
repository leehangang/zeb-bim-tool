# -*- coding: utf-8 -*-
"""
우리 BIM 스키마 → EnergyPlus IDF 생성기.

왜 만드는가
-----------
2026 민간 GR 이자지원 공고 p.16 축자:
    "에너지 시뮬레이션은 그린리모델링 창조센터에서 지정한 에너지 시뮬레이션 프로그램 사용
     (지정 에너지 시뮬레이션 : ECO2, ECO2-OD, GR-E, Energy Studio, **EnergyPlus**, IES-VE)"
→ **EnergyPlus는 센터 지정 프로그램**이다. 우리 GR 성능개선비율에 붙어 있는
  "지정 프로그램이 아니라 참고용" 딱지를, 사용자가 이 IDF를 EnergyPlus로 돌려
  결과를 되올리면 뗄 수 있다.
  (Track A인 ZEB 인증은 ECO2라 EnergyPlus로는 인증 숫자가 나오지 않는다 — 두 트랙이 다르다.)

왜 우리가 직접 쓰는가 (eppy·openstudio를 안 씀)
-----------------------------------------------
· **eppy는 시뮬레이터가 아니다.** IDF 편집기이고, IDF를 다루려면 Energy+.idd가 필요한데
  eppy 동봉 IDD는 최신이 V9_2_0(2019)이라 현행 E+ 26.1보다 7년 낡았다.
  우리는 IDF를 *편집*하는 게 아니라 *생성*하므로 텍스트 출력이면 충분하다.
· openstudio wheel은 cp313까지라 우리(3.14)에 설치 불가. 게다가 그 gbXML 임포트가
  Construction을 조용히 누락시키는 알려진 결함이 있다.

한계 (숨기지 않는다)
--------------------
· **좌표가 있는 면만 쓴다.** RectangularGeometry(W×H)만 있고 PolyLoop가 없는 면은
  IDF에 못 넣는다 — BuildingSurface:Detailed는 꼭짓점을 요구한다. 빠진 면은 반환값의
  `skipped`에 남긴다. (그래서 IDF export는 gbXML 입력에서만 가능하다. 우리 JSON 스키마는
  면적만 있어 지오메트리를 지어내야 하는데, 그건 하지 않는다.)
· **HVAC은 IdealLoads**다. 실제 설비(EHP 등)를 모델링하지 않고 부하만 뽑는다.
  성능개선비율은 개선 전/후의 상대비라 IdealLoads로도 방향은 유효하나,
  실제 신청 시엔 설비 모델링이 필요하다.
· 일정(재실·조명·기기)은 **어린이집 표준 가정**이며 원문 근거가 없다.
  재실 0.1인/㎡(=10㎡/인), 조명 10W/㎡, 기기 5W/㎡, 대사량 120W/인.
· 기상파일은 추풍령(471350) TMYx 하나뿐이다 — 김천 최근접이지 김천이 아니다.

2026-07-17 첫 실제 EnergyPlus 실행에서 잡은 것 (그 전엔 파싱만 통과한 상태였다)
------------------------------------------------------------------------------
· Zone 11번 필드(Zone Inside Convection Algorithm)에 autocalculate → Severe.
  autocalculate는 면적·체적 같은 수치 필드에만 쓴다. enum 자리엔 못 쓴다.
· People 13번 필드(Mean Radiant Temperature Calculation Type)에 autocalculate → Severe.
· People의 Activity Level Schedule Name이 빈칸이었다 — 필수 필드다.
· Version이 26.1인데 서비스는 25.1을 돈다 → EP_VERSION 상수로 묶고 테스트가 지킨다.
"""

import re
from typing import Optional

# EnergyPlus 버전. energyplus_service의 이미지 태그(nrel/energyplus:25.1.0)와
# **반드시 일치해야 한다** — 어긋나면 E+가 "Version: in IDF not the same as expected"
# 경고를 내고, 스키마가 바뀐 버전이면 조용히 틀린 결과가 나온다.
# scripts/test_eplus.py가 이 상수와 Dockerfile·modal_app 태그의 일치를 검사한다.
EP_VERSION = "25.1"

# ISO 6946 표면열저항 (㎡·K/W) — U에서 재료 R을 역산할 때 뺀다.
# 이걸 안 빼면 재료 R을 과대평가해 실제보다 단열이 좋게 나온다.
_R_SURFACE = {
    "wall": 0.13 + 0.04,      # 수평 열류: Rsi 0.13 + Rse 0.04
    "roof": 0.10 + 0.04,      # 상향 열류
    "floor": 0.17 + 0.00,     # 하향 열류 · 지면접지는 외기 Rse 없음
}
_R_MIN = 0.01                 # Material:NoMass 최소 R (E+ 요구)

# gbXML surfaceType → (IDF Surface Type, Outside Boundary Condition, Sun/Wind)
_IDF_SURFACE = {
    "ExteriorWall":     ("Wall",    "Outdoors",   "SunExposed",   "WindExposed"),
    "UndergroundWall":  ("Wall",    "Ground",     "NoSun",        "NoWind"),
    "Roof":             ("Roof",    "Outdoors",   "SunExposed",   "WindExposed"),
    "Ceiling":          ("Ceiling", "Adiabatic",  "NoSun",        "NoWind"),
    "UndergroundCeiling": ("Ceiling", "Ground",   "NoSun",        "NoWind"),
    "SlabOnGrade":      ("Floor",   "Ground",     "NoSun",        "NoWind"),
    "UndergroundSlab":  ("Floor",   "Ground",     "NoSun",        "NoWind"),
    "RaisedFloor":      ("Floor",   "Outdoors",   "NoSun",        "WindExposed"),
    "ExposedFloor":     ("Floor",   "Outdoors",   "NoSun",        "WindExposed"),
}


def _material_r(u_value: float, kind: str) -> float:
    """U-value(W/㎡·K) → Material:NoMass의 Thermal Resistance(㎡·K/W)."""
    r_total = 1.0 / float(u_value)
    return max(r_total - _R_SURFACE.get(kind, 0.17), _R_MIN)


def _fmt_vertices(pts: list) -> str:
    return ",\n".join(f"    {x:.4f}, {y:.4f}, {z:.4f}" for x, y, z in pts)


def _zone_of(item: dict, fallback: str) -> str:
    """면이 속한 존 이름. gbXML AdjacentSpaceId가 있으면 그걸 쓴다."""
    sid = item.get("space")
    return _safe(sid) if sid else fallback


def _safe(name: str) -> str:
    """IDF 이름에 쉼표·세미콜론이 들어가면 필드가 깨진다."""
    return re.sub(r"[,;!]", "_", str(name)).strip()


def write_idf(
    bim: dict,
    zone_name: str = "ZONE_1",
    ep_version: str = EP_VERSION,
    weather_hint: str = "김천(경북) — 추풍령 471350 최근접 (.epw 필요)",
) -> dict:
    """
    BIM dict(gbXML 파서 산출) → IDF 텍스트.

    Returns:
        {"idf": str, "skipped": [...], "warnings": [...], "stats": {...}}
        · skipped — 좌표가 없어 IDF에 못 넣은 면 (조용히 버리지 않는다)
        · warnings — U-value 미상 등, 사용자가 알아야 할 것
    """
    out, skipped, warnings = [], [], []

    surfaces = []          # (item, kind, gbxml_type)
    for item in bim.get("walls") or []:
        surfaces.append((item, "wall", item.get("surface_type") or "ExteriorWall"))
    for item in bim.get("roofs") or []:
        surfaces.append((item, "roof", item.get("surface_type") or "Roof"))
    for item in bim.get("floors") or []:
        surfaces.append((item, "floor", item.get("surface_type") or "SlabOnGrade"))

    # ── 헤더 ────────────────────────────────────────────────────────
    out.append(f"""!-  ==========================================================
!-  ZEB-ROI 자동 생성 IDF
!-  출처: {bim.get('_meta', {}).get('source', 'unknown')} → core/idf_writer.py
!-  ⚠️ 이 파일은 **자동 변환 결과**입니다. 그대로 신청서에 쓰지 마세요.
!-     · 단일 존(Zone)으로 단순화 — gbXML Space 분할 미반영
!-     · HVAC은 IdealLoads (실제 설비 미모델링) → 부하만 산출
!-     · 재실·조명·기기 일정은 어린이집 표준 가정 (원문 근거 없음)
!-     · 날씨 파일(.epw)은 별도 필요: {weather_hint}
!-  GR 성능개선비율은 EnergyPlus가 센터 지정 프로그램이므로 인정 대상입니다
!-  (2026 민간 GR 공고 p.16). ZEB 인증은 ECO2라 이 결과로는 안 됩니다.
!-  ==========================================================

Version, {ep_version};

SimulationControl,
    No,                      !- Do Zone Sizing Calculation
    No,                      !- Do System Sizing Calculation
    No,                      !- Do Plant Sizing Calculation
    No,                      !- Run Simulation for Sizing Periods
    Yes;                     !- Run Simulation for Weather File Run Periods

Building,
    {bim.get('_meta', {}).get('gbxml', {}).get('buildingType', 'Building')},  !- Name
    0.0,                     !- North Axis {{deg}}
    City,                    !- Terrain
    0.04,                    !- Loads Convergence Tolerance Value
    0.4,                     !- Temperature Convergence Tolerance Value {{deltaC}}
    FullExterior,            !- Solar Distribution
    25;                      !- Maximum Number of Warmup Days

Timestep, 6;

GlobalGeometryRules,
    UpperLeftCorner,         !- Starting Vertex Position
    Counterclockwise,        !- Vertex Entry Direction
    World;                   !- Coordinate System

RunPeriod,
    Annual, 1, 1, , 12, 31, , , , , , Yes;
""")

    # ── 존 ──────────────────────────────────────────────────────────
    # gbXML의 Space가 곧 존이다. 예전엔 이걸 버리고 단일 존으로 뭉갰다.
    # 면에 AdjacentSpaceId가 없으면 fallback 존 하나로 모은다.
    zones = []
    for sp in (bim.get("spaces") or []):
        zid = _safe(sp["id"])
        if zid not in zones:
            zones.append(zid)
    used_zones = {_zone_of(i, zone_name) for i, _, _ in surfaces}
    for z in sorted(used_zones):
        if z not in zones:
            zones.append(z)
    if not zones:
        zones = [zone_name]

    # 바닥이 빠진 존은 E+가 Floor Area를 0으로 잡고, 그러면 면적기반 부하
    # (조명 W/㎡·기기 W/㎡·재실 인/㎡)가 **전부 조용히 0**이 된다. 해석은 "성공"하고
    # 냉난방만 외피 관류로 나오므로 겉보기엔 멀쩡하다 — 2026-07-17 첫 성공 실행이
    # 정확히 이 상태였다(Electricity:Facility = 0.0 kWh). 반드시 표면에 올린다.
    # ⚠️ surfaces에는 나중에 제외될 면도 들어 있다. 제외 조건(좌표 없음·U 미상)과
    #    똑같은 기준으로 세지 않으면 "바닥 있음"으로 잘못 판정해 경고를 놓친다.
    _floor_zones = {
        _zone_of(i, zone_name)
        for i, kind, _ in surfaces
        if kind == "floor" and (i.get("vertices") or []) and i.get("u_value") is not None
    }
    out.append("!-  ===== 존 (gbXML Space = 존) =====\n")
    _stype = {_safe(s["id"]): s.get("spaceType") for s in (bim.get("spaces") or [])}
    for z in zones:
        st = _stype.get(z)
        out.append(
            # 필드 10=Floor Area까지만 쓴다. 11번은 Zone Inside Convection Algorithm
            # (enum)이라 autocalculate를 넣으면 E+가 Severe로 거절한다 — 실제로 그랬다.
            f"Zone,\n    {z}, 0, 0, 0, 0, , 1, , , autocalculate;"
            + (f"   !- gbXML spaceType: {st}" if st else "")
            + "\n\n"
        )
        if z not in _floor_zones:
            warnings.append(
                f"{z}: 바닥면이 IDF에 없어 존 면적이 0으로 잡힙니다 → "
                f"조명·기기·재실 부하가 전부 0이 됩니다. 해석은 '성공'해도 "
                f"내부발열이 빠진 값이니 그대로 쓰지 마세요."
            )

    # ── 재료·구성 (U-value → Material:NoMass) ───────────────────────
    out.append("!-  ===== 구성 (U-value에서 역산) =====\n")
    seen = set()
    for item, kind, _ in surfaces:
        u = item.get("u_value")
        cname = f"CON_{item['id']}"
        if u is None:
            # 🔑 지어내지 않는다. U를 모르면 그 면은 IDF에서 뺀다.
            continue
        if cname in seen:
            continue
        seen.add(cname)
        r = _material_r(u, kind)
        out.append(
            f"Material:NoMass,\n"
            f"    MAT_{item['id']},           !- Name\n"
            f"    MediumRough,             !- Roughness\n"
            f"    {r:.4f},                 !- Thermal Resistance {{m2-K/W}}  (U={u} 에서 표면열저항 "
            f"{_R_SURFACE.get(kind, 0.17):.2f} 차감)\n"
            f"    0.9, 0.7, 0.7;\n\n"
            f"Construction,\n"
            f"    {cname},\n"
            f"    MAT_{item['id']};\n\n"
        )

    # 창호: SimpleGlazingSystem은 U-Factor를 그대로 받는다 (역산 불필요)
    for item in (bim.get("windows") or []) + (bim.get("doors") or []):
        u = item.get("u_value")
        if u is None:
            continue
        out.append(
            f"WindowMaterial:SimpleGlazingSystem,\n"
            f"    WMAT_{item['id']},\n"
            f"    {u},                     !- U-Factor {{W/m2-K}}\n"
            f"    0.6;                     !- SHGC  ⚠️ gbXML에 없어 0.6 가정\n\n"
            f"Construction,\n"
            f"    WCON_{item['id']},\n"
            f"    WMAT_{item['id']};\n\n"
        )
        warnings.append(f"{item['id']}: SHGC를 0.6으로 가정 (gbXML에 없음)")

    # ── 면 ──────────────────────────────────────────────────────────
    out.append("!-  ===== 외피 =====\n")
    used_ids = set()
    for item, kind, gtype in surfaces:
        pts = item.get("vertices") or []
        u = item.get("u_value")
        if not pts:
            skipped.append(f"{item['id']}: 좌표 없음 (RectangularGeometry만) → IDF 제외")
            continue
        if u is None:
            skipped.append(f"{item['id']}: U-value 미상 → IDF 제외 (기본값 주입 안 함)")
            continue
        stype, obc, sun, wind = _IDF_SURFACE.get(
            gtype, ("Wall", "Outdoors", "SunExposed", "WindExposed")
        )
        used_ids.add(item["id"])
        out.append(
            f"BuildingSurface:Detailed,\n"
            f"    {item['id']},            !- Name\n"
            f"    {stype},                 !- Surface Type\n"
            f"    CON_{item['id']},        !- Construction Name\n"
            f"    {_zone_of(item, zone_name)},   !- Zone Name (gbXML AdjacentSpaceId)\n"
            f"    ,                        !- Space Name\n"
            f"    {obc},                   !- Outside Boundary Condition\n"
            f"    ,                        !- Outside Boundary Condition Object\n"
            f"    {sun},                   !- Sun Exposure\n"
            f"    {wind},                  !- Wind Exposure\n"
            f"    autocalculate,           !- View Factor to Ground\n"
            f"    {len(pts)},              !- Number of Vertices\n"
            f"{_fmt_vertices(pts)};\n\n"
        )

    # ── 개구부 ──────────────────────────────────────────────────────
    out.append("!-  ===== 개구부 =====\n")
    for item in (bim.get("windows") or []) + (bim.get("doors") or []):
        pts = item.get("vertices") or []
        host = item.get("host")
        if not pts:
            skipped.append(f"{item['id']}: 좌표 없음 → IDF 제외")
            continue
        if item.get("u_value") is None:
            skipped.append(f"{item['id']}: U-value 미상 → IDF 제외")
            continue
        if host not in used_ids:
            # 부모 면이 빠졌으면 창도 붙일 데가 없다
            skipped.append(f"{item['id']}: 부모 면({host})이 IDF에 없어 제외")
            continue
        out.append(
            f"FenestrationSurface:Detailed,\n"
            f"    {item['id']},            !- Name\n"
            f"    Window,                  !- Surface Type\n"
            f"    WCON_{item['id']},       !- Construction Name\n"
            f"    {host},                  !- Building Surface Name\n"
            f"    ,                        !- Outside Boundary Condition Object\n"
            f"    autocalculate,           !- View Factor to Ground\n"
            f"    ,                        !- Frame and Divider Name\n"
            f"    1,                       !- Multiplier\n"
            f"    {len(pts)},              !- Number of Vertices\n"
            f"{_fmt_vertices(pts)};\n\n"
        )

    # ── 부하·설비 (IdealLoads) ──────────────────────────────────────
    # 별표3(ZEB 인증기준) 실내 설정온도 — 냉방 26 / 난방 20. 우리 params와 같은 값.
    out.append(f"""!-  ===== 일정·부하·설비 =====
!-  ⚠️ 아래 일정과 내부부하는 **어린이집 표준 가정**이며 원문 근거가 없습니다.
!-     설정온도만 ZEB 인증기준 별표3(냉방 26℃ / 난방 20℃)을 따릅니다.

ScheduleTypeLimits, Frac, 0.0, 1.0, Continuous;
ScheduleTypeLimits, Temp, -60, 200, Continuous;

Schedule:Compact, SCH_OCC, Frac,
    Through: 12/31, For: Weekdays, Until: 08:00, 0.0, Until: 18:00, 1.0, Until: 24:00, 0.0,
    For: AllOtherDays, Until: 24:00, 0.0;

Schedule:Compact, SCH_HEAT, Temp,
    Through: 12/31, For: Weekdays, Until: 08:00, 15.0, Until: 18:00, 20.0, Until: 24:00, 15.0,
    For: AllOtherDays, Until: 24:00, 15.0;

Schedule:Compact, SCH_COOL, Temp,
    Through: 12/31, For: Weekdays, Until: 08:00, 30.0, Until: 18:00, 26.0, Until: 24:00, 30.0,
    For: AllOtherDays, Until: 24:00, 30.0;

!-  재실자 대사량 W/인. People의 Activity Level Schedule은 빈칸을 허용하지 않는다.
!-  120W ≒ 앉아서 하는 가벼운 활동(ASHRAE 55 기준 ~1.2 met).
Schedule:Compact, SCH_ACT, Any, Through: 12/31, For: AllDays, Until: 24:00, 120;

ThermostatSetpoint:DualSetpoint, TSTAT_SP, SCH_HEAT, SCH_COOL;
Schedule:Compact, ALWAYS_4, Any, Through: 12/31, For: AllDays, Until: 24:00, 4;
Schedule:Compact, ALWAYS_1, Any, Through: 12/31, For: AllDays, Until: 24:00, 1;
ScheduleTypeLimits, Any;
""")

    # 부하·설비는 **존마다** 필요하다. 단일 존일 때 하나만 쓰면 되던 게,
    # 존이 여럿이면 빠진 존은 온도제어도 설비도 없어 E+가 부하를 0으로 낸다.
    for z in zones:
        out.append(f"""
People,
    PPL_{z},                 !- Name
    {z},                     !- Zone Name
    SCH_OCC,                 !- Number of People Schedule Name
    People/Area,             !- Number of People Calculation Method
    ,                        !- Number of People
    0.1,                     !- People per Floor Area {{person/m2}} = 10㎡/인
    ,                        !- Floor Area per Person
    0.3,                     !- Fraction Radiant
    ,                        !- Sensible Heat Fraction
    SCH_ACT;                 !- Activity Level Schedule Name (필수 — 빈칸이면 거절)

Lights,
    LGT_{z}, {z}, SCH_OCC, Watts/Area, , 10.0, ,
    0.0, 0.4, 0.2, , General;

ElectricEquipment,
    EQP_{z}, {z}, SCH_OCC, Watts/Area, , 5.0, ,
    0.0, 0.5, 0.0;

ZoneControl:Thermostat,
    TSTAT_{z}, {z}, ALWAYS_4, ThermostatSetpoint:DualSetpoint, TSTAT_SP;

!-  침기 0.5회/h — 없으면 존이 완전 밀폐 상자가 된다.
ZoneInfiltration:DesignFlowRate,
    INF_{z}, {z}, ALWAYS_1, AirChanges/Hour, , , , 0.5;

!-  외기 도입 7.5 L/s·인. 이게 없으면 내부발열이 갇혀 **한겨울에도 냉방**이 돈다 —
!-  실제로 2026-07-17 데모 실행에서 1월 냉방이 최대치로 나왔고, 원인이 이것이었다.
DesignSpecification:OutdoorAir,
    DSOA_{z}, Flow/Person, 0.0075, , , , SCH_OCC;

ZoneHVAC:IdealLoadsAirSystem,
    IDEAL_{z},               !- Name
    ,                        !- Availability Schedule
    NODE_SUP_{z},            !- Zone Supply Air Node Name
    ,                        !- Zone Exhaust Air Node Name
    ,                        !- System Inlet Air Node Name
    50,                      !- Max Heating Supply Air Temp
    13,                      !- Min Cooling Supply Air Temp
    0.0156,                  !- Max Heating Supply Air Humidity Ratio
    0.0077,                  !- Min Cooling Supply Air Humidity Ratio
    NoLimit,                 !- Heating Limit
    ,                        !- Max Heating Air Flow Rate
    ,                        !- Max Sensible Heating Capacity
    NoLimit,                 !- Cooling Limit
    ,                        !- Max Cooling Air Flow Rate
    ,                        !- Max Total Cooling Capacity
    ,                        !- Heating Availability Schedule
    ,                        !- Cooling Availability Schedule
    None,                    !- Dehumidification Control Type
    ,                        !- Cooling Sensible Heat Ratio
    None,                    !- Humidification Control Type
    DSOA_{z};                !- Design Specification Outdoor Air Object Name

ZoneHVAC:EquipmentConnections,
    {z}, EQL_{z}, NODE_SUP_{z}, , NODE_AIR_{z}, NODE_RET_{z};

ZoneHVAC:EquipmentList,
    EQL_{z}, SequentialLoad, ZoneHVAC:IdealLoadsAirSystem, IDEAL_{z}, 1, 1;
""")

    out.append("""
!-  ===== 출력 =====
!-  성능개선비율은 '개선 전 대비'라 이 값들의 전후 비교로 산출한다.
!-  ⚠️ 미터 이름은 E+ 버전을 탄다. DistrictHeating:Facility는 25.1에서 없어졌고
!-     (DistrictHeatingWater:Facility로 바뀜) 요청하면 Warning만 내고 조용히 빠진다 —
!-     실제로 난방이 미터에서 통째로 누락돼 있었다. 이름을 바꿀 땐 EP_VERSION도 같이 본다.
Output:Meter, DistrictHeatingWater:Facility, Monthly;
Output:Meter, DistrictCooling:Facility, Monthly;
Output:Meter, Electricity:Facility, Monthly;
Output:Variable, *, Zone Ideal Loads Supply Air Total Heating Energy, Monthly;
Output:Variable, *, Zone Ideal Loads Supply Air Total Cooling Energy, Monthly;
Output:Table:SummaryReports, AllSummary;
OutputControl:Table:Style, HTML;
""")

    idf = "".join(out)
    return {
        "idf": idf,
        "skipped": skipped,
        "warnings": warnings,
        "stats": {
            "surfaces": len(used_ids),
            "surfaces_total": len(surfaces),
            "lines": idf.count("\n"),
        },
    }
