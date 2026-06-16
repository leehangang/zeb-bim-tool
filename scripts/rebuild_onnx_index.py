"""
정책 Q&A 인덱스를 ChromaDB 내장 ONNX 임베더(all-MiniLM-L6-v2, 384d)로 재구축.
- 기존 인덱스(로컬 sentence-transformers 384d, torch 필요)의 청크 텍스트/메타를 읽어
- ONNX 기본 EF로 재임베딩 → 클라우드에서 torch·API 키 없이 query_texts로 검색 가능.

실행: python scripts/rebuild_onnx_index.py
"""
import os, sys, io, shutil, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

import chromadb
from chromadb.utils import embedding_functions

SRC = "./data/chroma_db"
DST = "./data/chroma_db_onnx"
COLL = "policy_docs"

# 1) 기존 인덱스에서 전체 문서/메타/ID 읽기
src_client = chromadb.PersistentClient(path=SRC)
src_col = src_client.get_collection(COLL)
total = src_col.count()
print(f"원본 청크 수: {total}")
data = src_col.get(include=["documents", "metadatas"])
ids = data["ids"]
docs = data["documents"]
metas = data["metadatas"]
print(f"읽어온 문서: {len(docs)}")

# 2) 새 ONNX 인덱스 생성
if os.path.exists(DST):
    shutil.rmtree(DST)
ef = embedding_functions.DefaultEmbeddingFunction()  # all-MiniLM-L6-v2 (ONNX)
dst_client = chromadb.PersistentClient(path=DST)
dst_col = dst_client.create_collection(COLL, embedding_function=ef)

# 3) 배치로 추가 (ONNX가 자동 임베딩)
BATCH = 500
t0 = time.time()
for i in range(0, len(docs), BATCH):
    dst_col.add(
        ids=ids[i:i+BATCH],
        documents=docs[i:i+BATCH],
        metadatas=metas[i:i+BATCH],
    )
    done = min(i+BATCH, len(docs))
    print(f"  {done}/{len(docs)} ({(time.time()-t0):.0f}s)", flush=True)

print(f"새 인덱스 청크 수: {dst_col.count()}")
print(f"벡터 차원: {len(dst_col.peek(1)['embeddings'][0])}")

# 4) 샘플 쿼리 검증 (query_texts = ONNX 네이티브)
for q in ["ZEB 등급별 취득세 감면율은?", "그린리모델링 사업 신청 자격"]:
    r = dst_col.query(query_texts=[q], n_results=2, include=["documents", "metadatas"])
    print(f"\nQ: {q}")
    for doc, meta in zip(r["documents"][0], r["metadatas"][0]):
        print(f"  - [{meta.get('file','?')} p.{meta.get('page','?')}] {doc[:60]}...")
print("\n✅ ONNX 인덱스 재구축 완료:", DST)
