import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

"""
ZEB-ROI 그린리모델링 의사결정 플랫폼 — 메인 앱
============================================
4개 모드 통합 Streamlit 챗봇 + 랜딩 페이지.

실행:
    streamlit run streamlit_app.py
"""

import os
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
    apply_global_style, render_logo, render_footer,
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

    has_api = _check_anthropic_key()
    has_index = _check_rag_index()

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

    # 시스템 상태
    with st.expander("🔧 시스템 상태", expanded=False):
        st.markdown(f"- Claude API: {'🟢 연결됨' if has_api else '🔴 키 미설정'}")
        st.markdown(f"- RAG 인덱스: {'🟢 준비됨' if has_index else '🟡 미생성'}")
        st.markdown(f"- 단가DB: 🟢 로드 가능")

        if not has_api:
            st.caption("→ Mode 1, 2, 4 사용 시 .env에 ANTHROPIC_API_KEY 필요")
        if not has_index:
            st.caption("→ Mode 1 사용 시 `python scripts/build_index.py` 실행")

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
    <div style="padding: 2.5rem 0 2rem 0; text-align: center;">
        <div style="font-size: 0.95rem; color: #2E7D32; font-weight: 600; letter-spacing: 0.1em;">
            ZERO ENERGY BUILDING · ROI ANALYSIS PLATFORM
        </div>
        <h1 style="font-size: 2.6rem !important; margin-top: 0.5rem; line-height: 1.2;">
            BIM 한 번으로 <span style="color: #1B5E20;">그린리모델링</span> 전 과정을<br>
            한 자리에서 분석하세요
        </h1>
        <p style="font-size: 1.1rem; color: #757575; margin-top: 1rem; max-width: 700px; margin-left: auto; margin-right: auto;">
            Revit BIM 모델 업로드 → 11개 GR 기술요소 자동 평가 →
            보강 우선순위 + Max Cost + 보조금 + 회수기간 통합 산출
        </p>
    </div>
    """, unsafe_allow_html=True)

    # 핵심 수치 (KEPCO 도담 검증 기준)
    st.markdown("### 검증 결과 — KEPCO 도담어린이집")

    st.markdown("**① BIM 정밀 진단**")
    d1, d2, d3 = st.columns(3)
    d1.metric("현재 등급", "D", "25 / 100점")
    d2.metric("보강 후 등급", "A", "+50점")
    d3.metric("BIM 정밀 보강비", "5.07억", "점수 기여 항목 기준")

    st.markdown("**② 재무성 — 에너지 절감 회수**")
    f1, f2, f3 = st.columns(3)
    f1.metric("외피 보강 Max Cost", "1.81억", "50% 보조 → 자부담 0.91억")
    f2.metric("연간 에너지 절감", "1,238만원", "BIM 정밀 산정")
    f3.metric("단순 회수 기간", "7.3년", "GR 단독 (에너지 절감만)")

    st.markdown("**③ 경제성 — 현금흐름 기반 (20년 · 할인율 4.5%)**")
    g1, g2, g3 = st.columns(3)
    g1.metric("NPV (순현재가치)", "+1.08억", "자부담 대비 순이득")
    g2.metric("IRR (내부수익률)", "14.7%", "할인율의 3.3배")
    g3.metric("B-C 비율", "2.18배", "투입 1원당 편익 2.18원")

    st.caption(
        "※ ③ 경제성은 자부담(0.91억)을 투자로 본 현금흐름 지표입니다. "
        "별도 관점으로 수익환원법 자산가치 상승 ≈ 2.48억(환원율 5%, ΔNOI÷Cap) — "
        "에너지 절감→NOI↑→자산가치↑를 감정평가 방식으로 환산한 것이며 "
        "NPV와 합산하지 않습니다(같은 절감의 다른 표현). "
        "용적률 완화 증축 자산가치는 증축 계획 시에만 적용되는 조건부 항목으로 분리 제시합니다."
    )

    st.markdown("---")

    # 4개 모드 카드
    st.markdown("### 4가지 모드를 자유롭게 선택하세요")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(card_html(
            "🏢",
            "BIM 진단 + ROI 분석",
            "Dynamo로 추출한 Revit BIM JSON을 업로드하면 11개 GR 기술요소를 자동 매핑하고, "
            "01 가이드라인 정량평가표로 채점하며, 보강 우선순위를 효율 순으로 산출합니다.",
            badge="API 키 불필요"
        ), unsafe_allow_html=True)

        st.markdown(card_html(
            "💰",
            "ROI 시뮬레이션",
            "자연어로 \"연면적 1,200㎡, ZEB 5등급 목표\"라고 말하면 Claude가 파라미터를 추출해 "
            "Max Cost·보조금·취득세 감면·회수기간을 한 번에 산출합니다.",
            badge=None if has_api else "API 키 필요"
        ), unsafe_allow_html=True)

    with col2:
        st.markdown(card_html(
            "💬",
            "정책 Q&A (RAG)",
            "01/03/04/05/06/09 7개 법·고시·가이드라인을 ChromaDB로 인덱싱한 검색-증강 챗봇. "
            "근거 조항을 인용해 답변합니다.",
            badge=None if (has_api and has_index) else (
                "인덱스 필요" if not has_index else "API 키 필요"
            )
        ), unsafe_allow_html=True)

        st.markdown(card_html(
            "📋",
            "사업 신청 인테이크",
            "공공건축물 그린리모델링 사업 신청에 필요한 21개 항목을 챗봇과 대화로 수집하고 "
            "신청서 초안 마크다운을 자동 생성합니다.",
            badge=None if has_api else "API 키 필요"
        ), unsafe_allow_html=True)

    st.markdown("---")

    # 빠른 시작
    st.markdown("### 🚀 빠른 시작")
    quickstart = st.columns([1, 1, 1])
    with quickstart[0]:
        st.markdown(
            """
            **1️⃣ 데모 데이터로 체험**
            
            왼쪽 사이드바에서 **🏢 BIM 진단 + ROI** 선택 →
            `doam_archi_sample.json` 업로드 → 진단 실행
            """
        )
    with quickstart[1]:
        st.markdown(
            """
            **2️⃣ Claude API 키 설정**
            
            `.env` 파일에 `ANTHROPIC_API_KEY` 입력 →
            챗봇 재시작 → Mode 1/2/4 활성화
            """
        )
    with quickstart[2]:
        st.markdown(
            """
            **3️⃣ 정책 자료 인덱싱**
            
            `python scripts/build_index.py` 실행 →
            7개 PDF가 ChromaDB로 벡터화 → Mode 1 활성화
            """
        )

    # 기술 스택
    st.markdown("---")
    st.markdown("### 🛠 기술 스택")
    tech_col1, tech_col2, tech_col3, tech_col4 = st.columns(4)
    with tech_col1:
        st.markdown("**BIM 진단 엔진**")
        st.caption("• Python 3.10+\n• 11개 GR 매핑 규칙\n• 효율 기반 우선순위")
    with tech_col2:
        st.markdown("**ROI 계산기**")
        st.caption("• 07 조달청 단가DB\n• 08 간접공사비 매트릭스\n• 보조금·감면·인센티브")
    with tech_col3:
        st.markdown("**RAG 검색**")
        st.caption("• ChromaDB\n• OpenAI/Local 임베딩\n• 페이지 단위 청킹")
    with tech_col4:
        st.markdown("**Function Calling**")
        st.caption("• Claude Haiku 4.5\n• 자연어 → 도구 호출\n• 멀티턴 대화")


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
