"""
core/llm_client.py — Claude API 래퍼
=====================================
Mode 2/4에서 사용하는 Claude API 통합 인터페이스.

기능:
    - 단순 호출: call_claude(system, user)
    - Function Calling 루프: call_with_tools(system, user, tools, dispatcher)
        → Claude가 tool_use 블록 반환하면 디스패처로 실행 → 결과를 다시 Claude로
        → 최종 자연어 응답까지 자동 반복 (최대 max_iterations)
    - mock/real 백엔드 추상화: 환경변수 CLAUDE_PROVIDER

설계:
    - tenacity 재시도 (rate limit, transient errors)
    - 토큰 사용량 누적 (비용 추적)
    - mock 디스패처: tool_use 블록을 자동 생성해 Function Calling 흐름 검증
"""

import os
import json
import time
from typing import Optional, Callable


# 기본 모델 (Claude Haiku 4.5)
DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
DEFAULT_MAX_TOKENS = 1024
DEFAULT_MAX_ITERATIONS = 5


# ====================================================================
# Real Claude 클라이언트 (anthropic SDK)
# ====================================================================

_CLIENT_CACHE = None


def _get_anthropic_client():
    """anthropic.Anthropic 싱글톤."""
    global _CLIENT_CACHE
    if _CLIENT_CACHE is not None:
        return _CLIENT_CACHE
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic 미설치. pip install anthropic")
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-ant-api03-여기"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY 미설정. .env 확인 또는 CLAUDE_PROVIDER=mock"
        )
    _CLIENT_CACHE = anthropic.Anthropic(api_key=api_key)
    return _CLIENT_CACHE


