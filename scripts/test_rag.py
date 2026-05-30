"""
scripts/test_rag.py — RAG 파이프라인 단위 테스트
=================================================
core.rag_indexer + core.rag_retriever + modes.mode1_rag 검증.

실행:
    python scripts/test_rag.py

전제 조건:
    - chromadb, pypdf 설치
    - data/policy_docs/ 에 최소 한 개 이상의 .pdf/.txt/.md
    - 사전 빌드된 인덱스는 필요 없음 (테스트 중 임시 인덱스 생성)

환경 변수:
    EMBEDDING_PROVIDER=hash  (강제 — 외부 API 호출 없이 검증)
"""

import os
import sys
import shutil
import tempfile
from pathlib import Path

os.environ["EMBEDDING_PROVIDER"] = "hash"
os.environ["RAG_CLAUDE_PROVIDER"] = "mock"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ====================================================================
# 윈도우 안전 임시 디렉토리 매니저
# ====================================================================
# 표준 _make_tempdir()는 윈도우에서 ChromaDB가 SQLite 파일을
# 잠근 상태로 두는 경우 정리 단계에서 PermissionError(WinError 32)를 던진다.
# 테스트 검증 자체엔 영향 없는 OS 레벨 이슈이므로 정리 실패를 무시하도록 래핑.

class SafeTempDir:
    def __init__(self):
        self.path = tempfile.mkdtemp()
    def __enter__(self):
        return self.path
    def __exit__(self, *args):
        import shutil, gc
        gc.collect()
        try:
            shutil.rmtree(self.path, ignore_errors=True)
        except Exception:
            pass   # 윈도우 파일 잠금 무시


def _make_tempdir():
    """_make_tempdir() 대체. 윈도우 파일 잠금 PermissionError 회피."""
    return SafeTempDir()


def test_chunk_text():
    """청킹 기본 동작."""
    print("\n" + "=" * 70)
    print("청킹 동작 검증")
    print("=" * 70)
    from core.rag_indexer import chunk_text

    # 짧은 텍스트는 한 청크
    short = "안녕하세요. 이것은 짧은 텍스트입니다."
    c = chunk_text(short)
    assert len(c) == 1, f"짧은 텍스트는 1청크여야: {len(c)}"
    print(f"  [PASS] 짧은 텍스트: 1청크")

    # 정확히 chunk_size 길이
    exact = "가" * 1000
    c = chunk_text(exact, chunk_size=1000)
    assert len(c) == 1
    print(f"  [PASS] 정확히 1000자: 1청크")

    # chunk_size를 넘는 텍스트 → 여러 청크
    long = "이것은 첫 문장입니다. 이것은 두번째 문장입니다. " * 200
    c = chunk_text(long, chunk_size=500, overlap=50)
    assert len(c) > 1
    # 각 청크가 chunk_size 이하여야 함 (마지막 청크는 짧을 수 있음)
    for chunk in c:
        assert len(chunk) <= 500 + 200, f"청크 너무 김: {len(chunk)}"
    print(f"  [PASS] 긴 텍스트({len(long)}자) → {len(c)}청크")

    # 빈 텍스트
    c = chunk_text("")
    assert c == [], "빈 텍스트는 빈 리스트"
    print(f"  [PASS] 빈 텍스트: 0청크")


