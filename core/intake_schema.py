"""
core/intake_schema.py — 사업 신청서 스키마

🔑 공공과 민간은 **완전히 다른 사업**이다. 한 화면에 뭉개면 안 된다.
====================================================================
2026-07-17 실제 서식 원문 확보로 전면 개정. 예전 독스트링은 스스로
"필수/선택 분류는 졸업설계 단계 추정"이라 적고 있었고, 21개 필드가 전부
**공공 전용**(신청기관명·서울/중앙/공공 여부)이었다. 민간은 구조가 다르다.

┌──────────┬──────────────────────────┬──────────────────────────────┐
│          │ 공공 (public)             │ 민간 (private)                │
├──────────┼──────────────────────────┼──────────────────────────────┤
│ 근거     │ 공공건축물 GR 지원사업     │ 민간건축물 GR 이자지원 사업    │
│          │ 운영지침 (260421 개정)     │ 공고 [붙임3] 구비서류          │
│ 지원방식 │ **국비로 공사비 직접 보조**│ **대출 이자 보전 (4.5~5.5%)** │
│ 신청 주체│ 기관이 직접 (셀프 온라인)  │ **사업자 경유** (건축주 동의)  │
│ 신청 서식│ [별지 제1호서식]           │ [별지1] + [별지2~8]           │
│ 대상     │ 사용승인 10년 이상 경과    │ **2016-01-01 이전** 사용승인  │
│          │ 공공건축물                 │ 단독주택 또는 비주거           │
│ 전제조건 │ **당해연도 사전컨설팅 필수**│ 사업자 선정·계약이 출발점      │
│          │ (운영지침 제14조①)         │ 공사 완료 후 신청 **불가**     │
└──────────┴──────────────────────────┴──────────────────────────────┘

설계:
    - FIELDS: 필드 메타데이터. `tracks`로 어느 사업에 속하는지 표시한다.
      · tracks=("public",)  → 공공 전용
      · tracks=("private",) → 민간 전용
      · tracks=("public","private") → 공통
    - `required`도 트랙마다 다르다 → required_for=("public",) 형태로 둔다.
      (민간은 '한전고객번호'가 없고, 공공은 '건축주'가 없다)
    - fields_for_track() / get_missing_required(app, track) 로 걸러 쓴다.
"""

from typing import Optional

# 두 사업의 트랙 키 — 문자열을 여기저기 흩뿌리지 않는다
TRACK_PUBLIC = "public"
TRACK_PRIVATE = "private"
TRACKS = (TRACK_PUBLIC, TRACK_PRIVATE)

TRACK_LABEL = {
    TRACK_PUBLIC: "공공건축물 그린리모델링 지원사업",
    TRACK_PRIVATE: "민간건축물 그린리모델링 이자지원 사업",
}


# ====================================================================
# 필드 정의 (한국어 라벨 + 타입 + 검증 룰)
# ====================================================================
"""
필드 type:
    - "string":  자유 문자열
    - "number":  실수
    - "integer": 정수
    - "year":    연도 (1900~2025)
    - "enum":    options 중 하나
    - "date":    YYYY-MM-DD
    - "phone":   전화번호
    - "email":   이메일
    - "list":    문자열 리스트 (e.g. 적용 기술요소)
"""

