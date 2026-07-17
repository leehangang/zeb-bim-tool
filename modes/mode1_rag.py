"""
modes/mode1_rag.py — 정책 Q&A (RAG) UI
=======================================
ChromaDB에 인덱싱된 법령·고시·공고 원문에서 검색 + Claude 답변.
(문서 수를 여기 적지 않는다 — "7개"라고 박아뒀다가 19건이 되도록 낡아 있었다.
 화면은 core.doc_registry가 살아있는 색인에서 뽑아 쓴다.)

처리 흐름:
    사용자 질문
    → core.rag_retriever.answer_with_rag()
    → Streamlit UI:
        - 답변 본문 (markdown)
        - 출처 카드 (파일/페이지/스니펫)
        - 토큰 사용량 (옵션)

구조:
    - answer_question():    순수 함수 (테스트 가능, Streamlit 의존 X)
    - render_rag_panel():   Streamlit UI 렌더 (의존 O)

전제 조건:
    먼저 `python scripts/build_index.py` 실행해서 ChromaDB 인덱스 생성 필요.
"""

import html
import os
from typing import Optional

from core.legal_format import format_legal


# ====================================================================
# 순수 함수 (Streamlit 의존 X)
# ====================================================================

def answer_question(
    question: str,
    top_k: int = 5,
    persist_dir: str = "./data/chroma_db",
    max_tokens: int = 1024,
) -> dict:
    """
    RAG 검색 + 답변 생성.

    Args:
        question: 사용자 자연어 질문
        top_k: 검색할 청크 수 (기본 5)
        persist_dir: ChromaDB 경로
        max_tokens: Claude 응답 최대 토큰

    Returns:
        {
          "answer": str,
          "sources": [{"file": ..., "page": ..., "snippet": ..., "distance": ...}],
          "model": str,
          "usage": {"input_tokens": int, "output_tokens": int},
        }
    """
    from core.rag_retriever import KeywordRetriever, answer_with_rag
    # 키워드 검색기 사용 — 임베더(fastembed) 불필요 → 무료 클라우드 티어에서도 안정.
    retriever = KeywordRetriever(persist_dir=persist_dir)
    return answer_with_rag(
        question, top_k=top_k, retriever=retriever, max_tokens=max_tokens,
    )


def is_index_ready(persist_dir: str = "./data/chroma_db") -> tuple:
    """
    인덱스 존재 여부 확인.

    Returns:
        (ready: bool, message: str, chunk_count: int)
    """
    from pathlib import Path
    if not Path(persist_dir).exists():
        return False, (
            "ChromaDB 인덱스가 없습니다. "
            "프로젝트 루트에서 `python scripts/build_index.py` 를 실행해 인덱스를 만드세요."
        ), 0
    # 키워드 검색기는 임베더(fastembed) 없이 동작 → 무료 클라우드 티어에서도 준비 완료.
    try:
        from core.rag_retriever import KeywordRetriever
        retriever = KeywordRetriever(persist_dir=persist_dir)
        count = retriever.count()
        if count == 0:
            return False, "인덱스는 있지만 청크가 0개입니다. 재인덱싱이 필요합니다.", 0
        return True, f"인덱스 정상 ({count}개 청크 사용 가능)", count
    except Exception as e:
        return False, f"인덱스 로드 실패: {type(e).__name__}: {e}", 0


def _indexed_file_count(persist_dir: str = "./data/chroma_db") -> int:
    """색인에 실제로 들어 있는 원문 파일 수. 화면에 숫자를 손으로 적지 않기 위함."""
    try:
        from core.rag_retriever import KeywordRetriever
        retriever = KeywordRetriever(persist_dir=persist_dir)
        return len({m.get("file", "?") for m in retriever._cache["metas"]})
    except Exception:
        return 0


# ====================================================================
# Streamlit UI
# ====================================================================

