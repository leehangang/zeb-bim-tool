"""
modes/mode1_rag.py — 정책 Q&A (RAG) UI
=======================================
ChromaDB에 인덱싱된 7개 PDF에서 검색 + Claude 답변.

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

import os
from typing import Optional


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
    from core.rag_retriever import RagRetriever, answer_with_rag
    retriever = RagRetriever(persist_dir=persist_dir)
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
    try:
        from core.rag_retriever import RagRetriever
        retriever = RagRetriever(persist_dir=persist_dir)
        count = retriever.count()
        if count == 0:
            return False, "인덱스는 있지만 청크가 0개입니다. 재인덱싱이 필요합니다.", 0
        return True, f"인덱스 정상 ({count}개 청크 사용 가능)", count
    except Exception as e:
        return False, f"인덱스 로드 실패: {type(e).__name__}: {e}", 0


# ====================================================================
# Streamlit UI
# ====================================================================

def render_rag_panel() -> None:
    """
    Streamlit 메인 패널 (Mode 1 정책 Q&A).
    streamlit_app.py에서 모드 1 선택 시 호출.
    """
    import streamlit as st

    st.markdown("""
    <div style="margin-bottom:1.5rem;">
        <div style="font-size:0.85rem; color:#2E7D32; font-weight:600; letter-spacing:0.08em;">
            MODE 01 · POLICY Q&A
        </div>
        <h1 style="margin:0.2rem 0;">💬 정책 Q&A</h1>
        <div style="color:#757575;">
            01 GR 가이드라인 · 03 ZEB 인증기준 · 04 녹색건축법 · 05 지방세특례 ·
            06 에너지절약설계기준 · 09 영유아보육법 시행규칙 — 7개 정책 문서에서
            근거 조항을 인용해 답변합니다.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 인덱스 상태 확인
    ready, msg, count = is_index_ready()
    if not ready:
        st.info(
            "**정책 Q&A는 로컬 환경에서 작동합니다.** "
            "클라우드(Streamlit Community) 배포는 핵심 엔진인 BIM 진단·ROI를 "
            "가볍고 안정적으로 운영하기 위해 경량 구성으로 두었고, "
            "RAG 검색 모듈은 로컬에서 실행합니다."
        )
        st.markdown(
            "**동작 방식** — 7개 법·고시·가이드라인(01 GR 가이드라인, 03 ZEB 인증기준, "
            "04 녹색건축법, 05 지방세특례, 06 에너지절약설계기준, 09 영유아보육법)을 "
            "ChromaDB로 벡터 인덱싱(16,048개 청크)하고, 질문과 의미가 가까운 조항을 "
            "검색해 **근거 조항을 인용**하며 답변합니다."
        )
        st.markdown("**이런 질문에 답합니다**")
        _ex = [
            "ZEB 등급별 취득세 감면율은?",
            "그린리모델링 사업 신청 자격은?",
            "녹색건축법상 용적률 완화는 어떻게 적용되는가?",
            "어린이집의 일조·채광 기준은?",
            "보조금 지원 한도는 얼마인가?",
            "에너지절약설계기준에서 외벽 열관류율 기준은?",
        ]
        _c = st.columns(2)
        for _i, _q in enumerate(_ex):
            _c[_i % 2].markdown(f"- {_q}")
        st.caption(
            "로컬 실행: `python scripts/build_index.py --provider local` → "
            "`streamlit run streamlit_app.py`"
        )
        return

    st.success(f"✅ {msg}")
    st.divider()

    # 옵션
    col1, col2 = st.columns([3, 1])
    with col1:
        question = st.text_input(
            "질문",
            placeholder="예: ZEB 1등급 인증 시 취득세 감면율은 얼마인가요?",
        )
    with col2:
        top_k = st.slider("검색 청크 수", 3, 10, 5)

    # 예시 질문 (선택 시 자동 입력)
    with st.expander("💡 예시 질문"):
        examples = [
            "ZEB 등급별 취득세 감면율은?",
            "그린리모델링 사업 신청 자격은?",
            "녹색건축법상 용적률 완화는 어떻게 적용되는가?",
            "어린이집의 일조·채광 기준은?",
            "보조금 지원 한도는 얼마인가?",
            "에너지절약설계기준에서 외벽 열관류율 기준은?",
        ]
        cols = st.columns(2)
        for i, ex in enumerate(examples):
            with cols[i % 2]:
                if st.button(ex, key=f"ex_{i}", use_container_width=True):
                    st.session_state["_mode1_question_seed"] = ex
                    st.rerun()

    if "_mode1_question_seed" in st.session_state:
        question = st.session_state.pop("_mode1_question_seed")
        st.info(f"📝 선택된 질문: {question}")

    if not question:
        return

    # 답변 생성
    try:
        with st.spinner(f"7개 정책 자료에서 검색 중... (top-{top_k})"):
            result = answer_question(question, top_k=top_k)
    except Exception as e:
        from core.error_messages import friendly_error
        st.error(friendly_error(e))
        return

    # 답변 표시
    st.subheader("답변")
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
                st.text(src["snippet"])

    # 토큰 사용량 (디버그)
    usage = result.get("usage", {})
    if usage and usage.get("input_tokens", 0) > 0:
        with st.expander("🔍 API 호출 정보"):
            st.json({
                "model": result.get("model"),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            })