FIELDS = {
    # ────── 1. 신청 기관 정보 ──────
    "organization_name": {
        "label": "신청기관명",
        "tracks": ("public",),
        "section": "기관",
        "type": "string",
        "required": True,
        "example": "김천시청",
        "help": "사업 신청 주체 (지자체 또는 공공기관)",
    },
    "org_type": {
        "label": "신청기관 유형",
        "tracks": ("public",),
        "section": "기관",
        "type": "enum",
        "required": True,
        "options": ["지자체", "중앙행정", "공공기관"],
        "example": "지자체",
        "help": "[별지 제1호서식] '신청기관유형'. 보조율(50%/70%)이 여기서 갈린다.",
    },

    # ────── 민간 전용 — 신청 주체가 둘이다 ──────
    # 🔑 민간은 건축주가 직접 신청하지 않는다. **사업자가 건축주 동의를 받아 제출**한다.
    #    그래서 서식([별지1])에 '신청인(사업자)'과 '신청인(건축주)'이 나란히 있다.
    "gr_company_name": {
        "label": "그린리모델링 사업자명",
        "tracks": ("private",),
        "section": "기관",
        "type": "string",
        "required": True,
        "example": "○○종합건설(주)",
        "help": "[별지1] 신청인(사업자). 민간은 사업자가 센터에 제출한다 — "
                "사업자 선정·계약이 신청의 출발점이다.",
    },
    "gr_company_ceo": {
        "label": "사업자 대표자명",
        "tracks": ("private",),
        "section": "기관",
        "type": "string",
        "required": True,
        "example": "김대표",
    },
    "owner_name": {
        "label": "건축주명",
        "tracks": ("private",),
        "section": "기관",
        "type": "string",
        "required": True,
        "example": "박건축",
        "help": "[별지1] 신청인(건축주). 공동명의면 전원 제출.",
    },
    "owner_type": {
        "label": "건축주 구분",
        "tracks": ("private",),
        "section": "기관",
        "type": "enum",
        "required": True,
        "options": ["개인", "사업자"],
        "example": "개인",
        "help": "개인이면 신분증(뒷자리 삭제), 사업자면 사업자등록증. "
                "법인이면 [별지2] 개인정보 동의서는 제출하지 않는다.",
    },
    "contact_person": {
        "label": "담당자명",
        "tracks": ("public", "private"),
        "section": "기관",
        "type": "string",
        "required": True,
        "example": "홍길동 주무관",
    },
    "contact_phone": {
        "label": "담당자 연락처",
        "tracks": ("public", "private"),
        "section": "기관",
        "type": "phone",
        "required": True,
        "example": "054-420-6000",
    },
    "contact_email": {
        "label": "담당자 이메일",
        "tracks": ("public", "private"),
        "section": "기관",
        "type": "email",
        "required": False,
        "example": "official@gimcheon.go.kr",
    },

    # ────── 2. 대상 건축물 정보 ──────
    "building_name": {
        "label": "건축물명",
        "tracks": ("public", "private"),
        "section": "건축물",
        "type": "string",
        "required": True,
        "example": "김천 도담어린이집",
    },
    "building_address": {
        "label": "소재지",
        "tracks": ("public", "private"),
        "section": "건축물",
        "type": "string",
        "required": True,
        "example": "경상북도 김천시 ○○로 12",
    },
    "building_usage": {
        "label": "용도",
        "tracks": ("public", "private"),
        "section": "건축물",
        "type": "enum",
        "required": True,
        "options": [
            "어린이집", "도서관", "보건소", "주민센터",
            "학교", "노인복지시설", "행정청사", "체육관", "기타",
        ],
        "example": "어린이집",
    },
    "completion_year": {
        "label": "사용승인년도",
        "tracks": ("public", "private"),
        "section": "건축물",
        "type": "year",
        "required": True,
        "example": 2014,
        "help": "최초 사용승인일 기준 연도. 노후도 점수 산정에 사용.",
    },
    "total_area_m2": {
        "label": "연면적 (㎡)",
        "tracks": ("public", "private"),
        "section": "건축물",
        "type": "number",
        "required": True,
        "example": 1251,
        "min": 1,
    },
    "building_area_m2": {
        "label": "건축면적 (㎡)",
        "tracks": ("public", "private"),
        "section": "건축물",
        "type": "number",
        "required": False,
        "example": 600,
        "min": 1,
    },
    "structure": {
        "label": "구조",
        "tracks": ("public", "private"),
        "section": "건축물",
        "type": "enum",
        "required": False,
        "options": ["철근콘크리트", "철골", "조적", "목구조", "혼합구조", "기타"],
        "example": "철근콘크리트",
    },
    "floors": {
        "label": "층수",
        "tracks": ("public", "private"),
        "section": "건축물",
        "type": "string",
        "required": False,
        "example": "지하1층 / 지상2층",
    },
    "directly_owned": {
        "label": "직접 소유 여부",
        "tracks": ("public", "private"),
        "section": "건축물",
        "type": "boolean",
        "required": False,
        "example": True,
        "help": "신청기관이 직접 소유. True면 사업여건 점수 가산.",
    },

    # ────── 3. 사업 계획 ──────
    "project_type": {
        "label": "사업유형",
        "tracks": ("public",),   # 시그니처/종합형/군집형/맞춤형 = 공공 운영지침 유형
        "section": "사업",
        "type": "enum",
        "required": True,
        "options": ["시그니처", "종합형", "군집형", "맞춤형(개보수형)",
                    "맞춤형(성능개선형)", "맞춤형(건물특화형)"],
        "example": "시그니처",
        "help": "01 가이드라인의 사업 유형 분류.",
    },
    "target_zeb_grade": {
        "label": "목표 ZEB 등급",
        "tracks": ("public", "private"),
        "section": "사업",
        "type": "integer",
        # ⚠️ 두 신청서 어디에도 ZEB 등급 칸은 없다. 우리 ROI가 인센티브(취득세·용적률)
        #    계산에 쓰는 입력이라 남기되, 신청 필수는 아니므로 선택으로 둔다.
        "required": False,
        "options": [1, 2, 3, 4, 5],
        "example": 5,
        "min": 1, "max": 5,
    },
    "energy_saving_target_pct": {
        "label": "에너지 절감 목표 (%)",
        "tracks": ("public",),   # 민간은 improvement_ratio_pct([별지1] 성능개선비율)
        "section": "사업",
        "type": "number",
        "required": True,
        "example": 30,
        "min": 0, "max": 100,
        "help": "공사 전·후 1차 에너지소요량 절감률 목표.",
    },
    "project_duration_months": {
        "label": "사업 기간 (개월)",
        "tracks": ("public", "private"),
        "section": "사업",
        "type": "integer",
        "required": True,
        "example": 8,
        "min": 1, "max": 48,
    },
    "total_budget_won": {
        "label": "총사업비 (원)",
        "tracks": ("public", "private"),
        "section": "사업",
        "type": "number",
        "required": True,
        "example": 290_000_000,
        "min": 0,
        "help": "Max Cost (부가세 포함) 추정값. ROI 시뮬레이션 결과 활용 가능.",
    },
    "is_seoul_or_public": {
        "label": "서울/중앙/공공 여부",
        "tracks": ("public",),
        "section": "사업",
        "type": "boolean",
        "required": True,
        "example": True,
        "help": "True면 보조율 50%, False면 그외 지자체 70%.",
    },
    "pre_consulting_done": {
        "label": "당해연도 사전컨설팅 시행 여부",
        "tracks": ("public",),
        "section": "사업",
        "type": "boolean",
        "required": True,
        "example": True,
        "help": "🔴 운영지침 제14조① — '지원사업을 신청하고자 하는 건축물은 당해 사업연도에 "
                "제9조에 따른 사전컨설팅을 시행한 건축물이어야 한다.' 안 했으면 신청 자체가 불가.",
    },
    "building_pk": {
        "label": "건축물대장 PK",
        "tracks": ("public", "private"),
        "section": "건축물",
        "type": "string",
        "required": False,
        "example": "11110-100123456",
        "help": "건축행정시스템 세움터/건축HUB(hub.go.kr)에서 검색. "
                "공공 [별지1] 'PK번호', 민간 [별지1] '건축물PK'.",
    },
    "kepco_customer_no": {
        "label": "한전 고객번호",
        "tracks": ("public",),
        "section": "건축물",
        "type": "string",
        "required": False,
        "example": "0123456789",
        "help": "[별지 제1호서식] '한전고객번호(에너지정보수집용)'. 사업 후 에너지 모니터링에 쓴다.",
    },

    # ────── 민간 전용 사업 정보 ──────
    "project_stage": {
        "label": "사업단계",
        "tracks": ("private",),
        "section": "사업",
        "type": "enum",
        "required": True,
        "options": ["시공 전", "시공 중"],
        "example": "시공 전",
        "help": "🔴 [별지1] '*공사완료 시 신청 불가'. 이미 준공했으면 못 받는다.",
    },
    "usage_category": {
        "label": "용도구분",
        "tracks": ("private",),
        "section": "사업",
        "type": "enum",
        "required": True,
        "options": ["비주거", "주거(단독주택)", "주거(공동주택)"],
        "example": "비주거",
        "help": "[별지1]. 이 값이 필요 서류를 바꾼다 — 비주거는 [별지8] 대출가능 "
                "사전의향서, 단독주택은 [별지7] 간이평가표.",
    },
    "loan_method": {
        "label": "대출방법",
        "tracks": ("private",),
        "section": "사업",
        "type": "enum",
        "required": True,
        "options": ["은행대출", "신용카드"],
        "example": "은행대출",
        "help": "[별지1]. 민간은 공사비를 직접 주는 게 아니라 **대출 이자를 보전**한다.",
    },
    "improvement_metric": {
        "label": "성능개선비율 산출 방법",
        "tracks": ("private",),
        "section": "사업",
        "type": "enum",
        "required": True,
        "options": ["에너지 시뮬레이션", "창호 에너지소비 효율등급(공동주택)",
                    "간이평가표(단독주택)"],
        "example": "에너지 시뮬레이션",
        "help": "[별지6]. 시뮬레이션은 센터 지정 프로그램만 — "
                "ECO2, ECO2-OD, GR-E, Energy Studio, EnergyPlus, IES-VE.",
    },
    "improvement_ratio_pct": {
        "label": "성능개선비율 (%)",
        "tracks": ("private",),
        "section": "사업",
        "type": "number",
        "required": True,
        "example": 25,
        "min": 0, "max": 100,
        "help": "개선 전 대비 절감률. 20% 이상이어야 지원 대상 "
                "(20~30% 미만 4.5% / 30% 이상 5.5% 이차보전).",
    },
    "construction_cost_won": {
        "label": "성능개선 공사비 (원)",
        "tracks": ("private",),
        "section": "사업",
        "type": "number",
        "required": True,
        "example": 150_000_000,
        "min": 0,
        "help": "[별지1] '성능개선공사비'. 총 공사비 중 에너지 성능개선분.",
    },
    "loan_request_won": {
        "label": "사업신청금액 (대출 신청액, 원)",
        "tracks": ("private",),
        "section": "사업",
        "type": "number",
        "required": True,
        "example": 150_000_000,
        "min": 0,
        "help": "[별지1] '사업신청금액'. 이 금액의 이자를 보전받는다.",
    },

    "main_work_scope": {
        "label": "주요사업 내용",
        "tracks": ("private",),
        "section": "사업",
        "type": "list",
        "required": True,
        "options": ["구조", "단열", "창호", "기계설비", "전기설비", "신재생에너지", "기타"],
        "example": ["단열", "창호"],
        "help": "[별지1] '주요사업 내용'. 공공의 사업유형(종합형/맞춤형)과는 다른 축이다.",
    },

    # ────── 4. 적용 기술 요소 ──────
    "applied_elements": {
        "label": "적용 GR 기술요소",
        "tracks": ("public", "private"),
        "section": "기술요소",
        "type": "list",
        "required": True,
        "example": ["고성능창호", "외벽단열보강", "고효율 EHP", "태양광"],
        "help": "01 가이드라인 11개 기술요소 중 선택. 최소 3개 이상 권장.",
    },
    "climate_adaptation_elements": {
        "label": "기후위기적응 요소",
        "tracks": ("public", "private"),
        "section": "기술요소",
        "type": "list",
        "required": False,
        "example": ["옥상녹화", "외부 차양구조물"],
        "help": "홍수·태풍·폭염·대설 등 기후 재해 대응 요소 (종합형은 1개 이상 필수).",
    },
}