def test_chunk_pages_metadata():
    """페이지 청크 메타데이터 정확성."""
    print("\n" + "=" * 70)
    print("페이지 청크 메타데이터 검증")
    print("=" * 70)
    from core.rag_indexer import chunk_pages

    pages = [
        {"page": 1, "text": "1페이지 내용. " * 100},   # 분할됨
        {"page": 2, "text": "2페이지 짧음"},            # 1청크
        {"page": 3, "text": ""},                       # 0청크
    ]
    chunks = chunk_pages(pages, "test.pdf", chunk_size=500)
    assert len(chunks) > 0, "최소 1청크 이상"
    files = {c["metadata"]["file"] for c in chunks}
    assert files == {"test.pdf"}, "파일명 일관성"

    # 페이지 1: 분할되었고 chunk_idx가 0,1,2,...
    p1_chunks = [c for c in chunks if c["metadata"]["page"] == 1]
    assert len(p1_chunks) >= 2, "긴 페이지는 분할됨"
    assert p1_chunks[0]["metadata"]["chunk_idx"] == 0
    assert p1_chunks[-1]["metadata"]["chunk_idx"] == len(p1_chunks) - 1

    # 페이지 3 (빈 페이지): 0청크
    p3 = [c for c in chunks if c["metadata"]["page"] == 3]
    assert p3 == [], "빈 페이지는 청크 없음"

    print(f"  [PASS] 메타데이터(file/page/chunk_idx) 일관성")
    print(f"  [PASS] 빈 페이지 skip")


def test_hash_embedder():
    """HashEmbedder 결정성 + 차원."""
    print("\n" + "=" * 70)
    print("HashEmbedder 검증")
    print("=" * 70)
    from core.rag_indexer import HashEmbedder

    emb = HashEmbedder()
    assert emb.dim == 64
    v1 = emb.embed(["같은 텍스트"])[0]
    v2 = emb.embed(["같은 텍스트"])[0]
    assert v1 == v2, "결정적이지 않음"
    assert len(v1) == 64, f"차원 불일치: {len(v1)}"
    print(f"  [PASS] dim=64, 결정성 확인")

    v3 = emb.embed(["다른 텍스트"])[0]
    assert v1 != v3, "다른 입력에 같은 출력"
    print(f"  [PASS] 다른 입력 → 다른 벡터")


def test_indexer_end_to_end():
    """RagIndexer 전체 파이프라인 (임시 디렉토리)."""
    print("\n" + "=" * 70)
    print("RagIndexer end-to-end 검증")
    print("=" * 70)
    from core.rag_indexer import RagIndexer

    with _make_tempdir() as tmpdir:
        # 가짜 문서 만들기
        docs_dir = Path(tmpdir) / "docs"
        docs_dir.mkdir()
        (docs_dir / "test1.txt").write_text(
            "ZEB 5등급 인증 시 취득세 15% 감면이 적용됩니다. " * 30,
            encoding="utf-8",
        )
        (docs_dir / "test2.txt").write_text(
            "녹색건축법 제15조에 따라 용적률 완화가 가능합니다. " * 30,
            encoding="utf-8",
        )

        # 인덱싱
        chroma_dir = Path(tmpdir) / "chroma"
        indexer = RagIndexer(
            persist_dir=str(chroma_dir),
            collection_name="test_collection",
        )
        stats = indexer.index_directory(str(docs_dir))

        assert stats["files"] == 2, f"파일 수: {stats['files']}"
        assert stats["chunks"] > 0
        print(f"  [PASS] 2개 파일 → {stats['chunks']}청크 인덱싱")

        # 통계
        s = indexer.stats()
        assert s["chunk_count"] == stats["chunks"]
        assert s["embedding_dim"] == 64
        print(f"  [PASS] stats(): chunk_count={s['chunk_count']}, dim={s['embedding_dim']}")


def test_retriever_self_match():
    """RagRetriever: 동일 텍스트 검색 시 자기 자신이 1위."""
    print("\n" + "=" * 70)
    print("RagRetriever 자기-매칭 검증")
    print("=" * 70)
    from core.rag_indexer import RagIndexer
    from core.rag_retriever import RagRetriever

    with _make_tempdir() as tmpdir:
        docs_dir = Path(tmpdir) / "docs"
        docs_dir.mkdir()
        target = "이 문장은 검색 대상 문장입니다. 고유한 식별 텍스트 XYZQ12345."
        (docs_dir / "target.txt").write_text(
            target + "\n" + ("다른 내용. " * 100),
            encoding="utf-8",
        )

        chroma_dir = Path(tmpdir) / "chroma"
        indexer = RagIndexer(persist_dir=str(chroma_dir), collection_name="test")
        indexer.index_directory(str(docs_dir))

        retriever = RagRetriever(
            persist_dir=str(chroma_dir),
            collection_name="test",
        )

        # 인덱스에 들어간 정확한 텍스트로 검색 (단, 청킹된 결과여서 정확 일치는 보장 안 됨)
        # 대신 첫 청크 전체를 쿼리로
        all_chunks = retriever.collection.get(limit=10, include=["documents"])
        first_chunk = all_chunks["documents"][0]
        results = retriever.retrieve(first_chunk, top_k=1)

        assert len(results) == 1
        assert results[0]["distance"] < 0.01, (
            f"동일 텍스트 검색 시 distance≈0이어야: {results[0]['distance']}"
        )
        print(f"  [PASS] 자기-매칭 distance={results[0]['distance']:.6f}")


