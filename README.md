# ZEB-ROI Consulting Chatbot

> BIM 진단 기반 ZEB 평가 + 그린리모델링 ROI 컨설팅 AI 챗봇
> 졸업설계 작품 (한국전력기술 김천 본사 도담어린이집 사례 적용)

---

## 📋 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 프로젝트명 | ZEB-ROI Consulting Chatbot |
| 상위 도구 | ZEB-BIM-Tool (BIM 객체 단위 ZEB 평가 자동화) |
| 사용 LLM | Claude Haiku 4.5 (Anthropic) |
| 임베딩 | OpenAI text-embedding-3-small (RAG용) |
| 프론트엔드 | Streamlit |
| 벡터 DB | ChromaDB (로컬) |

## 🔧 4개 모드

| 모드 | 기능 | 사용 자료 |
|---|---|---|
| 1. 정책 Q&A | 9개 공식 자료 기반 RAG | PDF 7개 인덱싱 |
| 2. ROI 시뮬레이션 | Function Calling으로 산정식 호출 | 엑셀 2개 직접 lookup |
| 3. BIM 진단 | Dynamo JSON → 11개 GR 매핑 | 정량평가표 + 기술요소 |
| 4. 인테이크 | 5단 질문으로 자격 검증 | GR 가이드라인 자격조건 |

---

## 🚀 설치 및 실행

### 1. Python 환경 준비 (3.10+)

```bash
# 가상환경 생성
python -m venv venv

# 활성화 (Windows)
venv\Scripts\activate

# 활성화 (Mac/Linux)
source venv/bin/activate

# 패키지 설치
pip install -r requirements.txt
```

### 2. API 키 설정

```bash
# 템플릿 복사
cp .env.example .env

# .env 파일을 열어서 실제 API 키 입력
# - ANTHROPIC_API_KEY: https://console.anthropic.com/settings/keys
# - OPENAI_API_KEY: https://platform.openai.com/api-keys
```

⚠️ **비용 안전장치 설정 필수**:
- Anthropic Console → Settings → Limits → Monthly spend limit `$5`
- OpenAI Platform → Settings → Limits → Hard limit `$5`

### 3. 정책 자료 배치

`data/policy_docs/`에 9개 자료를 다음 파일명으로 배치:

```
data/policy_docs/
├── 01_GR_가이드라인.pdf
├── 02_GR_기술요소.pdf
├── 03_ZEB_인증기준_고시.pdf
├── 04_녹색건축법.pdf
├── 05_지방세특례제한법.pdf
├── 06_에너지절약설계기준.pdf
├── 07_조달청_단가DB.xlsx
├── 08_조달청_간접공사비_2026.xlsx
└── 09_영유아보육법_시행규칙.pdf
```

### 4. RAG 인덱스 빌드 (1회만)

```bash
python scripts/build_index.py
```

→ `data/chroma_db/`에 벡터 인덱스 생성됨 (약 5분 소요, 약 100원 사용)

### 5. 챗봇 실행

```bash
streamlit run streamlit_app.py
```

→ 브라우저에서 `http://localhost:8501` 자동 열림

---

## 📁 폴더 구조

```
zeb-chatbot/
├── .env.example          # API 키 템플릿 (이걸 .env로 복사해서 사용)
├── .gitignore            # .env, chroma_db, __pycache__ 제외
├── requirements.txt      # 의존 패키지
├── README.md             # 이 문서
├── streamlit_app.py      # 메인 앱 (4개 모드 통합 UI)
│
├── modes/                # 4개 모드별 라우팅 로직
│   ├── mode1_rag.py
│   ├── mode2_roi.py
│   ├── mode3_bim.py
│   └── mode4_intake.py
│
├── core/                 # 공통 핵심 로직
│   ├── llm_client.py     # Claude API 래퍼 + Function Calling
│   ├── roi_calculator.py # 엑셀 산정식 → Python 함수
│   ├── bim_diagnoser.py  # 11개 GR 매핑 로직
│   └── prompts.py        # 시스템 프롬프트 모음
│
├── data/
│   ├── policy_docs/      # 9개 정책 자료 (사용자가 직접 배치)
│   └── chroma_db/        # 벡터 인덱스 (자동 생성)
│
├── scripts/
│   ├── build_index.py    # RAG 인덱싱 (1회 실행)
│   └── test_roi.py       # ROI 함수 단위 테스트
│
└── docs/
    └── api_keys_guide.md # API 키 발급 상세 가이드
```

---

## 💡 자료 처리 방식 — 핵심 설계 결정

| 자료 | 처리 방식 | 이유 |
|---|---|---|
| 01~06, 09 (PDF 7개) | **RAG** | 자연어 질문 응답용 |
| 07 단가DB (xlsx) | **코드 lookup** | 442개 자재 row → pandas로 정확 조회 |
| 08 간접공사비 (xlsx) | **코드 lookup** | 공사규모×기간 매트릭스 함수화 |

> 엑셀을 RAG에 넣지 않는 이유:
> 단가는 "정확한 숫자"가 핵심인데 RAG는 텍스트 유사도 검색이라
> 단가를 부정확하게 가져올 위험. DataFrame 직접 조회가 100% 정확.

---

## 🔬 검증 목표

| 지표 | 목표 |
|---|---|
| RAG 출처 정확도 | 인용 문서·페이지가 실제와 일치 |
| ROI 산정 일치 | 엑셀 시트 8 결과와 ±5% 이내 |
| 응답 속도 | 평균 5초 이내 |
| KEPCO 사례 재현 | Max Cost 2.92억 / 자산화 ROI 16.9% |

---

## ⚠️ 알려진 제약

- 본 챗봇은 졸업설계 데모용입니다. 실제 GR 사업 신청 시에는 그린리모델링 창조센터(1588-8788)의 공식 컨설팅을 받으세요.
- 학생 라이선스 Revit으로 작성된 BIM 파일은 본인 학업/연구용으로만 사용 가능합니다.

---

## 📚 참고 자료 출처

1. 공공건축물 그린리모델링 2.0 지원사업 가이드라인 (국토교통부, 2026.3)
2. GR 11개 필수공사 기술요소 (그린리모델링 창조센터)
3. 제로에너지건축물 인증에 관한 규칙 (기후에너지환경부령 제1호, 2025.10.1)
4. 녹색건축물 조성 지원법 (법률 제20727호, 2025.1.31)
5. 지방세특례제한법 (법률 제21309호, 2025.12.31)
6. 건축물의 에너지절약설계기준 (국토교통부 고시)
7. 시설공통자재 가격정보 (조달청, 2026.4.20)
8. 건축공사 간접공사비 적용기준 (조달청, 2026.1.1)
9. 영유아보육법 시행규칙