def render_rag_panel() -> None:
    """
    Streamlit 메인 패널 (Mode 1 정책 Q&A).
    streamlit_app.py에서 모드 1 선택 시 호출.
    """
    import streamlit as st

    # 인덱스 상태 확인
    ready, msg, count = is_index_ready()

    # 문서 수는 색인에서 읽는다. 예전엔 화면 다섯 군데에 손으로 적혀 있었고,
    # 색인이 15건이 된 뒤에도 화면은 계속 12건이라고 말하고 있었다.
    n_files = _indexed_file_count()

    # 색인이 깨졌으면 문서 수를 말하지 않는다. 예전엔 이 문장이 무조건 나가서
    # 인덱스가 죽은 채로 "**0건의** 법령·고시·공고 원문을 색인하고"라고 떴다.
    _n_txt = (f"<b>{n_files}건의 법령·고시·공고 원문</b>을 색인하고, "
              if ready and n_files else "법령·고시·공고 <b>원문</b>을 색인하고, ")
    st.markdown(f"""
    <div style="margin-bottom:1.5rem;">
        <div style="font-size:0.85rem; color:#2E7D32; font-weight:600; letter-spacing:0.08em;">
            MODE 01 · POLICY Q&A
        </div>
        <h1 style="margin:0.2rem 0;">💬 정책 Q&A</h1>
        <div style="color:#757575;">
            ZEB 인증 · GR 지원사업 · 세제 · 케이스 적격 판정의 근거가 되는
            {_n_txt}
            질문과 관련된 대목을 찾아 <b>원문 그대로 인용</b>해 답변합니다.
            전체 목록은 사이드바 <b>📚 색인 원문</b>에 있습니다.
        </div>
    </div>
    """, unsafe_allow_html=True)
    if not ready:
        # is_index_ready()가 원인을 이미 알아냈다(디렉터리 없음 / 청크 0개 /
        # 로드 예외). 예전엔 그 msg를 버리고 "라이브 데모는 BIM에 집중되어
        # 있습니다"라는 **고정 문구**를 띄웠다. 그건 제품 결정을 서술하는데,
        # 코드엔 그런 결정이 없다 — 홈은 이 모드를 라이브 카드로 광고한다.
        # 고장을 기획으로 포장하면 고칠 사람이 고장인 줄 모른다.
        st.warning(f"**정책 Q&A를 지금 쓸 수 없습니다** — {msg}", icon="⚠️")
        st.caption(
            "색인을 만들려면 `python scripts/build_index.py`를 실행하세요. "
            "의존성·API키·네트워크가 필요 없습니다(기본 `--provider hash`)."
        )
        st.markdown(
            "**정상 동작 시** — ZEB 인증 판정 · GR 지원사업 판정 · 세제 · 케이스 적격 판정의 "
            "근거가 되는 법령·고시·공고 원문을 색인하고, 질문과 관련된 대목을 찾아 "
            "**원문을 그대로 인용**해 답변합니다."
        )
        st.markdown("**이런 질문에 답합니다**")
        _ex = [
            "ZEB(제로에너지건축물) 인증은 누가 신청할 수 있나요?",
            "녹색건축물의 용적률·높이 완화 기준은 얼마인가요?",
            "신재생에너지 자립률 점수는 어떻게 산정하나요?",
            "고성능 창호로 인정받는 기준은 무엇인가요?",
            "단열재 등급은 어떻게 분류되나요?",
            "취득세 감면을 추징당하는 경우는 언제인가요?",
        ]
        _c = st.columns(2)
        for _i, _q in enumerate(_ex):
            _c[_i % 2].markdown(f"- {_q}")
        return

    st.success(f"✅ {msg}")
    st.divider()

    # 옵션
    col1, col2 = st.columns([3, 1])
    with col1:
        # key= 로 위젯에 직접 담는다. 예전엔 예시 클릭을 별도 세션키(_seed)에 뒀다가
        # 렌더 때 pop 했는데, 그러면 **입력창은 빈 채로** 답만 뜨고, 그 다음 rerun
        # (슬라이더를 만지기만 해도) seed가 이미 없으니 질문이 통째로 사라졌다.
        # mode2가 같은 버그를 고치고 주석까지 남겼는데 여기만 안 따라왔다.
        question = st.text_input(
            "질문",
            key="_mode1_question",
            placeholder="예: 녹색건축물의 용적률·높이 완화 기준은 얼마인가요?",
        )
    with col2:
        top_k = st.slider("검색 청크 수", 3, 10, 5)

    # 예시 질문 (선택 시 자동 입력)
    with st.expander("💡 예시 질문"):
        examples = [
            "ZEB(제로에너지건축물) 인증은 누가 신청할 수 있나요?",
            "녹색건축물의 용적률·높이 완화 기준은 얼마인가요?",
            "신재생에너지 자립률 점수는 어떻게 산정하나요?",
            "고성능 창호로 인정받는 기준은 무엇인가요?",
            "단열재 등급은 어떻게 분류되나요?",
            "취득세 감면을 추징당하는 경우는 언제인가요?",
        ]
        cols = st.columns(2)
        for i, ex in enumerate(examples):
            with cols[i % 2]:
                if st.button(ex, key=f"ex_{i}", width="stretch"):
                    st.session_state["_mode1_question"] = ex
                    st.rerun()

    if not question:
        return

    # 답변 생성
    try:
        with st.spinner(f"{n_files}건의 법령·고시·공고 원문에서 근거 조항 검색 + 답변 생성 중..."):
            result = answer_question(question, top_k=top_k)
    except Exception as e:
        from core.error_messages import friendly_error
        st.error(friendly_error(e))
        return

    # 답변 표시 — 테두리로 묶는다. 글만 흘러가면 어디까지가 답인지 안 보인다.
    st.subheader("답변")
    with st.container(border=True):
        st.markdown(result["answer"])

    # 출처
    if result["sources"]:
        st.divider()
        st.subheader(f"📚 출처 ({len(result['sources'])}개)")
        for i, src in enumerate(result["sources"], 1):
            with st.expander(
                f"{i}. {src['file']} (p.{src['page']}) — "
                f"유사도 {1-src['distance']:.2f}"
            ):
                # 조·항·호마다 줄을 나눈다. 날짜(<신설 2014. 5. 28.>)를 봉인한 뒤에만
                # 호 번호를 끊는다 — 안 그러면 날짜가 세 줄로 찢어진다.
                # 공백 외엔 한 글자도 안 건드린다 (core/legal_format.py 계약).
                _snip = format_legal(src["snippet"])
                st.markdown(
                    f'<div style="white-space:pre-wrap; font-size:0.9rem; '
                    f'line-height:1.7; padding:0.2rem 0;">{html.escape(_snip)}</div>',
                    unsafe_allow_html=True,
                )
