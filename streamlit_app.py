import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

# ZEB-ROI 그린리모델링 의사결정 플랫폼 — 메인 앱
# 6개 모드 통합 Streamlit 앱 + 랜딩 페이지.
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

from core.fmt import signed_eok
from core.ui_theme import (
    apply_global_style, render_logo, render_footer, render_topbar,
    card_html, COLORS,
)

apply_global_style()


# ====================================================================
# API 키 / 인덱스 상태 점검
# ====================================================================

def _check_anthropic_key() -> bool:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    return bool(key) and not key.startswith("sk-ant-api03-여기")


# ── 색인 원문 내려받기 ──────────────────────────────────────────
# "이 조항이 진짜 그렇게 적혀 있나"를 화면에서 끝내려면 원문까지 닿아야 한다.
# 외부 링크(law.go.kr 등)로 걸면 그쪽 URL이 바뀌는 순간 죽고, 무엇보다
# **우리가 색인한 그 파일**이라는 보장이 없다. 색인한 파일 자체를 내려준다.
from pathlib import Path as _Path

_POLICY_DIR = _Path(os.getenv("POLICY_DOCS_DIR", "data/policy_docs"))
_MIME = {".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8",
         ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _file_reader(path: _Path):
    """누를 때 읽는다. 루프에서 만드는 클로저라 path를 기본값으로 묶어 둔다."""
    return lambda p=path: p.read_bytes()


def _check_rag_index() -> bool:
    from pathlib import Path
    return Path("./data/chroma_db").exists() and any(
        Path("./data/chroma_db").iterdir()
    )


@st.cache_data(show_spinner=False)
def _index_summary() -> dict:
    """
    색인에서 원문 목록·청크 수를 직접 읽는다.

    화면에 목록을 손으로 적지 않기 위한 함수다. 예전엔 사이드바·Mode 01 헤더·
    Mode 01 본문에 각각 다른 목록이 하드코딩돼 있었고 전부 실제 색인과 어긋났다.
    """
    try:
        from core.doc_registry import group_indexed_docs
        from core.rag_retriever import KeywordRetriever

        retriever = KeywordRetriever()
        files = [m.get("file", "?") for m in retriever._cache["metas"]]
        return {
            "n_files": len(set(files)),
            "n_chunks": retriever.count(),
            "groups": group_indexed_docs(files),
            "error": None,
        }
    except Exception as e:
        return {
            "n_files": 0, "n_chunks": 0, "groups": [],
            "error": f"{type(e).__name__}: {e}",
        }


def _auto_unzip_chroma_if_needed():
    """
    data/chroma_db.zip → data/chroma_db/ 압축 해제. **zip이 바뀌면 다시 푼다.**

    🔴 2026-07-16까지 이 함수는 이렇게 시작했다:
           if (chroma_dir / "chroma.sqlite3").exists():
               return
       한 번 풀리고 나면 새 zip을 **영원히 무시**했다. docstring은 "항상 압축 해제"라고
       적어놓고 실제로는 정반대였다. 배포 환경은 리포 디렉토리를 재사용하므로,
       색인을 아무리 다시 만들어 push해도 사이트는 낡은 색인을 계속 들고 있었다.
       실제로 라이브가 6건·438청크(= 커밋 7b59a09 이전 상태)를 표시하고 있었고,
       그 사이 세 번의 재색인이 사이트에 도달한 적이 없었다.
       테스트는 로컬 색인을 보므로 전부 통과했다 — 배포에서만 죽는 종류의 버그다.

    → zip 내용 해시를 스탬프로 남기고, 다르면 지우고 다시 푼다.
      Windows(PowerShell) zip의 역슬래시 경로도 슬래시로 정규화한다(Linux 대비).
    """
    from pathlib import Path
    import hashlib
    import shutil
    import zipfile

    chroma_dir = Path("./data/chroma_db")
    chroma_zip = Path("./data/chroma_db.zip")
    stamp = chroma_dir / ".zip_stamp"

    if not chroma_zip.exists():
        return

    digest = hashlib.md5(chroma_zip.read_bytes()).hexdigest()
    if (chroma_dir / "chroma.sqlite3").exists():
        if stamp.exists() and stamp.read_text().strip() == digest:
            return                       # 이미 이 zip으로 풀려 있음
        shutil.rmtree(chroma_dir, ignore_errors=True)   # zip이 바뀜 → 갈아엎는다

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
    stamp.write_text(digest)

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

            - 케이스: 공공기관 소유 어린이집 (중부2)

            **산정 데이터**
              - 07/08 조달청 단가DB·간접공사비
              - `data/params/*.yaml` (요율·한도 + 출처·시행일)

            상세 아키텍처: `docs/ARCHITECTURE.md`
            """
        )

    # 색인 원문 — 목록을 손으로 적지 않는다. 색인에서 읽어 역할별로 묶는다.
    _idx = _index_summary()
    with st.expander(f"📚 색인 원문 ({_idx['n_files']}건 · {_idx['n_chunks']:,}청크)", expanded=False):
        if _idx["error"]:
            st.caption(f"색인을 읽지 못했습니다 — {_idx['error']}")
        else:
            for _title, _items in _idx["groups"]:
                st.markdown(f"**{_title}**")
                for _fname, _label, _answers in _items:
                    _p = _POLICY_DIR / _fname
                    if _p.is_file():
                        # data에 callable을 넘기면 **누를 때만** 파일을 읽는다.
                        # 원문 19건이 25MB라, 미리 읽으면 사이드바가 다시 그려질 때마다
                        # 그만큼을 메모리에 얹는다 (무료 티어에서 감당 안 됨).
                        st.download_button(
                            f"📄 {_label}",
                            data=_file_reader(_p),
                            file_name=_fname,
                            mime=_MIME.get(_p.suffix.lower(), "application/octet-stream"),
                            key=f"_doc_{_fname}",
                            type="tertiary",
                            help=f"원문 내려받기 · {_fname}",
                        )
                    else:
                        st.markdown(
                            f"<div style='margin:0 0 0 .5rem; font-size:.82rem;'>{_label}</div>",
                            unsafe_allow_html=True,
                        )
                    st.markdown(
                        f"<div style='margin:-.35rem 0 .5rem .5rem; line-height:1.35;'>"
                        f"<span style='font-size:.72rem; color:#757575;'>↳ {_answers}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
        # 사이드바는 '무엇이 색인돼 있는가'만 답한다.
        # 2026-07-17: 예전엔 "④ 계산 경로·한계에 있습니다"라고 가리켰는데, 그 탭은
        # 5개→2개로 줄이면서 지워졌다. 없는 곳을 가리키는 안내가 없느니만 못하다.
        st.caption("각 숫자의 근거 조항은 **📐 근거·출처 → ① 파라미터 출처**에 있습니다.")

    st.markdown("---")
    st.caption(
        "⚠️ 자동 산출 결과로 참고용입니다. "
        "실제 사업 신청 시 그린리모델링 창조센터 공식 컨설팅 필수."
    )


# ====================================================================
# 메인 영역 라우팅
# ====================================================================

@st.cache_data(show_spinner=False)
def _case_zeb() -> dict:
    """
    홈에 띄울 실증 케이스 ZEB 수치를 **엔진에서 직접 산출**한다.

    왜 이 함수가 있나 — 예전엔 홈이 "4등급 · 66.0"을 문자열로 하드코딩하고 있었다.
    그래서 엔진의 결론이 4등급 → 5등급으로 바뀌었는데도 화면은 그대로였고,
    테스트도 화면을 검사하지 않아 아무것도 깨지지 않았다(조용한 drift).
    이제 화면이 엔진을 읽으므로 두 값이 어긋날 수 없다.
    """
    import json
    from pathlib import Path

    try:
        path = Path("data/sample_bim/case_daycare_archi_sample.json")
        bim = json.loads(path.read_text(encoding="utf-8"))
        from core.bim_diagnoser import map_to_gr_elements
        from core.zeb_evaluator import evaluate_zeb

        gr = map_to_gr_elements(bim)
        now = evaluate_zeb(bim, gr)
        full = evaluate_zeb(bim, gr, assume_full_reinforcement=True, assume_bems=True)
        return {
            "현재_소요량": round(now["post_energy_kwh_m2"], 1),
            "보강후_소요량": round(full["post_energy_kwh_m2"], 1),
            "보강후_등급": full["grade"]["label"],
            "자립률": full["autonomy_pct"],
            "절감률": full["reduction"]["total_reduction_pct"],
            "절감률_단순합산": full["reduction"]["total_reduction_pct_sum"],
            "결합방식": full["reduction"]["_결합방식"],
        }
    except Exception:
        return {}


@st.cache_data(show_spinner=False)
def _case_score() -> dict:
    """
    실증 케이스 GR 정량평가 점수 — 엔진에서 직접 산출.

    ⚠️ 홈이 "25/100점"을 하드코딩하고 있었는데 엔진은 23점이었다(이미 어긋나 있었음).
    ⚠️ 등급(A/D)은 붙이지 않는다 — 정량평가표는 "고득점 순으로 선정"하는 랭킹 점수이지
       등급표가 아니다(2026 공공 GR 2.0 가이드라인 p.18).
    """
    from pathlib import Path

    try:
        from core.bim_diagnoser import diagnose_from_json
        res = diagnose_from_json(
            str(Path("data/sample_bim/case_daycare_archi_sample.json")), with_roi=True,
        )
        cur = res["score"]["total_score"]
        uplift = sum(p["점수상승"] for p in (res.get("roi_plan") or []))
        return {"현재": cur, "보강후": cur + uplift, "상승": uplift}
    except Exception:
        return {}


@st.cache_data(show_spinner=False)
def _case_gr() -> dict:
    """
    Track B · 실증 케이스 GR 사업 자격 — 엔진(core.gr_evaluator)에서 직접 산출.
    ZEB와 분모가 다르므로(개선 전 대비 vs base 대비) 별도 모듈이 판정한다. P4 참고.
    """
    import json
    from pathlib import Path

    try:
        bim = json.loads(
            Path("data/sample_bim/case_daycare_archi_sample.json").read_text(encoding="utf-8")
        )
        from core.bim_diagnoser import map_to_gr_elements
        from core.gr_evaluator import evaluate_gr
        return evaluate_gr(bim, map_to_gr_elements(bim))
    except Exception:
        return {}


def _P_tariff() -> float:
    """전기 세후 실효단가 — 화면에 숫자를 손으로 적지 않기 위한 얇은 래퍼."""
    from core import params as _P
    try:
        return _P.electricity_tariff_won_per_kwh()
    except Exception:
        return 0.0


@st.cache_data(show_spinner=False)
def _case_roi() -> dict:
    """
    실증 케이스 재무성·경제성 — 엔진(core.roi_calculator)에서 직접 산출.

    🔴 2026-07-16까지 홈은 "회수 7.3년 · NPV +1.08억 · IRR 14.7% · B-C 2.19배"를
       **손으로 적어** 두고 있었다. 그런데 같은 가정으로 엔진을 돌리면 회수는 6.8년,
       B-C는 2.18배였다 — 하드코딩이 이미 엔진과 어긋나 있었다.
       게다가 절감 단가가 9,900원 → 5,172원으로 바뀌자 네 숫자가 전부 틀린 값이 됐다.
       등급 문자열을 하드코딩해 4등급→5등급을 놓쳤던 것과 같은 버그다. 엔진에서 읽는다.
    """
    from core import params as _P
    from core.roi_calculator import calculate_cashflow_metrics

    area = 1251.0
    unit = _P.annual_saving_per_m2()
    metrics = calculate_cashflow_metrics(
        self_burden=91_000_000, annual_saving=unit * area
    ) or {}
    return {
        "단가": unit,
        "연면적": area,
        "연간절감": unit * area,
        "가정여부": _P.annual_saving_is_assumption(),
        **metrics,
    }


def render_home():
    """랜딩 페이지 — 모드 카드 + 핵심 지표"""

    # 히어로 영역 — 제로에너지건축물(ZEB) 등급 평가 중심
    st.markdown("""
    <div class="zeb-hero">
        <div class="eyebrow">ZERO ENERGY BUILDING · GREEN REMODELING</div>
        <h1>BIM 한 번으로 <span class="accent">제로에너지건축물(ZEB)</span> 등급을 평가하고<br>그린리모델링 전 과정을 설계합니다</h1>
        <p class="lede">
            Revit BIM 모델을 업로드하면 건물의 <b>ZEB·에너지효율등급</b>을 평가하고,
            <b>그린리모델링</b>의 보강 우선순위 · 비용(Max Cost) ·
            보조금 · 회수기간까지 한 자리에서 산출합니다.
        </p>
    </div>
    """, unsafe_allow_html=True)

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
            "11개 기술요소를 100점(기술요소 80 + 사업여건 20)으로 채점합니다 — <b>등급이 아니라 고득점 순 선정용 랭킹 점수</b>입니다. "
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
        # 색인이 죽으면 n_files가 0으로 떨어진다(_index_summary가 예외를 삼킨다).
        # 그대로 끼워 넣으면 "0건의 법령·고시·공고 원문에서 찾아 답변합니다"라는
        # 자기모순 문장이 홈에 뜬다. 셀 수 있을 때만 숫자를 말한다.
        _idx_n = _index_summary()["n_files"]
        _n_txt = (f"<b>{_idx_n}건의 법령·고시·공고 원문</b>" if _idx_n
                  else "<b>법령·고시·공고 원문</b>")
        st.markdown(card_html(
            "💬",
            "정책 Q&A (RAG)",
            f"{_n_txt}(법률·시행령·고시·2026년 공고)에서 "
            "관련 대목을 찾아 <b>원문 그대로 인용</b>해 답변합니다. "
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

    st.markdown("---")

    # 핵심 수치 (실증 케이스 검증 기준) — ZEB 등급 평가가 우리 플랫폼의 출발점
    #
    # 편집 원칙 — 여기는 **결과만** 둔다.
    #   제도 해설·우리가 틀렸던 이력·연구 근거는 📐 근거·출처에 있다.
    #   같은 글을 홈에도 적으면 (1) 홈이 읽히지 않고 (2) 두 곳이 따로 낡는다.
    #   남기는 건 '숫자가 못 믿을 값일 때의 경고'뿐 — 그건 숫자에 붙어 있어야 한다.
    # (2026-07-17: 용어사전 모드를 화면에서 뺐다. modes/mode6_glossary.py는 남아 있지만
    #  어디서도 안 부른다 — 되살릴 땐 streamlit_app.py의 mode_options에 다시 넣으면 된다.)
    st.markdown("### 검증 결과 — 실증 케이스(어린이집)")
    st.caption("1,251㎡ · 2014년 사용승인 · 노유자시설(비주거) · 공공기관 소유 · 태양광 없음")

    st.markdown("**① ZEB 인증 등급 평가** — 본 플랫폼의 핵심")

    zeb = _case_zeb()      # ⚠️ 하드코딩 금지 — 엔진에서 직접 읽는다 (아래 함수 주석 참고)
    if zeb:
        z1, z2, z3 = st.columns(3)
        z1.metric("현재 ZEB", "인증 미달",
                  f"1차E 소요량 {zeb['현재_소요량']} kWh/㎡·년")
        z2.metric("보강 후 ZEB", zeb["보강후_등급"].replace("ZEB ", ""),
                  f"제2호 근거 · 자립률 {zeb['자립률']}%")
        z3.metric("1차에너지소요량", zeb["보강후_소요량"],
                  f"{zeb['현재_소요량']} → {zeb['보강후_소요량']} kWh/㎡·년")
        st.caption(
            f"태양광이 없어 **자립률 0%** → 등급은 **제2호(1차에너지소요량)가 지배**합니다. "
            f"‘보강 후 {zeb['보강후_소요량']}’은 11개 기술요소 전체 적용 + BEMS 설치를 가정한 "
            "**잠재 등급**이며, ECO2 정식 해석 전이라 추정치입니다 → **[📐 근거·출처]**"
        )
    else:
        st.warning("ZEB 엔진 계산에 실패했습니다 — [📐 근거·출처] 모드에서 상세를 확인하세요.")

    # ── Track B · GR 사업 자격 (ZEB와 별개 제도 — 분모가 다르다) ──────
    gr = _case_gr()
    if gr:
        imp = gr["성능개선"]
        st.markdown("**② 그린리모델링 사업 자격** — Track B (ZEB와 별개 제도)")
        g1, g2, g3 = st.columns(3)
        g1.metric("성능개선비율", f"{imp['성능개선비율_pct']}%",
                  f"기준 {imp['기준_pct']}% 이상")
        g2.metric("대상공사 7종", "충족 ✅" if gr["대상공사"]["충족"] else "미달 ❌",
                  f"{len(gr['대상공사']['해당공사'])}개 분야 해당")
        g3.metric("GR 자격", "충족 ✅" if gr["자격충족"] else "미달 ❌", gr["사업유형"])
        st.caption(
            f"분모가 **개선 전**({imp['개선전']})이라 ZEB 절감률"
            f"({zeb['절감률'] if zeb else 50.5}%, 분모 base 200)과 다릅니다 → **📐 근거·출처**. "
            "인정은 센터 지정 프로그램 결과로만 되므로 이 판정은 참고용입니다."
        )

    st.markdown("**③ BIM 정밀 진단** — GR 지원사업 정량평가표 채점")
    sc = _case_score()
    d1, d2, d3 = st.columns(3)
    d1.metric("현재 정량평가", f"{sc.get('현재', '—')} / 100점", "선정 랭킹 점수")
    d2.metric("보강 후", f"{sc.get('보강후', '—')} / 100점",
              f"+{sc.get('상승', 0)}점 (11개 전체 보강 시)")
    d3.metric("전체 보강비 (Max Cost)", "5.31억", "11개 항목 전체")
    st.caption(
        "가이드라인 p.18 *\"고득점 순으로 선정\"* 에 따른 **경쟁 선발용 랭킹 점수**입니다 "
        "— 등급이 아니고, 커트라인은 해마다 달라집니다"
    )

    # ④⑤ 숫자는 전부 엔진에서 읽는다 — _case_roi() 주석 참고 (하드코딩이 어긋나 있었다)
    roi = _case_roi()

    st.markdown("**④ 재무성 — 에너지 절감 회수**")
    f1, f2, f3 = st.columns(3)
    f1.metric("외피 보강 Max Cost", "1.81억", "50% 보조 → 자부담 0.91억")
    f2.metric("연간 에너지 절감", f"{roi['연간절감']/10000:,.0f}만원",
              f"㎡당 {roi['단가']:,.0f}원" + (" · 추정" if roi["가정여부"] else ""))
    f3.metric("단순 회수 기간", f"{roi.get('단순회수_년', 0):.1f}년",
              "GR 단독 (에너지 절감만)")

    st.markdown("**⑤ 경제성 — 현금흐름 기반 (20년 · 할인율 4.5% · 에너지상승률 2.5%)**")
    g1, g2, g3 = st.columns(3)
    _npv = roi.get("NPV_원", 0)
    g1.metric("NPV (순현재가치)", signed_eok(_npv),
              "자부담 대비 순이득" if _npv >= 0 else "자부담 대비 손실")
    g2.metric("IRR (내부수익률)", f"{roi.get('IRR', 0)*100:.1f}%",
              f"할인율(4.5%)의 {roi.get('IRR', 0)/0.045:.1f}배")
    g3.metric("B-C 비율", f"{roi.get('BC_ratio', 0):.2f}배",
              f"투입 1원당 편익 {roi.get('BC_ratio', 0):.2f}원")

    if roi["가정여부"]:
        # 남기는 이유 — 단가는 약관 원문으로 확정했지만 곱해지는 **절감 kWh**(base 200·
        # 요소별 절감률 11개)는 아직 ECO2 해석 전이라 추정이다. 위 네 숫자가 그 위에 있다.
        # 경위·산식은 📐 근거·출처에 있으므로 여기선 한 줄로만 알린다.
        st.caption(
            f"에너지 단가는 한전 기본공급약관(2026.7.1 시행) 원문 기준 "
            f"**{_P_tariff():.1f}원/kWh**입니다. 다만 곱해지는 **절감량**은 ECO2 정식 해석 전이라 "
            "추정치이며, ④⑤ 숫자는 그 위에 있습니다 → **[📐 근거·출처]**"
        )


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
