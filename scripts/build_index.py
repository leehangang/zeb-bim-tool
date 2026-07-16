"""
scripts/build_index.py — RAG 인덱스 빌드 (1회 실행)
====================================================
data/policy_docs/ 의 PDF/텍스트를 ChromaDB 인덱스로 변환.

⚠️ 임베더는 검색 품질에 영향을 주지 않는다 — 기본값이 'hash'인 이유:
    런타임 검색기는 core.rag_retriever.KeywordRetriever이고, 이것은
    collection.get(include=["documents"])로 **청크 원문만 꺼내 TF-IDF**를 돌린다.
    즉 저장된 임베딩 벡터를 한 번도 조회하지 않는다.
    (ChromaDB가 add() 시 벡터를 요구할 뿐이라 형식상 필요한 것)
    → 118MB 모델을 받거나 OpenAI 임베딩 비용을 낼 이유가 없다.
      'hash'는 의존성·API키·네트워크 없이 결정론적으로 같은 검색 결과를 낸다.
    나중에 벡터 검색으로 갈아탈 때만 fastembed/openai가 의미를 갖는다.

실행:
    # 기본 — 의존성·API키 불필요, 오프라인 동작 (권장)
    python scripts/build_index.py

    # 벡터 검색으로 전환할 때 (다국어 ONNX): pip install fastembed
    python scripts/build_index.py --provider fastembed

    # OpenAI 임베딩 (.env 의 OPENAI_API_KEY 필요, 유료)
    python scripts/build_index.py --provider openai

    # sentence-transformers (118MB 모델): pip install sentence-transformers
    python scripts/build_index.py --provider local

대상: data/policy_docs/ 의 11개 법령·고시·공고 원문 → 874청크
    04 녹색건축법 · 05 지방세특례제한법 · 06 에너지절약설계기준 ·
    10 녹색건축법 시행령 · 11 GR 지원사업 고시 · 12 ZEB 인증규칙 ·
    13 건축법 시행령 · 14 공공기관운영법 · 15 탄소중립기본법 시행령 ·
    16·17 2026년 GR 공고(민간·공공)

⚠️ 01·02·03·09는 .pdf 확장자지만 실제로는 **이미지 스캔본(ZIP)** 이라
   텍스트 추출이 불가 → 인덱서가 [SKIP] 경고를 내고 제외한다.
   (과거 이 가드가 없어 JPEG 바이너리를 텍스트로 색인하던 버그가 있었다)

엑셀 2개(07_조달청_단가DB, 08_조달청_간접공사비)는 RAG에 넣지 않음 —
코드 lookup 전용 (core.roi_calculator).
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
        default=os.getenv("EMBEDDING_PROVIDER", "hash"),
        choices=["hash", "fastembed", "openai", "local"],
        help=(
            "임베딩 백엔드 (기본: hash). 런타임 검색기(KeywordRetriever)는 "
            "임베딩을 조회하지 않으므로 hash로도 검색 결과가 동일하다 — "
            "의존성·API키·네트워크 불필요. 벡터 검색 전환 시에만 fastembed/openai 사용."
        ),
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
