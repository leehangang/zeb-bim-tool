"""
core/rag_retriever.py — RAG 검색 + Claude 답변 생성
====================================================
build_index.py로 만든 ChromaDB 인덱스를 사용해 사용자 질문에 답변.

처리 흐름:
    사용자 질문
    → 쿼리 임베딩 (rag_indexer.get_embedder)
    → ChromaDB top-k 청크 검색
    → 시스템 프롬프트 + 컨텍스트 + 질문으로 Claude API 호출
    → 출처 메타데이터 포함 응답 반환

설계 결정:
    - 답변 생성을 Claude SDK 직접 호출이 아니라 추상화 (mock 가능)
    - top-k는 기본 5 (졸업설계 단계엔 충분)
    - 컨텍스트 너무 길어지지 않게 청크당 최대 800자로 자름
    - 출처를 인용 형식으로 표기: [01_GR_가이드라인.pdf p.5]
"""

import os
from pathlib import Path
from typing import Optional, Callable


# 시스템 프롬프트 (정책 Q&A 모드 전용)
SYSTEM_PROMPT_KO = """당신은 한국의 그린리모델링 정책·법령 전문 컨설턴트입니다.
다음 자료들에서 추출한 컨텍스트만을 근거로 사용자의 질문에 답변하세요.

규칙:
1. 제공된 컨텍스트에 없는 정보는 추측하지 말고 "자료에 명시되지 않았습니다"라고 답하세요.
2. 답변할 때 반드시 출처를 본문 끝에 [파일명 p.페이지] 형식으로 표기하세요.
3. 법령·고시 조문은 정확히 인용하고, 의역하지 마세요.
4. 사용자가 명확한 결론을 얻을 수 있도록 핵심 사실 + 근거 조항 순으로 구성하세요.
5. 답변 길이는 질문에 비례합니다. 단답 질문엔 짧게, 종합 질문엔 구조화해서 답하세요.
"""


# ====================================================================
# Phase A — 검색
# ====================================================================

