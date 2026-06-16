"""
정책 Q&A 인덱스를 fastembed 다국어 ONNX 임베딩으로 재구축.
- 모델: paraphrase-multilingual-MiniLM-L12-v2 (384d) — 한국어 양호, torch·API 키 불필요.
- 기존 인덱스의 청크 텍스트/메타를 읽어 재임베딩 + 깨진(바이너리) 청크 필터링.
- 검색은 query_embeddings(외부 임베더)로 — 클라우드에서 fastembed로 동일 동작.

실행: python scripts/rebuild_onnx_index.py
"""
import os, sys, io, shutil, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import chromadb
from core.rag_indexer import FastEmbedEmbedder

SRC = "./data/chroma_db"
DST = "./data/chroma_db_new"
COLL = "policy_docs"


def is_clean(text: str) -> bool:
    """깨진/바이너리 청크 필터 — PDF 파싱 잔여물 제거."""
    if not text or len(text.strip()) < 10:
        return False
    if "\x00" in text or "PK\x03\x04" in text or ".txtPK" in text:
        return False
    printable = sum(1 for c in text if c.isprintable() or c in "\n\t ")
    if printable / len(text) < 0.85:
        return False
    meaningful = sum(1 for c in text if c.isalnum() or "가" <= c <= "힣")
    if meaningful / max(len(text), 1) < 0.3:
        return False
    return True


# 1) 기존 인덱스에서 전체 읽기
src = chromadb.PersistentClient(path=SRC).get_collection(COLL)
data = src.get(include=["documents", "metadatas"])
ids, docs, metas = data["ids"], data["documents"], data["metadatas"]
print(f"원본 청크: {len(docs)}")

# 2) 깨진 청크 필터링
keep = [(i, d, m) for i, d, m in zip(ids, docs, metas) if is_clean(d)]
print(f"정상 청크: {len(keep)} (제거 {len(docs) - len(keep)}개)")
ids = [k[0] for k in keep]
docs = [k[1] for k in keep]
metas = [k[2] for k in keep]

# 3) fastembed 다국어 임베딩
emb = FastEmbedEmbedder()
print(f"임베딩 모델: {emb.model_name}")

# 4) 새 인덱스 생성 + 명시적 임베딩으로 추가
if os.path.exists(DST):
    shutil.rmtree(DST)
dst = chromadb.PersistentClient(path=DST).create_collection(COLL)

BATCH = 256
t0 = time.time()
for i in range(0, len(docs), BATCH):
    chunk_docs = docs[i:i+BATCH]
    vecs = emb.embed(chunk_docs)
    dst.add(
        ids=ids[i:i+BATCH],
        documents=chunk_docs,
        metadatas=metas[i:i+BATCH],
        embeddings=vecs,
    )
    done = min(i+BATCH, len(docs))
    print(f"  {done}/{len(docs)} ({time.time()-t0:.0f}s)", flush=True)

print(f"새 인덱스 청크: {dst.count()} | 차원: {len(dst.peek(1)['embeddings'][0])}")

# 5) 검증 쿼리 (query_embeddings)
for q in ["그린리모델링 사업 신청 자격은?", "ZEB 등급별 취득세 감면율"]:
    qv = emb.embed([q])[0]
    r = dst.query(query_embeddings=[qv], n_results=2, include=["documents", "metadatas", "distances"])
    print(f"\nQ: {q}")
    for doc, meta, dist in zip(r["documents"][0], r["metadatas"][0], r["distances"][0]):
        print(f"  [{meta.get('file','?')} p.{meta.get('page','?')}] d={dist:.3f} {doc[:55]}...")
print("\n✅ 다국어 재구축 완료:", DST)
