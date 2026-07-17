# -*- coding: utf-8 -*-
"""
core/full_report.py — 종합 리포트 조립기

화면의 5개 탭(ZEB 등급 → GR 진단 → 보강·비용 → 최적화 → 민감도)과
에너지 해석 결과를 **한 문서**로 묶는다.

왜 만드는가
-----------
예전 리포트는 `bim_diagnoser.generate_diagnosis_report()` 하나였고,
**GR 진단(11개 요소 + 점수)만** 담고 있었다. 화면에서 ZEB 등급을 보고
비용을 보고 민감도를 봐도, 내려받은 리포트엔 그게 없었다.
화면과 산출물이 다른 이야기를 하고 있었던 셈이다.

원칙
----
· 숫자를 여기서 다시 계산하지 않는다. 엔진 결과를 받아 **문장으로 옮기기만** 한다.
· 없는 섹션은 **조용히 빼지 않고** 왜 없는지 적는다
  (에너지 해석을 안 돌렸으면 "안 돌렸다"고 쓴다).
"""

from typing import Optional

from core.bim_diagnoser import GR_ELEMENT_LABELS


def _won(v) -> str:
    try:
        return f"{int(v):,}원"
    except (TypeError, ValueError):
        return "—"


def _eok(v) -> str:
    try:
        return f"{float(v) / 1e8:.2f}억"
    except (TypeError, ValueError):
        return "—"


def _section_zeb(zeb: Optional[dict]) -> list:
    out = ["## 1. ZEB 인증 평가", ""]
    if not zeb:
        out += ["*평가 결과가 없습니다.*", ""]
        return out
    g = zeb.get("grade") or {}
    g1 = zeb.get("grade_clause1") or {}
    g2 = zeb.get("grade_clause2") or {}
    out += [
        f"**최종 등급: {g.get('label', '—')}**",
        "",
        "| 항목 | 값 | 근거 |",
        "|---|---|---|",
        f"| 에너지자립률 | {zeb.get('autonomy_pct', 0):.1f}% | 제1호 |",
        f"| 1차에너지소요량 (보강 후) | {zeb.get('post_energy_kwh_m2', 0):.1f} kWh/㎡·년 | 제2호 |",
        f"| 제1호 판정 | {g1.get('label', '—')} | 자립률 기준 |",
        f"| 제2호 판정 | {g2.get('label', '—')} | 1차E 소요량 기준 |",
        "",
    ]
    red = zeb.get("reduction") or {}
    if red:
        out += [
            f"절감률 **{red.get('total_reduction_pct', 0):.1f}%** "
            f"(결합 방식: `{red.get('_결합방식', '—')}`) — "
            "요소별 절감률은 1−Π(1−rᵢ)로 결합합니다. 단순 합산하면 100%를 넘어 "
            "에너지가 음수가 됩니다.",
            "",
        ]
    out += [
        "> ZEB 인증 = (제1호 자립률 **또는** 제2호 1차에너지소요량) + 제3호 BEMS 설치.",
        "> ⚠️ 이 등급은 **용도별 원단위 × 요소별 절감률의 간이 추정**입니다. "
        "공식 인증은 ECO2 정식 해석이 필요합니다.",
        "",
    ]
    return out


