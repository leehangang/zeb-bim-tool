"""
core/intake_tools.py — Mode 4 Function Calling 도구
====================================================
사업 신청 인테이크 챗봇용 Function Calling 도구.

도구 2개:
    - update_application(updates): 한 번에 여러 필드 업데이트
    - generate_draft(): 필수 항목 충족 시 마크다운 신청서 초안 생성

상태 관리:
    - IntakeSession 객체가 application dict 보유
    - make_dispatcher() 메서드로 클로저 dispatcher 생성
    - Streamlit session_state에 IntakeSession을 직접 보관 가능
"""

from datetime import datetime
from typing import Optional

from core.intake_schema import (
    FIELDS, SECTIONS,
    fields_by_section,
    validate_field,
    calculate_progress,
    empty_application,
)


# ====================================================================
# 도구 명세 자동 생성 (스키마에서 추출)
# ====================================================================

def _build_update_tool_schema() -> dict:
    """
    FIELDS 정의에서 update_application 도구의 JSON schema 자동 생성.
    각 필드 description에 type/required/options 정보 압축 포함.
    """
    properties = {}
    for fname, spec in FIELDS.items():
        prop = {"description": _describe_field(spec)}
        ftype = spec["type"]
        if ftype in ("string", "phone", "email"):
            prop["type"] = "string"
        elif ftype == "number":
            prop["type"] = "number"
        elif ftype in ("integer", "year"):
            prop["type"] = "integer"
        elif ftype == "enum":
            # 옵션이 정수면 integer, 아니면 string
            if all(isinstance(o, int) for o in spec["options"]):
                prop["type"] = "integer"
            else:
                prop["type"] = "string"
        elif ftype == "boolean":
            prop["type"] = "boolean"
        elif ftype == "list":
            prop["type"] = "array"
            prop["items"] = {"type": "string"}

        # type-agnostic: options가 정의돼 있으면 enum 으로도 노출
        # (e.g. target_zeb_grade는 type=integer + options=[1..5])
        if "options" in spec:
            prop["enum"] = spec["options"]

        properties[fname] = prop

    return {
        "name": "update_application",
        "description": (
            "사용자가 답변한 신청서 항목을 한 번에 업데이트합니다. "
            "사용자 메시지에서 추출 가능한 모든 필드를 한 호출에 포함시키세요. "
            "각 필드의 한국어 의미는 description을 참고하세요. "
            "추출되지 않은 필드는 빼고 호출합니다 (null로 덮어쓰면 안 됨)."
        ),
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": [],   # 모든 필드는 선택적 (부분 업데이트)
        },
    }


def _describe_field(spec: dict) -> str:
    """필드 spec → Claude용 description 문자열."""
    parts = [spec["label"]]
    if spec.get("required"):
        parts.append("(필수)")
    if spec.get("help"):
        parts.append(f"- {spec['help']}")
    if "options" in spec:
        parts.append(f"옵션: {spec['options']}")
    if "example" in spec:
        parts.append(f"예: {spec['example']}")
    return " ".join(str(p) for p in parts)