class RagRetriever:
    """ChromaDB 검색 래퍼."""

    def __init__(
        self,
        persist_dir: str = "./data/chroma_db",
        collection_name: str = "policy_docs",
        embedder=None,
    ):
        try:
            import chromadb
        except ImportError:
            raise RuntimeError("chromadb 미설치. pip install chromadb")

        if not Path(persist_dir).exists():
            raise RuntimeError(
                f"ChromaDB 디렉토리 없음: {persist_dir}\n"
                f"먼저 'python scripts/build_index.py' 실행 필요."
            )

        self.client = chromadb.PersistentClient(path=persist_dir)
        try:
            self.collection = self.client.get_collection(collection_name)
        except Exception as e:
            raise RuntimeError(
                f"컬렉션 '{collection_name}' 로드 실패. "
                f"build_index.py가 먼저 실행됐는지 확인하세요. ({e})"
            )

        if embedder is None:
            from core.rag_indexer import get_embedder
            embedder = get_embedder()
        self.embedder = embedder

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        max_snippet_chars: int = 800,
    ) -> list:
        """
        질의 → top-k 청크 list.

        Returns:
            [
              {
                "text": "...",
                "file": "01_GR_가이드라인.pdf",
                "page": 5,
                "chunk_idx": 0,
                "distance": 0.12,
              },
              ...
            ]
        """
        query_vec = self.embedder.embed([query])[0]
        results = self.collection.query(
            query_embeddings=[query_vec],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        out = []
        if not results["documents"] or not results["documents"][0]:
            return out

        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            snippet = doc[:max_snippet_chars]
            if len(doc) > max_snippet_chars:
                snippet += "..."
            out.append({
                "text": snippet,
                "file": meta.get("file", "unknown"),
                "page": meta.get("page", 0),
                "chunk_idx": meta.get("chunk_idx", 0),
                "distance": dist,
            })
        return out

    def count(self) -> int:
        """현재 인덱스에 저장된 청크 수."""
        return self.collection.count()


# ====================================================================
# Phase B — Claude 답변 생성
# ====================================================================

def format_contexts_for_prompt(contexts: list) -> str:
    """검색된 청크들을 Claude 시스템 프롬프트에 넣을 형태로 포맷."""
    if not contexts:
        return "(검색된 컨텍스트 없음)"

    lines = []
    for i, c in enumerate(contexts, 1):
        lines.append(
            f"[자료 {i}] {c['file']} (p.{c['page']})\n{c['text']}\n"
        )
    return "\n".join(lines)


def _build_user_message(question: str, contexts: list) -> str:
    """검색 컨텍스트 + 사용자 질문을 단일 user 메시지로 결합."""
    ctx_block = format_contexts_for_prompt(contexts)
    return (
        "다음은 정책 자료에서 검색된 관련 컨텍스트입니다:\n\n"
        "===== 검색 컨텍스트 =====\n"
        f"{ctx_block}\n"
        "===== 컨텍스트 끝 =====\n\n"
        f"**질문**: {question}\n\n"
        "위 컨텍스트에 근거해 답변하고, 마지막에 출처를 "
        "[파일명 p.페이지] 형식으로 표기하세요."
    )


# ====================================================================
# Claude 호출 추상화
# ====================================================================
"""
세 가지 호출 방식 지원:
    1. real     — anthropic SDK 실호출 (ANTHROPIC_API_KEY 필요)
    2. mock     — 컨텍스트를 그대로 요약해 반환 (테스트 전용)
    3. callable — 사용자 정의 함수 주입 (의존성 주입)

답변 시 청구 토큰 정보도 같이 반환 (사용자 비용 추적용).
"""


def _real_claude_caller(
    system_prompt: str,
    user_message: str,
    model: Optional[str] = None,
    max_tokens: int = 1024,
) -> dict:
    """anthropic SDK로 실제 Claude 호출."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic 미설치. pip install anthropic")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key.startswith("sk-ant-api03-여기"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY 미설정 — .env 확인 필요. "
            "또는 RAG_CLAUDE_PROVIDER=mock 으로 테스트."
        )

    client = anthropic.Anthropic(api_key=api_key)
    model = model or os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    # 텍스트 추출 (content는 블록 리스트)
    text_parts = []
    for block in resp.content:
        if hasattr(block, "text"):
            text_parts.append(block.text)
    text = "\n".join(text_parts)

    return {
        "text": text,
        "model": model,
        "usage": {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
        },
    }


def _mock_claude_caller(
    system_prompt: str,
    user_message: str,
    **kwargs,
) -> dict:
    """
    Mock 응답: 검색된 컨텍스트의 첫 청크를 그대로 반환.
    실제 API 호출 없이 RAG 파이프라인 검증용.
    """
    # user_message에서 "===== 검색 컨텍스트 ====="와 "===== 컨텍스트 끝 ====="
    # 사이를 추출
    if "===== 검색 컨텍스트 =====" not in user_message:
        return {"text": "[Mock] 컨텍스트 없음", "model": "mock", "usage": {}}

    ctx_block = user_message.split("===== 검색 컨텍스트 =====")[1]
    ctx_block = ctx_block.split("===== 컨텍스트 끝 =====")[0].strip()

    # 첫 자료의 파일/페이지 추출
    import re
    m = re.search(r"\[자료 \d+\] (\S+) \(p\.(\d+)\)", ctx_block)
    if m:
        src = f"[{m.group(1)} p.{m.group(2)}]"
    else:
        src = "[출처 미확인]"

    # 질문 추출
    q_match = re.search(r"\*\*질문\*\*:\s*(.+?)\n", user_message)
    question = q_match.group(1) if q_match else "(미상)"

    return {
        "text": (
            f"[Mock 응답 — 실제 Claude 호출 X]\n\n"
            f"질문: {question}\n\n"
            f"위 컨텍스트에서 관련 자료를 발견했습니다. "
            f"자세한 답변은 실제 Claude API 키 설정 후 확인 가능합니다.\n\n"
            f"출처: {src}"
        ),
        "model": "mock",
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


def get_claude_caller(provider: Optional[str] = None) -> Callable:
    """
    Claude 호출 백엔드 선택.

    값: 'real' (기본), 'mock'
    환경변수 RAG_CLAUDE_PROVIDER 로도 설정 가능.
    """
    if provider is None:
        provider = os.getenv("RAG_CLAUDE_PROVIDER", "real")
    provider = provider.lower()
    if provider == "real":
        return _real_claude_caller
    elif provider == "mock":
        return _mock_claude_caller
    raise ValueError(f"RAG_CLAUDE_PROVIDER='{provider}' 지원 안 됨. real/mock.")


# ====================================================================
# 통합 진입점
# ====================================================================

def answer_with_rag(
    question: str,
    top_k: int = 5,
    retriever: Optional[RagRetriever] = None,
    claude_caller: Optional[Callable] = None,
    system_prompt: Optional[str] = None,
    max_tokens: int = 1024,
) -> dict:
    """
    RAG 통합: 검색 + Claude 답변 생성.

    Args:
        question: 사용자 자연어 질문
        top_k: 검색할 청크 수
        retriever: RagRetriever 인스턴스 (None이면 자동 생성)
        claude_caller: Claude 호출 함수 (None이면 환경변수 기반)
        system_prompt: 커스텀 시스템 프롬프트
        max_tokens: Claude 응답 최대 토큰

    Returns:
        {
          "answer": "그린리모델링 사업 자격은 ...",
          "sources": [
            {"file": "01_GR_가이드라인.pdf", "page": 5, "snippet": "...",
             "distance": 0.12},
            ...
          ],
          "model": "claude-haiku-4-5-20251001",
          "usage": {"input_tokens": ..., "output_tokens": ...},
        }
    """
    if retriever is None:
        retriever = RagRetriever()
    if claude_caller is None:
        claude_caller = get_claude_caller()
    if system_prompt is None:
        system_prompt = SYSTEM_PROMPT_KO

    # 1) 검색
    contexts = retriever.retrieve(question, top_k=top_k)

    # 2) 사용자 메시지 구성
    user_msg = _build_user_message(question, contexts)

    # 3) Claude 호출
    claude_resp = claude_caller(
        system_prompt=system_prompt,
        user_message=user_msg,
        max_tokens=max_tokens,
    )

    return {
        "answer": claude_resp["text"],
        "sources": [
            {
                "file": c["file"],
                "page": c["page"],
                "snippet": c["text"][:200] + ("..." if len(c["text"]) > 200 else ""),
                "distance": round(c["distance"], 4),
            }
            for c in contexts
        ],
        "model": claude_resp.get("model"),
        "usage": claude_resp.get("usage", {}),
    }
