import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

# ZEB-ROI 그린리모델링 의사결정 플랫폼 — 메인 앱
# 4개 모드 통합 Streamlit 앱 + 랜딩 페이지.
# 실행: streamlit run streamlit_app.py
# (주의: 위 설명을 트리플쿼트 문자열로 두면 import os 다음이라 docstring이
#  아니라 bare expression이 되어 Streamlit magic으로 화면에 렌더됨 → 주석 유지)

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# 페이지 설정 (최상단에서 1회만)
st.set_page_config(
    page_title="ZEB-ROI · 그린리모델링 플랫폼",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

from core.ui_theme import (
    apply_global_style, render_logo, render_footer, render_topbar,
    card_html, GRADE_COLORS, COLORS,
)

apply_global_style()


# ====================================================================
# API 키 / 인덱스 상태 점검
# ====================================================================

def _check_anthropic_key() -> bool:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    return bool(key) and not key.startswith("sk-ant-api03-여기")


def _check_rag_index() -> bool:
    from pathlib import Path
    return Path("./data/chroma_db").exists() and any(
        Path("./data/chroma_db").iterdir()
    )


def _auto_unzip_chroma_if_needed():
    """
    data/chroma_db.zip을 항상 data/chroma_db/ 안에 올바른 폴더 구조로 압축 해제.
    Windows(PowerShell) zip의 역슬래시 경로를 슬래시로 정규화해
    배포 환경(Linux)에서도 UUID 폴더가 폴더로 풀리게 한다.
    """
    from pathlib import Path
    import zipfile

    chroma_dir = Path("./data/chroma_db")
    chroma_zip = Path("./data/chroma_db.zip")

    if (chroma_dir / "chroma.sqlite3").exists():
        return
    if not chroma_zip.exists():
        return

    chroma_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(chroma_zip, "r") as zf:
        for info in zf.infolist():
            rel = info.filename.replace("\\", "/").lstrip("/")
            if not rel or rel.endswith("/"):
                continue
            target = chroma_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())

# 앱 시작 시 1회 실행
_auto_unzip_chroma_if_needed()


# ====================================================================
# 사이드바
# ====================================================================

