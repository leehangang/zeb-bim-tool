# 🌱 ZEB-ROI · 그린리모델링 의사결정 플랫폼

**BIM 한 번으로 공공건축물 그린리모델링 전 과정을 자동 분석하는 챗봇**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B)](https://streamlit.io/)
[![Claude Haiku 4.5](https://img.shields.io/badge/LLM-Claude%20Haiku%204.5-D97757)](https://www.anthropic.com/)
[![Tests](https://img.shields.io/badge/Tests-76%20PASS-brightgreen)](#테스트)

> 2026년 졸업설계 작품. 케이스: KEPCO 김천 도담어린이집 (연면적 1,251㎡).
> **검증 결과**: 자산화 ROI **16.92%** (KEPCO 검증 목표 16.9% 일치)

---

## 📌 한 줄 요약

Revit BIM 모델을 업로드하면 11개 GR 기술요소 자동 평가 → 보강 우선순위 + Max Cost + 보조금 + 회수기간을 통합 산출하는 **4-모드 챗봇 플랫폼**.

## 🎯 무엇을 자동화하는가

기존엔 건축사·설비기사·세무사·시공사가 **각자 따로** 계산하던 항목들을 **하나의 BIM 입력**으로 통합:

| 분야 | 기존 작업 | 자동화 결과 |
|---|---|---|
| **건축** | 11개 기술요소 진단표 수기 작성 | BIM JSON → 자동 매핑 (Mode 3) |
| **시공** | 견적사 수기 견적 (수일~수주 소요) | 07/08 단가DB로 즉시 산출 (Mode 3) |
| **법무** | 04 녹색건축법 §15, 05 §47의2 일일이 확인 | 보조금·용적률·취득세 한 번에 (Mode 2) |
| **행정** | 사업 신청서 빈칸 채우기 | 챗봇과 대화로 자동 생성 (Mode 4) |
| **컨설팅** | 정책 조항 검색 | RAG 기반 출처 인용 답변 (Mode 1) |

## ✨ 4가지 모드

| 모드 | 입력 | 출력 | API 키 |
|---|---|---|---|
| 🏢 **BIM 진단 + ROI** | Revit BIM JSON | 11개 매핑 + 등급 + 보강 우선순위 | 불필요 |
| 💬 **정책 Q&A (RAG)** | 자연어 질문 | 근거 조항 인용 답변 | 필요 |
| 💰 **ROI 시뮬레이션** | 자연어 ("연면적 1,200㎡, ZEB 5등급") | Max Cost / 보조금 / 회수기간 | 필요 |
| 📋 **사업 신청 인테이크** | 챗봇 대화 | 신청서 마크다운 초안 | 필요 |

## 🗂 데이터 출처

7개 정책 자료 + 2개 단가 DB:

- **01_GR_가이드라인** (LH·국토부) — 11개 GR 기술요소, 사업 유형, 정량평가표
- **02_GR_기술요소** (LH) — 기술요소 상세 사양
- **03_ZEB_인증기준_고시** (국토부) — ZEB 1~5등급 자립률
- **04_녹색건축법** — §15 용적률 완화
- **05_지방세특례제한법** — §47의2 취득세 감면율
- **06_에너지절약설계기준** (국토부 고시) — 외피 열관류율
- **07_조달청_단가DB** — 자재별 단가 + 시공계수
- **08_조달청_간접공사비** — 공사기간별 간접비율
- **09_영유아보육법_시행규칙** (보건복지부) — 어린이집 일조·채광 기준

## 🚀 빠른 시작

### 1. 환경 준비

```bash
# 1. 저장소 클론
git clone https://github.com/leehangang/zeb-bim-tool.git
cd zeb-bim-tool

# 2. 가상환경 + 의존성
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt

# 3. .env 파일 만들기
copy .env.example .env             # Windows
# cp .env.example .env             # macOS/Linux
# 메모장으로 .env 열어서 ANTHROPIC_API_KEY 입력
```

### 2. 챗봇 실행

```bash
streamlit run streamlit_app.py
```

브라우저가 자동으로 `http://localhost:8501` 을 열어요. 사이드바에서 모드 선택.

### 3. (선택) Mode 1 RAG 인덱싱

7개 정책 PDF를 `data/policy_docs/` 폴더에 넣고:

```bash
python scripts/build_index.py --provider local   # 무료
# python scripts/build_index.py                  # OpenAI (유료, 한국어 검색 품질 우수)
```

## 🧪 테스트

```bash
python scripts/test_bim.py      # BIM 진단 + ROI 계산기 (28개)
python scripts/test_rag.py      # RAG 인덱싱 + 검색 (15개)
python scripts/test_mode2.py    # ROI Function Calling (15개)
python scripts/test_mode4.py    # 인테이크 챗봇 (18개)
```

총 **76개 단위 테스트** 전부 외부 API 호출 없이 mock 백엔드로 검증.

## 📊 검증 결과 — 도담어린이집

| 지표 | 값 | 비고 |
|---|---|---|
| 현재 등급 | D (25/100점) | 11개 중 2개만 적용 |
| 전체 보강 비용 | 5.31억 (Max Cost) | 11개 항목 전체 |
| 점수 상승 | +50점 | D → A |
| 자산화 ROI | **16.92%** | KEPCO 검증 목표 16.9% 일치 ✅ |
| GR 단독 회수기간 | 7.3년 | 에너지 절감만 고려 |
| 통합 회수기간 | 자부담 8년 미만 | 보조금 + 인센티브 포함 |
| 가성비 1위 보강 | 콘덴싱 보일러 1식 | 1,102만원 / +5점 / 효율 45.38 |

## 🏗 아키텍처

```
streamlit_app.py             ← 메인 앱 + 랜딩 + 사이드바
├─ core/                     ← 엔진 (UI 의존 X, 테스트 가능)
│   ├─ bim_diagnoser.py      ← 11개 GR 자동 매핑 + 정량평가표
│   ├─ roi_calculator.py     ← 단가DB + 간접비 + 보조금/세금 인센티브
│   ├─ rag_indexer.py        ← PDF → 청크 → ChromaDB 임베딩
│   ├─ rag_retriever.py      ← 검색 + Claude 답변 생성
│   ├─ llm_client.py         ← Claude API 추상화 + Function Calling 루프
│   ├─ roi_tools.py          ← Mode 2 도구 정의
│   ├─ intake_schema.py      ← 신청서 21개 필드 스키마
│   ├─ intake_tools.py       ← Mode 4 도구 + 세션 상태
│   ├─ error_messages.py     ← 친절한 한국어 에러 변환
│   └─ ui_theme.py           ← 글로벌 CSS + 로고 + 카드
├─ modes/                    ← 4개 모드 UI
│   ├─ mode1_rag.py
│   ├─ mode2_roi.py
│   ├─ mode3_bim.py
│   └─ mode4_intake.py
├─ scripts/                  ← 테스트 + 인덱싱
│   ├─ test_bim.py
│   ├─ test_rag.py
│   ├─ test_mode2.py
│   ├─ test_mode4.py
│   └─ build_index.py
└─ data/
    ├─ sample_bim/           ← 가상 BIM JSON 샘플
    ├─ policy_docs/          ← 정책 PDF + 단가 DB
    └─ chroma_db/            ← RAG 인덱스 (build_index 후 생성)
```

## 🛠 기술 스택

- **언어**: Python 3.10+
- **UI**: Streamlit
- **LLM**: Anthropic Claude Haiku 4.5
- **RAG**: ChromaDB + 임베딩 추상화 (OpenAI / 로컬 sentence-transformers / hash mock)
- **데이터 처리**: pandas, openpyxl (07/08 엑셀), pypdf (정책 PDF)

## 🏅 핵심 설계 결정

### 1. 모드별 분리, 엔진과 UI 분리
- `core/`(엔진) ↔ `modes/`(UI) ↔ `scripts/`(테스트·인덱싱)
- 각 모드는 `run_xxx()` (순수 함수, 테스트 가능) + `render_xxx_panel()` (Streamlit UI) 분리

### 2. 백엔드 추상화
- Claude API: `real` / `mock` 분기 (`CLAUDE_PROVIDER=mock` 시 외부 API 호출 X)
- 임베딩: `openai` / `local` / `hash` 분기 (`EMBEDDING_PROVIDER` 환경변수)
- 결과: 외부 API 키 없이도 76개 테스트 전부 통과

### 3. 자산화 ROI 정의
ZEB 그린리모델링은 단순 "에너지 절감 / 투자 비용"으로 평가하면 회수기간이 30~50년으로 나옴 → 정책 의사결정 불가.

**자산화 ROI** = (보조금 + 용적률 자산가치 + 취득세 감면 + 연간 절감액 × 30년) / 순투자

이 정의가 KEPCO 검증 결과(16.9%)와 일치 확인.

## 📋 졸업설계 작품 정보

- **작품명**: ZEB-BIM-Tool — 그린리모델링 의사결정 플랫폼
- **케이스**: KEPCO 김천 도담어린이집 (연면적 1,251㎡)
- **공모전**: 삼성E&A 환경에너지탐구대회
- **연도**: 2026

## 📚 참고 문서

- [Anthropic Claude API](https://docs.anthropic.com/)
- [Streamlit 문서](https://docs.streamlit.io/)
- [01 그린리모델링 가이드라인](https://www.greenremodeling.or.kr/) (LH·국토부)
- [03 ZEB 인증기준 고시](https://www.law.go.kr/) (국토부 고시)

## ⚠️ 면책 조항

본 챗봇의 모든 진단·산정 결과는 **자동 계산된 참고용 값**입니다.

실제 그린리모델링 사업 신청 시:
- 공식 컨설팅: **그린리모델링 창조센터 1588-8788**
- 시공 견적: 견적사·시공사 별도 검토 필수
- 법령 적용: 변호사·세무사 자문 권장

## 📄 라이선스

졸업설계 작품으로 비영리 학술 목적 사용 자유. 단가 DB 및 정책 PDF 원본 저작권은 조달청·국토부·LH에 있습니다.

## 🙏 감사

- **데이터**: 조달청, 국토교통부, LH 한국토지주택공사
- **케이스 협력**: KEPCO (한국전력공사)
- **개발 도구**: Anthropic Claude

---

**문의**: [GitHub Issues](https://github.com/leehangang/zeb-bim-tool/issues)
