"""
core/roi_tools.py — Mode 2 Function Calling 도구
=================================================
Claude API에 노출할 ROI 시뮬레이션 도구 정의 + 디스패처.

설계:
    - 단일 도구 `calculate_zeb_roi` 만 노출 (Claude 혼란 최소화)
    - 통합 함수 `core.roi_calculator.calculate_roi()` 가 백엔드
    - 입력 스키마는 자연어에서 추출하기 좋게 명확한 description + default

워크플로우:
    1. 사용자 자연어 입력
    2. Claude가 calculate_zeb_roi tool_use 발생 (입력 자동 추출)
    3. dispatch_tool() 가 core.roi_calculator.calculate_roi() 호출
    4. 결과를 Claude에 반환 → Claude가 자연어로 풀어서 답변
"""

import os
from typing import Optional


# ====================================================================
# 도구 명세 (Claude API tool schema)
# ====================================================================

CALCULATE_ZEB_ROI_TOOL = {
    "name": "calculate_zeb_roi",
    "description": (
        "건물의 그린리모델링 사업비, GR 보조금, 용적률 완화 자산가치, "
        "취득세 감면, 연간 에너지 절감액, 회수기간 등 ZEB 통합 ROI를 "
        "한 번에 산출합니다. "
        "07 조달청 단가DB, 08 간접공사비 매트릭스, 01 GR 가이드라인 보조율, "
        "04 녹색건축법 §15, 05 지방세특례 §47의2 를 모두 적용합니다. "
        "연면적과 보강 대상 면적(외벽·창호·문)을 입력으로 받습니다."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "total_area_m2": {
                "type": "number",
                "description": (
                    "건물 연면적 (㎡). 필수. 예: 도담어린이집 1,251㎡."
                ),
            },
            "wall_no_insulation_m2": {
                "type": "number",
                "description": (
                    "외벽 중 단열재 없는 면적 (㎡). 보강 대상. "
                    "기본 0 (보강 안 함)."
                ),
                "default": 0,
            },
            "window_area_m2": {
                "type": "number",
                "description": (
                    "교체 대상 창호 면적 (㎡). 고성능 복층유리로 교체 가정. "
                    "기본 0."
                ),
                "default": 0,
            },
            "door_area_m2": {
                "type": "number",
                "description": (
                    "교체 대상 단열문 면적 (㎡). 기본 0."
                ),
                "default": 0,
            },
            "zeb_target_grade": {
                "type": "integer",
                "description": (
                    "목표 ZEB 등급 (1=가장 높음 ~ 5=가장 낮음). "
                    "용적률 완화율과 취득세 감면율에 영향. 기본 5."
                ),
                "default": 5,
            },
            "is_seoul_or_public": {
                "type": "boolean",
                "description": (
                    "서울 또는 중앙·공공 건축물 여부. "
                    "True면 보조율 50%, False면 그외 지자체 70%. 기본 True."
                ),
                "default": True,
            },
            "is_signature": {
                "type": "boolean",
                "description": (
                    "GR 시그니처 사업 여부 (선도기술 적용). "
                    "True면 단위면적당 지원한도 상향. 기본 False."
                ),
                "default": False,
            },
            "project_duration_months": {
                "type": "integer",
                "description": (
                    "예상 공사 기간 (개월). 08 간접공사비 매트릭스의 "
                    "공사기간 구간(6/12/36개월)에 따라 율 다름. 기본 8."
                ),
                "default": 8,
            },
            "extension_area_m2": {
                "type": "number",
                "description": (
                    "증축 면적 (㎡). 0이면 증축 없이 리모델링만. "
                    "0보다 크면 신축비 + 용적률 보너스 자산가치 + "
                    "취득세 감면 계산에 사용. 기본 0."
                ),
                "default": 0,
            },
            "land_price_per_pyeong": {
                "type": "number",
                "description": (
                    "토지 평당가 (원). 용적률 보너스 자산가치 산정용. "
                    "기본 15,000,000원/평 (도담 인근 시세)."
                ),
                "default": 15_000_000,
            },
            "build_cost_per_pyeong": {
                "type": "number",
                "description": (
                    "증축 신축비 평당 (원). 기본 9,750,000원/평."
                ),
                "default": 9_750_000,
            },
            "annual_energy_saving_won_per_m2": {
                "type": "number",
                "description": (
                    "연간 단위면적당 에너지 절감액 (원/㎡·년). "
                    "ZEB 5등급 도담 케이스 기본 9,900원."
                ),
                "default": 9_900,
            },
            "analysis_years": {
                "type": "integer",
                "description": (
                    "경제성 분석기간 (년). NPV/IRR/B-C 산정용. "
                    "외피·창호 내용연수 기준 기본 20년."
                ),
                "default": 20,
            },
            "discount_rate": {
                "type": "number",
                "description": (
                    "사회적 할인율 (소수). NPV 현재가치 환산용. "
                    "KDI 예비타당성조사 기준 기본 0.045(4.5%)."
                ),
                "default": 0.045,
            },
            "energy_escalation": {
                "type": "number",
                "description": (
                    "연간 에너지 단가 상승률 (소수). 절감액 증가 반영. "
                    "전기·가스 장기 추세 기본 0.025(2.5%)."
                ),
                "default": 0.025,
            },
        },
        "required": ["total_area_m2"],
    },
}


