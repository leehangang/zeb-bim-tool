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
        <div style="color:#757575;">
            화면에 뜬 숫자가 <b>어느 조항에서, 언제 시행된 값으로</b> 나왔는지 —
            그리고 <b>아직 확인 못 한 값은 무엇인지</b>를 숨기지 않고 보여줍니다.
            아래 표는 <code>data/params/*.yaml</code>에서 <b>실시간으로 읽어</b> 그립니다.
        </div>
    </div>
    """, unsafe_allow_html=True)

    bid = build_id()
    st.caption(f"빌드 · git `{bid['commit']}` · {bid['date']}")

    tab1, tab2, tab3, tab4 = st.tabs([
        "① 파라미터 출처", "② 확인 필요", "③ 등급 민감도", "④ 계산 경로·한계",
    ])

    # ── ① 파라미터 출처 ──────────────────────────────────────────
    with tab1:
        st.markdown(
            "제도 파라미터(요율·한도·단가)는 **코드에 하드코딩하지 않고** "
            "`data/params/*.yaml`에 `source`·`effective_from`·`status`와 함께 둡니다. "
            "엔진은 이 표를 **결정론적으로 조회**하며 LLM을 경유시키지 않습니다."
        )
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

    # ── ② 확인 필요 ──────────────────────────────────────────────
    with tab2:
        from core import params as P

        st.markdown(
            "**아직 원문으로 확정하지 못한 값**입니다. 이 값들은 **고정하지 않고** "
            "화면에서 '확인 필요'로 표기하며, 산출에 쓰이는 경우 가정치임을 함께 밝힙니다. "
            "그럴싸한 값을 채워 넣는 것보다 **모른다고 말하는 쪽이 정확**하기 때문입니다."
        )
        miss = P.missing()
        if not miss:
            st.success("확인 필요 항목이 없습니다.")
        else:
            for m in miss:
                with st.expander(f"⚠️ `{m['set']}` — **{m['section']}**"):
                    st.markdown(f"**상태** — {m['status']}")
                    if m.get("source"):
                        st.markdown(f"**근거(예정)** — {m['source']}")
                    if m.get("확인필요"):
                        st.markdown("**무엇을 확인해야 하나**")
                        for item in m["확인필요"]:
                            st.markdown(f"- {item}")

        st.divider()
        st.markdown("#### 가장 큰 가정 — 연간 에너지 절감액")
        st.warning(
            "홈의 **연간 절감 1,238만원**은 `1,251㎡ × 9,900원/㎡`인 **단일 계수 가정**입니다. "
            "ZEB 엔진이 산출한 **kWh 절감량과 연결돼 있지 않고** 연료원(전기·가스·열) 구분도 없습니다. "
            "전기요금표·가스단가를 `energy_tariff.yaml`에 채워 **`절감kWh × 단가`**로 "
            "환산하는 것이 다음 작업입니다. 그때까지 이 숫자는 **가정치**로 읽어야 합니다.",
            icon="⚠️",
        )

    # ── ③ 등급 민감도 ────────────────────────────────────────────
    with tab3:
        st.markdown(
            "기본 시나리오가 좋아 보여도, **가정이 틀어졌을 때 결론이 버티는지**가 핵심 질문입니다. "
            "아래 표는 보강 후 **절감률**을 바꿔가며 **ZEB 엔진을 실제로 호출**해 그린 것입니다. "
            "임계값은 손으로 적지 않고 **이분 탐색으로 찾습니다** — 기준표가 바뀌면 이 표도 따라 바뀝니다."
        )

        from core.zeb_evaluator import get_base_energy

        col1, col2 = st.columns(2)
        use = col1.selectbox(
            "용도", ["어린이집", "유치원", "학교", "도서관", "공공청사", "공동주택"], index=0,
            help="용도별 기준 에너지요구량(base)과 주거/비주거 기준표가 함께 바뀝니다.",
        )
        base = col2.number_input(
            "기준 에너지요구량 base (kWh/㎡·년)", value=float(get_base_energy(use)), step=1.0,
            help="절감률의 분모입니다. 엔진의 용도별 기본값이 들어옵니다.",
        )

        try:
            sens = grade_sensitivity(base, building_use=use)
        except Exception as e:
            st.error(f"민감도 계산 실패: {type(e).__name__}: {e}")
            return

        st.info(
            f"**절감률의 분모는 기준 에너지요구량 base = {sens['base']:.0f} kWh/㎡·년**이지 "
            "'현재 소요량'이 아닙니다. 도담은 base 200에서 **현재 166.7**"
            "(기존 요소로 이미 16.65% 절감된 상태), **보강 후 66.0**(67% 절감)입니다. "
            "분모를 166.7로 착각하면 임계가 46%로 잘못 나옵니다.",
            icon="📐",
        )

        if sens["cliffs"]:
            st.markdown("**등급이 바뀌는 지점 (임계 절감률)**")
            cl = st.columns(len(sens["cliffs"]))
            for i, c in enumerate(sens["cliffs"]):
                cl[i].metric(c["라벨"], f"{c['임계_절감률_pct']}%", "이상이면 달성")

        import pandas as pd
        df = pd.DataFrame([
            {"절감률": f"{r['절감률_pct']}%", "1차E 소요량": r["소요량"], "제2호 등급": r["라벨"]}
            for r in sens["rows"]
        ])
        st.dataframe(df, width="stretch", hide_index=True)

        st.divider()
        st.markdown("#### 🔴 결합 방식을 바꾸면 등급이 뒤집힙니다")
        st.markdown(
            "현재 엔진은 11개 요소의 절감률을 **단순 덧셈**합니다. 이건 물리적으로 성립하지 않습니다 — "
            "10% 절감 요소가 11개면 단순합은 110%가 되어 **에너지가 음수**가 됩니다. "
            "각 요소가 *남은* 에너지를 줄인다고 보는 **1 − Π(1−rᵢ)** 가 방어 가능한 결합입니다."
        )

        try:
            from core.zeb_evaluator import GR_ENERGY_REDUCTION, combine_reductions
            rs = list(GR_ENERGY_REDUCTION.values())
            r_sum = combine_reductions(rs, "sum")
            r_mul = combine_reductions(rs, "multiplicative")
            KEEI = 20.4 / 33.0     # KEEI 실측/예측 비 — 아래 캡션에 출처

            rows = []
            for label, r in [
                ("① 단순합산 (구 기본값 — 폐기)", r_sum),
                ("② 상호작용 반영 1−Π(1−rᵢ) ← 현재 엔진", r_mul),
                ("③ ①에 KEEI 실측보정", r_sum * KEEI),
                ("④ ②에 KEEI 실측보정", r_mul * KEEI),
            ]:
                net = base * (1 - r)
                g = grade_at_ui(net, use)
                rows.append({"산정 방식": label, "절감률": f"{r*100:.1f}%",
                             "1차E 소요량": round(net, 1), "제2호 등급": g})
            import pandas as pd
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        except Exception as e:
            st.error(f"결합 방식 비교 실패: {type(e).__name__}: {e}")

        st.success(
            "**2026-07: 엔진을 ②로 전환했습니다 — 우리 헤드라인을 우리가 낮췄습니다.** "
            "기존 '4등급'은 ①(단순합산 67%)에서만 성립했습니다. ①은 100%를 넘길 수 있어 "
            "**정의상 틀린 산식**이라 유지할 이유가 없었습니다. ②로 계산하면 50.5% → "
            "소요량 99.1 → **5등급**입니다. 즉 4등급은 건물 성능이 아니라 **산정 방식의 산물**이었습니다. "
            "①은 비교·이력 목적으로만 남깁니다.",
            icon="✅",
        )
        st.info(
            "**②도 근사입니다 — 어느 쪽으로 틀리는지 밝힙니다.** 참값은 요소들이 같은 부하를 "
            "건드리는지에 달렸습니다. **겹치는 경우**(외벽단열 ↔ 고효율보일러: 단열하면 보일러가 "
            "줄일 난방부하가 이미 줄어듦)는 ①이 과대이고 ②가 가깝습니다. **겹치지 않는 경우**"
            "(LED(조명) ↔ 외벽단열(난방))는 실제로 거의 가산적이라 **②가 다소 과소**추정합니다. "
            "우리 11개 요소는 외피·설비·조명·환기·제어가 섞여 있어 참값은 두 값 **사이**에 있습니다. "
            "그럼에도 ②를 택한 이유는 ①이 정의상 틀렸고, 아래 실측 근거가 보수적인 쪽을 지지하기 때문입니다.",
            icon="📐",
        )
        st.caption(
            "**KEEI 실측보정 근거** — 에너지경제연구원 기본연구보고서 2025-14 "
            "「건물부문 그린리모델링 정책효과 분석 및 활성화 방안 연구: 공공건축물을 중심으로」 "
            "(김종우·조진만, 보도자료 2026-06-22): GR 시행 공공건축물 **522동(어린이집 358동 = 68.6%)** 의 "
            "월별 전기·도시가스 실사용량을 Stacked DID로 분석한 결과 **연간 20.4 kWh/㎡** 절감으로, "
            "엔지니어링 사전 예측 **33 kWh/㎡의 약 60% 수준**이었습니다. "
            "표본의 2/3이 어린이집이라 **도담 케이스에 전이 가능성이 높은 실증**입니다. "
            "다만 20.4는 전기+가스 합산 단일 모형 결과이고 우리 요소 구성과 1:1 대응은 아니므로, "
            "③·④는 **참고용 시나리오**이지 확정 산정이 아닙니다."
        )
        st.warning(
            "**요소별 절감률 자체도 출처 미확인입니다** — 외벽단열 15% · 창호 8% · 고효율냉난방 12% · "
            "폐열회수환기 8% 등 `GR_ENERGY_REDUCTION` 11개 값은 문헌 근거를 아직 찾지 못했습니다. "
            "ZEB 공식 산정 도구는 **ECO2**, GR 성능개선비율은 **EnergyPlus** 등 지정 프로그램이므로 "
            "정식 해석 결과로 교체해야 합니다.",
            icon="⚠️",
        )
        st.caption(
            "이 표는 제2호(1차에너지소요량) 경로만 봅니다. 최종 등급은 "
            "**제1호(자립률)와 제2호 중 상위**로 정하고 제3호(BEMS 13항목)를 함께 충족해야 합니다. "
            "도담은 태양광이 없어 제1호가 0%라 제2호가 결론을 지배합니다."
        )

    # ── ④ 계산 경로·한계 ────────────────────────────────────────
    with tab4:
        st.markdown("#### 숫자가 흐르는 경로")
        st.markdown(
            "```\n"
            "BIM(JSON)\n"
            "  └→ core/zeb_evaluator   1차에너지 환산(전력 ×2.75) → 제1호·제2호 → 상위 등급\n"
            "  └→ core/bim_diagnoser   11개 기술요소 채점 (자립률은 zeb_evaluator에 위임)\n"
            "         └→ core/roi_calculator  단가DB → Max Cost → 보조금·취득세·용적률\n"
            "                └→ core/params   요율·한도를 YAML에서 결정론적 조회\n"
            "```"
        )
        st.markdown("#### 설계 원칙")
        st.markdown(
            "- **계산은 절대 LLM에게 시키지 않습니다.** 숫자는 엔진이 산출하고, LLM은 언어만 담당합니다.\n"
            "- **숫자는 테이블에서, 근거는 RAG에서.** 전기요금표처럼 매트릭스에서 셀을 고르는 일을 "
            "LLM에 시키면 틀려도 그럴싸해서 **조용히 틀립니다(silent error).**\n"
            "- **자립률은 한 곳에서만 계산합니다.** 과거 진단(5.6%)과 홈(9.3%)이 갈렸던 버그를 "
            "`autonomy_for_diagnosis()` 단일 소스로 정정했습니다.\n"
            "- **원문에 없으면 없다고 답합니다.** RAG는 지어내지 않습니다."
        )
        st.divider()
        st.markdown("#### 한계 — 정직하게")
        st.error(
            "**이 도구는 ZEB 인증 판정이 아닙니다.** 성균관대 졸업설계 · 삼성E&A 환경에너지탐구대회 "
            "출품작으로, 공식 산정 도구(ECO2·EnergyPlus)를 아직 연결하지 않았습니다. "
            "절감률·단가·요금은 상당 부분 **가정치**이며, 실제 사업 신청·인증 판정은 "
            "**그린리모델링 창조센터 공식 컨설팅**과 인증기관을 거쳐야 합니다.",
            icon="🚧",
        )
        st.markdown(
            "**색인에서 빠진 원문** — 01 GR 가이드라인 · 02 GR 기술요소 · "
            "03 ZEB 인증기준 고시 · 09 영유아보육법은 **이미지 스캔본**이라 텍스트 추출이 "
            "불가능해 RAG 색인에서 제외돼 있습니다. 특히 **03은 별표1·2(자립률 산식·등급표)의 "
            "근거**라 가장 아쉬운 공백입니다."
        )
        st.caption("상세 아키텍처: `docs/ARCHITECTURE.md` · 파라미터: `data/params/*.yaml`")