def _section_gr(score: dict, gr_mapping: dict) -> list:
    out = ["## 2. 그린리모델링 정량평가", ""]
    out += [
        f"**정량평가 점수: {score.get('final_score', score.get('total_score', 0))}/100점**  ",
        "*선정 랭킹 점수입니다 — 고득점 순 경쟁 선발이며 제도상 등급이 아닙니다.*",
        "",
        f"- GR 요소: {score.get('gr_subtotal', 0)}/80점",
        f"- 사업여건: {score.get('site_subtotal', 0)}/20점",
    ]
    if score.get("bonus"):
        out.append(f"- 가점: +{score['bonus']}")
    if score.get("penalty"):
        out.append(f"- 감점: {score['penalty']}")
    out.append("")

    icon = {"적용": "✅", "부분적용": "⚠️", "미적용": "❌", "해당없음": "—"}
    out += ["| # | 기술요소 | 상태 | 적용 비율 | 비고 |", "|---|---|---|---|---|"]
    for num, key, label in GR_ELEMENT_LABELS:
        info = gr_mapping.get(key)
        if not info:
            continue
        st = info.get("status", "?")
        ratio = info.get("적용비율")
        rs = f"{ratio*100:.0f}%" if ratio is not None else "-"
        note = ""
        if info.get("미적용_m2", 0) > 0:
            note = f"미적용 {info['미적용_m2']:.1f}㎡"
        elif "용량_kW" in info:
            note = f"{info['용량_kW']}kW · 자립률 {info.get('자립률_추정', 0)*100:.1f}%"
        elif info.get("전체_개수", 0) > 0:
            note = f"LED {info.get('LED_개수', 0)}/{info['전체_개수']}개"
        out.append(f"| {num} | {label} | {icon.get(st, '—')} {st} | {rs} | {note} |")
    out.append("")

    _un = score.get("_미평가") or []
    if _un:
        out += [
            f"⚠️ **미평가 {len(_un)}건** — 채점 가능 최대 "
            f"{score.get('_채점가능최대', '—')}점. 입력이 없어 비워 둔 항목입니다:",
            "",
            "| 항목 | 만점 | 왜 비었나 |",
            "|---|---|---|",
        ]
        for x in _un:
            # dict를 그대로 f-string에 넣으면 "{'항목': ..., '만점': 3}"이 화면에 샌다
            if isinstance(x, dict):
                out.append(f"| {x.get('항목', '—')} | {x.get('만점', '—')}점 | "
                           f"{x.get('사유', '—')} |")
            else:
                out.append(f"| {x} | — | — |")
        out.append("")
    return out


def _section_cost(roi_plan: list) -> list:
    out = ["## 3. 보강 계획 · 비용", ""]
    if not roi_plan:
        out += ["*보강 계획이 없습니다.*", ""]
        return out
    total = sum(x.get("Max_Cost", 0) for x in roi_plan)
    uplift = sum(x.get("점수상승", 0) for x in roi_plan)
    out += [
        f"**전체 보강 비용 {_eok(total)}** · 점수 상승 **+{uplift}점**",
        "",
        "| 우선순위 | 항목 | 수량 | Max Cost | +점수 | 효율(점/억) |",
        "|---|---|---|---|---|---|",
    ]
    for i, x in enumerate(roi_plan, 1):
        out.append(
            f"| {i} | {x.get('label', '—')} | "
            f"{x.get('수량', '')} {x.get('단위', '')} | {_won(x.get('Max_Cost'))} | "
            f"+{x.get('점수상승', 0)} | {x.get('효율_점수당억', 0):.2f} |"
        )
    out += [
        f"| | **합계** | | **{_won(total)}** | **+{uplift}** | |",
        "",
        "> Max Cost = 조달청 단가DB × 물량 + 간접공사비(조달청 매트릭스, 공사기간 반영).",
        "> 효율이 높은 순으로 정렬했습니다 — 예산이 한정되면 위에서부터 채택합니다.",
        "",
    ]
    return out


def _section_econ(econ: Optional[dict]) -> list:
    out = ["## 4. 경제성", ""]
    if not econ:
        out += [
            "*경제성 지표가 없습니다 — 보조율·절감액 입력이 필요합니다.*", "",
        ]
        return out
    out += [
        "| 지표 | 값 |",
        "|---|---|",
        f"| 보조금 | {_won(econ.get('보조금'))} |",
        f"| 자부담 | {_won(econ.get('자부담'))} |",
        f"| NPV (20년) | {_eok(econ.get('npv'))} |",
        f"| IRR | {econ.get('irr_pct', 0):.1f}% |" if econ.get("irr_pct") is not None
        else "| IRR | — |",
        f"| B/C 비율 | {econ.get('bc_ratio', 0):.2f}배 |",
        f"| 단순 회수기간 | {econ.get('simple_payback_years', 0):.1f}년 |",
        "",
        "> 할인율 4.5% · 에너지상승률 2.5% · 20년 기준.",
        "> ⚠️ 연간 절감액은 **추정치**입니다 — 단가(140.9원/kWh)는 한전 약관 원문으로 "
        "확정됐지만, 곱해지는 절감량은 ECO2 정식 해석 전이라 가정입니다.",
        "",
    ]
    return out