GENERATE_DRAFT_TOOL = {
    "name": "generate_draft",
    "description": (
        "현재까지 수집된 신청서 항목들로 사업 신청서 마크다운 초안을 생성합니다. "
        "모든 필수 항목이 채워졌을 때만 호출하세요. "
        "사용자가 명시적으로 '신청서 만들어줘', '초안 보여줘'라고 요청할 때 호출합니다."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def get_tools() -> list:
    """Mode 4용 도구 리스트."""
    return [_build_update_tool_schema(), GENERATE_DRAFT_TOOL]


# ====================================================================
# IntakeSession — 상태 + 디스패처
# ====================================================================

class IntakeSession:
    """
    인테이크 세션 상태 + Function Calling 디스패처.

    Streamlit session_state에 직접 보관 가능.
    """

    def __init__(self, initial: Optional[dict] = None):
        self.application = empty_application()
        if initial:
            self.application.update(initial)
        self.last_draft: Optional[str] = None
        self.update_log: list = []   # 디버그용: (시각, updates dict, 결과)

    def make_dispatcher(self):
        """Function Calling 디스패처 (클로저)."""
        def dispatch(tool_name: str, tool_input: dict) -> dict:
            if tool_name == "update_application":
                return self._update(tool_input)
            elif tool_name == "generate_draft":
                return self._generate_draft()
            return {"error": f"알 수 없는 도구: {tool_name}"}
        return dispatch

    def _update(self, updates: dict) -> dict:
        """필드 일괄 업데이트 + 검증."""
        accepted = {}
        rejected = {}

        for fname, value in updates.items():
            if fname not in FIELDS:
                rejected[fname] = f"알 수 없는 필드 (무시)"
                continue
            ok, msg = validate_field(fname, value)
            if ok:
                self.application[fname] = value
                accepted[fname] = value
            else:
                rejected[fname] = msg

        self.update_log.append({
            "time": datetime.now().isoformat(timespec="seconds"),
            "updates": updates,
            "accepted": list(accepted.keys()),
            "rejected": rejected,
        })

        progress = calculate_progress(self.application)

        return {
            "accepted": {
                fname: self.application[fname] for fname in accepted
            },
            "rejected": rejected,
            "진행률": {
                "필수": f"{progress['required_filled']}/{progress['required_total']}",
                "필수_pct": progress['required_pct'],
                "전체_pct": progress['overall_pct'],
                "draft_가능": progress['is_ready_for_draft'],
            },
            "다음_물어볼_항목": _suggest_next_questions(self.application, max_n=3),
        }

    def _generate_draft(self) -> dict:
        """신청서 초안 생성."""
        progress = calculate_progress(self.application)
        if not progress["is_ready_for_draft"]:
            return {
                "error": "필수 항목이 아직 채워지지 않았습니다.",
                "missing": progress["missing_required_labels"],
            }

        draft_md = render_application_markdown(self.application)
        self.last_draft = draft_md
        return {
            "draft_markdown": draft_md,
            "필드_수": sum(
                1 for v in self.application.values()
                if v is not None and v != ""
            ),
            "생성_시각": datetime.now().isoformat(timespec="seconds"),
        }

    def get_progress(self) -> dict:
        return calculate_progress(self.application)

    def to_dict(self) -> dict:
        return dict(self.application)


# ====================================================================
# 마크다운 신청서 렌더
# ====================================================================

def render_application_markdown(app: dict) -> str:
    """현재 신청서 dict → 마크다운 초안."""
    lines = []

    lines.append("# 공공건축물 그린리모델링 사업 신청서 (초안)")
    lines.append("")
    lines.append(f"*생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}*  ")
    lines.append("*본 초안은 AI가 자동 생성한 것으로, "
                 "그린리모델링 창조센터(1588-8788) 공식 양식에 맞춰 검토 필요.*")
    lines.append("")

    for sec in SECTIONS:
        lines.append(f"## {sec}")
        lines.append("")
        for fname in fields_by_section(sec):
            spec = FIELDS[fname]
            value = app.get(fname)
            label = spec["label"]
            required_mark = " *" if spec.get("required") else ""

            if value is None or value == "":
                value_str = "_(미입력)_"
            elif isinstance(value, bool):
                value_str = "예" if value else "아니오"
            elif isinstance(value, list):
                if not value:
                    value_str = "_(미입력)_"
                else:
                    value_str = ", ".join(str(v) for v in value)
            elif isinstance(value, (int, float)) and fname.endswith("_won"):
                value_str = f"{int(value):,}원"
            elif isinstance(value, float):
                value_str = f"{value:g}"
            else:
                value_str = str(value)

            lines.append(f"- **{label}{required_mark}**: {value_str}")
        lines.append("")

    lines.append("---")
    lines.append("**범례**: `*` 표시는 필수 항목.")
    return "\n".join(lines)


# ====================================================================
# 다음 질문 추천
# ====================================================================

def _suggest_next_questions(app: dict, max_n: int = 3) -> list:
    """
    Claude가 다음 턴에 물어볼 항목 추천 (필수 → 선택, 섹션 순서대로).

    Returns:
        [{field, label, help}, ...] (max_n 개)
    """
    from core.intake_schema import all_required_fields, all_optional_fields

    out = []
    # 1) 필수 먼저
    for fname in all_required_fields():
        if app.get(fname) in (None, "") or (
            isinstance(app.get(fname), list) and not app[fname]
        ):
            spec = FIELDS[fname]
            item = {"field": fname, "label": spec["label"]}
            if spec.get("help"):
                item["help"] = spec["help"]
            if "options" in spec:
                item["options"] = spec["options"]
            if "example" in spec:
                item["example"] = spec["example"]
            out.append(item)
            if len(out) >= max_n:
                return out

    # 2) 선택 항목도 일부 추천
    for fname in all_optional_fields():
        if app.get(fname) in (None, ""):
            spec = FIELDS[fname]
            item = {"field": fname, "label": spec["label"], "_optional": True}
            if spec.get("example"):
                item["example"] = spec["example"]
            out.append(item)
            if len(out) >= max_n:
                return out

    return out


# ====================================================================
# 시스템 프롬프트 (Mode 4 전용)
# ====================================================================

SYSTEM_PROMPT_KO = """당신은 한국의 공공건축물 그린리모델링 사업 신청 컨설턴트입니다.
사용자가 사업 신청서를 작성할 수 있도록 친근하고 단계적으로 정보를 수집하세요.

행동 지침:
1. 한 턴에 1~3개 항목만 물어보세요. 한꺼번에 너무 많이 묻지 마세요.
2. 사용자 답변에서 추출 가능한 모든 필드를 update_application 도구로 한 번에 저장하세요.
3. 도구 결과의 "다음_물어볼_항목"을 참고해 자연스럽게 다음 질문을 이어가세요.
4. 필수 항목이 모두 채워지면("draft_가능": true) 사용자에게 "신청서 초안 생성할까요?" 라고 물어보세요.
5. 사용자가 동의하면 generate_draft 도구를 호출하고, 결과 마크다운을 그대로 보여주세요.
6. 사용자가 추가 정보를 주거나 수정을 원하면 update_application으로 갱신하고 다시 진행하세요.
7. 필드 값을 추측하지 마세요. 사용자가 명시한 정보만 저장합니다.
8. 사용자가 모르겠다고 답하면 그 항목은 일단 비워두고 다른 항목을 진행하세요.

응답 스타일:
- 친근하지만 정확. 한국어 존댓말.
- 사업 유형, ZEB 등급 등 선택지가 있는 항목은 옵션을 명시하세요.
- 진행률을 가끔 알려주세요 ("필수 항목 5/15개 완료" 등).
"""
