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
    from core.intake_schema import TRACK_LABEL
    _t = getattr(session, "track", "public")
    lines.append(f"- **신청 사업: {TRACK_LABEL.get(_t, _t)}**")
    if _t == "private":
        lines.append("  (민간 = 대출 이자 보전. 신청 주체는 **그린리모델링 사업자**이고 "
                     "건축주 동의가 필요하다. 공사 완료 후엔 신청 불가. "
                     "'신청기관명' 같은 공공 항목은 묻지 말 것.)")
    else:
        lines.append("  (공공 = 국비로 공사비 직접 보조. 신청 주체는 **기관**이다. "
                     "당해연도 사전컨설팅이 전제조건. "
                     "'건축주'·'사업자' 같은 민간 항목은 묻지 말 것.)")
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
    from core.intake_schema import TRACK_PRIVATE, TRACK_PUBLIC
    from core.intake_tools import IntakeSession, render_application_markdown
    from core.error_messages import friendly_error

    st.markdown("""
    <div style="margin-bottom:1rem;">
        <div style="font-size:0.85rem; color:#2E7D32; font-weight:600; letter-spacing:0.08em;">
            MODE 04 · APPLICATION INTAKE
        </div>
        <h1 style="margin:0.2rem 0;">📋 사업 신청 인테이크</h1>
        <div style="color:#757575;">
            대화로 정보를 모아 <b>신청서 초안</b>과 <b>내야 할 서류 목록</b>을 만듭니다.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 트랙 선택 ───────────────────────────────────────────────────
    # 🔑 공공과 민간은 근거·지원방식·신청주체·서식이 전부 다른 **별개 사업**이다.
    #    예전엔 한 화면에 뭉개서, 민간 신청자도 '신청기관명'을 요구받고
    #    '공공건축물 …' 제목의 초안을 받았다.
    _TRACKS = {
        "🏛 공공건축물 (공사비 직접 보조)": TRACK_PUBLIC,
        "🏠 민간건축물 (대출 이자 보전)": TRACK_PRIVATE,
    }
    _pick = st.radio(
        "어느 사업으로 신청하시나요?",
        list(_TRACKS),
        horizontal=True,
        key="_mode4_track_pick",
    )
    track = _TRACKS[_pick]

    _boxes = st.columns(2)
    with _boxes[0]:
        with st.container(border=True):
            st.markdown("**🏛 공공건축물 지원사업**")
            st.caption(
                "**국비로 공사비를 직접 보조**합니다 (서울·중앙·공공 50% / 그 외 지자체 70%).\n\n"
                "· 대상: 사용승인 **10년 이상** 경과한 공공건축물\n"
                "· 신청: 기관이 **관리시스템에서 직접** 작성 → PDF 추출·등록\n"
                "· 🔴 **당해연도 사전컨설팅**을 받은 건물만 신청 가능 (운영지침 제14조①)\n"
                "· 유형: 종합형(시그니처/일반) · 맞춤형 · 군집형"
            )
    with _boxes[1]:
        with st.container(border=True):
            st.markdown("**🏠 민간건축물 이자지원사업**")
            st.caption(
                "공사비를 주는 게 아니라 **대출 이자를 보전**합니다 "
                "(성능개선 20~30% 미만 **4.5%** / 30% 이상 **5.5%**).\n\n"
                "· 대상: **2016-01-01 이전** 사용승인 단독주택 또는 비주거\n"
                "· 신청: 건축주가 아니라 **그린리모델링 사업자**가 동의를 받아 제출\n"
                "· 🔴 **공사 완료 후에는 신청 불가** (시공 전·중만)\n"
                "· 비주거는 은행 **대출가능 사전의향서**([별지8])가 필요"
            )
    st.caption(
        "두 사업 모두 국토안전관리원 **그린리모델링 창조센터**가 운영하고 "
        "「녹색건축물 조성 지원법」이 근거입니다. 성능개선비율은 센터 **지정 프로그램**"
        "(ECO2 · ECO2-OD · GR-E · Energy Studio · EnergyPlus · IES-VE)으로 산출합니다."
    )
    st.divider()

    # 세션 초기화 — 트랙이 바뀌면 새로 만든다.
    # 안 그러면 공공에서 답한 '신청기관명'이 민간 신청서에 남는다.
    if (st.session_state.get("_mode4_session") is None
            or st.session_state.get("_mode4_track") != track):
        st.session_state["_mode4_session"] = IntakeSession(track=track)
        st.session_state["_mode4_track"] = track
        st.session_state["_mode4_history"] = []
        st.session_state["_mode4_last_draft"] = None
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


def _seed_examples(track: str) -> list:
    """트랙별 시작 예시 — (라벨, 프롬프트).

    왜 트랙별인가: 민간 신청자에게 "김천시청 도담어린이집"을 보여주면 안 된다.
    공공에만 있는 항목(신청기관·사전컨설팅)을 예시가 먼저 가르치면, 민간 사용자는
    자기 서식에 없는 걸 채우려 든다.

    왜 라벨에 결과를 적나: 예시는 설명서다. 각 예시가 **서로 다른 분기**를 태워야
    "이렇게 쓰면 이게 붙는다"를 눌러보기 전에 안다. mode2가 같은 이유로 이 꼴이다.
    """
    from core.intake_schema import TRACK_PRIVATE

    if track == TRACK_PRIVATE:
        return [
            ("🏪 비주거 — 전 항목 일괄. [별지8] 대출가능 사전의향서가 붙는다",
             "○○종합건설(주)에서 대행 신청합니다. 대표는 김대표이고, 건축주는 "
             "박건축님 개인 소유입니다. 대상은 김천 ○○상가, 경상북도 김천시 ○○로 12, "
             "근린생활시설이고 사용승인 2014년, 연면적 1,251㎡입니다. "
             "용도구분은 비주거, 아직 시공 전이고 은행대출로 진행합니다. "
             "에너지 시뮬레이션으로 산출한 성능개선비율 25%, 공사비 1억 5천만원 "
             "전액을 대출 신청하며 사업기간은 8개월, 주요 공사는 단열과 창호입니다."),

            ("🏠 단독주택 — [별지7] 간이평가표로 바뀐다",
             "△△그린건설에서 신청합니다. 대표 이대표, 건축주는 최○○님 개인입니다. "
             "대상은 대구 수성구 단독주택이고 1995년 사용승인, 연면적 180㎡입니다. "
             "용도구분은 주거(단독주택)입니다. 창호와 단열을 고치려는데 "
             "무슨 서류가 필요한지, 뭘 더 알려드려야 하는지 알려주세요."),

            ("👤 개인 vs 사업자 — 건축주 구분이 서류를 바꾼다",
             "건축주가 개인이 아니라 사업자(법인)입니다. 이 경우 개인정보 동의서나 "
             "신분증 대신 뭘 내야 하나요? 나머지 조건은 연면적 800㎡ 비주거, "
             "사용승인 2005년, 시공 전입니다."),

            ("⏱ 시공 단계 — 공사가 끝났으면 신청이 안 된다",
             "공사를 이미 절반쯤 진행했는데 지금 신청해도 되나요? "
             "○○건설이고 건축주는 개인, 연면적 600㎡ 비주거 건물입니다. "
             "신용카드로 대출받으려 합니다."),
        ]

    return [
        ("🏫 도담 케이스 — 우리 검증 대상. 전 항목 일괄 입력",
         "김천시청에서 도담어린이집 그린리모델링을 신청합니다. "
         "담당자는 홍길동 주무관, 연락처는 054-420-6000입니다. "
         "대상은 김천 도담어린이집, 경상북도 김천시 ○○로 12, 어린이집이고 "
         "사용승인 2014년, 연면적 1,251㎡입니다. 종합형으로 ZEB 5등급을 목표로 "
         "에너지 절감 30%, 사업기간 8개월, 총사업비 2억 9천만원입니다. "
         "당해연도 사전컨설팅은 받았고, 시가 직접 소유한 건물입니다."),

        ("🏛 보조율 70% — 기준은 수도권이 아니라 소유 주체다",
         "경상북도 ○○군청 소유 시립도서관입니다. 서울시나 중앙행정기관이 아니라 "
         "지방자치단체 소유인데, 담당자는 김철수 주무관 054-123-4567입니다. "
         "연면적 3,500㎡, 사용승인 1998년, 종합형으로 12개월 예정입니다. "
         "보조율이 어떻게 되는지와 아직 뭐가 빠졌는지 알려주세요."),

        ("🏢 군집형 — [별지 제3호서식] 추진계획서가 추가로 붙는다",
         "○○군청입니다. 관내 보건지소 3곳을 묶어 군집형으로 신청하려 합니다. "
         "담당자 박영희, 054-987-6543. 대표 건물은 ○○보건지소, 연면적 900㎡, "
         "사용승인 2003년입니다. 사업기간 10개월, 총사업비 4억입니다. "
         "군집형이면 서류가 어떻게 달라지나요?"),

        ("🔑 임차건물 — [별지 제2호서식] 임대인 동의서가 필요해진다",
         "저희가 소유한 게 아니라 임차해서 쓰는 건물입니다. 신청이 되나요? "
         "○○구청 담당 최민수, 02-1234-5678이고 대상은 연면적 1,800㎡ "
         "주민센터, 사용승인 2010년입니다. 사전컨설팅은 아직 안 받았습니다."),
    ]


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
        with st.expander("🚀 예시 입력 — 클릭하면 자동 입력", expanded=True):
            for i, (label, seed) in enumerate(_seed_examples(session.track)):
                st.markdown(f"<div style='margin-top:0.6rem; font-size:0.86rem; "
                            f"color:#5A6C7A;'><b>{label}</b></div>",
                            unsafe_allow_html=True)
                if st.button(seed, key=f"intake_seed_{session.track}_{i}",
                             width="stretch"):
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
                with st.expander(f"📋 추출·반영된 항목 ({len(tc)}건)"):
                    for t in tc:
                        if t.get("is_error"):
                            st.error(t["result"])
                        else:
                            st.json(t["result"])

    # 입력 — 안내문도 트랙을 따른다. 민간 신청자에게 '신청기관'을 예로 들면 안 된다.
    from core.intake_schema import TRACK_PRIVATE

    seed = st.session_state.pop("_mode4_input_seed", "")
    placeholder = (
        "예: ○○건설이고 건축주는 개인, 연면적 800㎡ 비주거, 시공 전입니다."
        if session.track == TRACK_PRIVATE
        else "예: 김천시청이고 연면적 1,251㎡, 사용승인 2014년 어린이집입니다."
    )
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
            except Exception as e:
                # RuntimeError를 먼저 잡아 날것으로 뿌리던 자리다. 하필 가장 흔한
                # 실패(API 키 미설정)가 RuntimeError라서, mode1·mode2는 🔑 안내 카드를
                # 주는데 여기만 내부 문자열을 보여줬다. friendly_error가 이미 그 분기를
                # 갖고 있다 — 갈라놓을 이유가 없다.
                from core.error_messages import friendly_error
                st.error(friendly_error(e))
                return

        st.markdown(result["answer"])

        tc = result.get("tool_calls", [])
        if tc:
            with st.expander(f"📋 추출·반영된 항목 ({len(tc)}건)"):
                for t in tc:
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
        for fname in fields_by_section(sec, getattr(session, 'track', None)):
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
        st.dataframe(df, hide_index=True, width="stretch")

    if st.button("🔄 신청서 전체 초기화"):
        # 지금 트랙을 그대로 유지한다. 예전엔 track을 안 넘겨 공공으로 되돌아갔는데,
        # _mode4_track은 그대로라 위쪽 재생성 가드(#215)가 못 잡고 계속 어긋났다.
        from core.intake_tools import IntakeSession

        st.session_state["_mode4_session"] = IntakeSession(track=session.track)
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
    # session.track을 반드시 넘긴다 — 안 넘기면 민간 신청자가 공공 서식을 받는다.
    st.subheader("📄 신청서 미리보기 (현재 상태 기준)")
    preview_md = render_application_markdown(session.application, session.track)
    with st.expander("초안 전문 보기/숨기기", expanded=progress["is_ready_for_draft"]):
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
