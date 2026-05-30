"""
scripts/test_mode2.py — Mode 2 (ROI Function Calling) 단위 테스트
=================================================================
core.llm_client + core.roi_tools + modes.mode2_roi 검증.

실행:
    python scripts/test_mode2.py

환경변수:
    CLAUDE_PROVIDER=mock  (강제 — 실제 API 호출 없이 검증)
"""

import os
import sys
from pathlib import Path

os.environ["CLAUDE_PROVIDER"] = "mock"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_tool_schema():
    """Function Calling 도구 명세 유효성."""
    print("\n" + "=" * 70)
    print("도구 명세 검증")
    print("=" * 70)
    from core.roi_tools import TOOLS, CALCULATE_ZEB_ROI_TOOL

    assert len(TOOLS) == 1, f"단일 도구 노출: {len(TOOLS)}"
    print(f"  [PASS] 도구 1개만 노출 (calculate_zeb_roi)")

    schema = CALCULATE_ZEB_ROI_TOOL["input_schema"]
    assert "total_area_m2" in schema["required"]
    assert schema["properties"]["total_area_m2"]["type"] == "number"
    print(f"  [PASS] total_area_m2 필수 + number 타입")

    # 모든 옵션 필드에 default 있는지
    for name, prop in schema["properties"].items():
        if name in schema["required"]:
            continue
        assert "default" in prop, f"옵션 필드 {name} default 누락"
    print(f"  [PASS] 옵션 필드 {len(schema['properties'])-1}개 모두 default 보유")


def test_dispatcher_kepco_case():
    """KEPCO 도담어린이집 케이스 디스패치 — 검증 목표값과 일치 확인."""
    print("\n" + "=" * 70)
    print("디스패처: 도담어린이집 케이스")
    print("=" * 70)
    from core.roi_tools import dispatch_tool

    result = dispatch_tool("calculate_zeb_roi", {
        "total_area_m2": 1251,
        "wall_no_insulation_m2": 887.5,
        "window_area_m2": 100,
        "door_area_m2": 28.85,
        "zeb_target_grade": 5,
        "is_seoul_or_public": True,
        "extension_area_m2": 200,
    })

    assert "error" not in result, f"error: {result.get('error')}"
    assert result["Max_Cost_원"] > 0
    assert result["자산화_ROI_pct"] > 0

    # 메모리 검증 목표: 자산화 ROI 16.9%
    roi = result["자산화_ROI_pct"]
    assert 16.5 <= roi <= 17.5, f"자산화 ROI가 검증 목표(16.9%) 범위 벗어남: {roi}"
    print(f"  [PASS] 자산화 ROI {roi}% (검증 목표 16.9% 일치)")

    # 보조율 50% (서울/공공)
    assert result["보조금"]["보조율"] == 0.50
    print(f"  [PASS] 보조율 50% (서울/중앙/공공)")

    # ZEB 5등급 취득세 감면 15%
    assert result["취득세_감면"]["감면율"] == 0.15
    print(f"  [PASS] 취득세 감면율 15% (ZEB 5등급)")


def test_dispatcher_errors():
    """디스패처 에러 케이스."""
    print("\n" + "=" * 70)
    print("디스패처 에러 처리")
    print("=" * 70)
    from core.roi_tools import dispatch_tool

    # 필수값 누락
    r = dispatch_tool("calculate_zeb_roi", {"wall_no_insulation_m2": 100})
    assert "error" in r
    print(f"  [PASS] 필수값 누락 → error")

    # 음수 면적
    r = dispatch_tool("calculate_zeb_roi", {"total_area_m2": -100})
    assert "error" in r
    print(f"  [PASS] 음수 면적 → error")

    # 알 수 없는 도구
    r = dispatch_tool("unknown_tool", {})
    assert "error" in r
    print(f"  [PASS] 알 수 없는 도구 → error")


def test_grade_difference():
    """ZEB 등급별 인센티브 차등 확인."""
    print("\n" + "=" * 70)
    print("ZEB 등급별 인센티브 비교")
    print("=" * 70)
    from core.roi_tools import dispatch_tool

    base = {
        "total_area_m2": 1000,
        "wall_no_insulation_m2": 500,
        "extension_area_m2": 200,
        "is_seoul_or_public": True,
    }

    # 1등급
    r1 = dispatch_tool("calculate_zeb_roi", {**base, "zeb_target_grade": 1})
    # 5등급
    r5 = dispatch_tool("calculate_zeb_roi", {**base, "zeb_target_grade": 5})

    # 1등급이 5등급보다 용적률 보너스율 높음
    assert r1["용적률_완화"]["보너스율"] > r5["용적률_완화"]["보너스율"]
    print(f"  [PASS] 1등급 용적률 보너스 {r1['용적률_완화']['보너스율']*100:.0f}% "
          f"> 5등급 {r5['용적률_완화']['보너스율']*100:.0f}%")

    # 1등급이 5등급보다 취득세 감면율 높음
    assert r1["취득세_감면"]["감면율"] > r5["취득세_감면"]["감면율"]
    print(f"  [PASS] 1등급 취득세 감면 {r1['취득세_감면']['감면율']*100:.0f}% "
          f"> 5등급 {r5['취득세_감면']['감면율']*100:.0f}%")