def _call_real(
    system: str,
    messages: list,
    tools: Optional[list] = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict:
    """단일 API 호출 (재시도 1회)."""
    client = _get_anthropic_client()
    kwargs = dict(
        model=model, max_tokens=max_tokens,
        system=system, messages=messages,
    )
    if tools:
        kwargs["tools"] = tools

    for attempt in range(2):
        try:
            resp = client.messages.create(**kwargs)
            break
        except Exception as e:
            # transient error → 1회 재시도
            if attempt == 0 and _is_transient(e):
                time.sleep(1.0)
                continue
            raise

    return _normalize_response(resp, model)


def _is_transient(e: Exception) -> bool:
    """Rate limit, server error 등 일시적 오류 판단."""
    msg = str(e).lower()
    return any(k in msg for k in ("rate", "timeout", "503", "502", "overloaded"))


def _normalize_response(resp, model: str) -> dict:
    """anthropic SDK Response → 통일된 dict."""
    content_blocks = []
    for block in resp.content:
        if hasattr(block, "text"):
            content_blocks.append({"type": "text", "text": block.text})
        elif hasattr(block, "name"):  # tool_use 블록
            content_blocks.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
    return {
        "stop_reason": resp.stop_reason,
        "content": content_blocks,
        "model": model,
        "usage": {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
        },
    }


# ====================================================================
# Mock Claude (테스트 전용)
# ====================================================================

# 전역 mock 시나리오: 다음에 어떻게 응답할지 큐
_MOCK_SCENARIO = []
_MOCK_DEFAULT_RESPONSE = None


def set_mock_scenario(responses: list) -> None:
    """
    Mock Claude의 응답 시퀀스 설정.
    각 응답은:
        {"type": "text", "text": "..."}
        {"type": "tool_use", "name": "...", "input": {...}}
        {"type": "mixed", "text": "...", "tool_use": {...}}  # 두 블록 다 반환
    """
    global _MOCK_SCENARIO
    _MOCK_SCENARIO = list(responses)


def set_mock_default(response: dict) -> None:
    """시나리오 소진 시 기본 응답."""
    global _MOCK_DEFAULT_RESPONSE
    _MOCK_DEFAULT_RESPONSE = response


def _call_mock(
    system: str,
    messages: list,
    tools: Optional[list] = None,
    model: str = "mock",
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict:
    """시나리오 큐에서 다음 응답 꺼내거나, 기본 응답 사용."""
    global _MOCK_SCENARIO, _MOCK_DEFAULT_RESPONSE
    if _MOCK_SCENARIO:
        spec = _MOCK_SCENARIO.pop(0)
    elif _MOCK_DEFAULT_RESPONSE is not None:
        spec = _MOCK_DEFAULT_RESPONSE
    else:
        spec = {"type": "text", "text": "[mock 기본 응답]"}

    content = []
    if spec.get("type") == "text":
        content.append({"type": "text", "text": spec.get("text", "")})
        stop = "end_turn"
    elif spec.get("type") == "tool_use":
        content.append({
            "type": "tool_use",
            "id": f"mock_tool_{int(time.time()*1000)}",
            "name": spec["name"],
            "input": spec.get("input", {}),
        })
        stop = "tool_use"
    elif spec.get("type") == "mixed":
        if spec.get("text"):
            content.append({"type": "text", "text": spec["text"]})
        tu = spec.get("tool_use", {})
        content.append({
            "type": "tool_use",
            "id": f"mock_tool_{int(time.time()*1000)}",
            "name": tu.get("name", "unknown"),
            "input": tu.get("input", {}),
        })
        stop = "tool_use"
    else:
        content.append({"type": "text", "text": str(spec)})
        stop = "end_turn"

    return {
        "stop_reason": stop,
        "content": content,
        "model": "mock",
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


# ====================================================================
# Public API
# ====================================================================

def get_provider() -> str:
    """환경변수 CLAUDE_PROVIDER ('real' 기본, 'mock' 가능)."""
    return os.getenv("CLAUDE_PROVIDER", "real").lower()


def call_claude(
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict:
    """
    단순 텍스트 호출 (Function Calling 없음).

    Returns:
        {"text": str, "model": str, "usage": {...}}
    """
    messages = [{"role": "user", "content": user}]
    if get_provider() == "mock":
        raw = _call_mock(system, messages, model=model, max_tokens=max_tokens)
    else:
        raw = _call_real(system, messages, model=model, max_tokens=max_tokens)

    text = "\n".join(
        b["text"] for b in raw["content"] if b["type"] == "text"
    )
    return {"text": text, "model": raw["model"], "usage": raw["usage"]}


def call_with_tools(
    system: str,
    user: str,
    tools: list,
    dispatcher: Callable[[str, dict], dict],
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> dict:
    """
    Function Calling 자동 루프.

    Claude가 tool_use를 반환 → dispatcher가 실행 → 결과를 tool_result로 전달
    → 최종 자연어 응답까지 반복 (최대 max_iterations 회).

    Args:
        system:     시스템 프롬프트
        user:       사용자 메시지
        tools:      [{"name": ..., "description": ..., "input_schema": ...}, ...]
        dispatcher: (tool_name, tool_input) → dict (결과)
        max_iterations: tool_use 루프 최대 횟수

    Returns:
        {
          "text":  최종 자연어 응답,
          "tool_calls": [(name, input, result), ...],
          "model": ...,
          "usage": 누적 사용량,
          "iterations": int,
        }
    """
    messages = [{"role": "user", "content": user}]
    tool_calls_log = []
    total_input = 0
    total_output = 0
    model_used = model
    provider = get_provider()

    for iteration in range(max_iterations):
        if provider == "mock":
            raw = _call_mock(system, messages, tools=tools, model=model, max_tokens=max_tokens)
        else:
            raw = _call_real(system, messages, tools=tools, model=model, max_tokens=max_tokens)

        total_input += raw["usage"].get("input_tokens", 0)
        total_output += raw["usage"].get("output_tokens", 0)
        model_used = raw["model"]

        # tool_use가 있으면 디스패처 호출 → 결과 message 추가
        tool_uses = [b for b in raw["content"] if b["type"] == "tool_use"]

        # assistant 응답을 메시지 히스토리에 추가 (Anthropic SDK 형식 유지)
        assistant_content = []
        for b in raw["content"]:
            if b["type"] == "text":
                assistant_content.append({"type": "text", "text": b["text"]})
            elif b["type"] == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": b["id"],
                    "name": b["name"],
                    "input": b["input"],
                })
        if assistant_content:
            messages.append({"role": "assistant", "content": assistant_content})

        if not tool_uses or raw["stop_reason"] == "end_turn":
            # 종료
            final_text = "\n".join(
                b["text"] for b in raw["content"] if b["type"] == "text"
            )
            return {
                "text": final_text,
                "tool_calls": tool_calls_log,
                "model": model_used,
                "usage": {"input_tokens": total_input, "output_tokens": total_output},
                "iterations": iteration + 1,
            }

        # tool_use 처리 → tool_result 메시지 만들기
        tool_results = []
        for tu in tool_uses:
            try:
                result = dispatcher(tu["name"], tu["input"])
                result_str = json.dumps(result, ensure_ascii=False, default=str)
                is_error = False
            except Exception as e:
                result_str = f"도구 실행 실패: {type(e).__name__}: {e}"
                is_error = True
            tool_calls_log.append({
                "name": tu["name"],
                "input": tu["input"],
                "result": result_str if is_error else result,
                "is_error": is_error,
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": result_str,
                "is_error": is_error,
            })

        messages.append({"role": "user", "content": tool_results})

    # max_iterations 초과 — 마지막 응답 텍스트라도 반환
    return {
        "text": "[알림] 최대 도구 호출 횟수 초과. 부분 결과만 반환합니다.",
        "tool_calls": tool_calls_log,
        "model": model_used,
        "usage": {"input_tokens": total_input, "output_tokens": total_output},
        "iterations": max_iterations,
    }