def _section_eplus(ep: Optional[dict], area_m2: float = 0) -> list:
    out = ["## 5. EnergyPlus 에너지 해석", ""]
    if not ep:
        out += [
            "**돌리지 않았습니다.** BIM 진단 화면에서 gbXML을 올리고 "
            "`🔬 EnergyPlus 실행`을 누르면 이 자리에 연간 해석 결과가 들어갑니다.",
            "",
            "> EnergyPlus는 그린리모델링 창조센터 **지정 프로그램**입니다"
            "(2026 민간 GR 공고 p.3·p.16 각주).",
            "",
        ]
        return out

    from core.eplus_client import label_meter

    out.append(f"기상: `{ep.get('weather', '—')}` · 8,760시간 연간 해석")
    out.append("")
    rows = []
    for k, v in (ep.get("meters") or {}).items():
        lb = label_meter(k)
        if not lb or not isinstance(v, dict):
            continue
        kwh = v.get("annual_kWh", 0)
        per = f"{kwh / area_m2:,.1f}" if area_m2 else "—"
        rows.append(f"| {lb[1]} {lb[0]} | {kwh:,.0f} kWh | {per} |")
    if rows:
        out += ["| 항목 | 연간 | kWh/㎡ |", "|---|---|---|"] + rows + [""]
    _w = (ep.get("errors") or {}).get("warning_count", 0)
    if _w:
        out.append(f"EnergyPlus 경고 {_w}건.")
        out.append("")
    out += [
        "> ⚠️ **이 값을 신청서에 그대로 쓰지 마세요.** 실제 설비가 아니라 "
        "IdealLoads(이상적 공조)로 **부하만** 뽑은 값이고, 재실·조명·기기 일정과 "
        "SHGC는 표준 가정입니다.",
        "> 공고는 '에너지 요구량' 기준을 허용하므로 지표 자체는 성립하지만, "
        "같은 각주가 용도프로필·기상데이터를 ZEB 운영규정 **별표2·별표6으로 준용**"
        "하라고 합니다 — 우리는 둘 다 안 지킵니다.",
        "",
    ]
    return out


def _section_sens(sens: Optional[dict]) -> list:
    out = ["## 6. 민감도", ""]
    if not sens:
        out += ["*민감도 분석 결과가 없습니다.*", ""]
        return out
    for title, rows in sens.items():
        if not rows:
            continue
        out += [f"### {title}", "", "| 조건 | 회수기간 | NPV |", "|---|---|---|"]
        for r in rows:
            out.append(
                f"| {r.get('label', '—')} | {r.get('payback', '—')} | {r.get('npv', '—')} |"
            )
        out.append("")
    return out


def build_full_report(
    result: dict,
    source_name: str = "bim.json",
    zeb: Optional[dict] = None,
    econ: Optional[dict] = None,
    eplus: Optional[dict] = None,
    sens: Optional[dict] = None,
    build: Optional[dict] = None,
) -> str:
    """화면의 흐름 그대로 한 문서로 묶는다.

    ZEB 등급 → GR 진단 → 보강·비용 → 경제성 → 에너지 해석 → 민감도
    """
    bim = result.get("bim_data") or {}
    area = float(bim.get("total_area_m2") or 0)
    b = build or {}

    lines = [
        "# 종합 리포트",
        "",
        f"**대상** {source_name}"
        + (f" · 연면적 {area:,.0f}㎡" if area else "")
        + (f" · {bim.get('building_usage')}" if bim.get("building_usage") else ""),
        "",
        f"*생성 {b.get('date', '')} · 엔진 `{b.get('commit', '')}`*",
        "",
        "> 이 문서는 **자동 산출 결과**입니다. 실제 사업 신청 시 "
        "그린리모델링 창조센터(1588-8788) 공식 컨설팅이 필요합니다.",
        "",
        "---",
        "",
    ]
    lines += _section_zeb(zeb)
    lines += _section_gr(result.get("score") or {}, result.get("gr_mapping") or {})
    lines += _section_cost(result.get("roi_plan") or [])
    lines += _section_econ(econ)
    lines += _section_eplus(eplus, area)
    lines += _section_sens(sens)
    lines += [
        "---",
        "",
        "**출처** — 공사비: 조달청 단가DB + 간접공사비 매트릭스(2026) · "
        "보조율: 공공건축물 GR 지원사업 운영지침 [별표3] · "
        "ZEB 등급: 제로에너지건축물 인증 기준 공동고시(국토부 제2024-893호 / "
        "산업부 제2024-208호) · 전기 단가: 한국전력 기본공급약관 [별표1].",
    ]
    return "\n".join(lines)
