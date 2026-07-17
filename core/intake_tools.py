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

    def __init__(self, initial: Optional[dict] = None, track: str = "public"):
        # 🔑 공공/민간은 다른 사업이다. 트랙 없이 진행하면 민간 신청자에게
        #    '신청기관명'을 묻고 공공 서식 초안을 내주게 된다.
        self.track = track
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

        progress = calculate_progress(self.application, self.track)

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
            "다음_물어볼_항목": _suggest_next_questions(
                self.application, max_n=3, track=self.track),
        }

    def _generate_draft(self) -> dict:
        """신청서 초안 생성."""
        progress = calculate_progress(self.application, self.track)
        if not progress["is_ready_for_draft"]:
            return {
                "error": "필수 항목이 아직 채워지지 않았습니다.",
                "missing": progress["missing_required_labels"],
            }

        draft_md = render_application_markdown(self.application, self.track)
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
        return calculate_progress(self.application, self.track)

    def to_dict(self) -> dict:
        return dict(self.application)


# ====================================================================
# 마크다운 신청서 렌더
# ====================================================================

def _required_documents(app: dict, track: str) -> list:
    """제출해야 할 서류 — 입력값에 따라 달라진다.

    민간은 용도구분·건축주 구분이 서류를 바꾼다([붙임3] 원문):
      · 비주거      → [별지8] 대출가능 사전의향서 (차주가 은행에 신청, 유효기간 6개월)
      · 단독주택    → [별지7] 간이평가표
      · 법인 건축주 → [별지2] 개인정보 동의서 **제출하지 않음**
    공공은 소유현황·유형이 바꾼다(운영지침 제14조③④).
    """
    if track == "private":
        docs = [
            "[별지1] 민간건축물 그린리모델링 이자지원 사업 신청서 — 건축주·사업자",
            "[별지3] 그린리모델링 사업계획서 — 사업자",
            "[별지4] 공사비 산출근거 (원가계산서·내역서·수량산출서) — 사업자",
            "[별지5] 건축물 부위별 현황 사진 (컬러) — 건축주·사업자",
            "[별지6] 에너지 성능개선 비율 산출기준 및 제출서류 — 사업자",
            "등기사항증명서 (미이전 시 부동산 매매계약서)",
            "건축물대장 (공동주택이면 전유부)",
            "사업 전·후 설계도서 — 사업자",
            "계약서 또는 협약서 — **건축주·사업자 공동날인**, 사본이면 원본대조필",
            "4대보험 사업장 가입자 명부 — 사업자 (전문인력 등재 확인)",
        ]
        if app.get("owner_type") != "사업자":
            docs.insert(1, "[별지2] 개인정보 수집·이용·제공 동의서 — 건축주 "
                           "(법인이면 제출 안 함)")
            docs.append("건축주 신분증 (뒷자리 삭제 후 제출)")
        else:
            docs.append("사업자등록증 (건축주가 사업자인 경우)")

        _u = app.get("usage_category")
        if _u == "비주거":
            docs.append("🔴 [별지8] 그린리모델링 자금 대출가능 사전의향서 — "
                        "**비주거만 해당** · 차주가 은행에 신청 · 유효기간 발급일로부터 6개월")
        elif _u == "주거(단독주택)":
            docs.append("🔴 [별지7] 에너지 성능개선 비율 간이평가표 — **단독주택만 해당**")
        elif _u == "주거(공동주택)":
            docs.append("효율관리기자재 신고 확인서(창호/보일러/LED 등)·평면도·"
                        "교체 내역서·현황 사진")
        return docs

    docs = [
        "[별지 제1호서식] 공공건축물 그린리모델링 지원사업 신청서 — 관리시스템에서 작성 후 "
        "**PDF로 추출해 등록**",
        "사업비 산출내역 (신청서 [붙임]) — 홈페이지 작성 후 PDF 추출",
        "개인정보 수집·이용·제공 동의서",
    ]
    if app.get("directly_owned") is False:
        docs.append("🔴 [별지 제2호서식] 임차건물 관리대상 확인서 및 임대인 동의서 — "
                    "**임차건축물이면 필수** (운영지침 제14조③)")
    if app.get("project_type") == "군집형":
        docs.append("🔴 [별지 제3호서식] 「군집형사업」 추진계획서 (운영지침 제14조④)")
    docs.append("최근 5년 이내 정기안전점검 보고서 (안전점검 이력이 있는 경우)")
    return docs


