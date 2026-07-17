"""
modes/mode3_bim.py — BIM 진단 + ROI 통합 UI
============================================
Revit gbXML(권장) 또는 Dynamo JSON 업로드 → 진단 + ROI + 최적화 + EnergyPlus 해석.

**두 입력이 같은 걸 주지 않는다:**
    gbXML → 진단·ROI + IDF 생성 + EnergyPlus 연간 해석
    JSON  → 진단·ROI만. 면적만 있고 꼭짓점 좌표가 없어 IDF를 못 만든다
            (BuildingSurface:Detailed가 좌표를 요구한다. 지어내지 않는다.)

처리 흐름:
    파일 업로드 (Streamlit file_uploader)
    → gbXML이면 core.gbxml_parser.parse_gbxml()로 우리 스키마로 변환
    → core.bim_diagnoser.diagnose_from_json(with_roi=True)
    → Streamlit UI:
        탭1: 진단 결과 (11개 GR 매핑, 점수 분해, 등급)
        탭2: ROI 보강 계획 (우선순위 표, 누적 비용·점수)
        탭3: 최적화 (예산 슬라이더 / 목표 등급 선택)
    → 다운로드: 진단 보고서 (markdown)

구조:
    - render_bim_panel():            Streamlit UI 렌더 (의존 O)
    - run_bim_diagnosis():           순수 진단 함수 (의존 X, 테스트 가능)
    - _render_diagnosis_tab():       탭1 렌더 (내부)
    - _render_roi_tab():             탭2 렌더 (내부)
    - _render_optimization_tab():    탭3 렌더 (내부)
"""

import html
import json
import tempfile
from pathlib import Path
from typing import Optional


# ====================================================================
# 순수 진단 함수 (Streamlit 의존 X — test_bim에서 사용 가능)
# ====================================================================

def run_bim_diagnosis(
    json_path: str,
    with_roi: bool = True,
    duration_months: int = 8,
) -> dict:
    """
    JSON 경로를 받아 진단 결과 dict 반환.

    Args:
        json_path: Dynamo 추출 BIM JSON 파일 경로
        with_roi: ROI 연계 보강 계획 포함 여부
        duration_months: ROI 산정 예상 공사 기간 (개월)

    Returns:
        diagnose_from_json의 결과 dict
        {gr_mapping, score, report, roi_plan (with_roi=True 시)}
    """
    from core.bim_diagnoser import diagnose_from_json
    return diagnose_from_json(
        json_path, with_roi=with_roi, duration_months=duration_months,
    )


GBXML_SUFFIXES = (".gbxml", ".xml")


def save_uploaded_to_temp(uploaded_file) -> str:
    """Streamlit UploadedFile → 엔진이 읽는 임시 JSON 경로."""
    return save_bytes_to_temp(uploaded_file.getvalue(), uploaded_file.name)


def save_bytes_to_temp(raw: bytes, name: str) -> str:
    """
    업로드 바이트 → 엔진이 읽는 임시 **JSON** 파일 경로.

    gbXML(.gbxml/.xml)이면 여기서 우리 스키마로 변환해 JSON으로 떨군다.
    엔진(diagnose_from_json)은 JSON만 알면 되게 두고, 포맷 차이는 이 경계에서 흡수한다.
    업로드와 데모 파일이 **같은 경계**를 지나게 한다 — 두 갈래면 한쪽만 고쳐진다.

    왜 gbXML인가 — Revit이 실제로 내보내는 유일한 에너지 해석 포맷이다.
    (Revit 2026 Export 목록에 IDF 없음. Insight/GBS 경로는 2025-07-01 폐지.)
    자세한 경위는 core/gbxml_parser.py 참고.
    """
    suffix = Path(name).suffix.lower() or ".json"

    if suffix in GBXML_SUFFIXES:
        import json

        from core.gbxml_parser import parse_gbxml

        bim = parse_gbxml(raw)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tmp:
            json.dump(bim, tmp, ensure_ascii=False, indent=2)
            return tmp.name

    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=suffix, delete=False
    ) as tmp:
        tmp.write(raw)
        return tmp.name


_MONTHS = ["1월", "2월", "3월", "4월", "5월", "6월",
           "7월", "8월", "9월", "10월", "11월", "12월"]


def _render_eplus_result(res: dict, bim: dict) -> None:
    """EnergyPlus 결과 → 화면.

    원본 미터명은 사용자가 읽을 물건이 아니다 —
    "IDEAL_SP-MAIN:Zone Ideal Loads Supply Air Total Heating Energy [J](Monthly)".
    시설 미터만 골라 이름을 붙이고, 월별 프로파일을 그린다.
    (월별을 보여주는 이유: 1월에 냉방이 최대로 나오면 한눈에 틀린 걸 안다.
     실제로 환기가 빠져 그런 결과가 나온 적이 있다.)
    """
    import streamlit as st

    from core.eplus_client import label_meter

    meters = res.get("meters") or {}
    if not meters:
        st.warning("해석은 끝났는데 미터가 비어 있습니다 — 아래 원문을 확인하세요.", icon="⚠️")
        return

    area = 0.0
    for _sp in (bim.get("spaces") or []):
        area += float(_sp.get("area") or 0)

    named = []
    for k, v in meters.items():
        lb = label_meter(k)
        if lb and isinstance(v, dict):
            named.append((lb[1], lb[0], v, k))

    if named:
        cols = st.columns(len(named))
        for c, (icon, label, v, _k) in zip(cols, named):
            _kwh = v["annual_kWh"]
            c.metric(
                f"{icon} {label}",
                f"{_kwh:,.0f} kWh",
                delta=(f"{_kwh / area:,.1f} kWh/㎡" if area > 0 else None),
                delta_color="off",
            )
        if area > 0:
            st.caption(
                f"연면적 {area:,.0f}㎡ 기준 · 합계 "
                f"{sum(v['annual_kWh'] for _, _, v, _ in named) / area:,.1f} kWh/㎡·년"
            )

    # 월별 프로파일 — 계절이 뒤집혀 있으면 여기서 바로 보인다
    _monthly = {
        label: [x / 3_600_000.0 for x in v.get("monthly") or []]
        for _, label, v, _ in named
        if len(v.get("monthly") or []) == 12
    }
    if _monthly:
        import pandas as pd

        st.bar_chart(pd.DataFrame(_monthly, index=_MONTHS), height=260)
        st.caption("월별 kWh — 난방은 겨울, 냉방은 여름에 몰려야 정상입니다.")

    with st.expander("🔬 EnergyPlus 원본 미터 전체"):
        import pandas as pd

        st.dataframe(
            pd.DataFrame([
                {"미터": k, "연간 kWh": round(v["annual_kWh"], 1)}
                for k, v in meters.items() if isinstance(v, dict)
            ]),
            width="stretch", hide_index=True,
        )
        st.caption(
            "`IDEAL_*`는 Output:Variable(존별 부하), `*:Facility`는 Output:Meter(시설 합계)라 "
            "냉·난방이 두 번 보입니다. 위 요약과 성능개선비율은 **시설 미터만** 셉니다."
        )

    st.warning(
        "**이 값을 신청서에 그대로 쓰지 마세요.** 실제 설비가 아니라 IdealLoads(이상적 "
        "공조)로 부하만 뽑은 값이고, 재실·조명·기기 일정과 SHGC는 표준 가정입니다. "
        "gbXML에 없는 값은 지어내지 않았으므로 그만큼 빠져 있습니다.",
        icon="⚠️",
    )


# ====================================================================
# Streamlit UI (의존 O — 호출 시 지연 import)
# ====================================================================

