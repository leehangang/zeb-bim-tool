"""
modes/mode5_evidence.py — 근거·출처 (Methodology & Provenance)
=============================================================
"이 숫자가 어디서 나왔는가"에 한 화면으로 답한다.

왜 필요한가:
    core/params.py는 모든 제도 파라미터를 source·effective_from·status와 함께
    들고 있고 provenance()·missing()까지 제공하는데, 정작 **화면에서 한 번도
    호출되지 않았다**. 근거를 데이터로 갖고 있으면서 보여주지 않으면
    사용자 입장에선 하드코딩과 구별할 방법이 없다.

원칙:
    · 이 페이지의 표는 **YAML에서 실시간으로 렌더**한다. 손으로 옮겨적지 않는다.
      → 파라미터를 고치면 이 페이지가 따라 바뀐다. stale이 구조적으로 불가능.
    · 민감도 표도 **엔진을 실제로 호출해** 만든다. 임계값을 손으로 적지 않는다.
      → "절감률 55%가 임계"는 주장이 아니라 재현되는 계산 결과여야 한다.
    · 확인 안 된 값은 **확인 필요로 표기**하고 숨기지 않는다.
"""

from typing import Optional


# ====================================================================
# 순수 함수 (Streamlit 의존 X — 테스트 가능)
# ====================================================================

# status 문자열 → (배지, 설명)
_STATUS_BADGE = {
    "확인됨_원문대조":   ("✅ 원문대조", "법령 원문 PDF를 직접 열어 문구를 대조함"),
    "확인됨":           ("✅ 확인됨",   "근거 조항을 특정함"),
    "임시가정_근거없음": ("🔴 임시가정", "근거 없이 임시로 넣은 값 — 결과를 그대로 믿으면 안 됨"),
    "확인필요":         ("⚠️ 확인 필요", "값이 미확정 — 고정 금지, 산출에 쓰면 가정치로 표기"),
    "미완성_확인필요":   ("⚠️ 확인 필요", "작성 중 — 고정 금지"),
    "미완성":           ("⚠️ 미완성",   "작성 중"),
    "폐지":             ("⛔ 폐지",     "현행 아님 — 편익에 포함 금지"),
}

# 부분 일치 순서 — 긴 키를 먼저 본다 ("확인됨_원문대조"가 "확인됨"에 먹히지 않도록).
_BADGE_ORDER = ("확인됨_원문대조", "임시가정", "미완성", "확인필요", "폐지", "확인됨")


def status_badge(status: Optional[str]) -> tuple:
    """
    status 문자열 → (배지 라벨, 설명).

    YAML의 status는 자유 문자열이라 새 값이 언제든 생긴다. 정확히 일치하지 않으면
    부분 일치로 한 번 더 시도한다 — 모르는 status를 조용히 중립 배지로 흘려보내면
    '임시가정_근거없음' 같은 **가장 위험한 값이 안전해 보이는** 사고가 난다.
    """
    if not status:
        return ("· 미표기", "status가 지정되지 않음")
    if status in _STATUS_BADGE:
        return _STATUS_BADGE[status]
    for key in _BADGE_ORDER:
        if key in status:
            return _STATUS_BADGE[key]
    return (f"⚠️ {status}", "정의되지 않은 status — 확인 필요")


def collect_provenance() -> list:
    """
    모든 파라미터 세트의 섹션별 출처를 수집한다.

    Returns:
        [{"set":.., "section":.., "source":.., "url":.., "effective":.., "status":.., "원문근거":..}]
    """
    from core import params as P

    rows = []
    for name in P.FILES:
        try:
            data = P.load(name)
        except Exception:
            continue
        for section, node in data.items():
            if section == "meta" or not isinstance(node, dict):
                continue
            prov = P.provenance(name, section)
            if not prov and "source" not in node:
                continue
            eff = prov.get("effective_from") or prov.get("effective_until") or prov.get("year")
            rows.append({
                "set": name,
                "section": section,
                "source": prov.get("source", "—"),
                "url": prov.get("url"),
                "effective": str(eff) if eff else "—",
                "status": prov.get("status"),
                "원문근거": node.get("원문근거"),
                "note": prov.get("note"),
            })
    return rows


