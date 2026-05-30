"""
core/error_messages.py — 친절한 에러 메시지 변환
=================================================
영문/기술적 에러 메시지를 한국어 사용자 친화적 메시지로 변환.

용법:
    from core.error_messages import friendly_error
    try:
        ...
    except Exception as e:
        st.error(friendly_error(e))
"""

import re


def friendly_error(error) -> str:
    """
    예외 또는 에러 문자열을 사용자 친화적 한국어 메시지로 변환.

    Returns:
        markdown 포맷 한국어 메시지 (이모지 + 원인 + 해결법)
    """
    if isinstance(error, Exception):
        msg = str(error)
        exc_name = type(error).__name__
    else:
        msg = str(error)
        exc_name = ""

    low = msg.lower()

    # ────────────────────────────────────────────────────
    # Anthropic API 에러
    # ────────────────────────────────────────────────────
    if "credit balance is too low" in low or "insufficient_quota" in low:
        return (
            "**💳 크레딧 잔액 부족**\n\n"
            "Anthropic API 크레딧이 부족합니다. 챗봇이 Claude를 호출하려면 결제된 크레딧이 필요합니다.\n\n"
            "**해결**:\n"
            "1. [Anthropic Console](https://console.anthropic.com) 접속\n"
            "2. **자금 추가** 또는 **Plans & Billing** 클릭\n"
            "3. 청구지 주소 + 카드 등록 후 $5 결제 (졸업설계 데모용으로 충분)\n\n"
            "또는 임시로 **Mock 모드**로 동작 확인할 수 있습니다 (`set CLAUDE_PROVIDER=mock`)."
        )

    if "anthropic_api_key" in low or (
        "api key" in low and ("missing" in low or "invalid" in low or "not set" in low)
    ):
        return (
            "**🔑 API 키 미설정 또는 잘못됨**\n\n"
            "Anthropic API 키가 `.env` 파일에 등록되지 않았거나 잘못된 값입니다.\n\n"
            "**해결**:\n"
            "1. [Anthropic Console](https://console.anthropic.com) → **API Keys** 에서 키 생성\n"
            "2. 프로젝트 루트에 `.env` 파일 만들기: `copy .env.example .env`\n"
            "3. `.env` 파일에 `ANTHROPIC_API_KEY=sk-ant-api03-...` 등록\n"
            "4. 챗봇 재시작"
        )

    if "rate_limit" in low or "429" in msg or "too many requests" in low:
        return (
            "**⏳ API 호출 한도 초과**\n\n"
            "잠깐 동안 너무 많이 호출했습니다. 10~30초 후 다시 시도해주세요.\n\n"
            "**원인**: Anthropic Free 등급은 분당 호출 횟수 제한이 있습니다."
        )

    if "401" in msg or "unauthorized" in low or "authentication" in low:
        return (
            "**🔒 인증 실패**\n\n"
            "API 키가 유효하지 않거나 만료되었습니다.\n\n"
            "**해결**:\n"
            "1. [Anthropic Console](https://console.anthropic.com) → API Keys 확인\n"
            "2. 새 키를 발급받고 `.env` 파일 업데이트"
        )

    if "overloaded" in low or "503" in msg or "service unavailable" in low:
        return (
            "**🌐 Anthropic 서버 일시적 과부하**\n\n"
            "Anthropic 서버가 잠시 응답하지 못하고 있습니다. 1~2분 후 다시 시도해주세요.\n\n"
            "(이건 사용자 컴퓨터나 코드 문제가 아닙니다)"
        )

    if "timeout" in low or "connection" in low and "error" in low:
        return (
            "**📡 네트워크 연결 문제**\n\n"
            "API 서버 응답이 너무 늦거나 연결되지 않습니다.\n\n"
            "**확인**:\n"
            "- 인터넷 연결 상태\n"
            "- 방화벽/VPN이 차단하고 있지 않은지\n"
            "- 잠시 후 다시 시도"
        )

    # ────────────────────────────────────────────────────
    # 파일/JSON 관련
    # ────────────────────────────────────────────────────
    if (
        "jsondecodeerror" in exc_name.lower()
        or "expecting value" in low or "expecting property name" in low
        or ("json" in low and ("decode" in low or "parse" in low))
    ):
        return (
            "**📄 JSON 파일 파싱 실패**\n\n"
            "업로드한 파일이 올바른 JSON 형식이 아닙니다.\n\n"
            "**확인**:\n"
            "- 파일이 정말 JSON 형식인지 (.json 확장자)\n"
            "- 파일 내용에 오타나 누락된 괄호 없는지\n"
            "- 샘플 형식은 `data/sample_bim/doam_archi_sample.json` 참고"
        )

    if "filenotfounderror" in low or "no such file" in low or "파일을 찾을 수 없" in msg:
        # 파일명 추출 시도
        m = re.search(r"['\"]([^'\"]+)['\"]", msg)
        filename = m.group(1) if m else "파일"
        return (
            f"**📁 파일을 찾을 수 없음**\n\n"
            f"`{filename}` 파일이 존재하지 않습니다.\n\n"
            f"**확인**:\n"
            f"- 경로가 정확한지\n"
            f"- 파일이 실제로 그 위치에 있는지\n"
            f"- 단가DB(`07_조달청_단가DB.xlsx`, `08_조달청_간접공사비_2026.xlsx`)는 "
            f"`data/policy_docs/` 폴더에 있어야 합니다"
        )

    # ────────────────────────────────────────────────────
    # ChromaDB / RAG 관련
    # ────────────────────────────────────────────────────
    if "chromadb" in low or "chroma" in low and "collection" in low:
        return (
            "**🗄 RAG 인덱스 문제**\n\n"
            "ChromaDB 벡터 인덱스에 접근할 수 없습니다.\n\n"
            "**해결**:\n"
            "1. cmd 창에서 `python scripts/build_index.py --provider local` 실행\n"
            "2. 인덱싱이 1~2분 소요됨\n"
            "3. 완료되면 챗봇 재시작"
        )

    if "permissionerror" in low and ("winerror 32" in low or "사용 중" in msg):
        return (
            "**🔒 윈도우 파일 잠금**\n\n"
            "ChromaDB가 SQLite 파일을 잠근 채로 두어 발생하는 윈도우 환경 문제입니다.\n\n"
            "**해결**:\n"
            "- 챗봇 완전 종료 후 다시 띄우기\n"
            "- 그래도 안 되면 컴퓨터 재시작"
        )

    # ────────────────────────────────────────────────────
    # KeyError / 스키마 누락
    # ────────────────────────────────────────────────────
    if "keyerror" in exc_name.lower():
        m = re.search(r"'([^']+)'", msg)
        key = m.group(1) if m else "필수 키"
        return (
            f"**🗝 데이터 스키마 누락**\n\n"
            f"필수 필드 `{key}` 가 입력 데이터에 없습니다.\n\n"
            f"**해결**:\n"
            f"- BIM JSON 파일에 해당 필드가 있는지 확인\n"
            f"- 샘플 스키마: `data/sample_bim/doam_archi_sample.json`"
        )

    # ────────────────────────────────────────────────────
    # 모듈 없음
    # ────────────────────────────────────────────────────
    if "modulenotfounderror" in low or "no module named" in low:
        m = re.search(r"named ['\"]?([^'\"]+)['\"]?", msg)
        mod = m.group(1) if m else "모듈"
        return (
            f"**📦 패키지 미설치**\n\n"
            f"`{mod}` 패키지가 설치되지 않았습니다.\n\n"
            f"**해결**: cmd 창에서:\n"
            f"```\n"
            f"pip install {mod}\n"
            f"```\n"
            f"또는 전체 의존성 설치: `pip install -r requirements.txt`"
        )

    # ────────────────────────────────────────────────────
    # 기본 (위 패턴에 안 걸린 경우)
    # ────────────────────────────────────────────────────
    return (
        f"**❌ 처리 중 오류 발생**\n\n"
        f"```\n{exc_name}: {msg[:300]}\n```\n\n"
        f"문제가 계속되면:\n"
        f"- 챗봇을 한 번 재시작해보세요\n"
        f"- 위 메시지를 캡처해서 GitHub Issues에 등록해주세요"
    )
