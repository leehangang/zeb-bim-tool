"""
modes/mode3_bim.py — BIM 진단 + ROI 통합 UI
============================================
Dynamo 추출 JSON 업로드 → core.bim_diagnoser 호출 → 진단 + ROI + 최적화.

처리 흐름:
    JSON 파일 업로드 (Streamlit file_uploader)
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


def save_uploaded_to_temp(uploaded_file) -> str:
    """Streamlit UploadedFile -> 임시 JSON 파일 경로."""
    suffix = Path(uploaded_file.name).suffix or ".json"
    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=suffix, delete=False
    ) as tmp:
        tmp.write(uploaded_file.getvalue())
        return tmp.name


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
            Dynamo로 추출한 BIM JSON 업로드 → 11개 GR 기술요소 자동 매핑 →
            01 가이드라인 정량평가표 채점 → 보강 우선순위 + 비용 산정.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 샘플 갤러리 (1-클릭 시연용)
    with st.expander("🎯 데모용 샘플 케이스 (1-클릭)", expanded=False):
        st.caption("실제 BIM 파일이 없어도 가상 케이스로 진단 흐름을 체험할 수 있습니다.")
        sample_cols = st.columns(3)
        samples = [
            ("doam_archi_sample.json",
             "🏫 도담어린이집",
             "1,251㎡ · 2014년 · 어린이집",
             "KEPCO 검증 케이스. 일부 보강 완료 (바닥/태양광)"),
            ("library_archi_sample.json",
             "📚 공공도서관",
             "3,500㎡ · 1998년 · 도서관",
             "노후 중대형 건물. 부분 보강 완료, 큰 잠재력"),
            ("health_center_sample.json",
             "🏥 보건지소",
             "450㎡ · 1985년 · 보건소",
             "최악 상태 소규모. 점수 상승 잠재력 극대"),
        ]
        for i, (fname, title, meta, desc) in enumerate(samples):
            with sample_cols[i]:
                if st.button(f"**{title}**\n\n{meta}\n\n{desc}",
                             key=f"sample_{i}", use_container_width=True):
                    # 샘플 파일을 직접 진단
                    st.session_state["_mode3_sample_path"] = f"data/sample_bim/{fname}"
                    st.session_state["_mode3_sample_name"] = fname
                    st.rerun()

    # 입력 영역
    col_upload, col_opts = st.columns([2, 1])

    with col_upload:
        uploaded = st.file_uploader(
            "또는 BIM JSON 파일 직접 업로드",
            type=["json"],
            help="Dynamo 노드로 추출한 walls/windows/doors/.../bems_installed 스키마 JSON",
        )

    with col_opts:
        duration = st.slider(
            "예상 공사 기간 (개월)",
            min_value=3, max_value=24, value=8, step=1,
            help="08 간접공사비 매트릭스 적용용. 6/12/36개월 구간별 율 다름.",
        )
        run_btn = st.button("진단 실행", type="primary", use_container_width=True)

    # ---------------------------------------------------------------
    # 진단 결과 캐싱 (session_state)
    # ---------------------------------------------------------------
    # 입력 소스: 1) 업로드 파일 2) 샘플 케이스 경로
    sample_path = st.session_state.pop("_mode3_sample_path", None)
    sample_name = st.session_state.pop("_mode3_sample_name", None)

    if uploaded is not None:
        input_key = ("upload", uploaded.name, uploaded.size, duration)
        source_for_diagnosis = "upload"
    elif sample_path is not None:
        input_key = ("sample", sample_name, duration)
        source_for_diagnosis = "sample"
    else:
        input_key = None
        source_for_diagnosis = None

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
            "👈 위에서 데모 케이스를 클릭하거나 BIM JSON 파일을 업로드하세요.\n\n"
            "스키마 예시: `data/sample_bim/doam_archi_sample.json`"
        )
        return

    if need_run:
        try:
            if source_for_diagnosis == "upload":
                diagnose_path = save_uploaded_to_temp(uploaded)
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
    else:
        result = cached_result

    if result is None:
        st.info("진단 결과가 없습니다. 파일을 업로드하고 진단 실행 버튼을 눌러주세요.")
        return

    # 결과 요약 헤더
    score = result["score"]
    st.success(
        f"✅ 진단 완료 — 총점 **{score['total_score']}/100점** "
        f"({score['grade']}등급)"
    )

    # 탭 구성
    tab1, tab2, tab3, tab_sens, tab_zeb, tab4 = st.tabs([
        "📊 진단 결과",
        "💰 ROI 보강 계획",
        "🎯 최적화",
        "📈 민감도·시나리오",
        "🏆 ZEB 평가",
        "📄 전체 리포트",
    ])

    # 파일명: 현재 업로드 또는 샘플 또는 캐시 키에서 추출
    if uploaded is not None:
        source_name = uploaded.name
    elif sample_name:
        source_name = sample_name
    elif cached_key:
        # cached_key 구조: ("upload"|"sample", name, ...)
        source_name = cached_key[1] if len(cached_key) > 1 else "bim.json"
    else:
        source_name = "bim.json"

    with tab1:
        _render_diagnosis_tab(result)
    with tab2:
        _render_roi_tab(result)
    with tab3:
        _render_optimization_tab(result)
    with tab_sens:
        _render_sensitivity_tab(result)
    with tab_zeb:
        _render_zeb_tab(result)
    with tab4:
        _render_full_report_tab(result, source_name)


# ====================================================================
# 탭별 렌더링 (내부)
# ====================================================================

def _render_diagnosis_tab(result: dict) -> None:
    """탭1: 11개 매핑 표 + 점수 분해 (시각화 강화)."""
    import streamlit as st
    import pandas as pd
    from core.ui_theme import GRADE_COLORS, COLORS, grade_badge_html

    score = result["score"]
    bd = score["breakdown"]
    gr = result["gr_mapping"]

    # ─────────────────────────────────────────────────────────
    # 상단: 총점 게이지 + 등급 배지 + 세부 메트릭
    # ─────────────────────────────────────────────────────────
    col_gauge, col_meta = st.columns([2, 3])

    with col_gauge:
        total = score["total_score"]
        grade = score["grade"]
        grade_color = GRADE_COLORS.get(grade, "#757575")

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
            <div style="margin-top: 0.5rem;">
              {grade_badge_html(grade, large=True)}
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

        # 등급 가이드
        st.markdown(
            f'<div style="margin-top:1.5rem; padding:0.8rem 1rem; background:#F9FBF9; '
            f'border-radius:8px; border-left:4px solid {grade_color};">'
            f'<div style="font-size:0.85rem; color:#757575;">현재 등급</div>'
            f'<div style="font-weight:700; color:{grade_color}; margin-top:0.2rem;">'
            f'{grade}등급 · {_grade_label(grade)}</div>'
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


def _grade_label(grade: str) -> str:
    """등급별 라벨."""
    labels = {
        "A+": "최우수 — 매우 효율적인 그린 빌딩",
        "A":  "우수 — 양호한 그린 빌딩",
        "B":  "양호 — 일부 보강 필요",
        "C":  "보통 — 적극적 보강 권장",
        "D":  "미흡 — 종합 그린리모델링 권장",
    }
    return labels.get(grade, "")


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
    from core.ui_theme import GRADE_COLORS, grade_badge_html

    plan = result.get("roi_plan")
    score = result["score"]

    if not plan:
        st.warning("ROI 계획 미생성 (단가DB 로드 실패 가능)")
        return

    # 요약 메트릭
    total_cost = sum(p.get("Max_Cost", 0) for p in plan)
    total_uplift = sum(p["점수상승"] for p in plan)
    new_score = score["total_score"] + total_uplift
    new_grade = _grade_from_score(new_score)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("전체 보강 비용", f"{total_cost/1e8:.2f}억",
                help=f"{total_cost:,}원")
    col2.metric("점수 상승", f"+{total_uplift}점",
                f"{score['total_score']} → {new_score}")
    col3.metric("예상 총점", f"{new_score}/100")
    col4.metric("예상 등급", new_grade,
                delta=f"{score['grade']} → {new_grade}")

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
        st.dataframe(df, hide_index=True, use_container_width=True)

    # ─────────────────────────────────────────────────────────
    # 누적 보강 효과 SVG 차트
    # ─────────────────────────────────────────────────────────
    st.markdown("### 📈 누적 보강 효과")
    st.caption("효율 좋은 항목을 누적 채택할수록 점수가 빠르게 상승하다 후반에 완만해지는 패턴 (체감 효용 체감)")

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
    """탭3: 예산 상한 / 목표 등급 최적화."""
    import streamlit as st
    import pandas as pd
    from core.bim_diagnoser import (
        optimize_within_budget,
        optimize_for_target_grade,
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
        ["예산 상한 (점수 최대화)", "목표 등급 (비용 최소화)"],
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
        col4.metric("예상 등급",
                    opt['예상등급'],
                    delta=f"{opt['현재등급']} → {opt['예상등급']}")

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
            st.dataframe(df, hide_index=True, use_container_width=True)
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
                st.dataframe(df_s, hide_index=True, use_container_width=True)

    else:
        # 목표 등급 선택
        target = st.select_slider(
            "목표 등급",
            options=["C", "B", "A", "A+"],
            value="B",
        )

        opt = optimize_for_target_grade(plan, target_grade=target, current_score=current_score)

        if opt["achievable"]:
            st.success(
                f"✅ 목표 등급 **{target}** 달성 가능 — "
                f"{opt['필요비용']/1e8:.2f}억 필요"
            )
        else:
            st.error(
                f"⚠️ 목표 등급 **{target}** 도달 불가 — "
                f"전 항목 보강 시 최대 {opt['달성점수']}점 (목표 {opt['목표점수']}점)"
            )

        col1, col2, col3 = st.columns(3)
        col1.metric("필요 비용", f"{opt['필요비용']/1e8:.2f}억")
        col2.metric("달성 점수", f"{opt['달성점수']}/100")
        col3.metric("달성 등급",
                    _grade_from_score(opt['달성점수']),
                    delta=f"{opt['현재등급']} → {_grade_from_score(opt['달성점수'])}")

        if opt['selected']:
            st.subheader(f"채택 항목 ({len(opt['selected'])}개)")
            df = pd.DataFrame([{
                "순위": i+1,
                "항목": p["label"],
                "수량": f"{p['수량']:.1f} {p['단위']}",
                "비용": f"{p['Max_Cost']:,}원",
                "Δ점수": f"+{p['점수상승']}",
            } for i, p in enumerate(opt['selected'])])
            st.dataframe(df, hide_index=True, use_container_width=True)


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
    area_m2 = scenario.get("연면적_m2", 1000)
    total_cost = sum(p.get("Max_Cost", 0) for p in plan)
    annual_saving = area_m2 * 9_900  # 보수적 단가 (원/m2/year)

    st.markdown("### 📈 민감도·시나리오 분석")
    st.caption(
        "성수동 PFV 사업수지 모델에서 영감 — 핵심 변수를 흔들면서 사업성 안정성 확인. "
        "심사위원에게 임팩트 있는 분석."
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
        st.dataframe(df, hide_index=True, use_container_width=True)

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
        st.dataframe(df, hide_index=True, use_container_width=True)

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
        st.dataframe(df, hide_index=True, use_container_width=True)

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
        "(ZEB 인증기준 고시 + ISO 13790 간이 방법 기반)"
    )

    # 모드 선택
    mode = st.radio(
        "평가 모드",
        ["🤖 자동 추정 (BIM 기반)", "📊 DesignBuilder 입력 (정밀)"],
        horizontal=True,
        help="자동: 11개 GR 충족도 기반. DesignBuilder: 시뮬레이션 결과 직접 입력."
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

    st.markdown("---")

    # ─────────────────────────────────────
    # 핵심 결과 — 자립률 + 등급
    # ─────────────────────────────────────
    autonomy = eval_result["autonomy_pct"]
    grade = eval_result["grade"]
    grade_num = grade["grade"]

    # 등급별 색상
    grade_colors = {
        1: "#4CAF50", 2: "#8BC34A", 3: "#FFC107",
        4: "#FF9800", 5: "#FF5722", 0: "#9E9E9E",
    }
    color = grade_colors.get(grade_num, "#9E9E9E")

    st.markdown(
        f"""