def test_answer_with_rag_mock():
    """answer_with_rag mock Claude 호출."""
    print("\n" + "=" * 70)
    print("answer_with_rag (mock) 검증")
    print("=" * 70)
    from core.rag_indexer import RagIndexer
    from core.rag_retriever import answer_with_rag, RagRetriever, _mock_claude_caller

    with _make_tempdir() as tmpdir:
        docs_dir = Path(tmpdir) / "docs"
        docs_dir.mkdir()
        (docs_dir / "policy.txt").write_text(
            "그린리모델링 사업 신청 자격은 공공건축물 소유자에 한합니다. " * 20,
            encoding="utf-8",
        )

        chroma_dir = Path(tmpdir) / "chroma"
        indexer = RagIndexer(persist_dir=str(chroma_dir), collection_name="test_col")
        indexer.index_directory(str(docs_dir))

        retriever = RagRetriever(persist_dir=str(chroma_dir), collection_name="test_col")
        result = answer_with_rag(
            "그린리모델링 사업 신청 자격은?",
            top_k=3,
            retriever=retriever,
            claude_caller=_mock_claude_caller,
        )

        assert "answer" in result
        assert "sources" in result
        assert len(result["sources"]) > 0
        assert result["sources"][0]["file"] == "policy.txt"
        assert result["model"] == "mock"
        print(f"  [PASS] mock 답변: {len(result['answer'])} chars, "
              f"{len(result['sources'])} sources")


def test_mode1_index_ready_negative():
    """is_index_ready: 인덱스 없을 때 False."""
    print("\n" + "=" * 70)
    print("mode1_rag.is_index_ready 검증")
    print("=" * 70)
    from modes.mode1_rag import is_index_ready

    ready, msg, count = is_index_ready(persist_dir="/tmp/non_existent_xyz_chroma")
    assert ready is False
    assert "인덱스가 없습니다" in msg or "없습니다" in msg
    assert count == 0
    print(f"  [PASS] 인덱스 없을 때: ready=False, count=0")


def test_extract_file_negative():
    """extract_text_from_file: 잘못된 입력에 빈 리스트."""
    print("\n" + "=" * 70)
    print("extract_text_from_file 예외 처리")
    print("=" * 70)
    from core.rag_indexer import extract_text_from_file

    # 존재하지 않는 파일
    assert extract_text_from_file("/tmp/non_existent_abc.pdf") == []
    print(f"  [PASS] 없는 파일: 빈 리스트")

    # 지원 안 되는 확장자
    with tempfile.NamedTemporaryFile(suffix=".xyz", mode="w", delete=False) as f:
        f.write("내용")
        tmppath = f.name
    assert extract_text_from_file(tmppath) == []
    os.unlink(tmppath)
    print(f"  [PASS] 미지원 확장자: 빈 리스트")


if __name__ == "__main__":
    try:
        test_chunk_text()
        test_chunk_pages_metadata()
        test_hash_embedder()
        test_indexer_end_to_end()
        test_retriever_self_match()
        test_answer_with_rag_mock()
        test_mode1_index_ready_negative()
        test_extract_file_negative()
        print("\n" + "=" * 70)
        print("모든 RAG 테스트 통과 ✅")
        print("=" * 70)
    except AssertionError as e:
        print(f"\n❌ 검증 실패: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 예외: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