def render_bim_panel() -> None:
    """
    Streamlit 메인 패널.
    streamlit_app.py에서 모드 3 선택 시 호출.

    UI 구성:
        - 파일 업로드 위젯
        - 옵션: 공사 기간(개월)
        - 진단 실행 버튼
        - 결과 탭 (진단 / ROI / 최적화)

    상태 관리:
        - 진단 결과를 st.session_state['_mode3_result']에 캐싱
        - 입력(파일/공사기간)이 바뀐 경우에만 재진단
        - 하위 탭의 위젯(슬라이더 등) 조작으로 인한 리런에도 결과 유지
    """
    import streamlit as st

    st.markdown("""
    <div style="margin-bottom:1.5rem;">
        <div style="font-size:0.85rem; color:#2E7D32; font-weight:600; letter-spacing:0.08em;">
            MODE 03 · BIM DIAGNOSIS + ROI
        </div>
        <h1 style="margin:0.2rem 0;">🏢 BIM 진단 + ROI 분석</h1>
        <div style="color:#757575;">
            <b>Revit gbXML</b>을 올리면 외피·열관류율을 읽어 11개 GR 기술요소를 매핑하고,
            정량평가표 채점 → 보강 우선순위 + 비용 → <b>EnergyPlus 연간 에너지 해석</b>까지
            한 번에 돌립니다. (Dynamo BIM JSON도 받지만 지오메트리가 없어 에너지 해석은 안 됩니다.)
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 입력 영역 — 진단 결과가 있으면 접어서 결과를 먼저 보이게 (UX)
    _has_result = st.session_state.get("_mode3_result") is not None
    with st.expander(
        "🏢 분석할 건물 선택 — 데모 케이스 클릭 또는 BIM 파일 업로드",
        expanded=not _has_result,
    ):
        st.markdown(
            "**어떤 파일을 넣느냐에 따라 나오는 게 다릅니다.**\n\n"
            "| 넣는 것 | 어디서 | 나오는 것 |\n"
            "|---|---|---|\n"
            "| **`.gbxml`** ← 권장 | Revit → File > Export > **gbXML** | GR 진단·점수·비용·ROI "
            "+ **EnergyPlus 연간 에너지 해석** |\n"
            "| `.json` | Dynamo 추출 | GR 진단·점수·비용·ROI (지오메트리가 없어 **에너지 해석 불가**) |\n"
            "| 아래 데모 버튼 | 파일 없이 | GR 진단 흐름 체험 |\n"
        )
        st.caption(
            "gbXML만 에너지 해석이 되는 이유: EnergyPlus는 면의 꼭짓점 좌표를 요구하는데, "
            "JSON 스키마엔 면적만 있어 좌표를 지어내야 합니다 — 그건 하지 않습니다."
        )
        # 4칸이다. 3칸에 넣으려다 보건지소를 밀어낼 뻔했다 — 데모를 조용히 지우지 않는다.
        samples = [
            ("demo_daycare_full.gbxml",
             "🔬 데모 gbXML (가상)",
             "1,252㎡ · 어린이집 · 외피 6면",
             "**에너지 해석까지** 도는 예시. 실제 건물 아님"),
            ("doam_archi_sample.json",
             "🏫 도담어린이집",
             "1,251㎡ · 2014년 · 어린이집",
             "KEPCO 검증 케이스. JSON이라 해석은 안 됨"),
            ("library_archi_sample.json",
             "📚 공공도서관",
             "3,500㎡ · 1998년 · 도서관",
             "노후 중대형 건물. 부분 보강 완료, 큰 잠재력"),
            ("health_center_sample.json",
             "🏥 보건지소",
             "450㎡ · 1985년 · 보건소",
             "최악 상태 소규모. 점수 상승 잠재력 극대"),
        ]
        sample_cols = st.columns(len(samples))
        for i, (fname, title, meta, desc) in enumerate(samples):
            with sample_cols[i]:
                if st.button(f"**{title}**\n\n{meta}\n\n{desc}",
                             key=f"sample_{i}", width="stretch"):
                    # 샘플 파일을 직접 진단
                    st.session_state["_mode3_sample_path"] = f"data/sample_bim/{fname}"
                    st.session_state["_mode3_sample_name"] = fname
                    st.rerun()

        st.markdown("")  # 간격
        col_upload, col_opts = st.columns([2, 1])
        with col_upload:
            uploaded = st.file_uploader(
                "⬆️ 여기에 **Revit gbXML**(권장) 또는 BIM JSON을 올리세요",
                type=["gbxml", "xml", "json"],
                help=(
                    "Revit → File > Export > gbXML 로 내보낸 파일을 그대로 올리세요. "
                    "외피(벽·창·문·지붕·바닥)와 열관류율을 읽어 진단합니다. "
                    "Revit은 IDF를 직접 내보내지 않으며(2026 기준), gbXML이 "
                    "Autodesk가 지원하는 유일한 에너지 해석 export 형식입니다."
                ),
            )
        with col_opts:
            duration = st.slider(
                "예상 공사 기간 (개월)",
                min_value=3, max_value=24, value=8, step=1,
                help="조달청 간접공사비 기준 적용. 공사기간 구간별 요율을 반영합니다.",
            )
            run_btn = st.button("진단 실행", type="primary", width="stretch")

    # ---------------------------------------------------------------
    # 진단 결과 캐싱 (session_state)
    # ---------------------------------------------------------------
    # 입력 소스: 1) 업로드 파일 2) 샘플 케이스 경로
    sample_path = st.session_state.pop("_mode3_sample_path", None)
    sample_name = st.session_state.pop("_mode3_sample_name", None)

    # 데모 gbXML은 세션에 붙여둔다 — 샘플 버튼은 rerun을 타서 pop되면 사라진다.
    if sample_path and Path(sample_path).suffix.lower() in GBXML_SUFFIXES:
        st.session_state["_mode3_gb_demo"] = (sample_path, sample_name)
        sample_path = sample_name = None
    if uploaded is not None:
        st.session_state.pop("_mode3_gb_demo", None)   # 업로드가 데모를 이긴다
    _gb_demo = st.session_state.get("_mode3_gb_demo")

    # 업로드든 데모든 gbXML 원본을 여기서 하나로 모은다. 두 갈래로 두면 한쪽만 고쳐진다.
    _gb_src = None      # (bytes, 표시이름)
    if uploaded is not None and Path(uploaded.name).suffix.lower() in GBXML_SUFFIXES:
        _gb_src = (uploaded.getvalue(), uploaded.name)
    elif _gb_demo:
        try:
            _gb_src = (Path(_gb_demo[0]).read_bytes(), _gb_demo[1])
        except OSError as _e:
            st.error(f"데모 gbXML을 읽지 못했습니다 — {_e}")

    if uploaded is not None:
        input_key = ("upload", uploaded.name, uploaded.size, duration)
        source_for_diagnosis = "upload"
    elif _gb_src:
        input_key = ("gbdemo", _gb_demo[0], duration)
        source_for_diagnosis = "gbdemo"
    elif sample_path is not None:
        input_key = ("sample", sample_name, duration)
        source_for_diagnosis = "sample"
    else:
        input_key = None
        source_for_diagnosis = None

    if _gb_src:
        # gbXML은 지오메트리 export라 우리가 필요한 걸 다 담지 못한다.
        # 무엇이 비었는지 **즉시** 알린다 — 안 그러면 조용히 0으로 진단된다.
        if _gb_demo:
            st.info(
                f"**데모 gbXML** ({_gb_src[1]}) — 실제 건물이 아니라 화면 예시용 "
                "가상 모델입니다. 연면적만 도담과 비슷하게 맞췄고 형상·열관류율은 가정값입니다.",
                icon="🔬",
            )
        if _gb_src:
            try:
                from core.gbxml_parser import parse_gbxml

                _peek = parse_gbxml(_gb_src[0])
                _g = _peek["_meta"]["gbxml"]
                _cnt = " · ".join(f"{k} {v}개" for k, v in _g["surfaces"].items() if v)
                st.success(f"gbXML 파싱 — {_cnt}", icon="✅")

                # 🔴 파싱이 됐다고 쓸 수 있는 건 아니다. 실제 도담 export는 1,251㎡ 건물에서
                #    해석 공간이 15㎡뿐이었는데 화면엔 "walls 6개"만 떠서 멀쩡해 보였다.
                #    이건 '값 몇 개 없음'이 아니라 '이 파일을 쓰면 안 됨'이다.
                if _g.get("blockers"):
                    st.error(
                        "**이 gbXML로는 진단할 수 없습니다** — Revit 해석 모델이 "
                        "제대로 만들어지지 않았습니다.\n\n"
                        + "\n".join(f"- {b}" for b in _g["blockers"])
                        + "\n\n아래 결과는 **건물 전체가 아닙니다.** 참고용으로만 보세요.",
                        icon="🚫",
                    )

                # EnergyPlus — GR 성능개선비율의 '센터 지정 프로그램' 경로.
                # E+는 Streamlit 무료 티어에서 못 돈다(CPU 0.078코어 하한·apt 부재).
                # 서비스 URL이 있으면 거기서 돌리고, 없으면 IDF를 내려줘 로컬 실행으로 물러선다.
                from core.eplus_client import health as _ep_health
                from core.eplus_client import run_idf as _ep_run
                from core.idf_writer import write_idf

                _idf = write_idf(_peek)
                _c1, _c2 = st.columns([1, 2])
                with _c1:
                    st.download_button(
                        "⬇️ EnergyPlus IDF 내려받기",
                        data=_idf["idf"].encode("utf-8"),
                        file_name=Path(_gb_src[1]).stem + ".idf",
                        mime="text/plain",
                        width="stretch",
                    )
                with _c2:
                    st.caption(
                        f"외피 {_idf['stats']['surfaces']}/{_idf['stats']['surfaces_total']}면 · "
                        f"존 {len(_peek.get('spaces') or []) or 1}개 반영. "
                        "**EnergyPlus는 GR 센터 지정 프로그램**입니다"
                        "(2026 민간 GR 공고 p.3 각주) — 개선 전·후를 비교하면 성능개선비율이 "
                        "**인정 대상**이 됩니다. ZEB 인증은 ECO2라 별개입니다.\n\n"
                        "⚠️ 자동 변환이라 그대로 신청서에 쓰면 안 됩니다 — IdealLoads·표준 일정 "
                        "가정이 들어 있습니다."
                    )
                if _idf["skipped"]:
                    with st.expander(f"⚠️ IDF에서 빠진 면 {len(_idf['skipped'])}건 — 왜 빠졌나"):
                        for _s in _idf["skipped"]:
                            st.markdown(f"- {_s}")

                # write_idf의 경고를 그동안 화면에 안 그렸다. 만들어놓고 아무도 못 보면
                # 없는 것과 같다 — 오히려 "경고했다"고 착각하게 만들어 더 나쁘다.
                # 바닥 누락(존 면적 0 → 부하 전부 0)은 해석이 '성공'해도 값이 틀리는
                # 조용한 실패라, 접히지 않게 본문에 띄운다.
                if _idf["warnings"]:
                    _zero = [w for w in _idf["warnings"] if "존 면적이 0" in w]
                    _rest = [w for w in _idf["warnings"] if w not in _zero]
                    if _zero:
                        st.warning(
                            "**해석은 돌아가지만 값이 틀립니다.**\n\n"
                            + "\n".join(f"- {w}" for w in _zero),
                            icon="⚠️",
                        )
                    if _rest:
                        with st.expander(f"⚠️ IDF 생성 시 둔 가정 {len(_rest)}건"):
                            for _w in _rest:
                                st.markdown(f"- {_w}")

                # ── 서비스에서 바로 실행 ──────────────────────────────
                _h = _ep_health()
                if not _h["configured"]:
                    st.info(
                        "**에너지 해석은 아직 이 사이트에서 못 돌립니다.** "
                        "EnergyPlus는 Streamlit 무료 티어에서 실행이 막혀 있어"
                        "(apt 저장소에 패키지 없음 · CPU 하한 0.078코어) 별도 서비스가 필요합니다. "
                        "위 IDF를 내려받아 **로컬 EnergyPlus(무료)** 로 돌리시면 됩니다. "
                        "서비스를 띄우는 방법은 `energyplus_service/README.md`에 있습니다.",
                        icon="🔬",
                    )
                elif not _h["ok"]:
                    st.warning(
                        f"EnergyPlus 서비스에 연결하지 못했습니다 — {_h['error']}\n\n"
                        "IDF를 내려받아 로컬에서 실행하시면 됩니다.",
                        icon="⚠️",
                    )
                else:
                    st.success(f"EnergyPlus 서비스 연결됨 — {_h['energyplus']}", icon="🔬")
                    _epw = st.file_uploader(
                        "기상파일 (.epw) — 없으면 서버 기본값",
                        type=["epw"], key="_epw_up",
                        help="도담(김천) 최근접 관측소는 추풍령 471350입니다. "
                             "climate.onebuilding.org에서 받을 수 있습니다.",
                    )
                    if st.button("🔬 EnergyPlus 실행 (연간 해석)", type="primary"):
                        with st.spinner("EnergyPlus 연간 해석 중… 수 분 걸릴 수 있습니다"):
                            _res = _ep_run(
                                _idf["idf"],
                                epw_bytes=_epw.getvalue() if _epw else None,
                            )
                        if _res.get("ok"):
                            st.success(f"✅ 해석 완료 — 기상: {_res.get('weather', '?')}")
                            # 리포트가 집어갈 수 있게 세션에 남긴다.
                            # 안 남기면 화면엔 보이는데 내려받은 문서엔 없다.
                            st.session_state["_mode3_eplus"] = _res
                            _render_eplus_result(_res, _peek)
                            _w = (_res.get("errors") or {}).get("warning_count", 0)
                            if _w:
                                st.caption(f"EnergyPlus 경고 {_w}건 — 결과 해석 시 참고하세요.")
                        else:
                            # E+ 실패는 대부분 eplusout.err 몇 줄로 원인이 잡힌다.
                            # 감추면 사용자는 '실패'만 보고 끝난다 → 그대로 보여준다.
                            st.error(f"❌ EnergyPlus 실행 실패 — {_res.get('error', '')}")
                            _e = _res.get("errors") or {}
                            for _f in (_e.get("fatal") or [])[:5]:
                                st.markdown(f"- 🔴 **Fatal**: {_f}")
                            for _s in (_e.get("severe") or [])[:5]:
                                st.markdown(f"- 🟠 Severe: {_s}")
                            if _e.get("raw_tail"):
                                with st.expander("eplusout.err 원문"):
                                    st.code(_e["raw_tail"][-2000:])
                _no_u = [
                    x["id"]
                    for k in ("walls", "roofs", "floors")
                    for x in _peek[k]
                    if x["u_value"] is None
                ]
                if _no_u or _g["missing"]:
                    # 마크다운에서 줄바꿈은 '\n' 하나로는 안 먹는다 — 항목이 한 줄로 뭉친다.
                    # '- ' 목록 + 앞뒤 빈 줄이 있어야 리스트로 렌더된다.
                    _items = []
                    if _no_u:
                        _items.append(
                            f"**열관류율 미상 {len(_no_u)}건** — {', '.join(_no_u[:5])}"
                            + (" 외" if len(_no_u) > 5 else "")
                        )
                    _items += list(_g["missing"])
                    st.warning(
                        "이 gbXML에 **없어서 채우지 못한 값**이 있습니다 — "
                        "지어내지 않고 비워 둡니다.\n\n"
                        + "\n".join(f"- {m}" for m in _items),
                        icon="⚠️",
                    )
            except Exception as e:
                st.error(f"gbXML을 읽지 못했습니다 — {type(e).__name__}: {e}")

    cached_key = st.session_state.get("_mode3_input_key")
    cached_result = st.session_state.get("_mode3_result")

    need_run = False
    if run_btn and uploaded is not None:
        need_run = True
    elif source_for_diagnosis is not None and input_key != cached_key:
        # 새 파일이 업로드되거나 새 샘플이 선택됨
        need_run = True

    if source_for_diagnosis is None and cached_result is None:
        st.info(
            "👆 **위 '분석할 건물 선택'에서 시작하세요** — 데모 케이스를 클릭하면 파일 없이 "
            "바로 진단 흐름을 볼 수 있고, **Revit gbXML**을 올리면 에너지 해석까지 돌아갑니다."
        )
        return

    if need_run:
        try:
            if source_for_diagnosis == "upload":
                diagnose_path = save_uploaded_to_temp(uploaded)
            elif source_for_diagnosis == "gbdemo":
                # 데모 gbXML도 업로드와 같은 경계를 지난다
                diagnose_path = save_bytes_to_temp(_gb_src[0], _gb_src[1])
            else:
                diagnose_path = sample_path

            with st.spinner("진단 중... (단가DB 로드 + 11개 항목 ROI 산정)"):
                result = run_bim_diagnosis(
                    diagnose_path,
                    with_roi=True,
                    duration_months=duration,
                )
        except Exception as e:
            from core.error_messages import friendly_error
            st.error(friendly_error(e))
            return

        st.session_state["_mode3_result"] = result
        st.session_state["_mode3_input_key"] = input_key
        try:
            st.toast("진단 완료 — 결과를 아래에서 확인하세요.", icon="✅")
        except Exception:
            pass
    else:
        result = cached_result

    if result is None:
        st.info("진단 결과가 없습니다. 파일을 업로드하고 진단 실행 버튼을 눌러주세요.")
        return

    # ── 결과 요약 헤더 — 두 제도의 판정을 나란히 ────────────────────
    # 과거엔 "진단 완료 — 총점 23/100점(D등급)"만 띄웠다. 그런데 그건 **GR 정량평가
    # 점수일 뿐**인데 종합 결론처럼 읽혔고, 정작 ZEB 등급은 5번째 탭에 숨어 있었다.
    # ZEB와 GR은 근거 법령이 다른 별개 제도다(P4) → 판정을 나란히 먼저 보여준다.
    score = result["score"]
    _verdict = _track_verdicts(result)

    st.success("✅ 진단 완료 — 두 제도의 판정을 나란히 보여줍니다")
    v1, v2 = st.columns(2)
    with v1:
        st.markdown(
            f"<div style='border-left:3px solid #C18A2D; padding:0.35rem 0 0.35rem 0.8rem;'>"
            f"<div style='font-size:0.78rem; color:#8A7A55; font-weight:600; letter-spacing:0.05em;'>"
            f"TRACK A · ZEB 인증 <span style='font-weight:400;'>(녹색건축법 §17 · 절대성능)</span></div>"
            f"<div style='font-size:1.35rem; font-weight:700; margin-top:0.15rem;'>"
            f"{_verdict['zeb_label']}</div>"
            f"<div style='font-size:0.82rem; color:#5C665F;'>{_verdict['zeb_sub']}</div></div>",
            unsafe_allow_html=True,
        )
    with v2:
        st.markdown(
            f"<div style='border-left:3px solid #1B5E20; padding:0.35rem 0 0.35rem 0.8rem;'>"
            f"<div style='font-size:0.78rem; color:#3D6B45; font-weight:600; letter-spacing:0.05em;'>"
            f"TRACK B · 그린리모델링 <span style='font-weight:400;'>(§27 · 상대 개선율)</span></div>"
            f"<div style='font-size:1.35rem; font-weight:700; margin-top:0.15rem;'>"
            f"{score['total_score']}/100점</div>"
            f"<div style='font-size:0.82rem; color:#5C665F;'>{_verdict['gr_sub']}</div></div>",
            unsafe_allow_html=True,
        )
    st.caption(
        "⚠️ **두 판정은 서로 다른 제도이고, 결과의 성격 자체가 다릅니다** — "
        "**ZEB**(녹색건축법 §17)는 절대성능으로 **등급**(+등급~5등급)을 매깁니다. "
        "**GR 정량평가**(§27 지원사업)는 **등급이 없습니다** — "
        "*\"정량평가 100%로 구성, 고득점 순으로 선정\"* 하는 **선정 랭킹 점수**입니다"
        "(2026 공공 GR 2.0 가이드라인 p.18). 그래서 GR 쪽은 등급 대신 점수만 표시합니다."
    )

    # ── 탭 구성 — 판정(2) → 경제성(3) → 산출물(1) ──────────────────
    # 변수명은 탭 내용과 일치시킨다 — 순서를 또 바꿀 때 잘못 매핑되지 않도록.
    tab_zeb, tab_gr, tab_cost, tab_opt, tab_sens, tab_report = st.tabs([
        "🏆 ZEB 등급",      # Track A 판정
        "🏗 GR 진단",       # Track B 판정  (구 "진단 결과" — GR임을 이름에 드러냄)
        "💰 보강·비용",      # ─┐
        "🎯 최적화",         #  ├ 두 트랙이 공유하는 경제성
        "📈 민감도",         # ─┘
        "📄 리포트",
    ])
    st.caption(
        "앞의 **두 탭은 서로 다른 제도의 판정**이고, 뒤의 **세 탭은 두 트랙이 공유하는 경제성**입니다."
    )

    # 파일명: 현재 업로드 또는 데모 gbXML 또는 샘플 또는 캐시 키에서 추출
    # ⚠️ gbdemo 분기를 빠뜨려 데모 gbXML을 눌러도 리포트 표지에 'bim.json'이 떴다.
    #    cached_key[1]이 데모에선 전체 경로라 파일명으로 못 쓴다 → Path().name으로 뽑는다.
    if uploaded is not None:
        source_name = uploaded.name
    elif _gb_src:
        source_name = _gb_src[1]
    elif sample_name:
        source_name = sample_name
    elif cached_key:
        # cached_key 구조: ("upload"|"gbdemo"|"sample", name_or_path, ...)
        source_name = Path(str(cached_key[1])).name if len(cached_key) > 1 else "bim.json"
    else:
        source_name = "bim.json"

    with tab_zeb:                       # Track A · 판정
        _render_zeb_tab(result)
    with tab_gr:                        # Track B · 판정
        _render_diagnosis_tab(result)
    with tab_cost:                      # 공통 · 경제성
        _render_roi_tab(result)
    with tab_opt:
        _render_optimization_tab(result)
    with tab_sens:
        _render_sensitivity_tab(result)
    with tab_report:                    # 산출물
        _render_full_report_tab(result, source_name)


# ====================================================================
# 탭별 렌더링 (내부)
# ====================================================================

def _track_verdicts(result: dict) -> dict:
    """
    헤더용 두 트랙 판정 요약 — 엔진에서 직접 산출한다(하드코딩 금지).

    ⚠️ 실패해도 진단 화면 전체가 죽으면 안 되므로 방어한다.
       값을 못 구하면 '—'를 돌려주고, 아래 각 탭이 상세를 보여준다.
    """
    out = {"zeb_label": "—", "zeb_sub": "ZEB 탭에서 확인", "gr_sub": "GR 정량평가표 채점"}
    bim = result.get("bim_data") or result.get("bim") or {}
    gr_mapping = result.get("gr_mapping", {})
    if not bim or not gr_mapping:
        return out

    try:
        from core.zeb_evaluator import evaluate_zeb
        now = evaluate_zeb(bim, gr_mapping)
        out["zeb_label"] = now["grade"]["label"]
        out["zeb_sub"] = (
            f"1차E 소요량 {now['post_energy_kwh_m2']:.1f} kWh/㎡·년 · "
            f"자립률 {now['autonomy_pct']}%"
        )
    except Exception:
        pass

    try:
        from core.gr_evaluator import evaluate_gr
        gr = evaluate_gr(bim, gr_mapping)
        imp = gr["성능개선"]
        out["gr_sub"] = (
            f"전체 보강 시 성능개선비율 {imp['성능개선비율_pct']}% "
            f"({'지원 자격 충족 ✅' if gr['자격충족'] else '기준 미달 ❌'} · 기준 {imp['기준_pct']}%)"
        )
    except Exception:
        pass
    return out


def _render_diagnosis_tab(result: dict) -> None:
    """탭1: 11개 매핑 표 + 점수 분해 (시각화 강화)."""
    import streamlit as st
    import pandas as pd
    from core.ui_theme import COLORS

    score = result["score"]
    bd = score["breakdown"]
    gr = result["gr_mapping"]

    # ─────────────────────────────────────────────────────────
    # 상단: 총점 게이지 + 등급 배지 + 세부 메트릭
    # ─────────────────────────────────────────────────────────
    col_gauge, col_meta = st.columns([2, 3])

    with col_gauge:
        total = score["total_score"]
        # 등급은 제도에 없다(선정 랭킹 점수) → 점수 구간으로 색만 준다.
        grade_color = ("#1B5E20" if total >= 75 else "#C18A2D" if total >= 50 else "#B3472F")

        # SVG 도넛 게이지 (총점)
        # circumference = 2 * pi * r, r=80 -> ~502
        pct = total / 100
        dash = int(502 * pct)
        rest = 502 - dash

        svg_gauge = f"""
        <div style="text-align:center; padding:1rem;">
            <svg width="200" height="200" viewBox="0 0 200 200">
              <circle cx="100" cy="100" r="80" stroke="#F0F0F0" stroke-width="16" fill="none"/>
              <circle cx="100" cy="100" r="80"
                stroke="{grade_color}" stroke-width="16" fill="none"
                stroke-dasharray="{dash} {rest}"
                stroke-dashoffset="125"
                transform="rotate(-90 100 100)"
                stroke-linecap="round"/>
              <text x="100" y="98" text-anchor="middle"
                font-family="Pretendard" font-size="36" font-weight="800" fill="#1A1A1A">
                {total}
              </text>
              <text x="100" y="125" text-anchor="middle"
                font-family="Pretendard" font-size="14" fill="#757575">
                / 100점
              </text>
            </svg>
            <div style="margin-top: 0.5rem; font-size: 0.82rem; color: #5C665F;">
              정량평가 점수<br>
              <span style="color:#8A9490; font-size:0.76rem;">선정 랭킹 · 등급 아님</span>
            </div>
        </div>
        """
        st.markdown(svg_gauge, unsafe_allow_html=True)

    with col_meta:
        st.markdown("#### 점수 구성")

        # GR 요소 진행바
        gr_pct = score["gr_subtotal"] / 80 * 100
        site_pct = score["site_subtotal"] / 20 * 100

        st.markdown(
            f'<div style="margin-top:1rem;">'
            f'<div style="display:flex; justify-content:space-between; margin-bottom:0.3rem;">'
            f'<span style="font-weight:500;">GR 기술요소</span>'
            f'<span style="color:#757575;">{score["gr_subtotal"]}/80점 ({gr_pct:.0f}%)</span>'
            f'</div>'
            f'<div style="background:#F0F0F0; border-radius:8px; height:14px; overflow:hidden;">'
            f'<div style="background:linear-gradient(90deg, #2E7D32, #76FF03); '
            f'height:100%; width:{gr_pct}%;"></div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="margin-top:1rem;">'
            f'<div style="display:flex; justify-content:space-between; margin-bottom:0.3rem;">'
            f'<span style="font-weight:500;">사업여건</span>'
            f'<span style="color:#757575;">{score["site_subtotal"]}/20점 ({site_pct:.0f}%)</span>'
            f'</div>'
            f'<div style="background:#F0F0F0; border-radius:8px; height:14px; overflow:hidden;">'
            f'<div style="background:linear-gradient(90deg, #5D4037, #8D6E63); '
            f'height:100%; width:{site_pct}%;"></div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # 점수 해석 — 등급이 아니라 '선정 경쟁' 관점으로 설명한다
        st.markdown(
            f'<div style="margin-top:1.5rem; padding:0.8rem 1rem; background:#F9FBF9; '
            f'border-radius:8px; border-left:4px solid {grade_color};">'
            f'<div style="font-size:0.85rem; color:#757575;">정량평가 점수</div>'
            f'<div style="font-weight:700; color:{grade_color}; margin-top:0.2rem;">'
            f'{score["total_score"]}/100점 · 선정 랭킹 점수</div>'
            f'<div style="font-size:0.78rem; color:#8A9490; margin-top:0.3rem;">'
            f'고득점 순 경쟁 선발이라 커트라인은 해마다 다릅니다 — 등급이 아닙니다.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ─────────────────────────────────────────────────────────
    # 11개 매핑 — 카드형
    # ─────────────────────────────────────────────────────────
    st.markdown("### 11개 GR 기술요소 현황")

    rows = []
    for key, info in gr.items():
        status = info.get("status", "?")
        ratio = info.get("적용비율")
        rows.append({
            "key": key,
            "status": status,
            "ratio": ratio,
            "info": info,
        })

    # 4열로 카드 배치
    for chunk_start in range(0, len(rows), 4):
        cols = st.columns(4)
        for i, item in enumerate(rows[chunk_start:chunk_start+4]):
            with cols[i]:
                _render_gr_card(item)

    st.divider()

    # ─────────────────────────────────────────────────────────
    # 점수 분해 — 막대그래프 (Altair 풍 SVG)
    # ─────────────────────────────────────────────────────────
    st.markdown("### 점수 분해")

    breakdown_rows = [
        ("단열 (벽·지붕·바닥)",
         f"벽 {bd['단열']['벽']['점수']} + 지붕 {bd['단열']['지붕']['점수']} + 바닥 {bd['단열']['바닥']['점수']}",
         bd['단열']['소계'], 20),
        ("창호 (창·문·일사)",
         f"창 {bd['창호']['창']['점수']} + 문 {bd['창호']['문']['점수']} + 일사 {bd['창호']['일사조절']['점수']}",
         bd['창호']['소계'], 16),
        ("설비 (냉·난·급)",
         f"냉방 {bd['설비']['냉방']['점수']} + 난방 {bd['설비']['난방']['점수']} + 급탕 {bd['설비']['급탕']['점수']}",
         bd['설비']['소계'], 15),
        ("신재생 자립률", f"자립률 {bd['신재생'].get('자립률', 0)*100:.1f}%",
         bd['신재생']['점수'], 5),
        ("환기 (폐열회수)", "", bd['환기']['점수'], 5),
        ("LED 조명", "", bd['LED']['점수'], 2),
        ("BEMS 자동제어", "", bd['BEMS']['점수'], 2),
        ("에너지 절감률", "", bd['에너지절감률']['점수'], 10),
        ("사업여건 (노후·소유·효율)", "", bd['사업여건']['소계'], 20),
    ]
    _render_score_bars(breakdown_rows)

    # ── 미평가 항목 — '0점'과 '데이터 없어 못 매김'을 구분해 공개 ──────
    unscored = score.get("_미평가") or []
    if unscored:
        scorable = score.get("_채점가능최대", 100)
        st.warning(
            f"**채점 가능 최대 {scorable}/100점** — 아래 {len(unscored)}개 항목은 "
            "**0점이 아니라 '미평가'** 입니다. BIM이나 사업 신청 정보에 없어서 점수를 "
            "매기지 못했을 뿐, 실제로는 받을 수 있는 점수입니다. "
            "선정은 **고득점 순 경쟁**이라 이 차이가 결과를 바꿉니다.",
            icon="⚠️",
        )
        with st.expander(f"📋 미평가 {len(unscored)}개 항목 — 무엇을 채우면 점수가 오르나"):
            import pandas as pd
            st.dataframe(
                pd.DataFrame([
                    {"항목": u["항목"],
                     "배점": f"{u['만점']:+d}점" if u["만점"] < 0 else f"{u['만점']}점",
                     "필요한 정보": u["사유"]}
                    for u in unscored
                ]),
                hide_index=True, width="stretch",
            )
            st.caption(
                "가점(14점)·감점(−10점)은 전부 **BIM에서 산출할 수 없는 사업 신청 정보**입니다 — "
                "안전점검 결과, 계량기 보급사업 참여 의사, 지방비 추가 확보, 재난지역 지정, "
                "과거 사업관리 이력. 실제 신청 시 담당자가 채워야 합니다. "
                "근거: 2026 공공 GR 2.0 가이드라인 p.20."
            )

    # ── 가점·감점 (원문 p.20) ───────────────────────────────────
    b_sub = (score.get("breakdown", {}).get("가점", {}) or {}).get("소계", 0)
    p_sub = (score.get("breakdown", {}).get("감점", {}) or {}).get("소계", 0)
    f1, f2, f3 = st.columns(3)
    f1.metric("기본 점수", f"{score['total_score']}/100", "GR요소 80 + 사업여건 20")
    f2.metric("가점", f"+{b_sub}/14", "안전성·적극성·기후위기")
    f3.metric("실제 선정 점수", f"{score.get('final_score', score['total_score'])}",
              f"감점 {p_sub}/-10")


# _grade_label() 제거 (2026-07) — 두 번 틀린 함수였다:
#   ① A+~D 자체가 제도에 없는 등급이었고(정량평가표는 선정 랭킹 점수),
#   ② 그 가짜 등급에 "최우수·우수"라는 **녹색건축 인증(G-SEED, §16)** 용어를 붙였다.
# G-SEED는 이 정량평가표(§27 지원사업)와 무관한 별개 제도다.


def _render_gr_card(item: dict) -> None:
    """11개 GR 항목 단일 카드."""
    import streamlit as st
    key = item["key"]
    status = item["status"]
    ratio = item["ratio"]
    info = item["info"]

    # 번호 + 라벨
    num = key.split("_")[0]
    label = key.split("_", 1)[1]

    # 상태 색상
    if status == "적용":
        bar_color, status_emoji, bar_bg = "#43A047", "✅", "linear-gradient(90deg, #43A047, #76FF03)"
    elif status == "부분적용":
        bar_color, status_emoji, bar_bg = "#FB8C00", "⚠️", "linear-gradient(90deg, #FB8C00, #FFB74D)"
    elif status == "미적용":
        bar_color, status_emoji, bar_bg = "#E53935", "❌", "#E53935"
    else:
        bar_color, status_emoji, bar_bg = "#BDBDBD", "—", "#BDBDBD"

    # 비율 표시 (있을 때)
    pct = ratio * 100 if ratio is not None else 0
    pct_display = f"{pct:.0f}%" if ratio is not None else "—"

    # 비고
    note = ""
    if "미적용_m2" in info and info["미적용_m2"] > 0:
        note = f"미적용 {info['미적용_m2']:.0f}㎡"
    elif "용량_kW" in info:
        note = f"{info['용량_kW']}kW (자립률 {info['자립률_추정']*100:.1f}%)"
    elif "LED_개수" in info:
        if info["전체_개수"] > 0:
            note = f"LED {info['LED_개수']}/{info['전체_개수']}개"

    html = f"""
    <div style="background:white; border:1px solid #E0E0E0; border-radius:10px;
                padding:0.9rem 1rem; margin-bottom:0.6rem; height:115px;
                position:relative; overflow:hidden;">
      <div style="display:flex; align-items:center; gap:0.4rem; margin-bottom:0.5rem;">
        <span style="background:#F5F5F5; color:#757575; padding:0.1rem 0.5rem;
                     border-radius:6px; font-size:0.75rem; font-weight:600;">
          {num}
        </span>
        <span style="font-weight:600; color:#1A1A1A; font-size:0.95rem;">{label}</span>
      </div>
      <div style="display:flex; justify-content:space-between; align-items:center;
                  font-size:0.85rem; margin-bottom:0.4rem;">
        <span style="color:{bar_color}; font-weight:600;">{status_emoji} {status}</span>
        <span style="color:#757575; font-weight:500;">{pct_display}</span>
      </div>
      <div style="background:#F0F0F0; border-radius:4px; height:6px; overflow:hidden;">
        <div style="background:{bar_bg}; height:100%; width:{pct}%;"></div>
      </div>
      <div style="font-size:0.75rem; color:#9E9E9E; margin-top:0.5rem;">{note or '&nbsp;'}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def _render_score_bars(rows: list) -> None:
    """점수 분해 막대그래프."""
    import streamlit as st

    html_parts = ['<div style="margin-top:0.5rem;">']
    for label, detail, score_val, max_val in rows:
        pct = (score_val / max_val * 100) if max_val > 0 else 0
        # 색: 80%+ 초록, 40-80% 노랑, <40% 빨강
        if pct >= 80:
            color = "#43A047"
            bg = "linear-gradient(90deg, #43A047, #76FF03)"
        elif pct >= 40:
            color = "#FB8C00"
            bg = "linear-gradient(90deg, #FB8C00, #FFB74D)"
        else:
            color = "#E53935"
            bg = "linear-gradient(90deg, #E53935, #EF5350)"

        detail_html = f'<span style="color:#9E9E9E; font-size:0.8rem; margin-left:0.4rem;">{detail}</span>' if detail else ""

        # 한 줄로 합쳐서 streamlit이 코드블록으로 오해하지 않도록
        bar_html = (
            f'<div style="margin-bottom:0.8rem;">'
            f'<div style="display:flex; justify-content:space-between; margin-bottom:0.25rem;">'
            f'<span style="font-weight:500; font-size:0.92rem;">{label}{detail_html}</span>'
            f'<span style="color:{color}; font-weight:600; font-size:0.9rem;">'
            f'{score_val}/{max_val}점 ({pct:.0f}%)'
            f'</span>'
            f'</div>'
            f'<div style="background:#F0F0F0; border-radius:6px; height:10px; overflow:hidden;">'
            f'<div style="background:{bg}; height:100%; width:{pct}%; transition: width 0.3s ease;"></div>'
            f'</div>'
            f'</div>'
        )
        html_parts.append(bar_html)
    html_parts.append('</div>')
    # 줄바꿈 없이 한 문자열로 합쳐 마크다운 코드블록 오해 방지
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def _render_roi_tab(result: dict) -> None:
    """탭2: 11개 항목 보강 ROI 표 + 누적 차트."""
    import streamlit as st
    import pandas as pd

    plan = result.get("roi_plan")
    score = result["score"]

    if not plan:
        st.warning("ROI 계획 미생성 (단가DB 로드 실패 가능)")
        return

    # 요약 메트릭
    total_cost = sum(p.get("Max_Cost", 0) for p in plan)
    total_uplift = sum(p["점수상승"] for p in plan)
    new_score = score["total_score"] + total_uplift

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("전체 보강 비용", f"{total_cost/1e8:.2f}억",
                help=f"{total_cost:,}원")
    col2.metric("점수 상승", f"+{total_uplift}점",
                f"{score['total_score']} → {new_score}")
    col3.metric("예상 총점", f"{new_score}/100")
    col4.metric("정량평가 점수", f"{new_score}점",
                delta=f"+{total_uplift} (선정 랭킹 점수)")

    st.divider()

    # ─────────────────────────────────────────────────────────
    # 보강 우선순위 카드 (Top 3 강조 + 나머지 표)
    # ─────────────────────────────────────────────────────────
    st.markdown("### 🏆 가성비 Top 3 보강 항목")
    st.caption("효율(점수/억) 내림차순. 같은 1억 투자해도 점수 상승은 항목마다 달라요.")

    top3 = plan[:3]
    cols = st.columns(3)
    medal_emojis = ["🥇", "🥈", "🥉"]
    for i, p in enumerate(top3):
        with cols[i]:
            cost_eok = p["Max_Cost"] / 1e8
            eff = p["효율_점수당억"]
            html = f"""
            <div style="background:linear-gradient(135deg, #ffffff 0%, #f9fbf9 100%);
                        border:1px solid #C8E6C9; border-radius:12px;
                        padding:1.2rem 1rem; height:170px;
                        box-shadow:0 2px 8px rgba(27,94,32,0.06);">
              <div style="font-size:1.8rem;">{medal_emojis[i]}</div>
              <div style="font-weight:700; color:#1A1A1A; font-size:1rem;
                          margin:0.3rem 0; line-height:1.3;">
                {p['label']}
              </div>
              <div style="display:flex; justify-content:space-between;
                          margin-top:0.6rem; font-size:0.85rem;">
                <span style="color:#757575;">비용</span>
                <span style="font-weight:600;">{cost_eok:.2f}억</span>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:0.85rem;">
                <span style="color:#757575;">점수 상승</span>
                <span style="font-weight:600; color:#1B5E20;">+{p['점수상승']}점</span>
              </div>
              <div style="display:flex; justify-content:space-between; font-size:0.85rem;">
                <span style="color:#757575;">효율</span>
                <span style="font-weight:700; color:#FB8C00;">{eff:.1f} 점/억</span>
              </div>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)

    st.markdown("")

    # 전체 우선순위 표
    with st.expander("📋 전체 11개 항목 우선순위 보기", expanded=False):
        rows = []
        for i, p in enumerate(plan, 1):
            rows.append({
                "순위": i,
                "항목": p["label"],
                "수량": f"{p['수량']:.1f} {p['단위']}",
                "예상 비용": f"{p['Max_Cost']:,}원",
                "현재→보강 점수": f"{p['현재점수']} → {p['보강후점수']}",
                "Δ점수": f"+{p['점수상승']}",
                "효율(점/억)": f"{p['효율_점수당억']:.2f}",
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, width="stretch")

    # ─────────────────────────────────────────────────────────
    # 누적 보강 효과 SVG 차트
    # ─────────────────────────────────────────────────────────
    st.markdown("### 📈 누적 보강 효과")
    st.caption("효율 좋은 항목부터 누적 채택할수록 점수가 빠르게 오르다 후반에 완만해지는 한계효용 체감 패턴")

    _render_cumulative_chart(plan, score["total_score"])

    st.caption(
        "ℹ️ 비용은 07 조달청 단가DB + 시공계수 + 08 간접공사비 매트릭스로 자동 산정. "
        "단가DB에 없는 설비/전기 항목은 ESTIMATED_UNIT_COSTS 추정 단가 사용. "
        "실시설계 시 견적사·시공사 검토 필수."
    )


def _render_cumulative_chart(plan: list, current_score: int) -> None:
    """누적 비용 vs 점수 SVG 차트."""
    import streamlit as st

    # 데이터 준비
    cum_cost = 0
    cum_uplift = 0
    points = [(0, current_score, 0)]   # (순위, 점수, 누적비용 억)
    for i, p in enumerate(plan, 1):
        cum_cost += p.get("Max_Cost", 0)
        cum_uplift += p["점수상승"]
        points.append((i, current_score + cum_uplift, cum_cost / 1e8))

    max_score = max(p[1] for p in points)
    max_cost_eok = max(p[2] for p in points) or 1
    max_score_display = max(100, max_score)

    # SVG 차트 (600x320, 패딩 60/40/40/60 = top/right/bottom/left)
    W, H = 700, 320
    px, py, pw, ph = 60, 40, 580, 220   # plot area
    n = len(points) - 1   # x축 끝값

    def x_to_px(x):
        return px + (x / n) * pw if n > 0 else px

    def score_to_px(s):
        return py + (1 - s / max_score_display) * ph

    def cost_to_px(c):
        return py + (1 - c / max_cost_eok) * ph

    # 점수 라인 path
    score_path = "M " + " L ".join(
        f"{x_to_px(p[0]):.0f},{score_to_px(p[1]):.0f}" for p in points
    )
    # 비용 라인 path
    cost_path = "M " + " L ".join(
        f"{x_to_px(p[0]):.0f},{cost_to_px(p[2]):.0f}" for p in points
    )

    # 격자
    grid_lines = ""
    for i in range(5):
        y = py + (i / 4) * ph
        score_val = max_score_display * (1 - i / 4)
        grid_lines += f'<line x1="{px}" y1="{y}" x2="{px+pw}" y2="{y}" stroke="#F0F0F0"/>'
        grid_lines += f'<text x="{px-8}" y="{y+4}" text-anchor="end" font-size="10" fill="#9E9E9E">{score_val:.0f}점</text>'
        # 우측 축 (비용)
        cost_val = max_cost_eok * (1 - i / 4)
        grid_lines += f'<text x="{px+pw+8}" y="{y+4}" font-size="10" fill="#9E9E9E">{cost_val:.1f}억</text>'

    # x축 라벨
    x_labels = ""
    for i, p in enumerate(points):
        if i % 2 == 0 or i == len(points) - 1:
            x_labels += f'<text x="{x_to_px(p[0]):.0f}" y="{py+ph+18}" text-anchor="middle" font-size="10" fill="#757575">{p[0]}</text>'

    # 점
    points_score = "".join(
        f'<circle cx="{x_to_px(p[0]):.0f}" cy="{score_to_px(p[1]):.0f}" r="3" fill="#1B5E20"/>'
        for p in points
    )
    points_cost = "".join(
        f'<circle cx="{x_to_px(p[0]):.0f}" cy="{cost_to_px(p[2]):.0f}" r="3" fill="#FB8C00"/>'
        for p in points
    )

    svg = f"""
    <div style="background:white; border:1px solid #E0E0E0; border-radius:10px; padding:0.5rem;">
      <svg width="100%" height="{H}" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet">
        {grid_lines}
        <path d="{score_path}" stroke="#1B5E20" stroke-width="2.5" fill="none"/>
        <path d="{cost_path}" stroke="#FB8C00" stroke-width="2.5" fill="none" stroke-dasharray="4,3"/>
        {points_score}
        {points_cost}
        {x_labels}
        <text x="{W/2}" y="{H-8}" text-anchor="middle" font-size="11" fill="#757575">
          누적 채택 항목 수
        </text>
        <text x="{px}" y="20" font-size="11" fill="#1B5E20" font-weight="600">━ 누적 점수</text>
        <text x="{px+120}" y="20" font-size="11" fill="#FB8C00" font-weight="600">--- 누적 비용</text>
      </svg>
    </div>
    """
    st.markdown(svg, unsafe_allow_html=True)


def _render_optimization_tab(result: dict) -> None:
    """탭3: 예산 상한 / 목표 점수 최적화. (등급은 제도에 없다 — 점수로 받는다)"""
    import streamlit as st
    import pandas as pd
    from core.bim_diagnoser import (
        TARGET_SCORE_PRESETS,
        optimize_within_budget,
        optimize_for_target_score,
    )

    plan = result.get("roi_plan")
    if not plan:
        st.warning("ROI 계획 없음")
        return

    score = result["score"]
    current_score = score["total_score"]
    total_cost = sum(p.get("Max_Cost", 0) for p in plan)

    mode = st.radio(
        "최적화 모드",
        ["예산 상한 (점수 최대화)", "목표 점수 (비용 최소화)"],
        horizontal=True,
    )

    if mode.startswith("예산"):
        # 예산 슬라이더 (0 ~ 전체 보강 비용의 1.5배)
        max_budget = int(total_cost * 1.5) if total_cost > 0 else 1_000_000_000
        budget = st.slider(
            "예산 (원)",
            min_value=10_000_000,
            max_value=max_budget,
            value=int(total_cost / 2) if total_cost > 0 else 500_000_000,
            step=10_000_000,
            format="%d원",
        )
        st.caption(f"≈ {budget/1e8:.2f}억")

        opt = optimize_within_budget(plan, budget_won=budget, current_score=current_score)

        # 결과 메트릭
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("사용 예산", f"{opt['사용예산']/1e8:.2f}억")
        col2.metric("잔여 예산", f"{opt['잔여예산']/1e8:.2f}억")
        col3.metric("점수 상승",
                    f"+{opt['누적점수상승']}점",
                    delta=f"→ {opt['예상총점']}점")
        col4.metric("예상 총점", f"{opt['예상총점']}/100",
                    delta=f"+{opt['누적점수상승']}점")

        st.divider()

        st.subheader(f"채택 항목 ({len(opt['selected'])}개)")
        if opt['selected']:
            df = pd.DataFrame([{
                "순위": i+1,
                "항목": p["label"],
                "수량": f"{p['수량']:.1f} {p['단위']}",
                "비용": f"{p['Max_Cost']:,}원",
                "Δ점수": f"+{p['점수상승']}",
                "효율": f"{p['효율_점수당억']:.2f}",
            } for i, p in enumerate(opt['selected'])])
            st.dataframe(df, hide_index=True, width="stretch")
        else:
            st.info("예산 범위 내 채택 가능한 항목 없음")

        skipped = [s for s in opt['skipped'] if s.get("Max_Cost", 0) > 0]
        if skipped:
            with st.expander(f"⏭ 예산 초과로 제외된 {len(skipped)}개 항목"):
                df_s = pd.DataFrame([{
                    "항목": s["label"],
                    "비용": f"{s['Max_Cost']:,}원",
                    "Δ점수": f"+{s['점수상승']}",
                    "제외 사유": s.get("_skip_reason", ""),
                } for s in skipped])
                st.dataframe(df_s, hide_index=True, width="stretch")

    else:
        # 목표 **점수** 선택 — 등급은 제도에 없다(고득점 순 경쟁 선발)
        target = st.slider(
            "목표 정량평가 점수", min_value=30, max_value=100,
            value=65, step=5,
            help="정량평가표는 등급표가 아니라 고득점 순 선정용 랭킹 점수입니다. "
                 "선정 커트라인은 해마다 경쟁 상황에 따라 달라집니다.",
        )
        st.caption(
            "참고 눈금: " + " · ".join(f"{s}점 {label}" for s, label in TARGET_SCORE_PRESETS)
            + " — ⚠️ 제도상 등급이 아니라 **우리가 UI 편의로 둔 눈금**입니다. "
            "어떤 점수도 선정을 보장하지 않습니다."
        )

        opt = optimize_for_target_score(plan, target_score=target, current_score=current_score)

        if opt["achievable"]:
            st.success(
                f"✅ 목표 **{target}점** 달성 가능 — {opt['필요비용']/1e8:.2f}억 필요"
            )
        else:
            st.error(
                f"⚠️ 목표 **{target}점** 도달 불가 — "
                f"전 항목 보강 시 최대 {opt['달성점수']}점"
            )

        col1, col2, col3 = st.columns(3)
        col1.metric("필요 비용", f"{opt['필요비용']/1e8:.2f}억")
        col2.metric("달성 점수", f"{opt['달성점수']}/100")
        col3.metric("목표 점수", f"{opt['목표점수']}/100")

        if opt['selected']:
            st.subheader(f"채택 항목 ({len(opt['selected'])}개)")
            df = pd.DataFrame([{
                "순위": i+1,
                "항목": p["label"],
                "수량": f"{p['수량']:.1f} {p['단위']}",
                "비용": f"{p['Max_Cost']:,}원",
                "Δ점수": f"+{p['점수상승']}",
            } for i, p in enumerate(opt['selected'])])
            st.dataframe(df, hide_index=True, width="stretch")


def _render_sensitivity_tab(result: dict) -> None:
    """탭4: 민감도 분석 + 시나리오 비교 (PFV 사업수지 모델에서 영감).
    
    엑셀 분석으로 도입한 두 가지 핵심 기능:
    1. 민감도 — 보조금율/비용/절감액을 ±N% 흔들었을 때 ROI 변화
    2. 시나리오 — 부분보강 / 전체보강 / 시그니처 3개 동시 비교
    """
    import streamlit as st
    import pandas as pd
    from core.sensitivity import run_sensitivity_analysis
    from core.scenario_compare import (
        compare_all_scenarios,
        recommend_scenario,
        build_inputs_from_diagnosis,
    )

    plan = result.get("roi_plan") or []
    if not plan:
        st.info("ROI 보강 계획이 없어 민감도/시나리오 분석을 할 수 없습니다.")
        return

    scenario = result.get("scenario", {})
    roi_summary = result.get("roi_summary", {})
    bim_data = result.get("bim_data", {})
    # 연면적: 진단 결과의 BIM 추출값(total_area_m2) 우선, 구버전 scenario 키 fallback
    area_m2 = bim_data.get("total_area_m2") or scenario.get("연면적_m2", 1000)
    total_cost = sum(p.get("Max_Cost", 0) for p in plan)
    # ⚠️ 단가는 params 단일 소스에서 조회 — 근거 없는 임시 가정치다(하드코딩 금지).
    from core import params as _P
    annual_saving = area_m2 * _P.annual_saving_per_m2()

    st.markdown("### 📈 민감도·시나리오 분석")
    st.caption(
        "보조금율·공사비·에너지 절감액 등 핵심 변수를 ±N% 흔들어 "
        "사업성이 얼마나 안정적인지(또는 민감한지) 확인합니다."
    )

    # ─────────────────────────────────────
    # Section 1: 시나리오 비교
    # ─────────────────────────────────────
    st.markdown("#### 🎬 3개 사업 전략 비교")

    base_inputs = {
        "total_cost_full": total_cost,
        "annual_saving_full": annual_saving,
        "area_m2": area_m2,
        "far_bonus_full": roi_summary.get("용적률_자산가치_원", 0),
        "tax_relief_full": roi_summary.get("취득세_감면액_원", 0),
    }
    scenarios = compare_all_scenarios(base_inputs)

    # 3개 카드 가로 배치
    cols = st.columns(3)
    colors = ["#FFE0B2", "#C8E6C9", "#BBDEFB"]  # 주황 / 초록 / 파랑
    for col, sc, color in zip(cols, scenarios, colors):
        with col:
            payback = sc["할인회수년"]
            payback_str = f"{payback:.1f}년" if (payback and payback < 99) else "∞"
            irr = sc["IRR"]
            irr_str = f"{irr*100:.1f}%" if irr is not None else "—"
            st.markdown(
                f"""
<div style="background:{color}; padding:14px; border-radius:10px; min-height:240px;">
<div style="font-weight:700; font-size:1.05em; margin-bottom:6px;">{sc['label']}</div>
<div style="color:#555; font-size:0.85em; margin-bottom:10px;">{sc['desc']}</div>
<div>보조율: <b>{sc['subsidy_pct']:.0f}%</b></div>
<div>자부담: <b>{sc['자부담_억']:.2f}억</b></div>
<div>할인회수: <b>{payback_str}</b></div>
<div>NPV: <b>+{sc['NPV_억']:.2f}억</b> · IRR <b>{irr_str}</b></div>
<div>B-C: <b>{sc['BC_ratio']:.2f}배</b></div>
<div style="font-size:0.85em; color:#555; margin-top:4px;">자산가치(수익환원): {sc['자산가치_수익환원_억']:.2f}억</div>
</div>
                """,
                unsafe_allow_html=True,
            )

    st.caption(
        "※ NPV·IRR·B-C는 자부담 대비 20년 할인 현금흐름 기준. "
        "자산가치(수익환원)는 ΔNOI÷환원율(5%)로 환산한 별도 관점이며 NPV와 합산하지 않습니다. "
        "용적률 완화 자산가치는 증축 계획 시에만 적용되는 조건부 항목으로 분리합니다."
    )

    # 우선순위별 추천
    st.markdown("##### 🏆 우선순위별 최적 시나리오")
    rec_cols = st.columns(3)
    priorities = [
        ("회수기간", "⏱️ 빨리 회수"),
        ("ROI", "📈 ROI 극대화"),
        ("초기부담", "💵 자부담 최소"),
    ]
    for col, (pri, label) in zip(rec_cols, priorities):
        with col:
            rec = recommend_scenario(scenarios, pri)
            best = rec["best_scenario"]
            st.markdown(
                f"""
<div style="background:#F5F5F5; padding:10px; border-radius:8px; border-left:4px solid #4CAF50;">
<div style="font-size:0.85em; color:#666;">{label}</div>
<div style="font-weight:700; margin:4px 0;">{best['label']}</div>
<div style="font-size:0.8em; color:#555;">{rec['reason']}</div>
</div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ─────────────────────────────────────
    # Section 2: 민감도 분석
    # ─────────────────────────────────────
    st.markdown("#### 🎚️ 민감도 분석 (변수 ±N% 흔들기)")

    baseline = {
        "subsidy_rate": 0.7,  # 기본 70% 보조
        "total_cost_won": total_cost,
        "annual_saving_won": annual_saving,
        "area_m2": area_m2,
        "far_bonus_value_won": roi_summary.get("용적률_자산가치_원", 0),
        "tax_relief_won": roi_summary.get("취득세_감면액_원", 0),
    }
    sens = run_sensitivity_analysis(baseline)

    sub_tab1, sub_tab2, sub_tab3, sub_tab4 = st.tabs([
        "보조금율 ±",
        "보강비용 ±",
        "절감액 ±",
        "🎯 손익분기",
    ])

    with sub_tab1:
        st.caption("정부 보조금율이 변하면 ROI는 어떻게 변할까?")
        rows = sens["subsidy_table"]
        df = pd.DataFrame([{
            "보조율": r["보조금율_pct"] + (" ◀기준" if r["_is_baseline"] else ""),
            "자부담": f"{r['자부담_억']:.2f}억",
            "GR 회수기간": f"{r['GR_단독_회수년']:.1f}년"
                if r["GR_단독_회수년"] < 99 else "∞",
            "통합 회수기간": f"{r['통합_회수년']:.1f}년"
                if r["통합_회수년"] < 99 else "∞",
            "NPV": f"{r['NPV_억']:+.2f}억",
            "B-C": f"{r['BC_ratio']:.2f}",
        } for r in rows])
        st.dataframe(df, hide_index=True, width="stretch")

    with sub_tab2:
        st.caption("자재비/인건비 변동(±30%)에 사업성이 얼마나 민감한가?")
        rows = sens["cost_table"]
        df = pd.DataFrame([{
            "변화율": r["비용_변화_pct"] + (" ◀기준" if r["_is_baseline"] else ""),
            "보강비용": f"{r['보강비용_억']:.2f}억",
            "자부담": f"{r['자부담_억']:.2f}억",
            "GR 회수기간": f"{r['GR_단독_회수년']:.1f}년"
                if r["GR_단독_회수년"] < 99 else "∞",
            "NPV": f"{r['NPV_억']:+.2f}억",
            "B-C": f"{r['BC_ratio']:.2f}",
        } for r in rows])
        st.dataframe(df, hide_index=True, width="stretch")

    with sub_tab3:
        st.caption("에너지 절감 예측은 ±20% 오차 가능. 그 영향은?")
        rows = sens["saving_table"]
        df = pd.DataFrame([{
            "변화율": r["절감_변화_pct"] + (" ◀기준" if r["_is_baseline"] else ""),
            "연간절감": f"{r['연간절감_만원']:.0f}만원",
            "GR 회수기간": f"{r['GR_단독_회수년']:.1f}년"
                if r["GR_단독_회수년"] < 99 else "∞",
            "통합 회수기간": f"{r['통합_회수년']:.1f}년"
                if r["통합_회수년"] < 99 else "∞",
            "NPV": f"{r['NPV_억']:+.2f}억",
            "B-C": f"{r['BC_ratio']:.2f}",
        } for r in rows])
        st.dataframe(df, hide_index=True, width="stretch")

    with sub_tab4:
        st.caption("**손익분기점** — 목표 회수기간 달성에 필요한 조건")
        bk = sens["breakeven"]
        cols2 = st.columns(2)
        with cols2[0]:
            st.metric("무보조 회수년", f"{bk['무보조_회수년']:.1f}년")
            st.metric("50% 보조 회수년", f"{bk['50%보조_회수년']:.1f}년")
            st.metric("현재(70%) 회수년", f"{bk['현재_회수년']:.1f}년")
        with cols2[1]:
            st.metric(
                "회수 8년 달성 필요 보조율",
                f"{bk['회수8년_필요_보조율']*100:.0f}%",
            )
            st.metric(
                "회수 10년 달성 필요 보조율",
                f"{bk['회수10년_필요_보조율']*100:.0f}%",
            )
        st.info(
            "💡 **해석**: 보조금율이 위 임계값보다 낮으면 회수기간 목표 미달. "
            "사업 신청 전 보조율 협의 필수."
        )


def _render_zeb_tab(result: dict) -> None:
    """🏆 ZEB 평가 탭 — BIM 데이터에서 자립률 자동 계산 + 등급 산정.
    
    두 가지 모드:
    - 자동 추정: BIM JSON의 11개 GR 요소 충족도 기반
    - DesignBuilder 입력: 정확한 시뮬레이션 결과 직접 입력
    """
    import streamlit as st
    from core.zeb_evaluator import evaluate_zeb, BASE_ENERGY_BY_USE

    bim = result.get("bim_data") or result.get("bim") or {}
    gr_mapping = result.get("gr_mapping", {})

    if not bim or not gr_mapping:
        st.info("ZEB 평가를 위해서는 BIM 진단 데이터가 필요합니다.")
        return

    st.markdown("### 🏆 ZEB 인증 평가")
    st.caption(
        "BIM 데이터로 1차 에너지 소요량 + 신재생 발전량 → 에너지자립률 → 등급 자동 산정. "
        "판정 규칙은 ZEB 인증기준 고시를 따르되, **에너지량은 용도별 원단위 × 요소별 "
        "절감률의 간이 추정**입니다."
    )

    st.warning(
        "**이 등급은 '설계 검토용 추정'입니다 — 공식 인증 결과가 아닙니다.** "
        "ZEB 공식 등급·자립률은 **ECO2**(월간·ISO 13790, 지역 기후 내장)로만 산정합니다. "
        "우리 엔진은 용도별 원단위 × 요소별 절감률의 간이 추정이고, EnergyPlus 계열"
        "(eppy·시간별 기후)로 바꾸더라도 **계산 엔진이 달라 ECO2와 값이 일치하지 않습니다.** "
        "설계 방향을 잡는 용도로 쓰고, 확정은 인증기관을 거쳐야 합니다.",
        icon="⚠️",
    )

    # 모드 선택
    mode = st.radio(
        "평가 모드",
        ["🤖 자동 추정 (BIM 기반)", "📊 DesignBuilder 입력 (정밀)"],
        horizontal=True,
        help="자동: 11개 GR 충족도 기반 간이 추정. "
             "DesignBuilder: 시뮬레이션 결과 직접 입력 — 그래도 ECO2 값과는 다르다."
    )

    overrides = None
    if "DesignBuilder" in mode:
        st.markdown("#### DesignBuilder 시뮬레이션 결과 입력")
        col1, col2, col3 = st.columns(3)
        with col1:
            base_e = st.number_input(
                "기본 에너지 소요량 (kWh/㎡·년)",
                min_value=50.0, max_value=600.0, value=200.0, step=10.0,
                help="DesignBuilder의 보강 전 1차 에너지 소요량",
            )
        with col2:
            saving = st.number_input(
                "절감률 (%)",
                min_value=0.0, max_value=80.0, value=30.0, step=1.0,
                help="보강 시뮬레이션 절감 비율",
            )
        with col3:
            pv_kwh = st.number_input(
                "PV 연간 발전량 (kWh)",
                min_value=0.0, max_value=1_000_000.0, value=7020.0, step=100.0,
                help="신재생 시뮬레이션 결과",
            )
        overrides = {
            "base_energy_kwh_m2": base_e,
            "annual_saving_pct": saving,
            "pv_generation_kwh": pv_kwh,
        }

    # 건물 용도 선택
    use_options = list(BASE_ENERGY_BY_USE.keys())
    default_use = "어린이집"
    selected_use = st.selectbox(
        "건물 용도",
        use_options,
        index=use_options.index(default_use),
        help="용도에 따라 기본 에너지 소요량이 달라집니다.",
    )

    # ZEB 평가 실행
    eval_result = evaluate_zeb(
        bim, gr_mapping,
        building_use=selected_use,
        manual_overrides=overrides,
    )

    # 보강 후 시나리오 (자동 추정 모드에서만 — 권장 전체 GR 보강 + BEMS 가정)
    eval_after = None
    if eval_result["mode"] == "estimated":
        eval_after = evaluate_zeb(
            bim, gr_mapping,
            building_use=selected_use,
            assume_full_reinforcement=True,
            assume_bems=True,
        )

    st.markdown("---")

    # ─────────────────────────────────────
    # 핵심 결과 — 자립률 + 등급
    # ─────────────────────────────────────
    autonomy = eval_result["autonomy_pct"]
    grade = eval_result["grade"]              # 최종 인증등급 (제1호·제2호 중 상위)
    gc1 = eval_result.get("grade_clause1", {})
    gc2 = eval_result.get("grade_clause2", {})
    net_primary = eval_result.get("net_primary_kwh_m2", 0)

    # 등급별 색상 (rank 기준: +등급 6 ~ 5등급 1, 미달 0)
    rank_colors = {
        6: "#1B5E20", 5: "#388E3C", 4: "#7CB342",
        3: "#FBC02D", 2: "#FB8C00", 1: "#F4511E", 0: "#9E9E9E",
    }
    color = rank_colors.get(grade.get("rank", 0), "#9E9E9E")

    st.markdown(
        f"""
<div style="background:{color}; color:white; padding:20px; border-radius:14px; text-align:center; margin-bottom:16px;">
<div style="font-size:0.9em; opacity:0.9;">ZEB 인증등급 (제1호·제2호 중 상위)</div>
<div style="font-size:2.4em; font-weight:800; margin:6px 0;">{grade['label']}</div>
<div style="font-size:0.98em; opacity:0.95;">
  제1호 에너지자립률 <b>{autonomy:.1f}%</b> ({gc1.get('label','-')}) &nbsp;·&nbsp;
  제2호 1차에너지소요량 <b>{net_primary:.0f}</b> kWh/㎡·년 ({gc2.get('label','-')})
</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # ─────────────────────────────────────
    # 현재 → 보강 후 예상 등급 (자동 추정 모드)
    # ─────────────────────────────────────
    if eval_after is not None:
        ag = eval_after["grade"]
        acolor = rank_colors.get(ag.get("rank", 0), "#9E9E9E")
        a_cert = eval_after["zeb_requirements"]["인증가능"]
        st.markdown(
            f'''
<div style="display:flex;align-items:stretch;gap:10px;margin-bottom:8px;">
  <div style="flex:1;border:1px solid #E0E0E0;border-radius:12px;padding:14px;text-align:center;background:#FAFAFA;">
    <div style="font-size:0.78rem;color:#757575;">현재 상태</div>
    <div style="font-size:1.2rem;font-weight:800;color:{color};margin:4px 0;">{grade['label']}</div>
    <div style="font-size:0.76rem;color:#9E9E9E;">자립률 {autonomy:.1f}% · 절감 {eval_result['reduction']['total_reduction_pct']:.0f}%</div>
  </div>
  <div style="display:flex;align-items:center;font-size:1.7rem;color:#BDBDBD;font-weight:700;">→</div>
  <div style="flex:1;border:2px solid {acolor};border-radius:12px;padding:14px;text-align:center;background:#fff;box-shadow:0 4px 16px rgba(27,94,32,0.10);">
    <div style="font-size:0.78rem;color:{acolor};font-weight:700;">권장 전체 보강 적용 시</div>
    <div style="font-size:1.45rem;font-weight:800;color:{acolor};margin:4px 0;">{ag['label']}</div>
    <div style="font-size:0.76rem;color:#757575;">자립률 {eval_after['autonomy_pct']:.1f}% · 절감 {eval_after['reduction']['total_reduction_pct']:.0f}% · {'인증 가능 ✅' if a_cert else '추가 보완 필요'}</div>
  </div>
</div>
            ''',
            unsafe_allow_html=True,
        )
        st.caption(
            "‘보강 후’는 11개 GR 기술요소 전체 적용 + BEMS 설치를 가정한 잠재 등급입니다. "
            "실제 달성 등급은 보강 범위·예산·신재생 추가량에 따라 달라집니다."
        )

    # ─────────────────────────────────────
    # 지표 4개 — 메트릭
    # ─────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "기본 소요량",
            f"{eval_result['base_energy_kwh_m2']:.0f} kWh/㎡·년",
            help=f"{eval_result['building_use']} 용도 기준",
        )
    with c2:
        st.metric(
            "에너지 절감률",
            f"{eval_result['reduction']['total_reduction_pct']:.1f}%",
            help=eval_result["reduction"].get("_source", ""),
        )
    with c3:
        st.metric(
            "보강 후 소요량",
            f"{eval_result['post_energy_kwh_m2']:.1f} kWh/㎡·년",
        )
    with c4:
        st.metric(
            "PV 발전 1차E(㎡당)",
            f"{eval_result['pv'].get('yield_per_m2_primary_kwh', 0):.1f} kWh/㎡·년",
            help=(
                f"실발전 {eval_result['pv']['yield_per_m2_kwh']:.1f} × 전력 1차에너지환산계수 "
                f"{eval_result.get('primary_energy_factor', 2.75)} · "
                + eval_result["pv"].get("_source", "")
            ),
        )

    # ─────────────────────────────────────
    # ZEB 인증요건 판정 — (제1호 또는 제2호) 그리고 제3호
    # ─────────────────────────────────────
    req = eval_result.get("zeb_requirements", {})
    st.markdown("#### 📋 ZEB 인증요건 충족 판정")
    st.caption(
        "ZEB 인증 = **(제1호 에너지자립률 또는 제2호 1차에너지소요량) 그리고 제3호(BEMS)**. "
        "제1호·제2호는 둘 중 하나만 충족하면 되고, 인증등급은 둘 중 **높은 등급**으로 산정합니다."
    )

    can_certify = req.get("인증가능", False)
    banner_color = "#1B5E20" if can_certify else "#C62828"
    banner_bg = "#E8F5E9" if can_certify else "#FFEBEE"
    banner_msg = (
        f"✅ ZEB 인증요건 충족 — 인증등급 <b>{grade['label']}</b>."
        if can_certify else
        "⚠️ 인증요건 미충족 — 제1호·제2호 중 하나(+제3호 BEMS)를 충족해야 합니다."
    )
    st.markdown(
        f'<div style="background:{banner_bg};border-left:4px solid {banner_color};'
        f'padding:12px 16px;border-radius:8px;color:{banner_color};font-weight:600;'
        f'margin-bottom:12px;">{banner_msg}</div>',
        unsafe_allow_html=True,
    )

    req_cols = st.columns(3)
    for col, item in zip(req_cols, req.get("items", [])):
        ok = item["충족"]
        ic = "✅" if ok else "❌"
        c = "#2E7D32" if ok else "#C62828"
        with col:
            st.markdown(
                f'<div style="border:1px solid #E0E0E0;border-radius:10px;padding:14px;'
                f'text-align:center;background:#fff;min-height:118px;">'
                f'<div style="font-size:1.6rem;">{ic}</div>'
                f'<div style="font-size:0.82rem;color:#757575;margin:4px 0;">{item["요건"]}</div>'
                f'<div style="font-size:1.0rem;font-weight:700;color:{c};">{item["현재"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.caption(
        "제1호·제2호는 OR 관계(택1). 제3호 BEMS는 필수. "
        + ("주거용" if eval_result.get("is_residential") else "비주거용")
        + " 1차에너지소요량 기준 적용 · ZEB 인증기준 별표."
    )

    st.markdown("---")

    # ─────────────────────────────────────
    # 등급 도달 가이드
    # ─────────────────────────────────────
    st.markdown("#### 🎯 등급 도달 가이드 (제1호 · 자립률 기준)")
    st.caption("각 ZEB 등급의 자립률 기준(제1호) 도달에 필요한 PV 용량. 제2호(소요량)로도 등급 산정 가능.")

    # 등급표는 엔진(ZEB_AUTONOMY_THRESHOLDS)에서 읽는다 — 여기서 다시 적지 않는다.
    # 과거 자립률을 두 모듈이 따로 계산해 5.6% vs 9.3%로 갈렸던 것과 같은 종류의 버그를 막는다.
    from core.zeb_evaluator import ZEB_AUTONOMY_THRESHOLDS
    target_grades = [
        (("+등급" if g == "+" else f"{g}등급"), lo)
        for lo, g, _label, _rank in ZEB_AUTONOMY_THRESHOLDS
    ]
    post_e = eval_result["post_energy_kwh_m2"]
    area = eval_result["area_m2"]

    pef = eval_result.get("primary_energy_factor", 2.75)
    region_yield = eval_result["pv"].get("region_yield_per_kw") or 1300
    grade_table = []
    for label, threshold in target_grades:
        # 자립률 X% 도달에 필요한 PV (kW)
        # 필요 1차에너지 생산(㎡당) = post_e × threshold/100 → 실발전(÷PEF) → 전체(×면적) → kW(÷지역수율)
        required_primary_kwh_m2 = post_e * threshold / 100
        required_site_total_kwh = (required_primary_kwh_m2 / pef) * area
        required_kw = required_site_total_kwh / region_yield
        is_achieved = autonomy >= threshold
        grade_table.append({
            "ZEB 등급": f"ZEB {label}",
            "필요 자립률": f"{threshold}%",
            "필요 PV": f"{required_kw:.1f} kW",
            "현재 상태": "✅ 달성" if is_achieved else "❌ 부족",
        })

    import pandas as pd
    df = pd.DataFrame(grade_table)
    st.dataframe(df, hide_index=True, width="stretch")

    # ─────────────────────────────────────
    # 절감 분해 (자동 모드일 때만)
    # ─────────────────────────────────────
    if eval_result["mode"] == "estimated" and eval_result["reduction"]["breakdown"]:
        with st.expander("📊 11개 GR 요소별 절감 기여도", expanded=False):
            br = eval_result["reduction"]["breakdown"]
            df2 = pd.DataFrame([
                {
                    "GR 요소": k.split("_", 1)[1] if "_" in k else k,
                    "이론 최대": f"{v['이론최대_pct']}%",
                    "적용도": f"{v['적용도_pct']:.0f}%",
                    "실제 절감": f"{v['실제절감_pct']:.2f}%",
                }
                for k, v in br.items()
            ])
            st.dataframe(df2, hide_index=True, width="stretch")

    # ─────────────────────────────────────
    # 해석
    # ─────────────────────────────────────
    rank = grade.get("rank", 0)
    if rank == 0:
        tail = ("ZEB 인증 최소 기준(제1호 자립률 20% 또는 제2호 1차에너지소요량 "
                "비주거 130 미만)에 미달 — PV 증설 또는 외피·설비 보강이 필요합니다.")
    elif rank >= 6:
        tail = "최고 등급(ZEB 플러스등급)에 도달했습니다. 🎉"
    else:
        tail = "상위 등급은 자립률 향상(PV 증설) 또는 1차에너지소요량 절감으로 달성할 수 있습니다."
    st.info(
        f"💡 **해석**: 보강 후 자립률 **{autonomy:.1f}%**(제1호 {gc1.get('label','-')}) · "
        f"1차에너지소요량(순) **{net_primary:.0f}** kWh/㎡(제2호 {gc2.get('label','-')}) "
        f"→ 인증등급 **{grade['label']}**. " + tail
    )


def _render_full_report_tab(result: dict, source_name: str) -> None:
    """탭4: 전체 리포트 + 다운로드 (마크다운/PDF 2종).

    예전엔 st.markdown(report) 한 줄로 긴 마크다운을 통째로 흘려보냈다.
    문서가 어디서 시작해 어디서 끝나는지 안 보이고, 화면의 다른 글과 구별이 안 됐다.
    표지(무엇을·언제·무엇으로) → 본문 박스 → 내려받기 순으로 세운다.
    """
    import streamlit as st
    from pathlib import Path

    source_name = source_name or "bim.json"  # None 방어 (캐시 경로에서 None 가능)
    file_stem = Path(source_name).stem

    # 빌드 식별자는 근거·출처의 것을 그대로 쓴다 — 같은 걸 두 벌 만들면 갈라진다.
    from modes.mode5_evidence import build_id

    _bid = build_id()

    # ── 종합 리포트 조립 ────────────────────────────────────────────
    # 🔴 예전엔 result["report"](GR 진단만)를 그대로 뿌렸다. 화면에서 ZEB 등급·비용·
    #    민감도·에너지해석을 다 보여주고도, 내려받은 문서엔 GR 점수표뿐이었다.
    #    화면과 산출물이 다른 이야기를 하고 있었다.
    from core.full_report import build_full_report
    from core.zeb_evaluator import evaluate_zeb

    _zeb = None
    try:
        _zeb = evaluate_zeb(result.get("bim_data") or {},
                            result.get("gr_mapping") or {},
                            assume_full_reinforcement=True, assume_bems=True)
    except Exception:
        pass   # ZEB 평가가 실패해도 리포트 전체가 죽으면 안 된다

    report = build_full_report(
        result,
        source_name=source_name,
        zeb=_zeb,
        eplus=st.session_state.get("_mode3_eplus"),
        build=_bid,
    )
    st.markdown(
        f"""
        <div style="border:1px solid #D8E1E7; border-radius:8px 8px 0 0;
                    border-bottom:none; padding:1.1rem 1.3rem 0.9rem;
                    background:#F3F6F8;">
          <div style="font-size:0.72rem; letter-spacing:0.1em; color:#2E6E8E;
                      font-weight:700;">COMPREHENSIVE REPORT</div>
          <div style="font-size:1.25rem; font-weight:700; margin:0.15rem 0 0.5rem;">
            종합 리포트</div>
          <div style="font-size:0.8rem; color:#5A6C7A; line-height:1.7;">
            대상 <b>{html.escape(source_name)}</b> · 생성 {_bid['date']}
            · 엔진 <code>{_bid['commit']}</code>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 본문 ────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(report)

    st.caption(
        "이 리포트는 **자동 산출 결과**입니다. 실제 사업 신청 시 그린리모델링 창조센터"
        "(1588-8788) 공식 컨설팅이 필요합니다."
    )
    st.divider()

    # 다운로드 버튼 2개 (마크다운 / PDF)
    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            label="📄 마크다운 다운로드 (.md)",
            data=report,
            file_name=f"종합리포트_{file_stem}.md",
            mime="text/markdown",
            width="stretch",
            help="GitHub, Notion, Obsidian 등에서 바로 사용 가능",
        )

    with col2:
        # PDF 생성 - 클릭 시 한 번만 (lazy)
        try:
            from core.pdf_report import generate_pdf_report
            pdf_bytes = generate_pdf_report(result, source_name=source_name)
            st.download_button(
                label="📕 PDF 리포트 다운로드 (.pdf)",
                data=pdf_bytes,
                file_name=f"종합리포트_{file_stem}.pdf",
                mime="application/pdf",
                width="stretch",
                help="인쇄·이메일 첨부·결재용 (한글 폰트 자동 적용)",
                type="primary",
            )
        except ImportError:
            st.info(
                "PDF 다운로드를 사용하려면 `reportlab` 패키지가 필요합니다.\n\n"
                "cmd: `pip install reportlab`"
            )
        except Exception as e:
            st.warning(f"PDF 생성 중 오류: {type(e).__name__}")
            st.caption("마크다운 다운로드는 정상 사용 가능합니다.")


# ====================================================================
# 유틸
# ====================================================================

# _grade_from_score() 제거 (2026-07) — A+~D는 제도에 없는 등급이었다.
# 정량평가표는 "고득점 순으로 선정"하는 랭킹 점수다(2026 공공 GR 2.0 가이드라인 p.18).
# core.bim_diagnoser.score_compliance 주석 참고.
