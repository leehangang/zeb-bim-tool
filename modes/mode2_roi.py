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

    from core.ui_theme import concept_divider

    st.markdown("""
    <div style="margin-bottom:1rem;">
        <div style="font-size:0.85rem; color:#2E7D32; font-weight:600; letter-spacing:0.08em;">
            MODE 02 · NATURAL LANGUAGE ROI
        </div>
        <h1 style="margin:0.2rem 0;">💰 ROI 시뮬레이션</h1>
        <div style="color:#757575;">
            건물 정보를 <b>문장으로 쓰면</b> 연면적·보강 면적·목표 등급·소유 주체·공사 기간을
            알아서 읽어 계산합니다.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 그린리모델링 vs ZEB 역할 구분 (헷갈림 방지)
    st.markdown(
        concept_divider(
            gr_text="공사비(Max Cost) · 보조금 · 자부담 · 회수기간 등 <b>사업 경제성</b>을 계산합니다.",
            zeb_text=(
                "입력한 <b>목표 등급</b>은 취득세 감면·용적률 완화·인증 수수료 환불 등 "
                "<b>인센티브</b>에 반영됩니다. 단 <b>취득세 감면은 신축·증축·개축분만</b> 해당해 "
                "(지방세특례제한법 §47조의2, <b>2026-12-31 일몰</b>) 단순 리모델링은 0원이고, "
                "<b>수수료 환불</b>은 의무 대상이 아닌 자율 인증에만 발생하는데 "
                "<b>적용 기한 쟁점</b>이 있습니다 → 📐 근거·출처"
            ),
        ),
        unsafe_allow_html=True,
    )

    # 무엇이 나오는지 — 두 박스 아래. "ROI"만 적어두면 뭘 주는지 알 수 없다.
    st.markdown("**나오는 수치**")
    _c = st.columns(4)
    _outs = [
        ("💵 Max Cost", "총 공사비", "조달청 단가DB × 보강 물량 + 간접공사비"),
        ("🏛 보조금 · 자부담", "실제 낼 돈", "소유 주체별 보조율 50% / 70%"),
        ("📈 NPV · IRR · B/C", "투자 가치", "20년 현금흐름 · 할인율 4.5%"),
        ("⏱ 회수기간", "몇 년에 본전", "단순 회수 + 할인 회수"),
    ]
    for _col, (_t, _sub, _how) in zip(_c, _outs):
        with _col:
            st.markdown(f"**{_t}**<br><span style='font-size:0.82rem;'>{_sub}</span>",
                        unsafe_allow_html=True)
            st.caption(_how)
    st.caption(
        "여기에 **취득세 감면 · 용적률 완화 · 인증 수수료 환불**을 목표 등급에 따라 더합니다. "
        "숫자는 전부 엔진이 계산합니다 — LLM은 문장에서 조건만 읽습니다."
    )
    st.divider()

    # 세션 상태 — 대화 히스토리 (단순 1턴씩 처리, 멀티턴 미지원)
    if "_mode2_history" not in st.session_state:
        st.session_state["_mode2_history"] = []

    # 예시 입력 — 정책 Q&A처럼 **문장을 그대로** 보여준다.
    #
    # 왜 바꿨나: 예전엔 "간단 시나리오"·"지자체 보조율 케이스" 같은 라벨만 보였다.
    #   (1) 뭘 물어보는지 눌러야 알 수 있고
    #   (2) 어떻게 써야 엔진이 알아듣는지 배울 수가 없었다.
    #   각 예시는 도구(core/roi_tools.py)가 실제로 받는 인자를 태우도록 짰다.
    #
    # 🔴 "수도권 외 지자체 … 70%"라 적혀 있던 걸 정정했다. 보조율 기준은 **수도권 여부가
    #    아니라 소유 주체**다 — 공고 원문: "서울특별시, 중앙·공공기관은 50%, 그 외
    #    지방자치단체는 70%". 경기도 지자체 건물도 70%다.
    with st.expander("💡 예시 입력 — 클릭하면 자동 입력",
                     expanded=not st.session_state.get("_mode2_history")):
        st.caption("눌러서 그대로 실행하거나, 숫자만 바꿔 보세요.")
        # (라벨, 문장) — 라벨이 없으면 6개 문장이 다 비슷해 보여 뭘 눌러야 할지 모른다.
        examples = [
            ("🏫 우리 검증 케이스 — 전 항목",
             # 도담 실제 물량. 도구(core/roi_tools.py)의 인자를 전부 태운다.
             "KEPCO 도담어린이집입니다. 연면적 1,251㎡ 노유자시설이고 공공기관 소유예요. "
             "외벽 단열 안 된 부분 887㎡, 창호 100㎡, 단열문 28.85㎡를 교체하려 합니다. "
             "ZEB 5등급 목표, 공사 8개월 예상입니다. Max Cost와 보조금·자부담·회수기간 알려주세요."),

            ("🏛 보조율 50% vs 70% — 기준은 소유 주체",
             # 🔴 "수도권 외 지자체 70%"라 적혀 있던 걸 정정했다. 기준은 수도권 여부가
             #    아니라 소유 주체다 — "서울시·중앙·공공기관 50%, 그 외 지자체 70%".
             #    경기도 지자체 건물도 70%다.
             "연면적 2,000㎡ 지자체 소유 공공건축물입니다. 서울시나 중앙기관이 아니라 "
             "지방자치단체 소유라 보조율 70%가 맞는지, 그러면 자부담이 얼마인지 "
             "ZEB 3등급 기준으로 알려주세요."),

            ("🧾 취득세 감면 — 증축이 없으면 0원",
             # §47조의2는 신축·증축·개축분만. 단순 리모델링은 감면이 안 붙는다.
             "1,500㎡ 건물을 ZEB 4등급으로 리모델링하는데 증축은 안 합니다. "
             "취득세 감면을 받을 수 있나요? 200㎡ 증축하면 얼마나 달라지는지도 비교해주세요."),

            ("⚖️ 등급이 인센티브를 얼마나 흔드나",
             "연면적 1,500㎡ 어린이집을 ZEB 1등급으로 할 때와 5등급으로 할 때 "
             "용적률 완화·취득세 감면·인증 수수료 환불이 각각 얼마나 차이 나나요?"),

            ("🔁 우리 가정을 실제 고지서로 뒤집기",
             # 절감액이 NPV·회수기간을 지배한다. 사용자가 실측값을 넣는 법.
             "연면적 1,251㎡인데 실제 전기요금 고지서로 계산한 연간 절감액이 "
             "㎡당 7,000원입니다. 기본 가정 말고 이 값으로 NPV와 회수기간을 다시 계산해주세요."),

            ("📆 공사 기간이 간접공사비를 바꾼다",
             # 08 매트릭스는 6/12/36개월 구간별 요율이 다르다.
             "800㎡ 공공건물 그린리모델링인데 공사 기간을 8개월로 할 때와 18개월로 할 때 "
             "간접공사비 차이가 얼마나 나나요? ZEB 5등급 기준입니다."),
        ]
        for i, (label, prompt) in enumerate(examples):
            st.markdown(f"<div style='margin-top:0.6rem; font-size:0.86rem; "
                        f"color:#5A6C7A;'><b>{label}</b></div>",
                        unsafe_allow_html=True)
            if st.button(prompt, key=f"ex_roi_{i}", width="stretch"):
                # 위젯 key에 직접 주입 → rerun 후에도 입력창에 유지되고,
                # '시뮬레이션 실행'을 눌러 다시 rerun돼도 내용이 보존됨.
                st.session_state["_mode2_input"] = prompt
                st.rerun()

    # 입력 — key 사용으로 예시 시드/직접 타이핑 모두 rerun 후에도 유지.
    # (value=만 쓰면 실행 버튼 클릭 시 rerun에서 초기화돼 빈 입력으로 처리되는 버그)
    user_message = st.text_area(
        "건물 정보를 자연어로 입력하세요",
        key="_mode2_input",
        height=120,
        placeholder=(
            "예: 연면적 1,200㎡짜리 공공도서관을 ZEB 5등급으로 그린리모델링하려고 합니다. "
            "외벽 단열 보강이 500㎡ 필요하고 창호 80㎡ 교체 예정입니다. "
            "총 사업비랑 자부담, 회수기간 알려주세요."
        ),
    )

    col_run, col_clear = st.columns([1, 4])
    with col_run:
        run_btn = st.button("시뮬레이션 실행", type="primary", width="stretch")
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
        with st.spinner("입력 조건 추출 + ROI 산정 중..."):
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
