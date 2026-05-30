"""
modes/mode4_intake.py — 사업 신청 인테이크 (Function Calling) UI
==================================================================
공공건축물 그린리모델링 사업 신청서 작성을 단계적으로 도와주는 챗봇.

처리 흐름:
    1. 사용자 메시지 입력
    2. Claude가 자연어에서 필드 추출 → update_application 도구 호출
    3. IntakeSession이 검증 + 저장 + 다음 질문 추천
    4. Claude가 다음 질문 자연어로 생성
    5. 필수 항목 모두 채워지면 generate_draft 호출 → 마크다운 신청서
    6. 사용자는 진행률, 미리보기, 최종 신청서를 UI에서 확인

구조:
    - run_intake_turn():    순수 함수 (Streamlit 의존 X, 테스트 가능)
    - render_intake_panel(): Streamlit UI (의존 O)

상태:
    - IntakeSession 객체를 st.session_state['_mode4_session']에 보관
    - 대화 히스토리는 st.session_state['_mode4_history']
"""

from typing import Optional


# ====================================================================
# 순수 함수 (테스트 가능)
# ====================================================================

def run_intake_turn(
    user_message: str,
    session,
    max_tokens: int = 1500,
    max_iterations: int = 5,
) -> dict:
    """
    한 턴의 인테이크 대화 실행.

    Args:
        user_message: 사용자 입력
        session: core.intake_tools.IntakeSession 인스턴스 (상태 보유)

    Returns:
        {
            "answer":      Claude의 자연어 응답,
            "tool_calls":  도구 호출 로그,
            "progress":    현재 진행률 dict,
            "draft":       생성된 마크다운 (없으면 None),
            "usage":       토큰 사용량,
            "iterations":  Function Calling 반복 횟수,
        }
    """
    from core.llm_client import call_with_tools
    from core.intake_tools import get_tools, SYSTEM_PROMPT_KO

    # 시스템 프롬프트에 현재 진행 상태 포함 (Claude가 컨텍스트 알도록)
    progress = session.get_progress()
    current_state_md = _render_current_state_for_prompt(session, progress)

    augmented_system = (
        SYSTEM_PROMPT_KO
        + "\n\n현재 신청서 상태:\n"
        + current_state_md
    )

    raw = call_with_tools(
        system=augmented_system,
        user=user_message,
        tools=get_tools(),
        dispatcher=session.make_dispatcher(),
        max_tokens=max_tokens,
        max_iterations=max_iterations,
    )

    # 이번 턴에 draft가 생성됐는지 확인
    draft = None
    for tc in raw["tool_calls"]:
        if tc["name"] == "generate_draft":
            result = tc["result"]
            if isinstance(result, dict) and "draft_markdown" in result:
                draft = result["draft_markdown"]
                break

    return {
        "answer": raw["text"],
        "tool_calls": raw["tool_calls"],
        "progress": session.get_progress(),
        "draft": draft,
        "model": raw["model"],
        "usage": raw["usage"],
        "iterations": raw["iterations"],
    }


def _render_current_state_for_prompt(session, progress: dict) -> str:
    """시스템 프롬프트용 현재 상태 요약."""
    from core.intake_schema import FIELDS
    lines = []
    lines.append(
        f"- 필수 항목 진행: {progress['required_filled']}/"
        f"{progress['required_total']} ({progress['required_pct']}%)"
    )
    lines.append(
        f"- 신청서 초안 생성 가능: "
        f"{'예 (모든 필수 채워짐)' if progress['is_ready_for_draft'] else '아니오'}"
    )
    if progress["missing_required_labels"]:
        lines.append(
            f"- 아직 빠진 필수 항목: "
            f"{', '.join(progress['missing_required_labels'][:6])}"
            + ("..." if len(progress['missing_required_labels']) > 6 else "")
        )

    # 이미 채워진 핵심 정보 요약 (Claude가 재질문 안 하도록)
    filled_lines = []
    for fname, value in session.application.items():
        if value is None or value == "" or (isinstance(value, list) and not value):
            continue
        label = FIELDS[fname]["label"]
        if isinstance(value, list):
            v_str = ", ".join(str(x) for x in value)
        elif isinstance(value, bool):
            v_str = "예" if value else "아니오"
        else:
            v_str = str(value)
        filled_lines.append(f"  - {label}: {v_str}")
    if filled_lines:
        lines.append("- 이미 채워진 항목:")
        lines.extend(filled_lines)

    return "\n".join(lines)


