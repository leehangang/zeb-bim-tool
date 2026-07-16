# EnergyPlus 실행 서비스 — 배포 방법

Streamlit 앱에서 EnergyPlus를 돌리기 위한 별도 서비스입니다.

## 왜 앱 안에서 못 돌리나

Streamlit Community Cloud 무료 티어의 실제 제약 (2026-07 조사):

| 경로 | 결과 |
|---|---|
| `packages.txt`(apt) | ❌ Debian 저장소에 `energyplus` 패키지 없음 (검색 0건) |
| 리포에 바이너리 커밋 | ❌ E+ Linux tar.gz 240MB > GitHub 100MiB 한도 |
| 런타임 `apt-get` | ❌ sudo 없음 |
| 런타임 다운로드 + chmod | ⚠️ 이론상 가능하나 동작 선례 못 찾음 |
| **CPU** | ⚠️ **하한 0.078코어** — 설치를 뚫어도 연간 해석이 실용 속도 안 남 |
| 12h 무트래픽 | ⚠️ 슬립 → 깨어날 때마다 재설치 |

**그런데 이 장벽들은 Docker 경로에선 전부 무효입니다.**
NREL 공식 이미지 `nrel/energyplus:25.1.0`은 **압축 106.5MB**이고 `FROM` 한 줄이면 끝입니다.

## ❌ Hugging Face Spaces — 막혔습니다 (2026-07-16 계정에서 확인)

1순위였으나 https://huggingface.co/new-space 화면에서 **Docker·Gradio 둘 다 `🔒 Paid` 배지**가
붙어 있고 **Static만 무료로 선택**됩니다:

> Gradio and Docker Spaces require a paid plan.
> Static Spaces stay free for everyone. To create a Space that runs on compute, subscribe to PRO.