def grade_sensitivity(base_primary_kwh_m2: Optional[float] = None,
                      building_use: str = "어린이집",
                      pv_primary_per_m2: float = 0.0,
                      lo: float = 0.30, hi: float = 0.80, step: float = 0.05) -> dict:
    """
    절감률 → ZEB 제2호 등급 민감도를 **엔진의 계산 경로 그대로** 산출한다.

    ⚠️ 2026-07-17부터 화면(③ 등급 민감도 탭)에서는 안 쓴다 — 탭을 없앴다.
       그래도 지우지 않는 이유: scripts/test_evidence.py가 이 함수로 **엔진의 등급
       임계(도담 기준 55%)가 안 바뀌었는지** 회귀 검사한다. 지우면 그 보호가 사라진다.
       (아래 base 함정 주석도 그 검사가 지키는 대상이다.)

    ⚠️ 절감률의 분모는 **용도별 기준 에너지요구량(base)** 이지 '현재 소요량'이 아니다.
       core.zeb_evaluator.evaluate_zeb()가 쓰는 식과 동일하게 맞춘다:
           post_energy = base_kwh × (1 − reduction_ratio)
           net_primary = post_energy − PV 1차에너지 생산
       (도담: base 200 → 현재 166.7은 기존 16.65% 적용 상태, 보강 후 66.0은 67% 절감)
       base에 166.7을 넣으면 임계가 46%로 잘못 나온다. 실제 임계는 55%다.

    임계값은 하드코딩하지 않고 이분 탐색으로 찾는다.
    → 기준표(ZEB_PRIMARY_THRESHOLDS_NONRES)가 바뀌면 이 표도 자동으로 따라간다.

    Args:
        base_primary_kwh_m2: 기준 에너지요구량. None이면 엔진의 용도별 기본값.
        building_use: 용도 (주거/비주거 기준표 + base 선택)
        pv_primary_per_m2: PV 1차에너지 생산 (kWh/㎡·년). 도담은 태양광이 없어 0.

    Returns:
        {"base":.., "rows": [...], "cliffs": [{"등급":.., "임계_절감률_pct":..}]}
    """
    from core.zeb_evaluator import (
        RESIDENTIAL_USES, determine_grade_clause2, get_base_energy,
    )

    # 주거/비주거·base 모두 엔진 값을 그대로 쓴다 (여기서 따로 정의하지 않는다).
    is_res = building_use in RESIDENTIAL_USES
    base = float(base_primary_kwh_m2 if base_primary_kwh_m2 else get_base_energy(building_use))

    def net_at(r: float) -> float:
        return base * (1.0 - r) - pv_primary_per_m2

    def grade_at(r: float) -> dict:
        return determine_grade_clause2(net_at(r), is_residential=is_res)

    rows = []
    r = lo
    while r <= hi + 1e-9:
        g = grade_at(r)
        rows.append({
            "절감률_pct": round(r * 100, 1),
            "소요량": round(net_at(r), 1),
            "등급": g.get("grade", "-"),
            "라벨": g.get("label", "-"),
            "rank": g.get("rank", 0),
        })
        r += step

    # 등급이 바뀌는 지점을 이분 탐색으로 특정 (0.01%p 해상도)
    cliffs = []
    for i in range(1, len(rows)):
        if rows[i]["rank"] != rows[i - 1]["rank"]:
            a, b = rows[i - 1]["절감률_pct"] / 100, rows[i]["절감률_pct"] / 100
            target_rank = rows[i]["rank"]
            for _ in range(40):
                m = (a + b) / 2
                if grade_at(m).get("rank", 0) >= target_rank:
                    b = m
                else:
                    a = m
            cliffs.append({
                "등급": rows[i]["등급"],
                "라벨": rows[i]["라벨"],
                "임계_절감률_pct": round(b * 100, 1),
            })
    return {"base": base, "rows": rows, "cliffs": cliffs}


def grade_at_ui(net_primary_kwh_m2: float, building_use: str) -> str:
    """net 1차E 소요량 → 제2호 등급 라벨. (엔진의 주거/비주거 판정 집합을 그대로 사용)"""
    from core.zeb_evaluator import RESIDENTIAL_USES, determine_grade_clause2
    g = determine_grade_clause2(
        net_primary_kwh_m2, is_residential=building_use in RESIDENTIAL_USES,
    )
    return g.get("label", "-")


def build_id() -> dict:
    """
    빌드 식별자 — 산출물에 찍어 "어느 버전이 이 숫자를 만들었나"를 추적한다.
    git이 없거나 배포 환경에서 실패해도 페이지가 죽지 않도록 방어한다.
    """
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    out = {"commit": "unknown", "date": "unknown"}
    try:
        out["commit"] = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=root,
            stderr=subprocess.DEVNULL, timeout=5,
        ).decode().strip()
        out["date"] = subprocess.check_output(
            ["git", "log", "-1", "--format=%cs"], cwd=root,
            stderr=subprocess.DEVNULL, timeout=5,
        ).decode().strip()
    except Exception:
        pass
    return out


# ====================================================================
# Streamlit UI
# ====================================================================

