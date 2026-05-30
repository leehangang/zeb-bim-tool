"""
scripts/test_mode4.py — Mode 4 (사업 신청 인테이크) 단위 테스트
=================================================================
core.intake_schema + core.intake_tools + modes.mode4_intake 검증.

실행:
    python scripts/test_mode4.py
"""

import os
import sys
from pathlib import Path

os.environ["CLAUDE_PROVIDER"] = "mock"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_schema_basics():
    """스키마 기본 구조."""
    print("\n" + "=" * 70)
    print("스키마 기본 구조")
    print("=" * 70)
    from core.intake_schema import (
        FIELDS, SECTIONS, fields_by_section,
        all_required_fields, all_optional_fields,
    )

    assert len(FIELDS) >= 15, f"최소 15개 필드 필요: {len(FIELDS)}"
    assert len(SECTIONS) == 4
    print(f"  [PASS] 필드 {len(FIELDS)}개, 섹션 {len(SECTIONS)}개")

    # 모든 필드가 section에 속해야 함
    all_fields_in_sections = []
    for sec in SECTIONS:
        all_fields_in_sections.extend(fields_by_section(sec))
    assert set(all_fields_in_sections) == set(FIELDS.keys()), \
        "모든 필드가 섹션에 속해야 함"
    print(f"  [PASS] 모든 필드가 섹션에 속함")

    # 필수 필드 분리
    req = all_required_fields()
    opt = all_optional_fields()
    assert len(req) + len(opt) == len(FIELDS)
    print(f"  [PASS] 필수 {len(req)}, 선택 {len(opt)}")


def test_field_validation():
    """필드 검증 룰."""
    print("\n" + "=" * 70)
    print("필드 검증 룰")
    print("=" * 70)
    from core.intake_schema import validate_field

    # 정상 케이스
    cases_ok = [
        ("organization_name", "김천시청"),
        ("total_area_m2", 1251),
        ("target_zeb_grade", 5),
        ("completion_year", 2014),
        ("contact_phone", "054-420-6000"),
        ("contact_email", "ok@example.com"),
        ("building_usage", "어린이집"),
        ("applied_elements", ["고성능창호", "외벽단열보강"]),
        ("directly_owned", True),
    ]
    for f, v in cases_ok:
        ok, msg = validate_field(f, v)
        assert ok, f"{f}={v!r} 검증 실패: {msg}"
    print(f"  [PASS] 정상값 {len(cases_ok)}개 모두 통과")

    # 거부 케이스
    cases_bad = [
        ("organization_name", ""),
        ("total_area_m2", -1),
        ("target_zeb_grade", 7),
        ("completion_year", 1850),
        ("contact_phone", "12"),
        ("contact_email", "invalid"),
        ("building_usage", "유치원"),
        ("applied_elements", "단일문자열"),
    ]
    for f, v in cases_bad:
        ok, msg = validate_field(f, v)
        assert not ok, f"{f}={v!r}가 통과되면 안 됨"
        assert msg, "에러 메시지 필요"
    print(f"  [PASS] 거부값 {len(cases_bad)}개 모두 거부")


def test_progress_calculation():
    """진행률 계산."""
    print("\n" + "=" * 70)
    print("진행률 계산")
    print("=" * 70)
    from core.intake_schema import (
        empty_application, calculate_progress, all_required_fields, FIELDS,
    )

    # 빈 신청서
    p = calculate_progress(empty_application())
    assert p["required_filled"] == 0
    assert p["overall_pct"] == 0
    assert p["is_ready_for_draft"] is False
    print(f"  [PASS] 빈 신청서: 0%")

    # 모든 필수 채움
    full = {k: FIELDS[k].get("example", "샘플")
            for k in all_required_fields()}
    p = calculate_progress(full)
    assert p["required_pct"] == 100.0
    assert p["is_ready_for_draft"] is True
    print(f"  [PASS] 모든 필수 채움: draft 가능")

    # 부분 채움
    partial = {"organization_name": "테스트", "total_area_m2": 1000}
    p = calculate_progress(partial)
    assert 0 < p["required_pct"] < 100
    assert p["is_ready_for_draft"] is False
    assert "신청기관명" not in p["missing_required_labels"]
    print(f"  [PASS] 부분 채움: {p['required_pct']}%")


def test_tool_schema():
    """도구 스키마 자동 생성."""
    print("\n" + "=" * 70)
    print("도구 스키마 자동 생성")
    print("=" * 70)
    from core.intake_tools import get_tools

    tools = get_tools()
    assert len(tools) == 2
    names = [t["name"] for t in tools]
    assert "update_application" in names
    assert "generate_draft" in names
    print(f"  [PASS] 도구 2개 ({names})")

    upd = next(t for t in tools if t["name"] == "update_application")
    props = upd["input_schema"]["properties"]
    assert len(props) >= 15
    # target_zeb_grade은 enum + integer
    assert props["target_zeb_grade"]["type"] == "integer"
    assert props["target_zeb_grade"]["enum"] == [1, 2, 3, 4, 5]
    # contact_email은 string
    assert props["contact_email"]["type"] == "string"
    # applied_elements는 array
    assert props["applied_elements"]["type"] == "array"
    print(f"  [PASS] {len(props)}개 필드 스키마 유효 (enum/string/array 타입 정확)")


