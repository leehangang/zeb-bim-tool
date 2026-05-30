"""
core/intake_schema.py — 사업 신청서 스키마
==========================================
공공건축물 그린리모델링 사업 신청서에 필요한 항목 정의.
출처: 01_GR_가이드라인.pdf 사업 신청 양식 (필수/선택 분류는 졸업설계 단계 추정).

설계:
    - FIELDS: 각 필드의 메타데이터 (한국어 라벨, 타입, 필수 여부, 선택지, 검증 룰)
    - SECTIONS: 신청서 구조 (기관/건축물/사업/기술요소 4섹션)
    - validate_field(): 단일 필드 값 검증
    - calculate_progress(): 현재 신청서 dict의 완성도(%)
    - get_missing_required(): 빠진 필수 항목 리스트
"""

from typing import Optional


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
        "section": "기관",
        "type": "string",
        "required": True,
        "example": "김천시청",
        "help": "사업 신청 주체 (지자체 또는 공공기관)",
    },
    "contact_person": {
        "label": "담당자명",
        "section": "기관",
        "type": "string",
        "required": True,
        "example": "홍길동 주무관",
    },
    "contact_phone": {
        "label": "담당자 연락처",
        "section": "기관",
        "type": "phone",
        "required": True,
        "example": "054-420-6000",
    },
    "contact_email": {
        "label": "담당자 이메일",
        "section": "기관",
        "type": "email",
        "required": False,
        "example": "official@gimcheon.go.kr",
    },

    # ────── 2. 대상 건축물 정보 ──────
    "building_name": {
        "label": "건축물명",
        "section": "건축물",
        "type": "string",
        "required": True,
        "example": "김천 도담어린이집",
    },
    "building_address": {
        "label": "소재지",
        "section": "건축물",
        "type": "string",
        "required": True,
        "example": "경상북도 김천시 ○○로 12",
    },
    "building_usage": {
        "label": "용도",
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
        "section": "건축물",
        "type": "year",
        "required": True,
        "example": 2014,
        "help": "최초 사용승인일 기준 연도. 노후도 점수 산정에 사용.",
    },
    "total_area_m2": {
        "label": "연면적 (㎡)",
        "section": "건축물",
        "type": "number",
        "required": True,
        "example": 1251,
        "min": 1,
    },
    "building_area_m2": {
        "label": "건축면적 (㎡)",
        "section": "건축물",
        "type": "number",
        "required": False,
        "example": 600,
        "min": 1,
    },
    "structure": {
        "label": "구조",
        "section": "건축물",
        "type": "enum",
        "required": False,
        "options": ["철근콘크리트", "철골", "조적", "목구조", "혼합구조", "기타"],
        "example": "철근콘크리트",
    },
    "floors": {
        "label": "층수",
        "section": "건축물",
        "type": "string",
        "required": False,
        "example": "지하1층 / 지상2층",
    },
    "directly_owned": {
        "label": "직접 소유 여부",
        "section": "건축물",
        "type": "boolean",
        "required": False,
        "example": True,
        "help": "신청기관이 직접 소유. True면 사업여건 점수 가산.",
    },

    # ────── 3. 사업 계획 ──────
    "project_type": {
        "label": "사업유형",
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
        "section": "사업",
        "type": "integer",
        "required": True,
        "options": [1, 2, 3, 4, 5],
        "example": 5,
        "min": 1, "max": 5,
    },
    "energy_saving_target_pct": {
        "label": "에너지 절감 목표 (%)",
        "section": "사업",
        "type": "number",
        "required": True,
        "example": 30,
        "min": 0, "max": 100,
        "help": "공사 전·후 1차 에너지소요량 절감률 목표.",
    },
    "project_duration_months": {
        "label": "사업 기간 (개월)",
        "section": "사업",
        "type": "integer",
        "required": True,
        "example": 8,
        "min": 1, "max": 48,
    },
    "total_budget_won": {
        "label": "총사업비 (원)",
        "section": "사업",
        "type": "number",
        "required": True,
        "example": 290_000_000,
        "min": 0,
        "help": "Max Cost (부가세 포함) 추정값. ROI 시뮬레이션 결과 활용 가능.",
    },
    "is_seoul_or_public": {
        "label": "서울/중앙/공공 여부",
        "section": "사업",
        "type": "boolean",
        "required": True,
        "example": True,
        "help": "True면 보조율 50%, False면 그외 지자체 70%.",
    },

    # ────── 4. 적용 기술 요소 ──────
    "applied_elements": {
        "label": "적용 GR 기술요소",
        "section": "기술요소",
        "type": "list",
        "required": True,
        "example": ["고성능창호", "외벽단열보강", "고효율 EHP", "태양광"],
        "help": "01 가이드라인 11개 기술요소 중 선택. 최소 3개 이상 권장.",
    },
    "climate_adaptation_elements": {
        "label": "기후위기적응 요소",
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


def fields_by_section(section: str) -> list:
    """특정 섹션에 속한 필드 키 리스트."""
    return [k for k, v in FIELDS.items() if v["section"] == section]


def all_required_fields() -> list:
    """필수 필드 키 리스트."""
    return [k for k, v in FIELDS.items() if v.get("required")]


def all_optional_fields() -> list:
    """선택 필드 키 리스트."""
    return [k for k, v in FIELDS.items() if not v.get("required")]


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

def get_missing_required(app: dict) -> list:
    """현재 신청서에 빠진 필수 필드 키 리스트."""
    missing = []
    for k in all_required_fields():
        v = app.get(k)
        if v is None or v == "" or (isinstance(v, list) and len(v) == 0):
            missing.append(k)
    return missing


def get_missing_optional(app: dict) -> list:
    """빠진 선택 필드."""
    missing = []
    for k in all_optional_fields():
        v = app.get(k)
        if v is None or v == "" or (isinstance(v, list) and len(v) == 0):
            missing.append(k)
    return missing


def calculate_progress(app: dict) -> dict:
    """
    신청서 완성도 계산.

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
    req = all_required_fields()
    opt = all_optional_fields()
    missing_req = get_missing_required(app)
    missing_opt = get_missing_optional(app)

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
    }


def get_field_labels() -> dict:
    """field_name → 한국어 라벨 매핑."""
    return {k: v["label"] for k, v in FIELDS.items()}


def empty_application() -> dict:
    """모든 필드가 None인 빈 신청서."""
    return {k: None for k in FIELDS}