def render_evidence_panel() -> None:
    """Mode 5 — 근거·출처."""
    import streamlit as st

    st.markdown("""
    <div style="margin-bottom:1.5rem;">
        <div style="font-size:0.85rem; color:#2E7D32; font-weight:600; letter-spacing:0.08em;">
            MODE 05 · METHODOLOGY &amp; PROVENANCE
        </div>
        <h1 style="margin:0.2rem 0;">📐 근거·출처</h1>
    </div>
    """, unsafe_allow_html=True)

    bid = build_id()
    st.caption(f"빌드 · git `{bid['commit']}` · {bid['date']}")

    tab1, tab5 = st.tabs(["① 파라미터 출처", "② 데이터 처리"])

    # ── ① 파라미터 출처 ──────────────────────────────────────────
    with tab1:
        rows = collect_provenance()
        if not rows:
            st.warning("파라미터를 읽지 못했습니다.")
            return

        _SET_LABEL = {
            "zeb_incentive": "Track A · ZEB 인센티브",
            "gr_support": "Track B · 그린리모델링 지원",
            "energy_tariff": "공통 · 에너지 단가",
        }
        for setname, label in _SET_LABEL.items():
            subset = [r for r in rows if r["set"] == setname]
            if not subset:
                continue
            st.markdown(f"#### {label}  `{setname}.yaml`")
            for r in subset:
                badge, badge_desc = status_badge(r["status"])
                with st.expander(f"{badge} · **{r['section']}** — {r['source'][:60]}"):
                    st.markdown(f"**근거** — {r['source']}")
                    st.markdown(f"**시행/기준일** — {r['effective']}")
                    st.markdown(f"**상태** — {badge} · {badge_desc}")
                    if r["원문근거"]:
                        st.markdown("**원문 인용**")
                        st.info(str(r["원문근거"]).strip())
                    if r["note"]:
                        st.caption(f"📝 {r['note']}")
                    if r["url"]:
                        st.markdown(f"[원문 링크]({r['url']})")

    # ── ② 데이터 처리 ────────────────────────────────────────────
    # (2026-07-17: 탭을 5개 → 2개로 줄였다. '확인 필요'·'등급 민감도'·'계산 경로·한계'는
    #  화면에서 뺐다 — status는 ① 파라미터 출처의 배지로 이미 다 보인다.)
    with tab5:
        st.markdown("#### 업로드한 BIM과 질문은 어디로 가나")
        st.error(
            "**업로드한 BIM 파일(gbXML·JSON)은 서버로 전송됩니다.** 이 앱은 Streamlit "
            "Community Cloud(해외 호스팅)에서 Python으로 실행되며, 파일 파싱·진단·ROI 계산이 "
            "**전부 그 서버에서** 일어납니다. 브라우저에서 처리되는 것이 아닙니다.\n\n"
            "**EnergyPlus 실행을 누르면 두 번째 해외 서버로 또 나갑니다.** E+는 Streamlit "
            "무료 티어에서 못 돌아(CPU 하한 0.078코어 · apt에 패키지 없음) **Modal**이라는 별도 "
            "서비스에 IDF를 보내 계산합니다. gbXML에서 뽑아낸 **건물 형상 좌표와 열관류율이 "
            "그 IDF에 담겨 나갑니다.**\n\n"
            "**정책 Q&A 질문은 Anthropic API로 전송됩니다.** 검색된 법령 조항과 질문이 "
            "함께 LLM에 전달됩니다.\n\n"
            "**실제 공공건축물 도면을 올리기 전에 소속 기관의 정보보호 정책을 확인하세요.** "
            "민감한 실물 데이터는 로컬 실행(`streamlit run streamlit_app.py`)을 권합니다 — "
            "저장소를 받아 직접 돌리면 데이터가 기관 밖으로 나가지 않습니다.",
            icon="🔴",
        )
        st.markdown("#### 어디까지 나가나 — 서버 세 곳")
        import pandas as pd
        st.dataframe(pd.DataFrame([
            {"보내는 것": "BIM 파일 (gbXML·JSON)", "받는 곳": "Streamlit Community Cloud (해외)",
             "언제": "업로드 즉시", "저장": "❌ 세션 종료 시 소멸 (DB 없음)"},
            {"보내는 것": "IDF (형상 좌표·열관류율)", "받는 곳": "Modal (해외) — EnergyPlus 서비스",
             "언제": "🔬 EnergyPlus 실행을 **누를 때만**", "저장": "❌ 실행 후 작업폴더 삭제"},
            {"보내는 것": "기상파일 (.epw)", "받는 곳": "Modal — 업로드한 경우에만",
             "언제": "E+ 실행 시", "저장": "❌ 실행 후 삭제"},
            {"보내는 것": "정책 Q&A 질문 + 법령 조항", "받는 곳": "Anthropic API (해외)",
             "언제": "질문할 때", "저장": "❌ 우리 쪽 미저장 (Anthropic 정책은 별도)"},
            {"보내는 것": "진단 결과", "받는 곳": "— (서버 밖으로 안 나감)",
             "언제": "—", "저장": "❌ 세션 캐시 한정 · 계정 없음"},
            {"보내는 것": "법령 원문 색인", "받는 곳": "— (저장소에 동봉)",
             "언제": "—", "저장": "✅ 공개 법령이라 민감정보 아님"},
        ]), hide_index=True, width="stretch")
        st.caption(
            "**EnergyPlus를 안 누르면 Modal로는 아무것도 안 나갑니다.** 진단·ROI만 쓰실 거면 "
            "데이터가 닿는 곳은 Streamlit 서버 한 곳입니다."
        )