def test_intake_session_flow():
    """IntakeSession 단계적 흐름."""
    print("\n" + "=" * 70)
    print("IntakeSession 단계적 흐름")
    print("=" * 70)
    from core.intake_tools import IntakeSession

    session = IntakeSession()
    dispatch = session.make_dispatcher()

    # 1차 업데이트 (일부 잘못된 값 포함)
    r1 = dispatch("update_application", {
        "organization_name": "김천시청",
        "contact_person": "홍길동",
        "target_zeb_grade": 7,      # 잘못된 값
    })
    assert "organization_name" in r1["accepted"]
    assert "target_zeb_grade" in r1["rejected"]
    print(f"  [PASS] 검증 통과 필드만 저장 + 거부 필드 메시지 반환")

    # draft 시도 (필수 부족)
    r2 = dispatch("generate_draft", {})
    assert "error" in r2
    assert "missing" in r2
    print(f"  [PASS] 필수 부족 시 generate_draft 거부 + 빠진 항목 안내")

    # 모든 필수 채우기
    from core.intake_schema import all_required_fields, FIELDS
    fill = {k: FIELDS[k]["example"] for k in all_required_fields()}
    dispatch("update_application", fill)

    r3 = dispatch("generate_draft", {})
    assert "draft_markdown" in r3
    assert "공공건축물 그린리모델링 사업 신청서" in r3["draft_markdown"]
    print(f"  [PASS] 필수 모두 채우면 draft 생성 ({len(r3['draft_markdown'])} chars)")


def test_session_rejects_unknown_fields():
    """알 수 없는 필드는 거부."""
    print("\n" + "=" * 70)
    print("알 수 없는 필드 처리")
    print("=" * 70)
    from core.intake_tools import IntakeSession

    session = IntakeSession()
    r = session.make_dispatcher()("update_application", {
        "organization_name": "OK기관",
        "what_is_this": "이상한 필드",
    })
    assert "organization_name" in r["accepted"]
    assert "what_is_this" in r["rejected"]
    print(f"  [PASS] 알 수 없는 필드 rejected, 알려진 필드 accepted")


def test_next_question_suggestion():
    """다음 질문 추천: 필수 → 선택 순서."""
    print("\n" + "=" * 70)
    print("다음 질문 추천")
    print("=" * 70)
    from core.intake_tools import IntakeSession

    session = IntakeSession()
    # 빈 상태 → 다음 질문은 필수 항목
    r = session.make_dispatcher()("update_application", {
        "organization_name": "테스트",
    })
    qs = r["다음_물어볼_항목"]
    assert len(qs) > 0
    # 첫 추천은 필수
    assert not qs[0].get("_optional"), "첫 추천은 필수 항목이어야"
    print(f"  [PASS] 빈 상태: 필수 항목 우선 추천")
    print(f"  추천 항목: {[q['label'] for q in qs]}")


def test_run_intake_turn_mock():
    """run_intake_turn: Claude mock으로 한 턴 실행."""
    print("\n" + "=" * 70)
    print("run_intake_turn: mock Claude 한 턴")
    print("=" * 70)
    from core.llm_client import set_mock_scenario
    from core.intake_tools import IntakeSession
    from modes.mode4_intake import run_intake_turn

    session = IntakeSession()

    set_mock_scenario([
        {
            "type": "tool_use",
            "name": "update_application",
            "input": {
                "organization_name": "테스트시청",
                "building_name": "테스트도서관",
                "total_area_m2": 3000,
            },
        },
        {"type": "text", "text": "정보 잘 받았습니다. 다음 질문은..."},
    ])

    result = run_intake_turn(
        "테스트시청에서 테스트도서관(3,000㎡) 신청합니다.", session,
    )

    assert result["iterations"] == 2
    assert session.application["organization_name"] == "테스트시청"
    assert session.application["building_name"] == "테스트도서관"
    assert session.application["total_area_m2"] == 3000
    assert result["draft"] is None   # 아직 draft 안 만들었음
    print(f"  [PASS] 1턴 처리: 3개 필드 저장, draft 미생성")


def test_full_conversation_to_draft():
    """전체 대화로 draft 생성까지."""
    print("\n" + "=" * 70)
    print("전체 대화 → draft 생성")
    print("=" * 70)
    from core.llm_client import set_mock_scenario
    from core.intake_tools import IntakeSession
    from core.intake_schema import all_required_fields, FIELDS
    from modes.mode4_intake import run_intake_turn

    session = IntakeSession()

    # 모든 필수 일괄 입력 + draft 호출 시나리오
    fill = {k: FIELDS[k]["example"] for k in all_required_fields()}
    set_mock_scenario([
        {"type": "tool_use", "name": "update_application", "input": fill},
        {"type": "tool_use", "name": "generate_draft", "input": {}},
        {"type": "text", "text": "🎉 신청서 초안 생성 완료!"},
    ])

    result = run_intake_turn("모든 정보 입력했으니 초안 만들어줘", session)

    assert result["iterations"] == 3
    assert result["draft"] is not None
    assert "공공건축물 그린리모델링" in result["draft"]
    assert result["progress"]["is_ready_for_draft"] is True
    print(f"  [PASS] 3회 iteration: update → draft → text")
    print(f"  [PASS] draft 생성: {len(result['draft'])} chars")


if __name__ == "__main__":
    try:
        test_schema_basics()
        test_field_validation()
        test_progress_calculation()
        test_tool_schema()
        test_intake_session_flow()
        test_session_rejects_unknown_fields()
        test_next_question_suggestion()
        test_run_intake_turn_mock()
        test_full_conversation_to_draft()
        print("\n" + "=" * 70)
        print("Mode 4 테스트 전체 통과 ✅")
        print("=" * 70)
    except AssertionError as e:
        print(f"\n❌ 검증 실패: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 예외: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