<div style="background:{color}; color:white; padding:20px; border-radius:12px; text-align:center; margin-bottom:16px;">
<div style="font-size:0.95em; opacity:0.9;">에너지자립률</div>
<div style="font-size:2.8em; font-weight:800; margin:6px 0;">{autonomy:.1f}%</div>
<div style="font-size:1.3em; font-weight:600;">{grade['label']}</div>
</div>
        """,
        unsafe_allow_html=True,
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
            "PV 발전(㎡당)",
            f"{eval_result['pv']['yield_per_m2_kwh']:.1f} kWh/㎡·년",
            help=eval_result["pv"].get("_source", ""),
        )

    # ─────────────────────────────────────
    # 등급 도달 가이드
    # ─────────────────────────────────────
    st.markdown("#### 🎯 등급 도달 가이드")

    target_grades = [(1, 100), (2, 80), (3, 60), (4, 40), (5, 20)]
    post_e = eval_result["post_energy_kwh_m2"]
    area = eval_result["area_m2"]

    grade_table = []
    for g, threshold in target_grades:
        # 자립률 X% 도달에 필요한 PV (kW)
        required_kwh_m2 = post_e * threshold / 100
        required_total_kwh = required_kwh_m2 * area
        required_kw = required_total_kwh / eval_result["pv"].get(
            "region_yield_per_kw", 1300
        ) if eval_result["pv"].get("region_yield_per_kw") else (
            required_total_kwh / 1300
        )
        is_achieved = autonomy >= threshold
        grade_table.append({
            "등급": f"ZEB {g}등급",
            "필요 자립률": f"{threshold}%",
            "필요 PV": f"{required_kw:.1f} kW",
            "현재 상태": "✅ 달성" if is_achieved else "❌ 부족",
        })

    import pandas as pd
    df = pd.DataFrame(grade_table)
    st.dataframe(df, hide_index=True, use_container_width=True)

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
            st.dataframe(df2, hide_index=True, use_container_width=True)

    # ─────────────────────────────────────
    # 해석
    # ─────────────────────────────────────
    st.info(
        f"💡 **해석**: 이 건물은 보강 후 자립률 **{autonomy:.1f}%**로 "
        f"**{grade['label']}**에 해당합니다. "
        + (
            f"ZEB {grade_num - 1}등급 도달까지 추가 PV 또는 절감이 필요합니다."
            if grade_num > 1 else
            "최고 등급에 도달했습니다. 🎉"
        )
    )


def _render_full_report_tab(result: dict, source_name: str) -> None:
    """탭4: 마크다운 전체 리포트 + 다운로드 (마크다운/PDF 2종)."""
    import streamlit as st
    from pathlib import Path

    report = result["report"]
    st.markdown(report)

    st.divider()
    file_stem = Path(source_name).stem

    # 다운로드 버튼 2개 (마크다운 / PDF)
    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            label="📄 마크다운 다운로드 (.md)",
            data=report,
            file_name=f"진단리포트_{file_stem}.md",
            mime="text/markdown",
            use_container_width=True,
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
                file_name=f"진단리포트_{file_stem}.pdf",
                mime="application/pdf",
                use_container_width=True,
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

def _grade_from_score(score: int) -> str:
    if score >= 85:
        return "A+"
    elif score >= 75:
        return "A"
    elif score >= 65:
        return "B"
    elif score >= 50:
        return "C"
    return "D"
