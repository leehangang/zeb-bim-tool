"""
core/rag_indexer.py — RAG 인덱스 빌더
=====================================
PDF 7개를 청크로 분할 → 임베딩 → ChromaDB 저장.

설계:
    - 1단계: PDF → 페이지별 텍스트 추출 (pypdf)
    - 2단계: 페이지 단위 청킹 (페이지 경계 안 넘음, 1000자 + 100자 오버랩)
    - 3단계: 임베딩 (OpenAI / 로컬 / mock — Embedder 인터페이스로 추상화)
    - 4단계: ChromaDB persist 저장

대상 파일:
    01_GR_가이드라인.pdf, 02_GR_기술요소.pdf, 03_ZEB_인증기준_고시.pdf
    04_녹색건축법.pdf, 05_지방세특례제한법.pdf, 06_에너지절약설계기준.pdf
    09_영유아보육법_시행규칙.pdf

    엑셀(07, 08)은 RAG에 포함 X — 코드 lookup 전용

사용:
    indexer = RagIndexer(persist_dir="./data/chroma_db")
    indexer.index_directory("./data/policy_docs")
"""

import os
import re
import hashlib
from pathlib import Path
from typing import Iterable, Optional


# ====================================================================
# Phase 1 — PDF / 텍스트 파일 추출
# ====================================================================

