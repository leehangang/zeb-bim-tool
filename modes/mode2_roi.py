"""
modes/mode2_roi.py — ROI 시뮬레이션 (Function Calling) UI
==========================================================
사용자 자연어 입력 → Claude Function Calling → core.roi_calculator 호출
→ 결과를 자연어로 답변.

처리 흐름:
    "연면적 1,200㎡, ZEB 5등급 목표로 그린리모델링하면?"
    → Claude tool_use: calculate_zeb_roi(total_area_m2=1200, zeb_target_grade=5)
    → dispatch_tool() → core.roi_calculator.calculate_roi() 실행
    → tool_result로 Max Cost, 보조금, 회수기간 등 반환
    → Claude가 자연어 답변 + 출처 표기

구조:
    - run_roi_simulation():   순수 함수 (Streamlit 의존 X)
    - render_roi_panel():     Streamlit UI (의존 O)

도구 명세 + 디스패처는 core.roi_tools 에 위치.
"""

from typing import Optional


# ====================================================================
# 순수 함수 (테스트 가능)
# ====================================================================

def run_roi_simulation(
    user_message: str,
    max_tokens: int = 1500,
    max_iterations: int = 5,
) -> dict:
    """
    사용자 자연어 메시지 → ROI 시뮬레이션 결과 + Claude 답변.

    Args:
        user_message: "연면적 1200㎡, ZEB 5등급 목표" 같은 자연어
        max_tokens: Claude 응답 최대 토큰
        max_iterations: Function Calling 루프 최대 횟수

    Returns:
        {
            "answer":      자연어 답변,
            "tool_calls":  [{"name":..., "input":..., "result":...}, ...],
            "model":       Claude 모델명,
            "usage":       {"input_tokens":..., "output_tokens":...},
            "iterations":  Function Calling 반복 횟수,
        }
    """
    from core.llm_client import call_with_tools
    from core.roi_tools import TOOLS, dispatch_tool, SYSTEM_PROMPT_KO

    raw = call_with_tools(
        system=SYSTEM_PROMPT_KO,
        user=user_message,
        tools=TOOLS,
        dispatcher=dispatch_tool,
        max_tokens=max_tokens,
        max_iterations=max_iterations,
    )
    # mode1_rag.answer_question 과 인터페이스 통일 (text → answer)
    return {
        "answer": raw["text"],
        "tool_calls": raw["tool_calls"],
        "model": raw["model"],
        "usage": raw["usage"],
        "iterations": raw["iterations"],
    }


# ====================================================================
# Streamlit UI
# ====================================================================

def render_roi_panel() -> None:
    """Mode 2 (ROI 시뮬레이션) Streamlit 패널."""
    import streamlit as st

    st.markdown("""
    <div style="margin-bottom:1.5rem;">
        <div style="font-size:0.85rem; color:#2E7D32; font-weight:600; letter-spacing:0.08em;">
            MODE 02 · NATURAL LANGUAGE ROI
        </div>
        <h1 style="margin:0.2rem 0;">💰 ROI 시뮬레이션</h1>
        <div style="color:#757575;">
            자연어로 건물 정보를 알려주시면 Claude가 파라미터를 추출해
            07 단가DB · 08 간접공사비 · 01 보조금 · 04 용적률 · 05 취득세 감면을
            한 번에 산출합니다.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 세션 상태 — 대화 히스토리 (단순 1턴씩 처리, 멀티턴 미지원)
    if "_mode2_history" not in st.session_state:
        st.session_state["_mode2_history"] = []

    # 예시 입력
    with st.expander("💡 예시 입력"):
        examples = [
            ("도담어린이집 시나리오",
             "도담어린이집인데, 연면적 1,251㎡짜리 어린이집이고 "
             "외벽 단열 안 된 부분이 887㎡, 창호 100㎡, 단열문 28.85㎡ 교체할 거야. "
             "ZEB 5등급 목표로 200㎡ 증축까지 포함해서 ROI 계산해줘."),
            ("간단 시나리오",
             "연면적 800㎡짜리 공공건물을 ZEB 4등급으로 그린리모델링하면 "
             "비용이랑 보조금이 얼마나 돼?"),
            ("등급 비교 (1등급 vs 5등급)",
             "연면적 1500㎡ 어린이집을 ZEB 1등급으로 했을 때랑 "
             "5등급으로 했을 때 인센티브 차이가 얼마나 나?"),
            ("지자체 보조율 케이스",
             "수도권 외 지자체 공공건축물 2,000㎡ 인데 보조율 70% 적용되면 "
             "자부담 얼마인지 ZEB 3등급 기준으로 알려줘."),
        ]
        for i, (label, prompt) in enumerate(examples):
            if st.button(label, key=f"ex_roi_{i}", use_container_width=True):
                st.session_state["_mode2_question_seed"] = prompt
                st.rerun()

    # 입력
    seed = st.session_state.pop("_mode2_question_seed", "")
    user_message = st.text_area(
        "건물 정보를 자연어로 입력하세요",
        value=seed,
        height=120,
        placeholder=(
            "예: 연면적 1,200㎡짜리 공공도서관을 ZEB 5등급으로 그린리모델링하려고 합니다. "
            "외벽 단열 보강이 500㎡ 필요하고 창호 80㎡ 교체 예정입니다. "
            "총 사업비랑 자부담, 회수기간 알려주세요."
        ),
    )

    col_run, col_clear = st.columns([1, 4])
    with col_run:
        run_btn = st.button("시뮬레이션 실행", type="primary", use_container_width=True)
    with col_clear:
        if st.button("히스토리 지우기"):
            st.session_state["_mode2_history"] = []
            st.rerun()

    if not run_btn or not user_message.strip():
        if st.session_state["_mode2_history"]:
            _render_history()
        else:
            st.info("👆 위에 자연어로 건물 정보를 입력하고 **시뮬레이션 실행** 버튼을 눌러주세요.")
        return

    # 실행
    try:
        with st.spinner("Claude가 파라미터 추출 + ROI 산정 중..."):
            result = run_roi_simulation(user_message)
    except Exception as e:
        from core.error_messages import friendly_error
        st.error(friendly_error(e))
        return

    # 히스토리 저장 후 표시
    st.session_state["_mode2_history"].append({
        "question": user_message,
        "result": result,
    })
    _render_history()


def _render_history() -> None:
    """대화 히스토리 렌더 (최신이 위)."""
    import streamlit as st
    history = st.session_state["_mode2_history"]
    if not history:
        return

    for i, entry in enumerate(reversed(history)):
        idx = len(history) - i
        result = entry["result"]
        with st.container(border=True):
            st.markdown(f"**🙋 질문 #{idx}**")
            st.markdown(entry["question"])

            st.markdown("**🤖 답변**")
            st.markdown(result["answer"])

            # 도구 호출 정보
            if result.get("tool_calls"):
                with st.expander(
                    f"🔧 도구 호출 ({len(result['tool_calls'])}회)"
                ):
                    for j, tc in enumerate(result["tool_calls"], 1):
                        st.markdown(f"**호출 {j}: `{tc['name']}`**")
                        st.markdown("**입력:**")
                        st.json(tc["input"])
                        st.markdown("**결과:**")
                        if tc.get("is_error"):
                            st.error(tc["result"])
                        else:
                            st.json(tc["result"])

            # 메타 (모델 + 토큰)
            with st.expander("ℹ️ API 호출 정보"):
                st.json({
                    "model": result.get("model"),
                    "usage": result.get("usage", {}),
                    "iterations": result.get("iterations"),
                })
