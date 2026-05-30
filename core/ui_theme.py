"""
core/ui_theme.py — 글로벌 디자인 시스템
==========================================
모든 모드에서 공통 사용하는 컬러, 폰트, CSS 주입, 재사용 UI 컴포넌트.

사용:
    from core.ui_theme import apply_global_style, render_logo, GRADE_COLORS

    apply_global_style()         # 페이지 시작 시 1회
    render_logo("sidebar")        # 사이드바 또는 헤더에서
"""

# ====================================================================
# 컬러 팔레트 (그린리모델링 톤)
# ====================================================================

COLORS = {
    # Primary - 딥 그린 (브랜드)
    "primary_900": "#0B3D0B",
    "primary_700": "#1B5E20",
    "primary_500": "#2E7D32",
    "primary_300": "#66BB6A",
    "primary_100": "#C8E6C9",

    # Accent - 라임 (강조)
    "accent_500": "#76FF03",
    "accent_300": "#B2FF59",

    # Neutral
    "ink_900": "#1A1A1A",
    "ink_700": "#424242",
    "ink_500": "#757575",
    "ink_300": "#BDBDBD",
    "ink_100": "#F5F5F5",
    "white": "#FFFFFF",

    # Earth (따뜻한 보조색)
    "earth_700": "#5D4037",
    "earth_500": "#8D6E63",

    # 의미 색상
    "success": "#43A047",
    "warning": "#FB8C00",
    "danger": "#E53935",
    "info": "#1E88E5",
}


GRADE_COLORS = {
    "A+": "#1B5E20",     # 진초록
    "A":  "#388E3C",
    "B":  "#7CB342",     # 라임그린
    "C":  "#FB8C00",     # 주황
    "D":  "#E53935",     # 빨강
}


# ====================================================================
# 글로벌 CSS
# ====================================================================