2026-07-09 포럼 보고([링크](https://discuss.huggingface.co/t/new-free-accounts-cannot-create-cpu-basic-gradio-spaces-only-zerogpu-available/177629),
미해결)가 **실제로 재현된 것**입니다. HF 공식 문서는 여전히 "CPU Basic FREE"라 적고 있어
문서와 실제가 어긋나 있습니다. Static Space는 정적 파일만 서빙하므로 E+를 못 돌립니다.

→ **`Dockerfile`은 남겨둡니다.** HF Docker가 무료로 풀리면 그대로 쓸 수 있습니다.

## 배포 (Modal) — 현재 경로

`modal_app.py`가 **같은 NREL 이미지 · 같은 `app.py`** 를 Modal에 올립니다.
**유휴 시 과금 0** (요청이 없으면 컨테이너가 0으로 내려감), 슬립로 인한 재설치 없음.

⚠️ **무료 크레딧 정정 (2026-07-17 대시보드에서 확인)**
"$30/월 무료 + 카드 불필요"라고 적었던 건 **틀렸습니다.** 실제 배너:

> You have **$1 of $30**/mo in free credits. Add a payment method to unlock the rest.

즉 **카드 미등록 상태의 실사용 한도는 $1**이고, $30은 카드를 넣어야 열립니다.
$1이 몇 번의 해석에 해당하는지는 **아직 실측 못 했습니다** — 이미지 빌드 자체도
컴퓨트를 씁니다. 대시보드 Credits 카운터로 확인하면서 씁니다.
(Streamlit·HF와 달리 Modal은 **초 단위 종량제**라 "무료 티어"라는 말 자체가 성립하지 않습니다.)

### ✅ 배포됨 (2026-07-17)

```
https://leehangang--zeb-energyplus-web.modal.run
```
`modal deploy` 34초. `/health` 응답 (HTTP 200, 4.1초 — 콜드스타트 포함):
```json
{"ok":true,"energyplus":"EnergyPlus, Version 25.1.0-68a4a7c774","weather_files":[]}
```
→ **EnergyPlus 바이너리가 실제로 실행된다** (존재 확인이 아니라 `--version` 실행 결과).

기상파일은 `weather/`에 추풍령(471350) TMYx 2011-2025를 넣어 함께 배포한다.
NREL 이미지에는 .epw가 0개다(`/usr/local`·`/opt`·`/root` 전수 조사 0건).

### ✅ 우리 IDF의 첫 EnergyPlus 실행 — 완주 (2026-07-17)

`data/sample_bim/doam_sample.gbxml` → 파서 → `write_idf` → Modal → E+ 8,760시간 연간 해석.

**1차 시도는 실패했다.** 그 전까지 "파싱은 통과"만 확인한 상태였고, 실제로 넣자마자
IDF 생성기의 진짜 버그 3개 + 에러 파서 버그 1개가 나왔다:

| 증상 | 원인 |
|---|---|
| Severe: `zone_inside_convection_algorithm - "autocalculate"` | Zone 11번(enum)에 autocalculate. 수치 필드에만 쓰는 값이다 |
| Severe: `mean_radiant_temperature_calculation_type - "autocalculate"` | People 13번(enum)에 같은 실수 |
| People의 Activity Level Schedule 빈칸 | 필수 필드다 → `SCH_ACT`(120W/인) 추가 |
| `Version: in IDF="26.1" not the same as expected="25.1"` | 생성기 기본값과 서비스 이미지가 어긋남 → `EP_VERSION` 상수로 묶음 |
| **fatal 0건으로 보고됐는데 실제론 fatal로 죽음** | `_parse_err` 정규식이 `**  Fatal  **`(공백 2)를 못 잡음 |

마지막 것이 제일 나빴다 — **프로그램이 죽었는데 화면엔 fatal 0건**으로 보인다.

### ⚠️ "성공"이 곧 "맞는 값"은 아니다

2차 시도는 `ok: True`로 완주했지만 `Electricity:Facility = 0.0 kWh`였다.
샘플의 바닥면이 U-value 미상이라 IDF에서 빠졌고 → **존 면적 0 → 면적기반 부하
(조명·기기·재실)가 전부 0**. 냉난방만 외피 관류로 나와 겉보기엔 멀쩡했다.
→ `write_idf`가 바닥 없는 존을 경고로 올린다. 해석 성공이 검증을 대신하지 않는다.

### 남은 것
- **실제 도담 Revit → gbXML은 아직 없다.** 위 실행은 우리가 만든 픽스처 기준이다.
- 라이브 사이트(share.streamlit.io)는 로컬 `.streamlit/secrets.toml`을 못 본다 →
  **Settings > Secrets에 `EPLUS_SERVICE_URL`을 직접 넣어야** 실행 버튼이 뜬다.

```bash
pip install modal
modal setup                                   # 브라우저 인증 (1회)
modal deploy energyplus_service/modal_app.py  # 첫 빌드 3~5분
```

배포되면 URL이 출력됩니다:
```
https://<사용자>--zeb-energyplus-web.modal.run
```

확인:
```bash
curl https://<사용자>--zeb-energyplus-web.modal.run/health
# → {"ok": true, "energyplus": "EnergyPlus, Version 25.1.0...", "weather_files": [...]}
```

Streamlit 앱에 URL 등록 — `.streamlit/secrets.toml`(로컬) 또는 Streamlit Cloud Secrets:
```toml
EPLUS_SERVICE_URL = "https://<사용자>--zeb-energyplus-web.modal.run"
```
등록되는 즉시 BIM 진단 화면의 "🔬 아직 못 돌립니다" 안내가 **실행 버튼으로 바뀝니다**
(`core/eplus_client.py` → `modes/mode3_bim.py`).

⚠️ `modal_app.py`는 **아직 배포된 적이 없습니다.** 첫 `modal deploy`에서 깨질 수 있고,
그때는 출력이 원인을 알려줍니다.

### 그 밖의 대안 (같은 Dockerfile)
- **Google Cloud Run** — 월 180,000 vCPU-초 무료 (결제계정 등록 필요)
- **Render** — 750 인스턴스-시간/월 무료 (콜드스타트 30~60초)

## 기상파일 (.epw)

`weather/` 디렉토리에 넣으면 서버 기본값이 됩니다. 요청에 `epw`를 함께 올리면 그게 우선입니다.

도담(김천) 최근접 관측소는 **추풍령(471350)** 입니다:
```
https://climate.onebuilding.org/WMO_Region_2_Asia/KOR_South_Korea/
  → KOR_HB_Chupungnyeong.471350_TMYx.2011-2025.zip
```
⚠️ 김천 자체 관측소는 없습니다. 추풍령은 인접 관측소이며, **인증용이 아니라 추정용**입니다.

> **참고**: ZEB 인증에 쓰는 ECO2는 **자체 기상데이터**(인증 제도 운영규정 [별표6], 66지역
> 월평균)를 내장하며 사용자가 못 바꿉니다. .epw와는 **별개 체계**입니다.

## API

```
GET  /health                      → E+ 실행 가능 여부 + 내장 기상파일 목록
POST /run  (multipart)
     idf=@model.idf               → 필수
     epw=@weather.epw             → 선택 (없으면 서버 기본값)
     weather_name=...             → 선택 (서버 내장 파일명 지정)
  ← {ok, returncode, weather, errors:{fatal,severe,warning_count,raw_tail},
     meters:{<이름>:{monthly,annual_J,annual_kWh}}, stdout_tail}
```

`errors.fatal`/`severe`를 그대로 돌려주는 게 중요합니다 — E+ 실패는 대부분
`eplusout.err` 몇 줄로 원인이 특정되는데, 그걸 감추면 사용자는 "실패"만 보고 끝납니다.

## 법적 의미

**EnergyPlus는 그린리모델링 창조센터 지정 시뮬레이션 프로그램입니다** —
「2026년 민간건축물 그린리모델링 이자지원사업 공고」(국토부공고 제2026-876호) p.3 각주:

> 지정 에너지 시뮬레이션 : ECO2, ECO2-OD, GR-E, Energy Studio, **EnergyPlus**, IES-VE

→ 개선 전·후를 각각 돌려 비교하면 **성능개선비율이 인정 대상**이 됩니다.

⚠️ **ZEB 인증은 다릅니다.** ECO2(ISO 13790 + DIN V 18599 **월별법**)를 쓰며,
EnergyPlus(시간별 상세 해석) 결과로는 ZEB 인증 숫자가 나오지 않습니다.

⚠️ 지정 목록은 **고시가 아니라 센터 연례 공고**로 정해집니다 → 매년 확인하세요.
(「그린리모델링 지원사업 운영 등에 관한 고시」 전문에 프로그램명 0건)
