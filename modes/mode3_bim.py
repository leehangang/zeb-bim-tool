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

    # 입력 영역
    col_upload, col_opts = st.columns([2, 1])

    with col_upload:
        uploaded = st.file_uploader(
            "BIM JSON 파일 업로드",
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
    # 입력 키: 파일 이름 + 크기 + 공사 기간. 변경되면 재진단.
    if uploaded is not None:
        input_key = (uploaded.name, uploaded.size, duration)
    else:
        input_key = None

    cached_key = st.session_state.get("_mode3_input_key")
    cached_result = st.session_state.get("_mode3_result")

    need_run = False
    if run_btn and uploaded is not None:
        # 사용자가 명시적으로 진단 실행 버튼 눌렀을 때
        need_run = True
    elif uploaded is not None and input_key != cached_key:
        # 파일 업로드되었고 입력이 바뀐 경우 (캐시 무효)
        need_run = (cached_result is None) or run_btn

    if uploaded is None and cached_result is None:
        st.info(
            "👈 BIM JSON 파일을 업로드한 뒤 **진단 실행** 버튼을 눌러주세요.\n\n"
            "스키마 예시: `data/sample_bim/doam_archi_sample.json`"
        )
        return

    if need_run:
        try:
            tmp_path = save_uploaded_to_temp(uploaded)
            with st.spinner("진단 중... (단가DB 로드 + 11개 항목 ROI 산정)"):
                result = run_bim_diagnosis(
                    tmp_path,
                    with_roi=True,
                    duration_months=duration,
                )
        except json.JSONDecodeError as e:
            st.error(f"❌ JSON 파싱 실패: {e}")
            return
        except KeyError as e:
            st.error(f"❌ JSON 스키마 오류: 필수 키 누락 — {e}")
            st.caption("스키마 예시는 `data/sample_bim/doam_archi_sample.json`을 참고하세요.")
            return
        except Exception as e:
            st.error(f"❌ 진단 실패: {type(e).__name__}: {e}")
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
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 진단 결과",
        "💰 ROI 보강 계획",
        "🎯 최적화",
        "📄 전체 리포트",
    ])

    # 파일명: 현재 업로드 또는 캐시 키에서 추출
    source_name = uploaded.name if uploaded is not None else (
        cached_key[0] if cached_key else "bim.json"
    )

    with tab1:
        _render_diagnosis_tab(result)
    with tab2:
        _render_roi_tab(result)
    with tab3:
        _render_optimization_tab(result)
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
    from core.ui_theme import COLORS

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

        html_parts.append(f"""
        <div style="margin-bottom:0.8rem;">
          <div style="display:flex; justify-content:space-between; margin-bottom:0.25rem;">
            <span style="font-weight:500; font-size:0.92rem;">{label}{detail_html}</span>
            <span style="color:{color}; font-weight:600; font-size:0.9rem;">
              {score_val}/{max_val}점 ({pct:.0f}%)
            </span>
          </div>
          <div style="background:#F0F0F0; border-radius:6px; height:10px; overflow:hidden;">
            <div style="background:{bg}; height:100%; width:{pct}%; transition: width 0.3s ease;"></div>
          </div>
        </div>
        """)
    html_parts.append('</div>')
    st.markdown("\n".join(html_parts), unsafe_allow_html=True)


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


def _render_full_report_tab(result: dict, source_name: str) -> None:
    """탭4: 마크다운 전체 리포트 + 다운로드."""
    import streamlit as st

    report = result["report"]
    st.markdown(report)

    st.divider()
    file_stem = Path(source_name).stem
    st.download_button(
        label="📥 진단 리포트 다운로드 (.md)",
        data=report,
        file_name=f"진단리포트_{file_stem}.md",
        mime="text/markdown",
    )


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