GLOBAL_CSS = """
<style>
/* Pretendard 폰트 (한국어 최적화) */
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');

/* Pretendard를 기본 폰트로만 등록 — 강제하지 않음 */
.stApp {
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Roboto, sans-serif;
}

/* 모든 Material 아이콘 폰트 강제 보호 (텍스트로 깨지지 않도록) */
[class*="material-symbols"],
[class*="material-icons"],
span[data-testid="stIconMaterial"],
[data-testid*="Icon"],
[data-testid*="icon"] {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined',
                 'Material Icons' !important;
    font-size: 1.2rem !important;
    line-height: 1 !important;
}

/* 사이드바 토글 / 햄버거 메뉴 / 헤더 버튼 영역 */
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
button[kind="header"],
[data-testid="stHeaderActionElements"],
[data-testid="stMainMenu"],
[data-testid="baseButton-headerNoPadding"] {
    font-family: 'Material Symbols Rounded', 'Material Icons' !important;
}
[data-testid="stSidebarCollapseButton"] *,
[data-testid="stSidebarCollapsedControl"] *,
[data-testid="collapsedControl"] *,
button[kind="header"] *,
[data-testid="stHeaderActionElements"] *,
[data-testid="stMainMenu"] * {
    font-family: 'Material Symbols Rounded', 'Material Icons' !important;
    font-size: 1.2rem !important;
}

/* Expander 화살표 영역 보호 */
details > summary > span:first-child,
.streamlit-expanderHeader > div > svg {
    font-family: 'Material Symbols Rounded', 'Material Icons' !important;
}

/* 메인 영역 padding 줄이기 */
.main .block-container {
    padding-top: 2rem;
    padding-bottom: 3rem;
    max-width: 1400px;
}

/* 헤더 폰트 */
h1, h2, h3 {
    font-weight: 700 !important;
    color: #1A1A1A;
    letter-spacing: -0.02em;
}
h1 { font-size: 2.0rem !important; }
h2 { font-size: 1.5rem !important; }
h3 { font-size: 1.2rem !important; }

/* Streamlit 기본 헤더 작아지게 */
[data-testid="stHeader"] {
    background: rgba(255,255,255,0.0);
}

/* primary 버튼 */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #1B5E20 0%, #2E7D32 100%) !important;
    border: none !important;
    font-weight: 600 !important;
    box-shadow: 0 2px 8px rgba(27, 94, 32, 0.25) !important;
    transition: all 0.2s ease !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 16px rgba(27, 94, 32, 0.35) !important;
    transform: translateY(-1px);
}

/* secondary 버튼 */
.stButton > button[kind="secondary"] {
    border: 1.5px solid #1B5E20 !important;
    color: #1B5E20 !important;
    font-weight: 500 !important;
}

/* Metric 박스 */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #ffffff 0%, #f9fbf9 100%);
    padding: 1rem 1.25rem;
    border-radius: 12px;
    border: 1px solid #E0E0E0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    transition: box-shadow 0.2s ease;
}
[data-testid="stMetric"]:hover {
    box-shadow: 0 4px 12px rgba(27, 94, 32, 0.08);
}
[data-testid="stMetricLabel"] {
    font-size: 0.85rem !important;
    color: #757575 !important;
    font-weight: 500 !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.75rem !important;
    color: #1A1A1A !important;
    font-weight: 700 !important;
}
[data-testid="stMetricDelta"] {
    font-size: 0.8rem !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.5rem;
    border-bottom: 2px solid #E0E0E0;
}
.stTabs [data-baseweb="tab"] {
    padding: 0.6rem 1.2rem !important;
    font-weight: 500 !important;
    border-radius: 8px 8px 0 0 !important;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(180deg, #f1f8f1 0%, #ffffff 100%) !important;
    color: #1B5E20 !important;
    font-weight: 600 !important;
    border-bottom: 3px solid #1B5E20 !important;
}

/* Expander */
.streamlit-expanderHeader {
    background: #FAFAFA;
    border-radius: 8px;
    font-weight: 500 !important;
}

/* Info / Success / Warning / Error 박스 */
.stAlert {
    border-radius: 10px !important;
    border: none !important;
}

/* 사이드바 배경 */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #f9fbf9 0%, #ffffff 100%);
    border-right: 1px solid #E0E0E0;
}
section[data-testid="stSidebar"] .stRadio > div {
    gap: 0.4rem;
}
section[data-testid="stSidebar"] .stRadio label {
    padding: 0.6rem 0.8rem;
    border-radius: 8px;
    transition: background 0.15s ease;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
}
section[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(27, 94, 32, 0.06);
}

/* 데이터프레임 */
[data-testid="stDataFrame"] {
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid #E0E0E0;
}

/* 진행바 */
.stProgress > div > div > div > div {
    background: linear-gradient(90deg, #2E7D32 0%, #76FF03 100%);
}

/* 다운로드 버튼 */
.stDownloadButton > button {
    background: #1B5E20 !important;
    color: white !important;
    border: none !important;
    font-weight: 500 !important;
}

/* 코드 블록 */
code {
    background: #F5F5F5 !important;
    color: #1B5E20 !important;
    padding: 0.15rem 0.4rem !important;
    border-radius: 4px !important;
    font-size: 0.88em !important;
}

/* 컴팩트 카드 (custom div용) */
.zeb-card {
    background: white;
    border: 1px solid #E0E0E0;
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    transition: all 0.2s ease;
}
.zeb-card:hover {
    border-color: #66BB6A;
    box-shadow: 0 4px 16px rgba(27, 94, 32, 0.08);
}
.zeb-card-icon {
    font-size: 2rem;
    margin-bottom: 0.5rem;
}
.zeb-card-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: #1A1A1A;
    margin-bottom: 0.25rem;
}
.zeb-card-desc {
    font-size: 0.88rem;
    color: #757575;
    line-height: 1.5;
}
.zeb-badge {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
    background: #C8E6C9;
    color: #1B5E20;
}
.zeb-badge-warn {
    background: #FFE0B2;
    color: #E65100;
}

/* 푸터 */
.zeb-footer {
    margin-top: 4rem;
    padding-top: 1.5rem;
    border-top: 1px solid #E0E0E0;
    text-align: center;
    color: #BDBDBD;
    font-size: 0.85rem;
}
</style>
"""


