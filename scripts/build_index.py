"""
scripts/build_index.py — RAG 인덱스 빌드 (1회 실행)
====================================================
data/policy_docs/ 의 PDF/텍스트를 ChromaDB 벡터 인덱스로 변환.

실행:
    # 기본 (OpenAI 임베딩, .env 의 OPENAI_API_KEY 필요)
    python scripts/build_index.py

    # 로컬 임베딩 (sentence-transformers, 무료)
    EMBEDDING_PROVIDER=local python scripts/build_index.py

    # 테스트용 해시 임베딩 (의미는 없지만 파이프라인 검증)
    EMBEDDING_PROVIDER=hash python scripts/build_index.py

대상 파일:
    data/policy_docs/01_GR_가이드라인.pdf
    data/policy_docs/02_GR_기술요소.pdf
    data/policy_docs/03_ZEB_인증기준_고시.pdf
    data/policy_docs/04_녹색건축법.pdf
    data/policy_docs/05_지방세특례제한법.pdf
    data/policy_docs/06_에너지절약설계기준.pdf
    data/policy_docs/09_영유아보육법_시행규칙.pdf

엑셀 2개(07_조달청_단가DB, 08_조달청_간접공사비)는 RAG에 넣지 않음 —
코드 lookup 전용 (core.roi_calculator).

비용 예상 (OpenAI text-embedding-3-small 기준):
    7개 PDF (약 500페이지) → 약 30~50만 토큰
    @ $0.02/1M tokens → 약 100~150원 (1회만)
"""

import os
import sys
import time
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()


def parse_args():
    parser = argparse.ArgumentParser(description="ZEB-ROI Chatbot RAG 인덱싱")
    parser.add_argument(
        "--docs-dir",
        default=os.getenv("POLICY_DOCS_DIR", "./data/policy_docs"),
        help="인덱싱할 PDF/텍스트 디렉토리",
    )
    parser.add_argument(
        "--chroma-dir",
        default=os.getenv("CHROMA_DB_DIR", "./data/chroma_db"),
        help="ChromaDB 영속 디렉토리",
    )
    parser.add_argument(
        "--provider",
        default=os.getenv("EMBEDDING_PROVIDER", "openai"),
        choices=["openai", "local", "hash"],
        help="임베딩 백엔드 (기본: openai)",
    )
    parser.add_argument(
        "--chunk-size", type=int, default=1000,
        help="청크 크기 (자, 기본 1000)",
    )
    parser.add_argument(
        "--overlap", type=int, default=100,
        help="청크 오버랩 (자, 기본 100)",
    )
    parser.add_argument(
        "--collection", default="policy_docs",
        help="ChromaDB 컬렉션명",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    os.environ["EMBEDDING_PROVIDER"] = args.provider

    print("=" * 70)
    print("ZEB-ROI Chatbot — RAG 인덱싱")
    print("=" * 70)
    print(f"  대상 디렉토리:   {args.docs_dir}")
    print(f"  ChromaDB 경로:   {args.chroma_dir}")
    print(f"  임베딩 백엔드:   {args.provider}")
    print(f"  청크 크기:       {args.chunk_size}자 (오버랩 {args.overlap}자)")
    print(f"  컬렉션명:        {args.collection}")
    print("=" * 70)
    print()

    docs_dir = Path(args.docs_dir)
    if not docs_dir.exists():
        print(f"❌ 대상 디렉토리가 없습니다: {docs_dir}")
        sys.exit(1)

    candidates = (
        list(docs_dir.glob("*.pdf"))
        + list(docs_dir.glob("*.txt"))
        + list(docs_dir.glob("*.md"))
    )
    if not candidates:
        print(f"❌ 인덱싱 대상 파일이 없습니다 (*.pdf, *.txt, *.md)")
        sys.exit(1)

    print(f"인덱싱 대상 파일 ({len(candidates)}개):")
    for f in sorted(candidates):
        size_kb = f.stat().st_size / 1024
        print(f"  - {f.name} ({size_kb:.1f} KB)")
    print()

    if args.provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "")
        if not key or key.startswith("sk-proj-여기"):
            print("❌ OPENAI_API_KEY 미설정 또는 placeholder 값.")
            print("   .env 파일 확인하거나 --provider local 사용.")
            sys.exit(1)

    from core.rag_indexer import RagIndexer

    print("[Step 1/2] 임베더 초기화 + ChromaDB 컬렉션 준비 중...")
    t0 = time.time()
    try:
        indexer = RagIndexer(
            persist_dir=args.chroma_dir,
            collection_name=args.collection,
        )
    except Exception as e:
        print(f"❌ Indexer 초기화 실패: {type(e).__name__}: {e}")
        sys.exit(1)
    print(f"  완료 ({time.time()-t0:.1f}s) — "
          f"{type(indexer.embedder).__name__} (dim={indexer.embedder.dim})")
    print()

    print("[Step 2/2] PDF/텍스트 파싱 + 청킹 + 임베딩 + 저장...")
    t0 = time.time()
    stats = indexer.index_directory(
        args.docs_dir,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )
    elapsed = time.time() - t0
    print()
    print("=" * 70)
    print(f"✅ 인덱싱 완료 ({elapsed:.1f}s)")
    print("=" * 70)
    print(f"  처리된 파일:   {stats['files']}개")
    print(f"  총 청크 수:    {stats['chunks']}개")
    if stats["skipped"]:
        print(f"  스킵된 파일:   {len(stats['skipped'])}개")
        for s in stats["skipped"]:
            print(f"    - {s}")

    final = indexer.stats()
    print(f"\n  ChromaDB 컬렉션:    {final['collection']}")
    print(f"  저장된 총 청크:     {final['chunk_count']}개")
    print(f"  임베딩 차원:        {final['embedding_dim']}")
    print(f"  영속 디렉토리:      {final['persist_dir']}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[중단됨]")
        sys.exit(1)
