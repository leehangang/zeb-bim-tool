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



def test_page_bundle_extraction():
    """
    페이지 번들(ZIP) 텍스트 추출 — 회귀 방지.

    🔴 이 버그로 01/02/09(114쪽·13만자)를 색인에서 통째로 버리고 있었다.
       .pdf 확장자 안이 ZIP이고 .jpeg가 보이면 "이미지 스캔본 → 텍스트 없음"이라
       단정했는데, 실제로는 페이지마다 .txt가 동봉된 번들이었다.
       "스캔본이라 추출 불가"라는 우리 진단 자체가 틀렸던 것.
    """
    import json
    import zipfile

    print("\n" + "=" * 70)
    print("페이지 번들(ZIP) 추출 — 01/02/09 회귀 방지")
    print("=" * 70)
    from core.rag_indexer import _extract_from_page_bundle, extract_text_from_file

    JPEG = b"\xff\xd8\xff"   # 진짜 JPEG 헤더

    # ① manifest 기반 번들
    with tempfile.TemporaryDirectory() as d:
        bp = os.path.join(d, "bundle.pdf")     # 확장자는 .pdf, 내용은 ZIP
        with zipfile.ZipFile(bp, "w") as z:
            z.writestr("manifest.json", json.dumps({
                "num_pages": 2,
                "pages": [
                    {"page_number": 1, "image": {"path": "1.jpeg"}, "text": {"path": "1.txt"}},
                    {"page_number": 2, "image": {"path": "2.jpeg"}, "text": {"path": "2.txt"}},
                ],
            }, ensure_ascii=False))
            z.writestr("1.jpeg", JPEG)
            z.writestr("2.jpeg", JPEG)
            z.writestr("1.txt", "제1조 목적 조항 본문")
            z.writestr("2.txt", "제2조 적용대상 조항 본문")

        pages = extract_text_from_file(bp)
        assert len(pages) == 2, f"번들에서 2쪽 나와야 함: {len(pages)}"
        assert pages[0]["page"] == 1 and "제1조" in pages[0]["text"]
        assert pages[1]["page"] == 2 and "제2조" in pages[1]["text"]
        print("  [PASS] manifest 번들: 2쪽 추출 · 페이지 번호 보존")

    # ② manifest 없어도 숫자 .txt 폴백 + 순서 (문자열 정렬이면 10 < 2가 되는 함정)
    with tempfile.TemporaryDirectory() as d:
        bp = os.path.join(d, "nomanifest.pdf")
        with zipfile.ZipFile(bp, "w") as z:
            for i in (1, 2, 10):
                z.writestr(f"{i}.txt", f"{i}쪽 본문")
                z.writestr(f"{i}.jpeg", JPEG)
        pages = _extract_from_page_bundle(bp)
        got = [p["page"] for p in pages]
        assert got == [1, 2, 10], f"순서 오류: {got}"
        print("  [PASS] manifest 없음: 숫자 순 폴백 (1,2,10 — 문자열 정렬 아님)")

    # ③ 텍스트 없는 진짜 이미지 스캔본은 여전히 SKIP (가드 유지)
    with tempfile.TemporaryDirectory() as d:
        bp = os.path.join(d, "imageonly.pdf")
        with zipfile.ZipFile(bp, "w") as z:
            z.writestr("1.jpeg", JPEG)
        assert extract_text_from_file(bp) == [], "텍스트 없는 스캔본은 SKIP돼야 함"
        print("  [PASS] 텍스트 없는 스캔본: 여전히 SKIP (가드 유지)")

    # ④ 실제 코퍼스 — 01/02/09가 살아 있는가
    for name, min_pages in [("01_GR_가이드라인_pdf.pdf", 70),
                            ("02_GR_기술요소.pdf", 2),
                            ("09_영유아보육법_시행규칙.pdf", 20)]:
        fp = PROJECT_ROOT / "data" / "policy_docs" / name
        if not fp.exists():
            print(f"  [SKIP] {name} 없음")
            continue
        pages = extract_text_from_file(str(fp))
        chars = sum(len(p["text"]) for p in pages)
        assert len(pages) >= min_pages, f"{name}: {len(pages)}쪽 (기대 {min_pages}+)"
        assert chars > 2000, f"{name}: 텍스트 {chars}자"
        print(f"  [PASS] {name}: {len(pages)}쪽 · {chars:,}자")