# ====================================================================
# 로고 (SVG)
# ====================================================================

LOGO_SVG = """
<svg width="160" height="48" viewBox="0 0 200 60" xmlns="http://www.w3.org/2000/svg">
  <!-- 건물 + 잎 아이콘 -->
  <g transform="translate(4, 8)">
    <!-- 빌딩 -->
    <rect x="0" y="14" width="14" height="30" fill="#1B5E20" rx="1"/>
    <rect x="3" y="18" width="3" height="3" fill="#76FF03"/>
    <rect x="8" y="18" width="3" height="3" fill="#76FF03"/>
    <rect x="3" y="24" width="3" height="3" fill="#76FF03"/>
    <rect x="8" y="24" width="3" height="3" fill="#76FF03"/>
    <rect x="3" y="30" width="3" height="3" fill="#76FF03"/>
    <rect x="8" y="30" width="3" height="3" fill="#76FF03"/>
    <!-- 잎 -->
    <path d="M 14 14 Q 24 6 32 14 Q 30 18 24 18 Q 18 18 14 14 Z" fill="#43A047"/>
    <path d="M 14 14 Q 22 11 28 14" stroke="#1B5E20" stroke-width="0.8" fill="none"/>
  </g>
  <!-- 텍스트 -->
  <text x="46" y="32" font-family="Pretendard, sans-serif" font-size="18" font-weight="800" fill="#1A1A1A">
    ZEB-ROI
  </text>
  <text x="46" y="46" font-family="Pretendard, sans-serif" font-size="9" font-weight="500" fill="#757575">
    그린리모델링 의사결정 플랫폼
  </text>
</svg>
"""


# ====================================================================
# 적용 함수
# ====================================================================

def apply_global_style():
    """페이지 진입 시 1회 호출 — 글로벌 CSS 주입."""
    import streamlit as st
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def render_logo(size: str = "default"):
    """
    SVG 로고 렌더.

    Args:
        size: "small" / "default" / "large"
    """
    import streamlit as st
    if size == "small":
        svg = LOGO_SVG.replace('width="160"', 'width="120"').replace('height="48"', 'height="36"')
    elif size == "large":
        svg = LOGO_SVG.replace('width="160"', 'width="240"').replace('height="48"', 'height="72"')
    else:
        svg = LOGO_SVG
    st.markdown(svg, unsafe_allow_html=True)


def grade_badge_html(grade: str, large: bool = False) -> str:
    """등급 배지 HTML (인라인 사용)."""
    color = GRADE_COLORS.get(grade, "#757575")
    font_size = "1.5rem" if large else "1rem"
    padding = "0.4rem 1rem" if large else "0.2rem 0.6rem"
    return (
        f'<span style="background:{color};color:white;padding:{padding};'
        f'border-radius:8px;font-weight:700;font-size:{font_size};'
        f'display:inline-block;">{grade}등급</span>'
    )


def card_html(icon: str, title: str, desc: str, badge: str = None) -> str:
    """카드 HTML 생성 (커스텀 div)."""
    badge_html = ""
    if badge:
        cls = "zeb-badge-warn" if "준비" in badge or "미설정" in badge else "zeb-badge"
        badge_html = f'<span class="{cls}" style="float:right;">{badge}</span>'
    return (
        f'<div class="zeb-card">'
        f'{badge_html}'
        f'<div class="zeb-card-icon">{icon}</div>'
        f'<div class="zeb-card-title">{title}</div>'
        f'<div class="zeb-card-desc">{desc}</div>'
        f'</div>'
    )


def render_footer():
    """페이지 푸터."""
    import streamlit as st
    st.markdown(
        '<div class="zeb-footer">'
        'ZEB-ROI · 그린리모델링 의사결정 플랫폼 · 2026 졸업설계<br>'
        '본 진단은 자동 산출 결과로, 실제 사업 신청 시 그린리모델링 창조센터(1588-8788) 공식 컨설팅 필수'
        '</div>',
        unsafe_allow_html=True,
    )