with st.sidebar:
    render_logo("default")
    st.markdown(
        '<div style="text-align:center; color:#757575; font-size:0.8rem; '
        'margin-top:-0.3rem; margin-bottom:0.5rem;">'
        'ZEB-ROI · 그린리모델링 의사결정 플랫폼'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # 모드 선택
    st.markdown("**모드 선택**")

    mode_options = [
        "🏠 홈",
        "🏢 BIM 진단 + ROI",
        "💬 정책 Q&A",
        "💰 ROI 시뮬레이션",
        "📋 사업 신청 인테이크",
    ]
    mode = st.radio(
        label="모드 선택",
        options=mode_options,
        index=0,
        label_visibility="collapsed",
    )

    st.markdown("---")

    # 프로젝트 정보
    with st.expander("ℹ️ 프로젝트 정보", expanded=False):
        st.markdown(
            """
            **ZEB-BIM-Tool**
            
            BIM 기반 그린리모델링 자동 진단 + ROI 분석 플랫폼.
            
            - 케이스: KEPCO 도담어린이집 (김천)
            - 데이터 출처:
              - 01 GR 가이드라인 (LH·국토부)
              - 03 ZEB 인증기준 고시
              - 04 녹색건축법
              - 05 지방세특례제한법
              - 07/08 조달청 단가DB·간접공사비
              - 09 영유아보육법 시행규칙
            """
        )

    st.markdown("---")
    st.caption(
        "⚠️ 자동 산출 결과로 참고용입니다. "
        "실제 사업 신청 시 그린리모델링 창조센터 공식 컨설팅 필수."
    )


# ====================================================================
# 메인 영역 라우팅
# ====================================================================

def render_home():
    """랜딩 페이지 — 4개 모드 카드 + 핵심 지표"""

    # 히어로 영역
    st.markdown("""
    <div class="zeb-hero">
        <div class="eyebrow">ZERO ENERGY BUILDING · ROI ANALYSIS</div>
        <h1>BIM 한 번으로 <span class="accent">그린리모델링</span> 전 과정을<br>한 자리에서 분석합니다</h1>
        <p class="lede">
            Revit BIM 모델을 업로드하면 11개 GR 기술요소를 자동 평가하고,
            보강 우선순위 · Max Cost · 보조금 · ZEB 등급 · 회수기간을 통합 산출합니다.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # 핵심 수치 (KEPCO 도담 검증 기준)
    st.markdown("### 검증 결과 — KEPCO 도담어린이집")

    st.markdown("**① BIM 정밀 진단**")
    d1, d2, d3 = st.columns(3)
    d1.metric("현재 등급", "D", "25 / 100점")
    d2.metric("보강 후 등급", "A", "+50점")
    d3.metric("전체 보강비 (Max Cost)", "5.31억", "11개 항목 전체")

    st.markdown("**② 재무성 — 에너지 절감 회수**")
    f1, f2, f3 = st.columns(3)
    f1.metric("외피 보강 Max Cost", "1.81억", "50% 보조 → 자부담 0.91억")
    f2.metric("연간 에너지 절감", "1,238만원", "BIM 정밀 산정")
    f3.metric("단순 회수 기간", "7.3년", "GR 단독 (에너지 절감만)")

    st.markdown("**③ 경제성 — 현금흐름 기반 (20년 · 할인율 4.5%)**")
    g1, g2, g3 = st.columns(3)
    g1.metric("NPV (순현재가치)", "+1.08억", "자부담 대비 순이득")
    g2.metric("IRR (내부수익률)", "14.7%", "할인율의 3.3배")
    g3.metric("B-C 비율", "2.19배", "투입 1원당 편익 2.19원")

    st.caption(
        "③ 경제성은 자부담(0.91억)을 투자로 본 현금흐름 지표입니다. "
        "에너지 절감을 자산가치로 환산한 수익환원 가치(≈2.48억, 환원율 5%)는 "
        "같은 절감의 다른 표현이라 NPV와 합산하지 않고 별도 관점으로 봅니다."
    )

    st.markdown("---")

    # 4개 모드 카드
    st.markdown("### 4가지 모드를 자유롭게 선택하세요")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(card_html(
            "🏢",
            "BIM 진단 + ROI 분석",
            "BIM 모델을 업로드하면 11개 그린리모델링 기술요소를 자동 진단하고, "
            "보강 우선순위·비용·보조금·ZEB 등급·회수기간을 한 번에 산출합니다.",
            badge="핵심 엔진"
        ), unsafe_allow_html=True)

        st.markdown(card_html(
            "💰",
            "ROI 시뮬레이션",
            "자연어로 건물 조건(연면적·목표 등급 등)을 입력하면 공사비·보조금·"
            "취득세 감면·회수기간을 즉시 계산합니다.",
        ), unsafe_allow_html=True)

    with col2:
        st.markdown(card_html(
            "💬",
            "정책 Q&A",
            "그린리모델링 관련 법·고시·가이드라인 원문에서 근거 조항을 찾아 "
            "인용하며 답변합니다.",
        ), unsafe_allow_html=True)

        st.markdown(card_html(
            "📋",
            "사업 신청 인테이크",
            "공공건축물 그린리모델링 사업 신청에 필요한 항목을 대화로 수집하고 "
            "신청서 초안을 자동 생성합니다.",
        ), unsafe_allow_html=True)


# 상단 브랜드 바 (모든 페이지 공통 프레임)
render_topbar()

# 모드 라우팅
if mode == "🏠 홈":
    render_home()

elif mode == "🏢 BIM 진단 + ROI":
    from modes.mode3_bim import render_bim_panel
    render_bim_panel()

elif mode == "💬 정책 Q&A":
    from modes.mode1_rag import render_rag_panel
    render_rag_panel()

elif mode == "💰 ROI 시뮬레이션":
    from modes.mode2_roi import render_roi_panel
    render_roi_panel()

elif mode == "📋 사업 신청 인테이크":
    from modes.mode4_intake import render_intake_panel
    render_intake_panel()


# 푸터
render_footer()
