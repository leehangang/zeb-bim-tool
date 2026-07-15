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
        "📐 근거·출처",
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
            **ZEB-ROI**

            AI Agent 기반 ZEB / 그린리모델링 평가 및 ROI 산정 플랫폼.

            **설계 원칙**
            - 파인튜닝이 아닌 **Agent + RAG** — 단가·법령이 수시로 바뀌므로
            - **계산은 엔진이, 언어만 LLM이** — 숫자는 결정론적으로 산출
            - 법령은 **RAG로 원문 인용**, 없으면 없다고 답변 (환각 차단)
            - **ZEB ≠ 그린리모델링** — 판정은 분리, 데이터·해석 기반은 공유

            - 케이스: KEPCO 도담어린이집 (김천)

            **RAG 색인 원문 (11건 · 874청크)**
              - 04 녹색건축물 조성 지원법 (제20727호, 2026.2.1)
              - 10 같은 법 시행령 (제36231호, 2026.3.31)
              - 11 GR 지원사업 운영 고시 (제2023-385호)
              - 12 ZEB 인증에 관한 규칙 (기후에너지환경부령 제1호)
              - 06 에너지절약설계기준 (제2025-738호, 2025.12.31)
              - 05 지방세특례제한법
              - 13 건축법 시행령 (제35717호)
              - 14 공공기관의 운영에 관한 법률
              - 15 탄소중립기본법 시행령 (제36303호)
              - 16·17 2026년 GR 공고 (민간 이자지원 / 공공 2.0)

            **산정 데이터**
              - 07/08 조달청 단가DB·간접공사비
              - `data/params/*.yaml` (요율·한도 + 출처·시행일)

            ⚠️ 01 GR 가이드라인 · 02 GR 기술요소 · 03 ZEB 인증기준 고시 ·
            09 영유아보육법은 **이미지 스캔본**이라 텍스트 추출이 불가해
            색인에서 제외돼 있습니다 (원문 PDF 확보 필요).

            상세 아키텍처: `docs/ARCHITECTURE.md`
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

    # 히어로 영역 — 제로에너지건축물(ZEB) 등급 평가 중심
    st.markdown("""
    <div class="zeb-hero">
        <div class="eyebrow">ZERO ENERGY BUILDING · GREEN REMODELING</div>
        <h1>BIM 한 번으로 <span class="accent">제로에너지건축물(ZEB)</span> 등급을 평가하고<br>그린리모델링 전 과정을 설계합니다</h1>
        <p class="lede">
            Revit BIM 모델을 업로드하면 건물의 <b>ZEB 인증 등급</b>을 자동 평가하고,
            그 등급에 도달하기 위한 <b>그린리모델링</b> 보강 우선순위 · 비용(Max Cost) ·
            보조금 · 회수기간까지 한 자리에서 산출합니다.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # 핵심 수치 (KEPCO 도담 검증 기준) — ZEB 등급 평가가 우리 플랫폼의 출발점
    st.markdown("### 검증 결과 — KEPCO 도담어린이집")

    st.markdown("**① ZEB 인증 등급 평가** — 본 플랫폼의 핵심")
    z1, z2, z3 = st.columns(3)
    z1.metric("현재 ZEB", "인증 미달", "1차E 소요량 166.7 kWh/㎡·년")
    z2.metric("보강 후 ZEB", "4등급", "제2호 기준 충족 ✅")
    z3.metric("1차에너지소요량", "66.0", "166.7 → 66.0 kWh/㎡·년 (90 미만)")
    st.caption(
        "ZEB 인증등급은 **제1호(에너지자립률) 또는 제2호(1차에너지소요량) 중 상위 등급**으로 정하고, "
        "제3호(BEMS 13항목)를 함께 충족해야 합니다(인증기준 고시 별표2 주1·주2). "
        "**보강 후 4등급은 제2호(소요량 66.0 < 비주거 4등급 기준 90) 근거**입니다. "
        "도담은 태양광이 없어 **에너지자립률(제1호)이 0%** 이며, 4등급은 "
        "**태양광이 아니라 외피·설비 효율개선으로 소요량을 낮춰서** 나옵니다. "
        "‘보강 후’는 11개 GR 기술요소 전체 적용 + BEMS 설치를 가정한 잠재 등급입니다."
    )
    st.info(
        "🔧 **정정 반영(2026-07)** — 기존에 도담의 **태양열집열판 27㎡(급탕용)를 태양광 5.4kW로 오분류**해 "
        "자립률이 9.3%로 과대 산정되고, 진단 페이지(5.6%)와 홈(9.3%)의 값도 서로 달랐습니다. "
        "GR 고시 §7 제6호 **가목(태양광·전력)/나목(태양열·급탕)을 분리**하고 자립률 산출처를 "
        "ZEB 엔진 하나로 통일해 정정했습니다. **등급 결론(4등급)은 제2호 근거라 그대로입니다.**",
        icon="🔧",
    )
    st.warning(
        "⚠️ **확인 필요** — 보강 후 절감률 **67%는 요소별 가정치**(`GR_ENERGY_REDUCTION`)의 합입니다. "
        "제2호 4등급의 임계는 **절감률 55%** 라서 여유가 12%p뿐이며, "
        "**ECO2/EnergyPlus로 재계산하면 등급이 5등급으로 내려갈 수 있습니다.** "
        "(ZEB 자립률 공식 산정 도구는 ECO2, GR 성능개선비율은 EnergyPlus 등 지정 프로그램)",
        icon="⚠️",
    )

    st.markdown("**② BIM 정밀 진단** — 11개 그린리모델링 기술요소 채점")
    d1, d2, d3 = st.columns(3)
    d1.metric("현재 등급", "D", "25 / 100점")
    d2.metric("보강 후 등급", "A", "+50점")
    d3.metric("전체 보강비 (Max Cost)", "5.31억", "11개 항목 전체")

    st.markdown("**③ 재무성 — 에너지 절감 회수**")
    f1, f2, f3 = st.columns(3)
    f1.metric("외피 보강 Max Cost", "1.81억", "50% 보조 → 자부담 0.91억")
    f2.metric("연간 에너지 절감", "1,238만원", "㎡당 9,900원 가정 · 확인 필요")
    f3.metric("단순 회수 기간", "7.3년", "GR 단독 (에너지 절감만)")
    st.caption(
        "⚠️ **연간 절감액은 아직 가정치입니다.** 현재는 연면적 × 9,900원/㎡ 단일 계수로 산출하며 "
        "(1,251㎡ × 9,900원 = 1,238만원), ZEB 엔진이 계산한 **kWh 절감량과 연결되어 있지 않고 "
        "연료원(전기·가스·열) 구분도 없습니다.** "
        "전기요금표·가스단가를 `data/params/energy_tariff.yaml`에 채워 "
        "`절감kWh × 단가`로 환산하는 작업이 예정되어 있습니다."
    )

    st.markdown("**④ 경제성 — 현금흐름 기반 (20년 · 할인율 4.5%)**")
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

    # ── 두 트랙 구조 (ZEB 인증 ≠ 그린리모델링 사업) ──────────────────
    st.markdown("### 두 개의 제도, 하나의 BIM 입력")
    st.markdown(
        "ZEB 인증과 그린리모델링 사업은 **근거 법령과 판정 방식이 다른 별개의 제도**입니다. "
        "본 플랫폼은 두 트랙을 나눠 판정하되, **BIM 파싱·에너지 해석·단가DB·법령 RAG는 하나의 공유 코어**로 처리합니다."
    )

    t1, t2 = st.columns(2)
    with t1:
        st.markdown(
            "<div style='border-left:3px solid #C18A2D; padding:0.1rem 0 0.1rem 0.8rem; margin-bottom:0.6rem;'>"
            "<b>TRACK A · ZEB 인증</b><br>"
            "<span style='color:#5C665F; font-size:0.88rem;'>목표: 인증 등급 취득 · "
            "근거: ZEB 인증기준 고시(제1·2·3호)</span></div>",
            unsafe_allow_html=True,
        )
        st.markdown(card_html(
            "🏢",
            "ZEB 등급 평가",
            "에너지 자립률 <b>또는</b> 1차에너지소요량, <b>그리고</b> BEMS로 인증 등급(+등급~5등급)을 "
            "판정합니다. 전력은 1차에너지 환산계수 ×2.75를 적용합니다.",
            badge="핵심 엔진"
        ), unsafe_allow_html=True)

    with t2:
        st.markdown(
            "<div style='border-left:3px solid #1B5E20; padding:0.1rem 0 0.1rem 0.8rem; margin-bottom:0.6rem;'>"
            "<b>TRACK B · 그린리모델링 사업</b><br>"
            "<span style='color:#5C665F; font-size:0.88rem;'>목표: 사업 선정 + 경제성 · "
            "근거: GR 가이드라인 정량평가표</span></div>",
            unsafe_allow_html=True,
        )
        st.markdown(card_html(
            "🏗️",
            "BIM 정밀 진단 + 보강 계획",
            "11개 기술요소를 100점(기술요소 80 + 사업여건 20)으로 채점해 등급(A+~D)을 내고, "
            "비용 효율순 보강 우선순위·Max Cost를 산출합니다.",
        ), unsafe_allow_html=True)

    b1, b2 = st.columns(2)
    with b1:
        st.markdown(card_html(
            "💰",
            "ROI 시뮬레이션",
            "자연어로 건물 조건을 입력하면 단가DB·간접비·보조금·용적률·취득세를 묶어 "
            "Max Cost·자부담·NPV/IRR·회수기간을 산출합니다.",
        ), unsafe_allow_html=True)
    with b2:
        st.markdown(card_html(
            "📋",
            "사업 신청 인테이크",
            "신청에 필요한 항목을 대화로 수집하고 신청서 초안을 자동 생성합니다.",
        ), unsafe_allow_html=True)

    st.markdown(
        "<div style='border-left:3px solid #9BA39C; padding:0.1rem 0 0.1rem 0.8rem; margin:0.8rem 0 0.6rem;'>"
        "<b>공통 · 근거 레이어</b><br>"
        "<span style='color:#5C665F; font-size:0.88rem;'>두 트랙이 함께 쓰는 법령·고시 근거</span></div>",
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(card_html(
            "💬",
            "정책 Q&A (RAG)",
            "<b>11개 법령·고시·공고 원문</b>(법률·시행령·고시·2026년 공고)에서 근거 조항을 찾아 <b>인용</b>해 답변합니다. "
            "원문에 없으면 지어내지 않고 '자료에 없음'이라고 답해 <b>환각을 차단</b>합니다.",
        ), unsafe_allow_html=True)
    with c2:
        st.markdown(card_html(
            "📐",
            "근거·출처",
            "위 숫자가 <b>어느 조항의, 언제 시행된 값</b>인지 파라미터 YAML에서 실시간으로 펼쳐 보여주고, "
            "<b>아직 확인 못 한 값</b>과 등급이 뒤집히는 <b>임계 절감률</b>까지 숨기지 않고 공개합니다.",
            badge="투명성",
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

elif mode == "📐 근거·출처":
    from modes.mode5_evidence import render_evidence_panel
    render_evidence_panel()


# 푸터
render_footer()
