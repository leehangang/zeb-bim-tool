# API 키 발급 가이드

> 챗봇 실행에 필요한 2개 API 키 발급 절차

## 필요한 키

| 서비스 | 용도 | 권장 충전 |
|---|---|---|
| Anthropic (Claude) | 자연어 대화 응답 | $5 (약 7,000원) |
| OpenAI | 임베딩 (RAG 인덱싱만) | $5 (약 7,000원) |

**총 약 14,000원**으로 졸업설계 + 발표 시연까지 충분합니다.

---

## 1. Anthropic API 키 (Claude Haiku 4.5)

### 발급 절차

1. **회원가입**: https://console.anthropic.com 접속 → "Sign Up"
2. **결제수단 등록**: 좌측 메뉴 → **Plans & Billing** → 신용카드 등록
3. **크레딧 충전**: **Buy Credits** → **$5** 충전
4. **API 키 발급**: 좌측 메뉴 → **Settings → API Keys** → **Create Key**
   - 이름: `zeb-chatbot`
   - 권한: `default`
5. **키 복사**: `sk-ant-api03-...` 형식으로 시작
   - ⚠️ 이 화면에서만 키 전체가 보입니다. **반드시 복사해서 .env에 저장**.

### 비용 안전장치 (필수)

- **Settings → Limits → Monthly spend limit**: `$5` 설정
- 초과 시 자동 차단됨

---

## 2. OpenAI API 키 (임베딩 전용)

### 발급 절차

1. **회원가입**: https://platform.openai.com 접속 → "Sign up"
2. **결제수단 등록**: 우상단 프로필 → **Billing** → **Add payment method**
3. **크레딧 충전**: **Add to credit balance** → **$5** 충전
4. **API 키 발급**: 좌측 메뉴 → **API keys** → **Create new secret key**
   - 이름: `zeb-chatbot-embedding`
   - 권한: `All`
5. **키 복사**: `sk-proj-...` 형식으로 시작

### 비용 안전장치 (필수)

- **Settings → Limits → Hard limit**: `$5` 설정
- Usage limit: `$3` 설정 권장 (경고용)

---

## 3. .env 파일에 등록

```bash
# 프로젝트 루트에서
cp .env.example .env

# .env 열어서 두 키 모두 입력
```

`.env` 파일:
```
ANTHROPIC_API_KEY=sk-ant-api03-실제_키_여기에
OPENAI_API_KEY=sk-proj-실제_키_여기에
```

---

## 4. 키 작동 확인

```bash
python -c "
from dotenv import load_dotenv
load_dotenv()
import os
print('Anthropic:', '✅' if os.getenv('ANTHROPIC_API_KEY', '').startswith('sk-ant') else '❌')
print('OpenAI:', '✅' if os.getenv('OPENAI_API_KEY', '').startswith('sk-') else '❌')
"
```

둘 다 ✅면 준비 완료.

---

## 비용 추적

### Anthropic Console
- https://console.anthropic.com/settings/usage
- Claude Haiku 4.5 가격: 입력 $1/1M tokens, 출력 $5/1M tokens
- 챗봇 대화 1턴 약 3,000 토큰 → 약 5~10원/턴
- 개발+발표까지 약 200턴 → 약 1,000~2,000원

### OpenAI Console
- https://platform.openai.com/usage
- text-embedding-3-small: $0.02/1M tokens
- 인덱싱 1회 (PDF 7개) 약 30~50만 토큰 → 약 100~150원
- **재인덱싱은 자료 추가/수정 시에만 필요**

---

## 발표 시 보안 주의사항

- 발표 PC에서 코드 보여줄 때 `.env` 파일 절대 열지 말 것
- GitHub 푸시 전 `.gitignore`에 `.env` 등록 확인
- 키 노출 사고 발생 시:
  1. Anthropic/OpenAI 콘솔에서 즉시 키 폐기
  2. 새 키 발급 후 `.env` 갱신