def test_call_with_tools_loop():
    """Function Calling 자동 루프 (tool_use → tool_result → text)."""
    print("\n" + "=" * 70)
    print("Function Calling 자동 루프")
    print("=" * 70)
    from core.llm_client import call_with_tools, set_mock_scenario

    def echo_dispatcher(name, inp):
        return {"echoed": inp, "tool": name}

    set_mock_scenario([
        {"type": "tool_use", "name": "echo_tool", "input": {"x": 42}},
        {"type": "text", "text": "결과: 42"},
    ])

    result = call_with_tools(
        system="test",
        user="x=42",
        tools=[{"name": "echo_tool", "description": "echo",
                "input_schema": {"type": "object", "properties": {}}}],
        dispatcher=echo_dispatcher,
    )

    assert result["iterations"] == 2
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["result"]["echoed"]["x"] == 42
    assert result["text"] == "결과: 42"
    print(f"  [PASS] 2회 iteration, 1회 tool_use → 자연어 종료")


def test_max_iterations_safety():
    """무한 루프 방지: max_iterations 도달 시 안전 종료."""
    print("\n" + "=" * 70)
    print("max_iterations 안전장치")
    print("=" * 70)
    from core.llm_client import call_with_tools, set_mock_scenario, set_mock_default

    # 무한히 tool_use만 발생하도록
    set_mock_default({"type": "tool_use", "name": "inf_tool", "input": {}})
    set_mock_scenario([])

    def always_ok(name, inp):
        return {"ok": True}

    result = call_with_tools(
        system="test", user="loop", tools=[{
            "name": "inf_tool", "description": "infinite",
            "input_schema": {"type": "object", "properties": {}},
        }],
        dispatcher=always_ok,
        max_iterations=3,
    )

    assert result["iterations"] == 3, f"max에서 종료: {result['iterations']}"
    print(f"  [PASS] max_iterations=3 도달 시 안전 종료")

    # 기본 응답 리셋
    set_mock_default({"type": "text", "text": "done"})


def test_mode2_integration():
    """mode2_roi.run_roi_simulation 통합."""
    print("\n" + "=" * 70)
    print("mode2_roi 통합")
    print("=" * 70)
    from core.llm_client import set_mock_scenario
    from modes.mode2_roi import run_roi_simulation

    set_mock_scenario([
        {
            "type": "tool_use",
            "name": "calculate_zeb_roi",
            "input": {
                "total_area_m2": 1000,
                "wall_no_insulation_m2": 400,
                "zeb_target_grade": 3,
            },
        },
        {"type": "text", "text": "결과 요약: Max Cost X억, 자부담 Y억."},
    ])

    result = run_roi_simulation("연면적 1000㎡, 외벽 400㎡ 보강, ZEB 3등급")
    assert "answer" in result
    assert result["answer"].startswith("결과 요약")
    assert len(result["tool_calls"]) == 1
    tc = result["tool_calls"][0]
    assert tc["name"] == "calculate_zeb_roi"
    assert tc["result"]["보조금"]["보조율"] == 0.50  # 기본 서울/공공
    print(f"  [PASS] mode2 통합: answer + tool_calls + 결과 정상")


def test_dispatcher_failed_returns_error_in_result():
    """디스패처 예외가 tool_result에 에러로 반영되는지."""
    print("\n" + "=" * 70)
    print("디스패처 예외 → tool_result 에러 전달")
    print("=" * 70)
    from core.llm_client import call_with_tools, set_mock_scenario

    def broken_dispatcher(name, inp):
        raise ValueError("의도된 실패")

    set_mock_scenario([
        {"type": "tool_use", "name": "broken_tool", "input": {}},
        {"type": "text", "text": "에러 발생, 죄송합니다."},
    ])

    result = call_with_tools(
        system="t", user="u",
        tools=[{"name": "broken_tool", "description": "broken",
                "input_schema": {"type": "object", "properties": {}}}],
        dispatcher=broken_dispatcher,
    )

    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["is_error"] is True
    assert "ValueError" in result["tool_calls"][0]["result"]
    print(f"  [PASS] 디스패처 예외가 tool_result에 is_error=True 로 전달")


if __name__ == "__main__":
    try:
        test_tool_schema()
        test_dispatcher_kepco_case()
        test_dispatcher_errors()
        test_grade_difference()
        test_call_with_tools_loop()
        test_max_iterations_safety()
        test_mode2_integration()
        test_dispatcher_failed_returns_error_in_result()
        print("\n" + "=" * 70)
        print("Mode 2 테스트 전체 통과 ✅")
        print("=" * 70)
    except AssertionError as e:
        print(f"\n❌ 검증 실패: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 예외: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