# ====================================================================
# 섹션 구성
# ====================================================================

SECTIONS = ["기관", "건축물", "사업", "기술요소"]


def in_track(field_name: str, track: Optional[str]) -> bool:
    """이 필드가 해당 사업(트랙)에 속하는가. track=None이면 전부 통과(구버전 호환)."""
    if not track:
        return True
    return track in FIELDS[field_name].get("tracks", TRACKS)


def fields_for_track(track: Optional[str] = None) -> list:
    """해당 사업에서 실제로 쓰는 필드만.

    🔑 이걸 안 거치면 민간 사용자에게 '신청기관명'을 요구하게 된다 —
       민간은 신청 주체가 기관이 아니라 **사업자 + 건축주**다.
    """
    return [k for k in FIELDS if in_track(k, track)]


def fields_by_section(section: str, track: Optional[str] = None) -> list:
    """특정 섹션에 속한 필드 키 리스트 (트랙으로 거른다)."""
    return [k for k, v in FIELDS.items()
            if v["section"] == section and in_track(k, track)]


def all_required_fields(track: Optional[str] = None) -> list:
    """필수 필드 키 리스트."""
    return [k for k, v in FIELDS.items() if v.get("required") and in_track(k, track)]


def all_optional_fields(track: Optional[str] = None) -> list:
    """선택 필드 키 리스트."""
    return [k for k, v in FIELDS.items()
            if not v.get("required") and in_track(k, track)]