def extract_text_from_file(file_path: str) -> list:
    """
    PDF 또는 텍스트 파일 → 페이지별 텍스트 리스트.

    Returns:
        [{"page": 1, "text": "..."}, ...]

    PDF는 pypdf로, 텍스트 파일은 통째로 1페이지로 처리.
    텍스트 추출 실패 시 빈 리스트 반환 (그 파일은 인덱싱 skip).
    """
    path = Path(file_path)
    if not path.exists():
        return []

    suffix = path.suffix.lower()

    # 텍스트 파일 (.txt, .md 또는 UTF-8 텍스트 PDF)
    if suffix in (".txt", ".md"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            return [{"page": 1, "text": text}] if text.strip() else []
        except Exception:
            return []

    # PDF
    if suffix == ".pdf":
        # 일부 PDF는 사실 UTF-8 텍스트 파일일 수 있음 (가공된 형태)
        # 헤더를 보고 분기
        try:
            with open(path, "rb") as f:
                header = f.read(8)
        except Exception:
            return []

        if not header.startswith(b"%PDF"):
            # PDF가 아닌 텍스트인 경우 텍스트로 시도
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if text.strip():
                    return [{"page": 1, "text": text}]
            except Exception:
                pass
            return []

        # 정상 PDF
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError(
                "pypdf 미설치. requirements.txt 또는 pip install pypdf 필요"
            )

        try:
            reader = PdfReader(str(path))
            pages = []
            for i, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                if text.strip():
                    pages.append({"page": i, "text": text})
            return pages
        except Exception as e:
            print(f"[WARN] PDF 추출 실패 {path.name}: {type(e).__name__}: {e}")
            return []

    return []


# ====================================================================
# Phase 2 — 청킹
# ====================================================================

# 청크 크기 기본값 (한국어 기준 1,000자 ≈ 700~800 토큰)
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 100


def _normalize_whitespace(text: str) -> str:
    """다중 공백 → 단일 공백. 한국어 PDF는 페이지 헤더/푸터 노이즈 많음."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list:
    """
    단일 텍스트 → 오버랩 청크 list.

    - 청크 크기 미만이면 한 청크
    - 그 이상이면 chunk_size 단위로 자르되 overlap만큼 겹침
    - 가능한 경우 문장 경계(.,!,?,。,?) 또는 줄바꿈에서 끊음

    Returns:
        list[str]
    """
    text = _normalize_whitespace(text)
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = start + chunk_size
        if end >= n:
            chunk = text[start:]
            if chunk.strip():
                chunks.append(chunk)
            break

        # 문장 경계 탐색 (마지막 200자 안)
        search_start = max(start + chunk_size - 200, start + chunk_size // 2)
        sub = text[search_start:end]
        # 우선순위: 마침표/줄바꿈, 그 다음 쉼표
        boundary = -1
        for m in re.finditer(r"[.!?。?]\s|\n", sub):
            boundary = m.end()
        if boundary < 0:
            for m in re.finditer(r",\s", sub):
                boundary = m.end()
        if boundary > 0:
            end = search_start + boundary

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        # 다음 시작점 (overlap)
        start = max(start + 1, end - overlap)

    return chunks


def chunk_pages(
    pages: list,
    file_name: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list:
    """
    페이지별 텍스트 list → 청크 list (메타데이터 포함).

    페이지 경계를 넘지 않음 — 각 페이지 내에서만 청크 분할.
    (법령/고시는 페이지 단위 의미 단위가 강함)

    Returns:
        [
          {
            "text": "...",
            "metadata": {"file": "01_xxx.pdf", "page": 5, "chunk_idx": 0}
          },
          ...
        ]
    """
    out = []
    for p in pages:
        page_num = p["page"]
        page_text = p["text"]
        subs = chunk_text(page_text, chunk_size=chunk_size, overlap=overlap)
        for i, sub in enumerate(subs):
            out.append({
                "text": sub,
                "metadata": {
                    "file": file_name,
                    "page": page_num,
                    "chunk_idx": i,
                },
            })
    return out


# ====================================================================
# Phase 3 — 임베딩 추상화
# ====================================================================
"""
세 가지 백엔드 지원:
    1. openai       — text-embedding-3-small (한국어 우수, 유료)
    2. local        — sentence-transformers / chromadb 기본 (로컬, 무료)
    3. hash         — 해시 기반 mock (의미는 없지만 테스트용)

환경 변수 EMBEDDING_PROVIDER 로 선택. 기본은 'openai'.
"""


class Embedder:
    """임베딩 백엔드 추상 인터페이스."""
    dim: int = 0

    def embed(self, texts: list) -> list:
        """list[str] → list[list[float]]"""
        raise NotImplementedError


class OpenAIEmbedder(Embedder):
    """OpenAI text-embedding-3-small (기본 1536 차원)."""
    dim = 1536

    def __init__(self, model: str = "text-embedding-3-small"):
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai 미설치. pip install openai")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key.startswith("sk-proj-여기"):
            raise RuntimeError(
                "OPENAI_API_KEY 미설정 — .env 확인 필요. "
                "또는 EMBEDDING_PROVIDER=local|hash 로 변경."
            )
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def embed(self, texts: list) -> list:
        # OpenAI 임베딩은 한 번에 최대 2048개. 100개씩 배치.
        out = []
        batch = 100
        for i in range(0, len(texts), batch):
            chunk = texts[i:i+batch]
            resp = self.client.embeddings.create(model=self.model, input=chunk)
            out.extend([d.embedding for d in resp.data])
        return out


class LocalEmbedder(Embedder):
    """
    sentence-transformers 다국어 모델.
    paraphrase-multilingual-MiniLM-L12-v2 (118MB, 384 dim, 한국어 OK).
    """
    dim = 384

    def __init__(self, model: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError(
                "sentence-transformers 미설치. "
                "pip install sentence-transformers"
            )
        self.model = SentenceTransformer(model)

    def embed(self, texts: list) -> list:
        emb = self.model.encode(texts, show_progress_bar=False)
        return emb.tolist()


class HashEmbedder(Embedder):
    """
    SHA-256 기반 의사 임베딩 (의미 X, 테스트 전용).
    같은 텍스트는 같은 벡터 → ChromaDB 저장/조회 무결성 검증 가능.
    실제 검색 품질은 X — 정확한 텍스트 매치만 가능.

    sha256(32B) + sha256(reversed)(32B) = 64B → 64 dim
    """
    dim = 64

    def embed(self, texts: list) -> list:
        out = []
        for t in texts:
            encoded = t.encode("utf-8")
            h1 = hashlib.sha256(encoded).digest()
            h2 = hashlib.sha256(encoded[::-1]).digest()
            combined = h1 + h2   # 64바이트
            vec = [(b - 128) / 128.0 for b in combined[:self.dim]]
            out.append(vec)
        return out


def get_embedder(provider: Optional[str] = None) -> Embedder:
    """
    환경변수 EMBEDDING_PROVIDER 또는 매개변수로 임베더 선택.

    값: 'openai' (기본), 'local', 'hash'
    """
    if provider is None:
        provider = os.getenv("EMBEDDING_PROVIDER", "openai")
    provider = provider.lower()
    if provider == "openai":
        return OpenAIEmbedder()
    elif provider == "local":
        return LocalEmbedder()
    elif provider == "hash":
        return HashEmbedder()
    raise ValueError(
        f"EMBEDDING_PROVIDER='{provider}' 지원 안 됨. "
        f"openai/local/hash 중 하나."
    )


# ====================================================================
# Phase 4 — ChromaDB 인덱싱
# ====================================================================

DEFAULT_COLLECTION = "policy_docs"


class RagIndexer:
    """PDF → 청크 → 임베딩 → ChromaDB 통합 빌더."""

    def __init__(
        self,
        persist_dir: str = "./data/chroma_db",
        collection_name: str = DEFAULT_COLLECTION,
        embedder: Optional[Embedder] = None,
    ):
        try:
            import chromadb
        except ImportError:
            raise RuntimeError("chromadb 미설치. pip install chromadb")

        self.persist_dir = persist_dir
        self.collection_name = collection_name
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        # PersistentClient: 디스크 영속화
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.embedder = embedder or get_embedder()

        # 기존 컬렉션 reset (재인덱싱 시)
        try:
            self.client.delete_collection(collection_name)
        except Exception:
            pass

        # 컬렉션 생성 — 임베딩은 직접 주입 (chromadb 내장 함수 미사용)
        self.collection = self.client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def index_file(
        self,
        file_path: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
    ) -> int:
        """단일 파일 인덱싱. 반환: 추가된 청크 수."""
        path = Path(file_path)
        pages = extract_text_from_file(str(path))
        if not pages:
            print(f"[SKIP] {path.name}: 텍스트 추출 실패 또는 빈 파일")
            return 0

        chunks = chunk_pages(pages, path.name, chunk_size, overlap)
        if not chunks:
            print(f"[SKIP] {path.name}: 청크 0개")
            return 0

        texts = [c["text"] for c in chunks]
        metas = [c["metadata"] for c in chunks]
        ids = [
            f"{path.stem}_p{m['page']}_c{m['chunk_idx']}"
            for m in metas
        ]

        embeddings = self.embedder.embed(texts)

        self.collection.add(
            ids=ids,
            documents=texts,
            metadatas=metas,
            embeddings=embeddings,
        )
        print(f"[OK]   {path.name}: {len(chunks)}개 청크 인덱싱 "
              f"({len(pages)}페이지)")
        return len(chunks)

    def index_directory(
        self,
        dir_path: str,
        patterns: tuple = ("*.pdf", "*.txt", "*.md"),
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
    ) -> dict:
        """디렉토리 내 PDF/텍스트 일괄 인덱싱."""
        dir_p = Path(dir_path)
        files = []
        for pat in patterns:
            files.extend(sorted(dir_p.glob(pat)))

        stats = {"files": 0, "chunks": 0, "skipped": []}
        for f in files:
            n = self.index_file(str(f), chunk_size, overlap)
            if n > 0:
                stats["files"] += 1
                stats["chunks"] += n
            else:
                stats["skipped"].append(f.name)
        return stats

    def stats(self) -> dict:
        """현재 인덱스 통계."""
        count = self.collection.count()
        return {
            "collection": self.collection_name,
            "chunk_count": count,
            "embedding_dim": self.embedder.dim,
            "embedder": type(self.embedder).__name__,
            "persist_dir": self.persist_dir,
        }