def test_zip_refresh_on_change():
    """
    배포 재현 — 낡은 색인이 이미 풀려 있을 때 **새 zip이 반영되는가**.

    🔴 2026-07-16: 라이브가 6건·438청크를 표시하고 있었다. 커밋 5453785 시점의 색인이다.
       그 뒤 세 번(874 → 1,140 → 1,300청크) 재색인해 push했지만 **한 번도 사이트에
       도달하지 않았다.** 원인은 _auto_unzip_chroma_if_needed()의 첫 줄:
           if (chroma_dir / "chroma.sqlite3").exists(): return
       한 번 풀리면 새 zip을 영원히 무시했다(docstring엔 "항상 압축 해제"라 적혀 있었다).
       배포 환경은 리포 디렉토리를 재사용하므로 낡은 색인이 계속 살아남았다.

       로컬 테스트는 전부 통과했다 — 로컬 색인 디렉토리를 직접 보기 때문이다.
       **배포에서만 죽는 버그**라 이 시뮬레이션이 필요하다.
    """
    import shutil
    import subprocess
    import zipfile

    print("\n" + "=" * 70)
    print("배포 시뮬 — zip이 바뀌면 색인이 갱신되는가")
    print("=" * 70)

    # 앱의 압축 해제 로직만 떼어온다 (streamlit import 회피)
    src = (PROJECT_ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    s = src.index("def _auto_unzip_chroma_if_needed")
    e = src.index("# 앱 시작 시 1회 실행")
    ns = {}
    exec(src[s:e], ns)
    unzip = ns["_auto_unzip_chroma_if_needed"]

    cwd0 = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        (work / "data").mkdir()

        # ① '낡은 zip' — 청크 2개짜리 가짜 색인을 만들어 심는다
        old_dir = work / "_old"
        (old_dir).mkdir()
        (old_dir / "chroma.sqlite3").write_bytes(b"OLD-INDEX-PLACEHOLDER")
        old_zip = work / "data" / "chroma_db.zip"
        with zipfile.ZipFile(old_zip, "w") as z:
            z.write(old_dir / "chroma.sqlite3", "chroma.sqlite3")

        os.chdir(work)
        unzip()
        got = (work / "data" / "chroma_db" / "chroma.sqlite3").read_bytes()
        assert got == b"OLD-INDEX-PLACEHOLDER", "낡은 zip이 안 풀림"
        print("  [PASS] ① 낡은 zip 압축 해제됨")

        # ② 같은 zip으로 재시작 — 다시 풀 필요 없다 (스탬프 일치)
        stamp1 = (work / "data" / "chroma_db" / ".zip_stamp").read_text()
        unzip()
        assert (work / "data" / "chroma_db" / ".zip_stamp").read_text() == stamp1
        print("  [PASS] ② 같은 zip 재시작: 불필요한 재압축 없음")

        # ③ zip 교체 — 이게 라이브에서 무시되던 그 지점
        with zipfile.ZipFile(old_zip, "w") as z:
            z.writestr("chroma.sqlite3", "NEW-INDEX-PLACEHOLDER")
        unzip()
        got = (work / "data" / "chroma_db" / "chroma.sqlite3").read_bytes()
        assert got == b"NEW-INDEX-PLACEHOLDER", (
            "🔴 새 zip이 무시됐다 — 라이브가 6건·438청크에 얼어붙던 바로 그 버그"
        )
        assert (work / "data" / "chroma_db" / ".zip_stamp").read_text() != stamp1
        print("  [PASS] ③ zip 교체 → 색인 갱신됨 (배포 반영)")

        # Windows는 사용 중인 디렉토리를 못 지운다 — with를 빠져나가기 전에 벗어난다
        os.chdir(cwd0)

    # ④ 실제 배포 zip이 현재 색인과 같은 내용인가 — push 전 최종 확인
    os.chdir(PROJECT_ROOT)
    zp = PROJECT_ROOT / "data" / "chroma_db.zip"
    if zp.exists():
        with zipfile.ZipFile(zp) as z:
            names = {n.replace("\\", "/").split("/")[-1] for n in z.namelist()}
        assert "chroma.sqlite3" in names, f"zip에 chroma.sqlite3 없음: {sorted(names)[:5]}"
        print(f"  [PASS] ④ 배포 zip 정상 ({zp.stat().st_size/1e6:.1f}MB)")


def test_retrieval_quality():
    """
    검색 품질 하한선 — 청킹·전처리를 건드렸을 때 조용히 나빠지는 걸 막는다.

    🔴 2026-07-16: "화면이 '조항 단위 색인'이라 하니 실제로 조 단위로 쪼개자"는
       그럴듯한 개선을 넣었다가 측정하고 되돌렸다. 문서 적중은 그대로였는데
       **인용 청크에 답이 들어있는 비율이 top3 90% → 60%로 무너졌다**
       (조가 짧아 top-k에 담기는 본문 총량이 줄어든 탓). 청크만 49% 늘었다.
       측정이 없었으면 개악을 배포했다. 그래서 이 테스트가 있다.

    두 가지를 잰다:
      ① 문서 적중 — 질문에 맞는 '파일'이 top3에 오는가
      ② 인용 품질 — 실제 답 문구가 검색된 '청크 안'에 있는가 (앱이 인용하는 단위)
    """
    print("\n" + "=" * 70)
    print("검색 품질 하한선 (문서 적중 · 인용 품질)")
    print("=" * 70)
    if not (PROJECT_ROOT / "data" / "chroma_db").exists():
        print("  [SKIP] 색인 없음")
        return
    os.chdir(PROJECT_ROOT)
    from core.rag_retriever import KeywordRetriever

    r = KeywordRetriever()

    # ① 문서 적중 — (질문, 정답 파일 접두)
    DOCS = [
        ("보조금 교부 결정 용도 외 사용 금지", "21_"),
        ("2030년 국가 온실가스 감축 목표 부문별", "22_"),
        ("대지 외 생산량 보정계수 가중치", "19_"),
        ("제로에너지건축물 인증등급 비주거용 기준", "19_"),
        ("ZEB 인증 신청 자격 누가", "12_"),
        ("취득세 감면 녹색건축 인증 건축물", "05_"),
        ("노유자시설 용도 분류", "13_"),
        ("한국전력공사는 공기업인가 준정부기관인가", "14_"),
        ("어린이집 설치 기준 면적", "09_"),
        ("지역별 열관류율 중부2 외벽", "06_"),
        ("성능개선비율 산정 기준 개선공사 이전", "16_"),
        ("공공건축물 그린리모델링 정량평가 배점", "18_"),
    ]
    hit3 = sum(
        1 for q, exp in DOCS
        if any(h["file"].startswith(exp) for h in r.retrieve(q, top_k=3))
    )
    print(f"  문서 적중 top3: {hit3}/{len(DOCS)}")
    assert hit3 >= 10, f"문서 적중 하한 미달: {hit3}/{len(DOCS)} (기준 10)"

    # ② 인용 품질 — (질문, 답이 담긴 원문 문구)
    CITE = [
        ("대지 외 생산량 보정계수 가중치", "0.7"),
        ("제로에너지건축물 인증등급 비주거용 기준", "130"),
        ("취득세 감면 녹색건축 인증 건축물", "녹색건축 인증 건축물에 대한 감면"),
        ("2030년 국가 온실가스 감축 목표", "2018년"),
        ("보조금 교부 결정", "교부 결정"),
        ("기존 건축물의 종류 및 공사의 범위", "10년이 지난"),
        ("건축물에너지관리시스템 설치기준 항목", "시스템 확장성"),
        ("ZEB 인증 수수료 환불 자율 인증", "100분의 30"),
    ]
    cite3 = sum(
        1 for q, need in CITE
        if any(need in h["text"] for h in r.retrieve(q, top_k=3))
    )
    print(f"  인용 청크에 답 포함 top3: {cite3}/{len(CITE)}")
    assert cite3 >= 6, (
        f"인용 품질 하한 미달: {cite3}/{len(CITE)} (기준 6). "
        f"청킹을 바꿨다면 되돌리세요 — 조 단위 분할이 여기서 무너집니다."
    )
    print("  [PASS] 문서 적중·인용 품질 모두 하한선 이상")


def test_doc_registry():
    """
    색인 원문 레지스트리 — 화면 목록이 색인과 어긋나지 않는가.

    🔴 이 검사가 없어서 사이드바(15건)·Mode 01 헤더(10건)·Mode 01 본문("12개 법령")이
       전부 서로 다르고 전부 실제 색인과 달랐다. 목록을 손으로 적으면 반드시 낡는다.
       — 홈 등급 문자열을 하드코딩해 4등급→5등급 변경을 놓쳤던 것과 같은 버그 종류.
    """
    import re

    print("\n" + "=" * 70)
    print("색인 원문 레지스트리 — 화면 ↔ 색인 정합")
    print("=" * 70)
    from core.doc_registry import REGISTRY, group_indexed_docs

    # ① 레지스트리 항목 자체가 온전한가
    valid_groups = {"zeb", "gr", "incentive", "case"}
    for fname, (g, label, answers) in REGISTRY.items():
        assert g in valid_groups, f"{fname}: 알 수 없는 그룹 '{g}'"
        assert label.strip() and answers.strip(), f"{fname}: 표시명/설명 비어 있음"
    print(f"  [PASS] 레지스트리 {len(REGISTRY)}건: 그룹·표시명·설명 모두 유효")

    # ② 실제 색인과 대조 — 양방향
    if not (PROJECT_ROOT / "data" / "chroma_db").exists():
        print("  [SKIP] 색인 없음 — 정합 검사 생략")
        return
    from core.rag_retriever import KeywordRetriever

    # 앱과 동일하게 기본(상대) 경로로 연다. 절대경로를 넘기면 chromadb가
    # 한글이 포함된 경로에서 hnsw 인덱스 로드에 실패한다(개발 PC 한정).
    os.chdir(PROJECT_ROOT)
    retriever = KeywordRetriever()
    indexed = {m.get("file", "?") for m in retriever._cache["metas"]}

    missing = indexed - set(REGISTRY)     # 색인엔 있는데 설명이 없다
    orphan = set(REGISTRY) - indexed      # 설명은 있는데 색인에 없다 (삭제된 문서)
    assert not missing, f"레지스트리에 설명 없는 색인 문서: {sorted(missing)}"
    assert not orphan, f"색인에 없는 레지스트리 항목(유령): {sorted(orphan)}"
    print(f"  [PASS] 색인 {len(indexed)}건 ↔ 레지스트리 {len(REGISTRY)}건 완전 일치")

    # ③ 그룹 렌더에 '미분류'가 새지 않는가
    groups = group_indexed_docs(indexed)
    assert not any("미분류" in t for t, _ in groups), f"미분류 발생: {groups[-1][0]}"
    total = sum(len(items) for _, items in groups)
    assert total == len(indexed), f"그룹 합계 {total} ≠ 색인 {len(indexed)}"
    for title, items in groups:
        print(f"         {title}")

    # ③-b 화면이 인용하는 **문서 번호**가 실존하는가
    #     Mode 02 헤더가 "01 보조금"이라 적고 있었는데 보조율 50/70%의 출처는
    #     01(GR 가이드라인)이 아니라 17(공공 GR 2.0 공고)이었다. 번호를 손으로 적으면 어긋난다.
    _cited = {"05": "지방세특례", "06": "에너지절약", "10": "시행령",
              "17": "공공GR2.0", "19": "ZEB_인증기준"}
    for _n, _frag in _cited.items():
        _hit = [f for f in indexed if f.startswith(_n + "_") and _frag in f]
        assert _hit, f"Mode 02가 인용하는 {_n}({_frag})이 색인에 없음 — 화면 문구 정정 필요"
    _m2 = (PROJECT_ROOT / "modes" / "mode2_roi.py").read_text(encoding="utf-8")
    assert "01</b> 보조금" not in _m2 and "01 보조금" not in _m2, (
        "Mode 02가 보조금 출처를 01로 표기 — 실제 출처는 17 공공 GR 2.0 공고다"
    )
    print(f"  [PASS] 화면 인용 문서번호 {len(_cited)}건 실존 (05·06·10·17·19)")

    # ④ 화면에 문서 수/목록을 다시 손으로 적지 않았는가 (재발 방지)
    #    주석/독스트링의 과거 기록(예: 버그 경위에 적은 '6건·438청크')은 화면이 아니므로 제외.
    for rel in ["streamlit_app.py", "modes/mode1_rag.py"]:
        src = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
        code = "\n".join(
            ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
        )
        code = re.sub(r'"""[\s\S]*?"""', "", code)      # 독스트링 제거
        for pat in [r"\d+개\s*법령", r"\d+건\s*·\s*[\d,]+\s*청크"]:
            hits = re.findall(pat, code)
            assert not hits, f"{rel}: 문서 수가 하드코딩됨 {hits} — 색인에서 읽으세요"
    print("  [PASS] 화면에 문서 수 하드코딩 없음 (색인에서 파생)")


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
        test_page_bundle_extraction()
        test_zip_refresh_on_change()
        test_retrieval_quality()
        test_doc_registry()
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