# ====================================================================
# 검증
# ====================================================================

def validate_field(field_name: str, value) -> tuple:
    """
    단일 필드 값 검증.

    Returns:
        (ok: bool, error_message: str | None)
    """
    if field_name not in FIELDS:
        return False, f"알 수 없는 필드: {field_name}"

    spec = FIELDS[field_name]

    # null 허용? 필수면 None 불가
    if value is None or value == "":
        if spec.get("required"):
            return False, f"'{spec['label']}'은(는) 필수 항목입니다."
        return True, None

    ftype = spec["type"]

    if ftype == "string":
        if not isinstance(value, str):
            return False, f"'{spec['label']}'은 문자열이어야 합니다."

    elif ftype == "number":
        try:
            v = float(value)
        except (ValueError, TypeError):
            return False, f"'{spec['label']}'은 숫자여야 합니다."
        if "min" in spec and v < spec["min"]:
            return False, f"'{spec['label']}' 최솟값은 {spec['min']}입니다."
        if "max" in spec and v > spec["max"]:
            return False, f"'{spec['label']}' 최댓값은 {spec['max']}입니다."

    elif ftype == "integer":
        try:
            v = int(value)
        except (ValueError, TypeError):
            return False, f"'{spec['label']}'은 정수여야 합니다."
        if "options" in spec and v not in spec["options"]:
            return False, (
                f"'{spec['label']}'은 다음 중 하나여야 합니다: {spec['options']}"
            )
        if "min" in spec and v < spec["min"]:
            return False, f"'{spec['label']}' 최솟값은 {spec['min']}입니다."
        if "max" in spec and v > spec["max"]:
            return False, f"'{spec['label']}' 최댓값은 {spec['max']}입니다."

    elif ftype == "year":
        try:
            v = int(value)
        except (ValueError, TypeError):
            return False, f"'{spec['label']}'은 연도(정수)여야 합니다."
        if not (1900 <= v <= 2030):
            return False, f"'{spec['label']}'은 1900~2030 범위여야 합니다."

    elif ftype == "enum":
        if value not in spec["options"]:
            return False, (
                f"'{spec['label']}'은 다음 중 하나여야 합니다: {spec['options']}"
            )

    elif ftype == "boolean":
        if not isinstance(value, bool):
            return False, f"'{spec['label']}'은 True/False 값이어야 합니다."

    elif ftype == "phone":
        if not isinstance(value, str) or len(value.replace("-", "")) < 8:
            return False, f"'{spec['label']}' 형식 오류 (최소 8자리)."

    elif ftype == "email":
        if not isinstance(value, str) or "@" not in value:
            return False, f"'{spec['label']}' 형식 오류 (@ 누락)."

    elif ftype == "list":
        if not isinstance(value, list):
            return False, f"'{spec['label']}'은 리스트여야 합니다."
        if len(value) == 0 and spec.get("required"):
            return False, f"'{spec['label']}' 최소 1개 이상."

    return True, None