# ====================================================================
# Streamlit UI
# ====================================================================

def render_intake_panel() -> None:
    """Mode 4 Streamlit 패널."""
    import streamlit as st
    from core.intake_tools import IntakeSession, render_application_markdown
    from core.error_messages import friendly_error

    st.markdown("""
    <div style="margin-bottom:1.5rem;">
        <div style="font-size:0.85rem; color:#2E7D32; font-weight:600; letter-spacing:0.08em;">
            MODE 04 · APPLICATION INTAKE
        </div>
        <h1 style="margin:0.2rem 0;">📋 사업 신청 인테이크</h1>
        <div style="color:#757575;">
            공공건축물 그린리모델링 사업 신청에 필요한 정보를 챗봇과 대화로 수집하고
            신청서 초안 마크다운을 자동 생성합니다. 출처: 01 GR 가이드라인.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 세션 초기화
    if "_mode4_session" not in st.session_state:
        st.session_state["_mode4_session"] = IntakeSession()
    if "_mode4_history" not in st.session_state:
        st.session_state["_mode4_history"] = []
    if "_mode4_last_draft" not in st.session_state:
        st.session_state["_mode4_last_draft"] = None

    session = st.session_state["_mode4_session"]
    progress = session.get_progress()

    # 진행률 표시
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "필수 항목",
        f"{progress['required_filled']}/{progress['required_total']}",
        delta=f"{progress['required_pct']}%",
    )
    col2.metric(
        "선택 항목",
        f"{progress['optional_filled']}/{progress['optional_total']}",
    )
    col3.metric("전체 완성도", f"{progress['overall_pct']}%")
    col4.metric(
        "초안 생성",
        "가능 ✅" if progress["is_ready_for_draft"] else "대기 ⏳",
    )

    st.progress(progress["overall_pct"] / 100)

    # 탭 구성
    tab_chat, tab_state, tab_draft = st.tabs([
        "💬 대화",
        "📝 현재 신청서",
        "📄 신청서 초안",
    ])

    with tab_chat:
        _render_chat_tab(session)
    with tab_state:
        _render_state_tab(session)
    with tab_draft:
        _render_draft_tab(session)


def _render_chat_tab(session) -> None:
    """대화 탭."""
    import streamlit as st

    history = st.session_state["_mode4_history"]

    # 시작 안내 + 예시 시작 메시지
    if not history:
        st.info(
            "💡 자연어로 사업 신청 정보를 알려주시면 됩니다. "
            "한 번에 모두 말하지 않아도 됩니다 — 단계적으로 채워나가요."
        )
        with st.expander("🚀 시작 예시"):
            seeds = [
                ("도담 케이스 시작",
                 "안녕하세요. 김천시청에서 도담어린이집 그린리모델링 사업 신청하려고 합니다. "
                 "담당자는 홍길동 주무관이고 전화번호는 054-420-6000입니다."),
                ("간단 시작",
                 "사업 신청서 작성 좀 도와주세요. 어디서부터 시작하면 되나요?"),
                ("일괄 입력",
                 "신청기관: 서울시 강남구청, 담당자: 김철수, 연락처: 02-3423-1000. "
                 "대상은 강남도서관, 연면적 3,500㎡, 사용승인 1998년. "
                 "ZEB 3등급 목표 종합형으로 진행 예정이고 사업기간 12개월입니다."),
            ]
            for i, (label, seed) in enumerate(seeds):
                if st.button(label, key=f"intake_seed_{i}", use_container_width=True):
                    st.session_state["_mode4_input_seed"] = seed
                    st.rerun()

    # 기존 히스토리 렌더
    for entry in history:
        with st.chat_message("user"):
            st.markdown(entry["user"])
        with st.chat_message("assistant"):
            st.markdown(entry["answer"])
            tc = entry.get("tool_calls", [])
            if tc:
                with st.expander(f"🔧 도구 호출 {len(tc)}회"):
                    for j, t in enumerate(tc, 1):
                        st.markdown(f"**{j}. `{t['name']}`**")
                        if t.get("is_error"):
                            st.error(t["result"])
                        else:
                            st.json(t["result"])

    # 입력
    seed = st.session_state.pop("_mode4_input_seed", "")
    placeholder = "예: 연면적 1,251㎡, 사용승인 2014년 어린이집입니다."
    user_message = st.chat_input(placeholder)
    if seed and not user_message:
        user_message = seed

    if not user_message:
        return

    # 사용자 메시지 즉시 렌더
    with st.chat_message("user"):
        st.markdown(user_message)

    # Claude 호출
    with st.chat_message("assistant"):
        with st.spinner("처리 중..."):
            try:
                result = run_intake_turn(user_message, session)
            except RuntimeError as e:
                st.error(f"❌ {e}")
                return
            except Exception as e:
                from core.error_messages import friendly_error
                st.error(friendly_error(e))
                return

        st.markdown(result["answer"])

        tc = result.get("tool_calls", [])
        if tc:
            with st.expander(f"🔧 도구 호출 {len(tc)}회"):
                for j, t in enumerate(tc, 1):
                    st.markdown(f"**{j}. `{t['name']}`**")
                    if t.get("is_error"):
                        st.error(t["result"])
                    else:
                        st.json(t["result"])

    # 히스토리에 저장
    st.session_state["_mode4_history"].append({
        "user": user_message,
        "answer": result["answer"],
        "tool_calls": result.get("tool_calls", []),
    })

    # 새 draft 생성됐으면 저장
    if result.get("draft"):
        st.session_state["_mode4_last_draft"] = result["draft"]

    # 진행 상태 변경됐을 수 있으니 rerun
    st.rerun()


def _render_state_tab(session) -> None:
    """현재 신청서 항목별 상태 탭."""
    import streamlit as st
    import pandas as pd
    from core.intake_schema import FIELDS, SECTIONS, fields_by_section

    st.subheader("현재 신청서 항목별 상태")
    st.caption("✅=채워짐, ⭕=비어있음 (필수), ⚪=비어있음 (선택)")

    for sec in SECTIONS:
        st.markdown(f"### {sec}")
        rows = []
        for fname in fields_by_section(sec):
            spec = FIELDS[fname]
            value = session.application.get(fname)
            is_filled = value not in (None, "") and not (
                isinstance(value, list) and not value
            )
            if is_filled:
                status = "✅"
            elif spec.get("required"):
                status = "⭕"
            else:
                status = "⚪"

            if value is None or value == "":
                v_str = "—"
            elif isinstance(value, list):
                v_str = ", ".join(str(x) for x in value) if value else "—"
            elif isinstance(value, bool):
                v_str = "예" if value else "아니오"
            elif isinstance(value, (int, float)) and fname.endswith("_won"):
                v_str = f"{int(value):,}원"
            else:
                v_str = str(value)

            rows.append({
                "상태": status,
                "필수": "★" if spec.get("required") else "",
                "항목": spec["label"],
                "값": v_str,
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, use_container_width=True)

    if st.button("🔄 신청서 전체 초기화"):
        st.session_state["_mode4_session"] = __import__(
            "core.intake_tools", fromlist=["IntakeSession"]
        ).IntakeSession()
        st.session_state["_mode4_history"] = []
        st.session_state["_mode4_last_draft"] = None
        st.rerun()


def _render_draft_tab(session) -> None:
    """신청서 초안 미리보기 + 다운로드."""
    import streamlit as st
    from core.intake_tools import render_application_markdown

    progress = session.get_progress()
    last_draft = st.session_state.get("_mode4_last_draft")

    if not progress["is_ready_for_draft"]:
        st.warning(
            f"⏳ 아직 필수 항목 {len(progress['missing_required'])}개가 비어있습니다. "
            "대화 탭에서 챗봇과 대화로 채워주세요."
        )
        st.markdown("**빠진 필수 항목**:")
        for label in progress["missing_required_labels"]:
            st.markdown(f"- {label}")

    # 현재까지의 상태로 임시 미리보기 (필수 부족해도)
    st.subheader("📄 신청서 미리보기 (현재 상태 기준)")
    preview_md = render_application_markdown(session.application)
    with st.expander("마크다운 보기/숨기기", expanded=progress["is_ready_for_draft"]):
        st.markdown(preview_md)

    # 다운로드 (필수 모두 채워졌을 때만)
    if progress["is_ready_for_draft"]:
        final_draft = last_draft or preview_md
        st.download_button(
            label="📥 신청서 초안 다운로드 (.md)",
            data=final_draft,
            file_name=f"GR신청서_{session.application.get('building_name', 'draft')}.md",
            mime="text/markdown",
        )
    else:
        st.info("필수 항목이 모두 채워지면 다운로드 가능합니다.")
