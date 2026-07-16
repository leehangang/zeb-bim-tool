"""
core/pdf_report.py — PDF 진단 리포트 생성
==========================================
Mode 3 진단 결과를 PDF로 변환. reportlab 기반.

한국어 PDF 생성 시 한글 폰트가 필요한데, 시스템에 있는 폰트 또는 reportlab 내장 CJK 폰트를 사용합니다.
- 내장 CID: HeiseiMin-W3, STSong-Light 등 (일본어/중국어용이지만 한자만 일부 지원)
- 안전한 방법: HTML 기반 PDF (reportlab의 platypus + BabelStone Han 등) 또는 weasyprint
- 졸업설계 단계: 시스템 폰트 시도 → 실패 시 영문+한자만 출력 + 한글은 마크다운 별첨

이 구현은 **HTML 마크업을 reportlab으로 렌더**하는 방식.
한국어 글꼴 등록 시도, 안 되면 안내 메시지와 함께 시각 요약만 출력.
"""

import io
from typing import Optional


def _try_register_korean_font():
    """
    시스템에서 한국어 폰트를 찾아 reportlab에 등록.

    Returns:
        등록된 폰트 이름 (str) 또는 None (실패)
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    candidates = [
        # Windows
        ("C:/Windows/Fonts/malgun.ttf",          "MalgunGothic"),
        ("C:/Windows/Fonts/malgunbd.ttf",        "MalgunGothicBold"),
        ("C:/Windows/Fonts/NanumGothic.ttf",     "NanumGothic"),
        ("C:/Windows/Fonts/batang.ttc",          "Batang"),
        # macOS
        ("/Library/Fonts/AppleGothic.ttf",       "AppleGothic"),
        ("/System/Library/Fonts/AppleSDGothicNeo.ttc", "AppleSDGothic"),
        # Linux
        ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",  "NanumGothic"),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "NotoSansCJK"),
        ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "NotoSansCJK"),
    ]

    for path, name in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                return name
            except Exception:
                continue
    return None


def generate_pdf_report(result: dict, source_name: str = "BIM") -> bytes:
    """
    Mode 3 진단 결과 dict → PDF 바이트.

    Args:
        result: run_bim_diagnosis() 결과
        source_name: 원본 파일명 (PDF 헤더에 표시)

    Returns:
        PDF 파일 바이트 (Streamlit st.download_button data로 직접 사용 가능)
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER

    # 한글 폰트 등록 시도
    font_name = _try_register_korean_font() or "Helvetica"
    bold_font = font_name if font_name == "Helvetica" else font_name

    # 스타일
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "H1Korean", parent=styles["Heading1"],
        fontName=font_name, fontSize=18, leading=22,
        textColor=colors.HexColor("#1B5E20"),
        spaceAfter=8,
    )
    h2 = ParagraphStyle(
        "H2Korean", parent=styles["Heading2"],
        fontName=font_name, fontSize=14, leading=18,
        textColor=colors.HexColor("#1A1A1A"),
        spaceAfter=6, spaceBefore=12,
    )
    body = ParagraphStyle(
        "BodyKorean", parent=styles["BodyText"],
        fontName=font_name, fontSize=10, leading=14,
    )
    small = ParagraphStyle(
        "SmallKorean", parent=styles["BodyText"],
        fontName=font_name, fontSize=8, leading=11,
        textColor=colors.HexColor("#757575"),
    )
    title_white = ParagraphStyle(
        "TitleWhite", parent=styles["Heading1"],
        fontName=font_name, fontSize=17, leading=21, textColor=colors.white,
    )
    subtitle_white = ParagraphStyle(
        "SubWhite", parent=styles["BodyText"],
        fontName=font_name, fontSize=9, leading=12, textColor=colors.HexColor("#C8E6C9"),
    )

    # 메모리 버퍼에 PDF 생성
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=18*mm, bottomMargin=18*mm,
    )

    story = []

    # ─────────────────────────────────────
    # 헤더
    # ─────────────────────────────────────
    import datetime
    from core.zeb_evaluator import detect_building_use
    bim = result.get("bim_data", {}) or {}
    use = detect_building_use(bim)
    area = bim.get("total_area_m2", "-")
    today = datetime.date.today().strftime("%Y-%m-%d")

    header_band = Table([[
        Paragraph("ZEB-ROI 그린리모델링 진단 리포트", title_white),
        Paragraph(f"발행일<br/>{today}", subtitle_white),
    ]], colWidths=[120*mm, 54*mm])
    header_band.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#1B5E20")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("ALIGN", (1,0), (1,0), "RIGHT"),
    ]))
    story.append(header_band)
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        f"BIM 정밀 진단 · ROI · ZEB 인증 평가&nbsp;&nbsp;|&nbsp;&nbsp;"
        f"대상: {use} (연면적 {area}㎡)&nbsp;&nbsp;|&nbsp;&nbsp;원본: {source_name}",
        small,
    ))
    story.append(Spacer(1, 10))

    # ─────────────────────────────────────
    # 핵심 지표
    # ─────────────────────────────────────
    score = result["score"]
    plan = result.get("roi_plan", []) or []
    total_cost = sum(p.get("Max_Cost", 0) for p in plan)
    total_uplift = sum(p["점수상승"] for p in plan)
    new_score = score["total_score"] + total_uplift

    summary_data = [
        ["항목", "현재", "보강 후"],
        ["정량평가 점수 (100점)", f"{score['total_score']}점", f"{new_score}점"],
        ["GR 요소 점수 (80)", f"{score['gr_subtotal']}점",    f"{score['gr_subtotal']+total_uplift}점"],
        ["사업여건 (20)",     f"{score['site_subtotal']}점", f"{score['site_subtotal']}점"],
        ["보강 비용 (Max Cost)",  "-",                        f"{total_cost/1e8:.2f}억"],
    ]
    table = Table(summary_data, colWidths=[55*mm, 50*mm, 50*mm])
    table.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), font_name, 10),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1B5E20")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTSIZE", (0,0), (-1,0), 11),
        ("ALIGN", (0,0), (-1,-1), "LEFT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("BACKGROUND", (0,1), (-1,-1), colors.HexColor("#F9FBF9")),
        ("LINEBELOW", (0,0), (-1,0), 0.5, colors.HexColor("#2E7D32")),
        ("GRID", (0,1), (-1,-1), 0.25, colors.HexColor("#E0E0E0")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#F9FBF9"), colors.white]),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))

    # ─────────────────────────────────────
    # ZEB 인증 평가 (현재 → 권장 보강 후)
    # ─────────────────────────────────────
    try:
        from core.zeb_evaluator import evaluate_zeb
        gr = result.get("gr_mapping", {})
        z_cur = evaluate_zeb(bim, gr, building_use=use)
        z_aft = evaluate_zeb(bim, gr, building_use=use,
                             assume_full_reinforcement=True, assume_bems=True)
        story.append(Paragraph("ZEB 인증 평가", h2))
        zeb_rows = [
            ["항목", "현재", "권장 보강 후"],
            ["에너지자립률 (제1호)",
             f"{z_cur['autonomy_pct']:.1f}%", f"{z_aft['autonomy_pct']:.1f}%"],
            ["1차에너지소요량 순 (제2호)",
             f"{z_cur['net_primary_kwh_m2']:.0f} kWh/㎡", f"{z_aft['net_primary_kwh_m2']:.0f} kWh/㎡"],
            ["ZEB 인증등급",
             z_cur["grade"]["label"], z_aft["grade"]["label"]],
            ["인증 가능 여부",
             "충족" if z_cur["zeb_requirements"]["인증가능"] else "미충족",
             "충족" if z_aft["zeb_requirements"]["인증가능"] else "미충족"],
        ]
        zeb_table = Table(zeb_rows, colWidths=[55*mm, 50*mm, 50*mm])
        zeb_table.setStyle(TableStyle([
            ("FONT", (0,0), (-1,-1), font_name, 10),
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2E7D32")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("GRID", (0,1), (-1,-1), 0.25, colors.HexColor("#E0E0E0")),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#F1F8F1"), colors.white]),
        ]))
        story.append(zeb_table)
        story.append(Paragraph(
            "ZEB 인증 = (제1호 자립률 또는 제2호 1차에너지소요량) + 제3호 BEMS 설치. "
            "‘권장 보강 후’는 11개 GR 기술요소 전체 적용 + BEMS 설치를 가정한 잠재 등급입니다.",
            small,
        ))
        story.append(Spacer(1, 12))
    except Exception:
        pass

    # ─────────────────────────────────────
    # 11개 GR 매핑
    # ─────────────────────────────────────
    story.append(Paragraph("11개 GR 기술요소 현황", h2))

    gr_rows = [["#", "기술요소", "상태", "적용비율", "비고"]]
    for key, info in result["gr_mapping"].items():
        num = key.split("_")[0]
        label = key.split("_", 1)[1]
        status = info.get("status", "?")
        ratio = info.get("적용비율")
        ratio_str = f"{ratio*100:.0f}%" if ratio is not None else "-"
        note = ""
        if "미적용_m2" in info and info["미적용_m2"] > 0:
            note = f"미적용 {info['미적용_m2']:.0f}㎡"
        elif "용량_kW" in info:
            note = f"{info['용량_kW']}kW (자립률 {info['자립률_추정']*100:.1f}%)"
        elif "LED_개수" in info and info.get("전체_개수", 0) > 0:
            note = f"LED {info['LED_개수']}/{info['전체_개수']}개"
        gr_rows.append([num, label, status, ratio_str, note])

    gr_table = Table(gr_rows, colWidths=[10*mm, 50*mm, 25*mm, 22*mm, 50*mm])
    gr_table.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), font_name, 9),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#5D4037")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (0,0), (0,-1), "CENTER"),
        ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#E0E0E0")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#FAFAFA")]),
    ]))
    story.append(gr_table)
    story.append(Spacer(1, 10))

    # ─────────────────────────────────────
    # 보강 우선순위 Top 5
    # ─────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("보강 우선순위 Top 5 (효율 기준)", h2))

    top_rows = [["순위", "항목", "수량", "예상 비용", "+점수", "효율"]]
    for i, p in enumerate(plan[:5], 1):
        top_rows.append([
            str(i),
            p["label"],
            f"{p['수량']:.1f} {p['단위']}",
            f"{p['Max_Cost']:,}원",
            f"+{p['점수상승']}",
            f"{p['효율_점수당억']:.1f}",
        ])
    top_table = Table(top_rows, colWidths=[12*mm, 65*mm, 28*mm, 35*mm, 15*mm, 15*mm])
    top_table.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), font_name, 9),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1B5E20")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (0,0), (0,-1), "CENTER"),
        ("ALIGN", (3,1), (5,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#E0E0E0")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#FAFAFA")]),
    ]))
    story.append(top_table)
    story.append(Spacer(1, 10))

    # ─────────────────────────────────────
    # 전체 11개 보강 표
    # ─────────────────────────────────────
    story.append(Paragraph("전체 11개 보강 계획", h2))

    full_rows = [["#", "항목", "비용", "+점수", "효율(점/억)"]]
    for i, p in enumerate(plan, 1):
        full_rows.append([
            str(i),
            p["label"],
            f"{p['Max_Cost']:,}원",
            f"+{p['점수상승']}",
            f"{p['효율_점수당억']:.2f}",
        ])
    full_rows.append([
        "", "합계",
        f"{total_cost:,}원",
        f"+{total_uplift}",
        "-",
    ])
    full_table = Table(full_rows, colWidths=[12*mm, 70*mm, 38*mm, 18*mm, 22*mm])
    full_table.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), font_name, 9),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1B5E20")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTSIZE", (0,0), (-1,0), 9),
        ("ALIGN", (0,0), (0,-1), "CENTER"),
        ("ALIGN", (2,1), (4,-1), "RIGHT"),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#FFF3E0")),
        ("FONT", (0,-1), (-1,-1), font_name, 9),
        ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#E0E0E0")),
    ]))
    story.append(full_table)
    story.append(Spacer(1, 14))

    # ─────────────────────────────────────
    # 면책 조항
    # ─────────────────────────────────────
    story.append(Paragraph(
        "<font color='#9E9E9E'>"
        "본 진단 결과는 자동 산출된 참고용 값입니다. "
        "실제 사업 신청·시공 시 그린리모델링 창조센터(1588-8788) 공식 컨설팅, "
        "견적사·시공사 검토, 변호사·세무사 자문이 필요합니다.<br/>"
        "단가 출처: 07 조달청 단가DB + 08 간접공사비 매트릭스 (2026년 기준).<br/>"
        "정책 출처: 01 GR 가이드라인, 04 녹색건축법 §15, 05 지방세특례 §47의2."
        "</font>",
        small,
    ))

    # 페이지 푸터 (브랜드 + 페이지 번호)
    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor("#9E9E9E"))
        canvas.drawString(18*mm, 10*mm,
                          "ZEB-ROI · 그린리모델링 의사결정 플랫폼")
        canvas.drawRightString(A4[0]-18*mm, 10*mm, f"- {doc_.page} -")
        canvas.setStrokeColor(colors.HexColor("#E0E0E0"))
        canvas.line(18*mm, 13*mm, A4[0]-18*mm, 13*mm)
        canvas.restoreState()

    # 빌드
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)

    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


# _grade_from_score_local() 제거 (2026-07) — A+~D는 제도에 없는 등급이었다.
# 정량평가표는 선정 랭킹 점수다. core.bim_diagnoser.score_compliance 주석 참고.