def validate_application(app: dict) -> tuple:
    """
    전체 신청서 검증.

    Returns:
        (ok: bool, errors: dict[field, msg])
    """
    errors = {}
    for field_name, value in app.items():
        ok, msg = validate_field(field_name, value)
        if not ok:
            errors[field_name] = msg
    return (len(errors) == 0), errors


# ====================================================================
# 진행률 / 결측 필드
# ====================================================================

def get_missing_required(app: dict, track: Optional[str] = None) -> list:
    """현재 신청서에 빠진 필수 필드 키 리스트 (해당 사업 것만)."""
    missing = []
    for k in all_required_fields(track):
        v = app.get(k)
        if v is None or v == "" or (isinstance(v, list) and len(v) == 0):
            missing.append(k)
    return missing


def get_missing_optional(app: dict, track: Optional[str] = None) -> list:
    """빠진 선택 필드."""
    missing = []
    for k in all_optional_fields(track):
        v = app.get(k)
        if v is None or v == "" or (isinstance(v, list) and len(v) == 0):
            missing.append(k)
    return missing


def calculate_progress(app: dict, track: Optional[str] = None) -> dict:
    """
    신청서 완성도 계산.

    track을 주면 그 사업의 필드만 센다 — 안 주면 공공+민간 전부를 세서
    민간 사용자가 영원히 100%에 못 닿는다.

    Returns:
        {
            "required_filled": int,
            "required_total": int,
            "required_pct": float,
            "optional_filled": int,
            "optional_total": int,
            "overall_pct": float,
            "missing_required": list[str],
            "is_ready_for_draft": bool,
        }
    """
    req = all_required_fields(track)
    opt = all_optional_fields(track)
    missing_req = get_missing_required(app, track)
    missing_opt = get_missing_optional(app, track)

    req_filled = len(req) - len(missing_req)
    opt_filled = len(opt) - len(missing_opt)
    total = len(req) + len(opt)
    filled = req_filled + opt_filled

    return {
        "required_filled": req_filled,
        "required_total": len(req),
        "required_pct": round(req_filled / len(req) * 100, 1) if req else 100,
        "optional_filled": opt_filled,
        "optional_total": len(opt),
        "optional_pct": round(opt_filled / len(opt) * 100, 1) if opt else 100,
        "overall_pct": round(filled / total * 100, 1) if total else 100,
        "missing_required": missing_req,
        "missing_required_labels": [
            FIELDS[k]["label"] for k in missing_req
        ],
        "is_ready_for_draft": len(missing_req) == 0,
        "track": track,
    }


def get_field_labels() -> dict:
    """field_name → 한국어 라벨 매핑."""
    return {k: v["label"] for k, v in FIELDS.items()}


def empty_application() -> dict:
    """모든 필드가 None인 빈 신청서."""
    return {k: None for k in FIELDS}