# 도구 리스트 (Claude API에 그대로 전달)
TOOLS = [CALCULATE_ZEB_ROI_TOOL]


# ====================================================================
# 디스패처
# ====================================================================

def dispatch_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Claude tool_use를 받아 실제 함수 호출 → 결과 반환.

    Args:
        tool_name: Claude가 요청한 도구 이름
        tool_input: 도구 입력 dict

    Returns:
        결과 dict (Claude에 tool_result로 전달됨)
    """
    if tool_name == "calculate_zeb_roi":
        return _dispatch_calculate_zeb_roi(tool_input)
    return {"error": f"알 수 없는 도구: {tool_name}"}


def _dispatch_calculate_zeb_roi(args: dict) -> dict:
    """
    calculate_zeb_roi 도구 호출 → core.roi_calculator.calculate_roi() 위임.

    Claude가 자연어에서 추출한 dict를 (bim_input, building_info) 두 dict로
    분리해서 전달.
    """
    from core.roi_calculator import calculate_roi

    # 입력 검증 — total_area_m2는 필수
    total_area = args.get("total_area_m2")
    if total_area is None or total_area <= 0:
        return {"error": "total_area_m2(연면적)이 필요합니다 (양수)."}

    # bim_input: 보강 대상 면적들
    bim_input = {
        "wall_no_insulation_m2": float(args.get("wall_no_insulation_m2", 0)),
        "window_area_m2": float(args.get("window_area_m2", 0)),
        "door_area_m2": float(args.get("door_area_m2", 0)),
    }

    # building_info: 건물 / 사업 정보
    building_info = {
        "total_area_m2": float(total_area),
        "zeb_target_grade": int(args.get("zeb_target_grade", 5)),
        "is_seoul_or_public": bool(args.get("is_seoul_or_public", True)),
        "is_signature": bool(args.get("is_signature", False)),
        "project_duration_months": int(args.get("project_duration_months", 8)),
        "extension_area_m2": float(args.get("extension_area_m2", 0)),
        "land_price_per_pyeong": float(
            args.get("land_price_per_pyeong", 15_000_000)
        ),
        "build_cost_per_pyeong": float(
            args.get("build_cost_per_pyeong", 9_750_000)
        ),
        "annual_energy_saving_won_per_m2": float(
            args.get("annual_energy_saving_won_per_m2", 9_900)
        ),
        "analysis_years": int(args.get("analysis_years", 20)),
        "discount_rate": float(args.get("discount_rate", 0.045)),
        "energy_escalation": float(args.get("energy_escalation", 0.025)),
    }

    try:
        result = calculate_roi(bim_input, building_info)
    except Exception as e:
        return {
            "error": f"ROI 산정 실패: {type(e).__name__}: {e}",
            "_inputs": {"bim_input": bim_input, "building_info": building_info},
        }

    # Claude가 자연어로 풀기 좋게 핵심 지표를 요약
    return {
        "Max_Cost_원": result["max_cost"],
        "직접공사비_원": result["boq"]["직접공사비_합계"] if "직접공사비_합계" in result.get("boq", {}) else 0,
        "보조금": {
            "보조율": result["subsidy"]["보조율"],
            "보조금_원": result["subsidy"]["보조금"],
            "자부담_원": result["subsidy"]["자부담"],
        },
        "용적률_완화": {
            "보너스율": result["far_bonus"]["용적률_보너스율"],
            "추가_연면적_m2": result["far_bonus"]["추가_연면적_m2"],
            "자산가치_원": result["far_bonus"]["자산가치"],
        },
        "취득세_감면": {
            "감면율": result["tax_relief"]["감면율"],
            "감면액_원": result["tax_relief"]["감면액"],
        },
        "신축비_원": result["build_cost"],
        "연간_절감액_원": result["annual_saving"],
        "총_투자_원": result["total_investment"],
        "즉시_수혜_원": result["immediate_benefit"],
        "순_투자_원": result["net_investment"],
        "자산화_ROI_pct": result["asset_roi_pct"],
        "GR_단독_회수기간_년": result["gr_only_payback_years"],
        "통합_회수기간_년": result["combined_payback_years"],
        "수익성_지표": (
            {
                "NPV_원": result["cashflow"]["NPV_원"],
                "IRR": result["cashflow"]["IRR"],
                "BC_ratio": result["cashflow"]["BC_ratio"],
                "할인회수_년": result["cashflow"]["할인회수_년"],
                "명목총절감_원": result["cashflow"]["명목총절감_원"],
                "편익현재가치_원": result["cashflow"]["편익현재가치_원"],
                "분석기간_년": result["cashflow"]["분석기간_년"],
                "할인율": result["cashflow"]["할인율"],
                "에너지상승률": result["cashflow"]["에너지상승률"],
            }
            if result.get("cashflow") else None
        ),
        "_BOQ_세부": result["boq"].get("items", []),
        "_적용율": result["indirect"].get("_적용율", {}),
    }


# ====================================================================
# 시스템 프롬프트 (Mode 2 전용)
# ====================================================================

SYSTEM_PROMPT_KO = """당신은 한국의 그린리모델링 ROI 컨설턴트입니다.
사용자가 자연어로 건물 정보(연면적, 보강 대상 면적, 목표 ZEB 등급 등)를 알려주면,
calculate_zeb_roi 도구를 호출해 정확한 사업비, 보조금, 인센티브, 회수기간을 산출하세요.

행동 지침:
1. 필수값(total_area_m2)이 누락되었으면, 사용자에게 명확히 되묻거나 합리적 기본값을 가정하고
   가정값을 명시한 뒤 진행하세요.
2. 보강 면적(외벽·창호·문)이 안 알려졌으면 0으로 가정합니다.
3. 도구 결과를 받으면 핵심 지표(Max Cost / 보조금 / 자부담 / 회수기간)와
   수익성 지표(NPV / IRR / B-C / 할인회수기간)를 원 또는 억 단위로 자연어로 풀어서 설명하세요.
   특히 NPV·IRR·B-C는 단순 회수기간보다 강한 경제성 근거이니 반드시 함께 제시하세요.
4. 단위와 출처를 명확히 표시하세요. 예: "Max Cost 2.92억원 (07 단가DB + 08 간접공사비 적용)"
5. 비교 시나리오 요청 시(예: "5등급 vs 1등급 비교") 도구를 여러 번 호출해 표로 비교하세요.
6. 추정치임을 명확히 알리세요. 실제 사업 시엔 공식 컨설팅 필요.
"""