def render_application_markdown(app: dict, track: str = "public") -> str:
    """현재 신청서 dict → 마크다운 초안.

    ⚠️ 예전엔 제목이 '공공건축물 …'으로 하드코딩돼 있어, 민간 신청자도
       공공 서식 초안을 받았다. 두 사업은 근거·서식·제출 주체가 전부 다르다.
    """
    lines = []
    is_private = track == "private"

    if is_private:
        lines.append("# 민간건축물 그린리모델링 이자지원 사업 신청서 (초안)")
        lines.append("")
        lines.append("> **근거**: 「녹색건축물 조성 지원법」 제25·26·27조 · "
                     "2026년 민간건축물 그린리모델링 이자지원 사업 공고 [붙임3]  ")
        lines.append("> **지원 방식**: 공사비 직접 보조가 아니라 **대출 이자 보전**"
                     "(성능개선비율 20~30% 미만 4.5% / 30% 이상 5.5%)  ")
        lines.append("> **제출 주체**: 건축주가 아니라 **그린리모델링 사업자**가 "
                     "건축주 동의를 받아 센터에 제출  ")
        lines.append("> **제출처**: 그린리모델링 창조센터장")
    else:
        lines.append("# 공공건축물 그린리모델링 지원사업 신청서 (초안)")
        lines.append("")
        lines.append("> **근거**: 「녹색건축물 조성 지원법」 제27조 · "
                     "공공건축물 그린리모델링 지원사업 운영지침 (2026-04-21 개정)  ")
        lines.append("> **지원 방식**: **국비로 공사비 직접 보조** "
                     "(서울·중앙·공공 50% / 그 외 지자체 70%)  ")
        lines.append("> **제출 주체**: 신청기관이 **관리시스템에서 직접** 작성 "
                     "→ PDF 추출 후 등록 (운영지침 제14조②)  ")
        lines.append("> **제출처**: 국토안전관리원 그린리모델링 창조센터")
    lines.append("")
    lines.append(f"*생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}*  ")
    lines.append("*본 초안은 자동 생성물입니다. 공식 양식은 "
                 "그린리모델링 창조센터(greenremodeling.or.kr · 1588-8788)에서 받아 "
                 "대조하세요.*")
    lines.append("")

    for sec in SECTIONS:
        _keys = fields_by_section(sec, track)
        if not _keys:
            continue
        lines.append(f"## {sec}")
        lines.append("")
        for fname in _keys:
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
    lines.append("")
    lines.append("## 함께 낼 서류")
    lines.append("")
    for d in _required_documents(app, track):
        lines.append(f"- {d}")
    lines.append("")
    lines.append("---")
    lines.append("**범례**: `*` 표시는 필수 항목. 🔴 는 입력하신 조건 때문에 "
                 "**추가로 필요해진** 서류입니다.")
    return "\n".join(lines)


# ====================================================================
# 다음 질문 추천
# ====================================================================

def _suggest_next_questions(app: dict, max_n: int = 3,
                            track: Optional[str] = None) -> list:
    """
    Claude가 다음 턴에 물어볼 항목 추천 (필수 → 선택, 섹션 순서대로).

    Returns:
        [{field, label, help}, ...] (max_n 개)
    """
    # 🔑 트랙 없이 추천하면 공공 항목('신청기관 유형')과 민간 항목('사업자명')이
    #    섞여 나온다 — 실제로 그랬다.
    from core.intake_schema import all_required_fields, all_optional_fields

    out = []
    # 1) 필수 먼저
    for fname in all_required_fields(track):
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
    for fname in all_optional_fields(track):
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
