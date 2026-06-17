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

/* ── 디자인 토큰 ───────────────────────────────────── */
:root {
    --brand-900:#0F3D1E; --brand-700:#1B5E20; --brand-600:#226A28;
    --brand-500:#2E7D32; --brand-100:#E7F2E9; --brand-050:#F4F9F5;
    --ink-900:#0F1A14; --ink-700:#33403A; --ink-500:#65726B; --ink-300:#A6AFA9;
    --surface:#FFFFFF; --surface-2:#F7F9F7; --border:#E6EAE7;
    --radius-lg:16px; --radius:12px; --radius-sm:8px;
    --shadow-sm:0 1px 2px rgba(16,24,20,.05);
    --shadow-md:0 6px 22px rgba(16,24,20,.07);
}

.stApp {
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Roboto, sans-serif;
    background: var(--surface-2);
}

/* ── Streamlit 기본 chrome 숨김 (전문 플랫폼 프레임) ── */
/* 주의: stToolbar 전체를 숨기면 그 안의 사이드바 '펼침' 버튼까지 죽어
   접힌 사이드바를 다시 못 연다. 메뉴·배포 버튼만 개별 숨김. */
#MainMenu,
[data-testid="stMainMenu"],
[data-testid="stAppDeployButton"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[class*="viewerBadge"],
a[href*="streamlit.io"][target="_blank"],
footer { display: none !important; }
[data-testid="stHeader"] { background: transparent !important; }
/* 툴바·사이드바 토글·펼침 컨트롤은 항상 보이게 (네비게이션 필수) */
[data-testid="stToolbar"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stExpandSidebarButton"] { visibility: visible !important; }

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

/* 메인 영역 */
.main .block-container {
    padding-top: 1.2rem;
    padding-bottom: 4rem;
    max-width: 1280px;
}

/* 헤더 타이포 */
h1, h2, h3, h4 {
    font-weight: 700 !important;
    color: var(--ink-900);
    letter-spacing: -0.022em;
}
h1 { font-size: 1.95rem !important; line-height: 1.25; }
h2 { font-size: 1.45rem !important; }
h3 { font-size: 1.18rem !important; }
h4 { font-size: 1.02rem !important; color: var(--ink-700); }
p, li, .stMarkdown { color: var(--ink-700); }

/* 섹션 헤더 좌측 악센트 바 (전문 플랫폼 시그니처) */
.main h3 { position: relative; padding-left: 0.85rem; margin-top: 1.2rem; }
.main h3::before {
    content: ""; position: absolute; left: 0; top: 0.18em; bottom: 0.18em;
    width: 4px; border-radius: 3px;
    background: linear-gradient(180deg, var(--brand-600), var(--brand-500));
}

/* primary 버튼 */
.stButton > button[kind="primary"] {
    background: var(--brand-700) !important;
    border: none !important; border-radius: var(--radius-sm) !important;
    font-weight: 700 !important; letter-spacing: -0.01em;
    box-shadow: var(--shadow-sm) !important;
    transition: background .18s ease, transform .18s ease, box-shadow .18s ease !important;
}
/* 라벨 흰색 강제 (전역 p 색상이 버튼 글씨를 어둡게 칠하는 문제 방지) */
.stButton > button[kind="primary"],
.stButton > button[kind="primary"] *,
.stButton > button[kind="primary"] p {
    color: #ffffff !important;
}
.stButton > button[kind="primary"]:hover {
    background: var(--brand-900) !important;
    box-shadow: var(--shadow-md) !important; transform: translateY(-1px);
}
.stButton > button[kind="secondary"] {
    border: 1.5px solid var(--border) !important; border-radius: var(--radius-sm) !important;
    color: var(--brand-700) !important; font-weight: 600 !important; background: var(--surface) !important;
}
.stButton > button[kind="secondary"]:hover { border-color: var(--brand-500) !important; }

/* Metric — 클린 카드 */
[data-testid="stMetric"] {
    background: var(--surface);
    padding: 1rem 1.2rem; border-radius: var(--radius);
    border: 1px solid var(--border); box-shadow: var(--shadow-sm);
    transition: box-shadow .2s ease, border-color .2s ease;
}
[data-testid="stMetric"]:hover { box-shadow: var(--shadow-md); border-color: #D2DBD5; }
[data-testid="stMetricLabel"] { font-size: 0.8rem !important; color: var(--ink-500) !important; font-weight: 600 !important; letter-spacing: 0.01em; }
[data-testid="stMetricValue"] { font-size: 1.7rem !important; color: var(--ink-900) !important; font-weight: 800 !important; letter-spacing: -0.02em; }
[data-testid="stMetricDelta"] { font-size: 0.78rem !important; }

/* Tabs — 필 네비 */
.stTabs [data-baseweb="tab-list"] { gap: 0.35rem; border-bottom: 1px solid var(--border); }
.stTabs [data-baseweb="tab"] {
    padding: 0.55rem 1.05rem !important; font-weight: 600 !important;
    color: var(--ink-500) !important; border-radius: var(--radius-sm) var(--radius-sm) 0 0 !important;
}
.stTabs [data-baseweb="tab"]:hover { color: var(--brand-700) !important; background: var(--brand-050) !important; }
.stTabs [aria-selected="true"] {
    background: var(--brand-050) !important; color: var(--brand-700) !important;
    font-weight: 700 !important; border-bottom: 2.5px solid var(--brand-600) !important;
}

/* Expander */
.streamlit-expanderHeader, details > summary {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-sm); font-weight: 600 !important;
}

/* Alert */
.stAlert { border-radius: var(--radius) !important; border: 1px solid var(--border) !important; }

/* 사이드바 — 네비 메뉴 */
section[data-testid="stSidebar"] {
    background: var(--surface); border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] .stRadio > div { gap: 0.25rem; }
section[data-testid="stSidebar"] .stRadio label {
    padding: 0.62rem 0.85rem; border-radius: var(--radius-sm);
    transition: background .15s ease, color .15s ease;
    font-size: 0.94rem !important; font-weight: 600 !important; color: var(--ink-700) !important;
}
section[data-testid="stSidebar"] .stRadio label:hover { background: var(--brand-050); }
/* 선택된 메뉴 강조 */
section[data-testid="stSidebar"] .stRadio label:has(input:checked) {
    background: var(--brand-050); color: var(--brand-700) !important;
    box-shadow: inset 3px 0 0 var(--brand-600);
}

/* 데이터프레임 */
[data-testid="stDataFrame"] { border-radius: var(--radius-sm); overflow: hidden; border: 1px solid var(--border); }

/* 진행바 */
.stProgress > div > div > div > div { background: linear-gradient(90deg, var(--brand-600), var(--brand-500)); }

/* 다운로드 버튼 */
.stDownloadButton > button {
    background: var(--surface) !important; color: var(--brand-700) !important;
    border: 1.5px solid var(--border) !important; border-radius: var(--radius-sm) !important; font-weight: 600 !important;
}
.stDownloadButton > button:hover { border-color: var(--brand-500) !important; }

/* 코드 */
code { background: var(--brand-050) !important; color: var(--brand-700) !important; padding: 0.12rem 0.4rem !important; border-radius: 5px !important; font-size: 0.86em !important; }

/* ── 커스텀 상단바 ───────────────────────────────── */
.zeb-topbar {
    display:flex; align-items:center; justify-content:space-between;
    padding: 0.7rem 0 1.1rem 0; margin-bottom: 0.6rem;
    border-bottom: 1px solid var(--border);
}
.zeb-topbar .brand { display:flex; align-items:center; gap:0.6rem; }
.zeb-topbar .brand-mark {
    width:34px; height:34px; border-radius:9px;
    background: linear-gradient(140deg, var(--brand-700), var(--brand-500));
    display:flex; align-items:center; justify-content:center; color:#fff; font-weight:800; font-size:0.78rem; letter-spacing:-0.02em;
    box-shadow: var(--shadow-sm);
}
.zeb-topbar .brand-text { line-height:1.1; }
.zeb-topbar .brand-name { font-weight:800; color:var(--ink-900); font-size:1.02rem; letter-spacing:-0.02em; }
.zeb-topbar .brand-sub { font-size:0.72rem; color:var(--ink-500); font-weight:600; letter-spacing:0.04em; }
.zeb-topbar .ctx { display:flex; gap:0.4rem; flex-wrap:wrap; justify-content:flex-end; }
.zeb-topbar .pill {
    font-size:0.72rem; font-weight:600; color:var(--ink-700);
    background:var(--surface-2); border:1px solid var(--border);
    padding:0.28rem 0.66rem; border-radius:999px;
}
.zeb-topbar .pill b { color: var(--brand-700); }

/* ── 카드 ───────────────────────────────────────── */
.zeb-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-lg); padding: 1.4rem 1.5rem; margin-bottom: 1rem;
    box-shadow: var(--shadow-sm); transition: box-shadow .2s ease, border-color .2s ease, transform .2s ease;
}
.zeb-card:hover { border-color: #CFE0D4; box-shadow: var(--shadow-md); transform: translateY(-2px); }
.zeb-card-icon { font-size: 1.7rem; margin-bottom: 0.5rem; }
.zeb-card-title { font-size: 1.08rem; font-weight: 700; color: var(--ink-900); margin-bottom: 0.3rem; letter-spacing:-0.01em; }
.zeb-card-desc { font-size: 0.87rem; color: var(--ink-500); line-height: 1.6; }
.zeb-badge { display:inline-block; padding:0.2rem 0.6rem; border-radius:999px; font-size:0.72rem; font-weight:700; background:var(--brand-100); color:var(--brand-700); }
.zeb-badge-warn { background:#FFF3E0; color:#E65100; }

/* ── 히어로 ─────────────────────────────────────── */
.zeb-hero { padding: 1.8rem 0 1.4rem 0; }
.zeb-hero .eyebrow { font-size:0.8rem; color:var(--brand-600); font-weight:700; letter-spacing:0.14em; }
.zeb-hero h1 { font-size:2.5rem !important; margin:0.6rem 0 0.5rem 0; line-height:1.18; }
.zeb-hero .lede { font-size:1.06rem; color:var(--ink-500); max-width:680px; line-height:1.6; }
.zeb-hero .accent { color: var(--brand-700); }

/* 푸터 */
.zeb-footer { margin-top: 3.5rem; padding-top: 1.4rem; border-top: 1px solid var(--border); text-align: center; color: var(--ink-300); font-size: 0.82rem; }

/* ── 반응형 (좁은 화면·모바일) ───────────────────── */
@media (max-width: 700px) {
    .main .block-container { padding-left: 0.9rem; padding-right: 0.9rem; }
    .zeb-topbar { flex-direction: column; align-items: flex-start; gap: 0.55rem; }
    .zeb-topbar .ctx { justify-content: flex-start; }
    .zeb-hero { padding: 1.2rem 0 1rem 0; }
    .zeb-hero h1 { font-size: 1.7rem !important; }
    .zeb-hero .lede { font-size: 0.98rem; }
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
    .stTabs [data-baseweb="tab"] { padding: 0.5rem 0.7rem !important; font-size: 0.86rem !important; }
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
    SZG 로고 렌더 (PNG 파일). PNG 없으면 SVG로 fallback.

    Args:
        size: "small" / "default" / "large"
    """
    import streamlit as st
    import os

    # 사이즈 매핑
    width_map = {"small": 120, "default": 180, "large": 280}
    width = width_map.get(size, 180)

    # PNG 파일 경로
    logo_path = os.path.join("assets", "szg_logo.png")

    if os.path.exists(logo_path):
        # PNG 로고 표시 (Streamlit 최신 버전 호환)
        try:
            st.image(logo_path, width=width)
        except TypeError:
            # 구버전 streamlit 호환
            st.image(logo_path, use_column_width=False)
    else:
        # PNG 없으면 SVG fallback
        if size == "small":
            svg = LOGO_SVG.replace('width="160"', 'width="120"').replace('height="48"', 'height="36"')
        elif size == "large":
            svg = LOGO_SVG.replace('width="160"', 'width="240"').replace('height="48"', 'height="72"')
        else:
            svg = LOGO_SVG
        st.markdown(svg, unsafe_allow_html=True)


def render_topbar(context_pills=None):
    """상단 브랜드 바 — 전문 플랫폼 프레임. 메인 영역 최상단 1회 호출.

    Args:
        context_pills: 우측에 표시할 컨텍스트 칩 HTML 문자열 리스트.
    """
    import streamlit as st
    # 컨텍스트 칩은 기본 미표시 — 브랜드(ZEB-ROI)만 노출.
    if context_pills is None:
        context_pills = []
    pills = "".join(f'<span class="pill">{p}</span>' for p in context_pills)
    st.markdown(
        f'''
<div class="zeb-topbar">
  <div class="brand">
    <div class="brand-mark">ZEB</div>
    <div class="brand-text">
      <div class="brand-name">ZEB-ROI</div>
      <div class="brand-sub">GREEN REMODELING DECISION PLATFORM</div>
    </div>
  </div>
  <div class="ctx">{pills}</div>
</div>
        ''',
        unsafe_allow_html=True,
    )


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
        'ZEB-ROI · 그린리모델링 의사결정 플랫폼<br>'
        '본 진단은 자동 산출 결과로, 실제 사업 신청 시 그린리모델링 창조센터(1588-8788) 공식 컨설팅 필수'
        '</div>',
        unsafe_allow_html=True,
    )
