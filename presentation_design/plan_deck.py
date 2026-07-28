# -*- coding: utf-8 -*-
"""
ZEB-ROI 아이디어 기획서 — 디자인 시안.

나인와트 덱의 규율(머리말 바 · 큰 숫자는 도형 안 · OUTPUT만 색 반전 · 되먹임 라벨)을
가져오되 색과 형태는 우리 것(딥그린 · 선 도형)으로 바꾼다.

★ 배포용(PDF로 읽는 기획서) 기준. 캔버스 1280단위 = PowerPoint 13.333in이므로
  1단위 = 0.75pt. 본문 하한 11pt = 14.7단위 → 아래 TYPE의 body를 15로 잡았다.
  첫 시안은 body 10(=7.5pt)이라 레퍼런스 중 제일 작은 사이드바보다도 작았다.
  글자를 키우면 가로가 모자라므로 '두 트랙 상세'를 06장으로 분리했다.
"""
import os
from PIL import Image, ImageDraw, ImageFont

NOTO = "C:/Windows/Fonts/NotoSansKR-VF.ttf"
BASE = "C:/Users/이혁주/Desktop/zeb-chatbot/presentation_design/"
OUT = BASE + "plan_slides/"
os.makedirs(OUT, exist_ok=True)

W, H, S = 1280, 720, 3
INK   = (18, 32, 26)       # #12201A
GREEN = (15, 74, 59)       # #0F4A3B
BG    = (239, 245, 241)    # #EFF5F1
CARD  = (255, 255, 255)
G1    = (92, 102, 95)      # 본문 회색
G2    = (138, 150, 143)    # 보조
G3    = (207, 220, 213)    # 선
CHEV  = (150, 178, 165)    # 갈매기 — G3로 두면 배경에 묻힌다
MX    = 64

# 크기는 여기 한 곳에서만 정한다. 옆의 pt는 PowerPoint 16:9 환산값.
TYPE = {
    "head":   30,    # 22.5pt  헤드라인
    "sub":    14,    # 10.5pt  헤드라인 부제
    "kicker": 12,    #  9.0pt  머리말
    "zone":   12,    #  9.0pt  구역 이름
    "bxt":    17,    # 12.8pt  박스 제목
    "bxs":    14.5,  # 10.9pt  박스 부제
    "body":   16,    # 12.0pt  본문
    "outc":   16,    # 12.0pt  OUTPUT 카드
    "concl":  16,    # 12.0pt  결론 한 줄
    "note":   12,    #  9.0pt  ※ 주석
    "foot":   11,    #  8.3pt  근거 각주
}

_fc = {}
OVERFLOW = []
MISSING = set()

# NotoSansKR-VF에 없는 글자는 두부(□)로 찍힌다. 렌더 결과를 눈으로 봐야만 알 수 있어서
# 실제로 06장의 아래첨자 ᵢ가 □로 나왔다. 쓰기 전에 cmap으로 걸러 둔다.
try:
    from fontTools.ttLib import TTFont as _TTF
    _CMAP = set()
    for _t in _TTF(NOTO)["cmap"].tables:
        _CMAP |= set(_t.cmap.keys())
except Exception:
    _CMAP = None


def F(weight, size):
    key = (weight, round(size * S))
    if key in _fc:
        return _fc[key]
    f = ImageFont.truetype(NOTO, round(size * S))
    for arg in (weight, weight.encode()):
        try:
            f.set_variation_by_name(arg)
            break
        except Exception:
            continue
    _fc[key] = f
    return f


class Slide:
    def __init__(s, bg=BG):
        s.img = Image.new("RGB", (W * S, H * S), bg)
        s.d = ImageDraw.Draw(s.img)

    def T(s, x, y, t, w, sz, c, anchor="la", track=0.0):
        if _CMAP is not None:
            for ch in t:
                if ch != "\n" and ord(ch) not in _CMAP:
                    MISSING.add((ch, hex(ord(ch))))
        f = F(w, sz)
        if track == 0:
            s.d.text((x * S, y * S), t, font=f, fill=c, anchor=anchor)
            return
        cx = x * S
        for ch in t:
            s.d.text((cx, y * S), ch, font=f, fill=c, anchor=anchor)
            cx += f.getlength(ch) + track * S

    def line(s, x0, y0, x1, y1, c, w=1.0):
        s.d.line([x0 * S, y0 * S, x1 * S, y1 * S], fill=c, width=max(1, round(w * S)))

    def rect(s, x0, y0, x1, y1, fill=None, outline=None, w=1.0, r=0):
        bb = [x0 * S, y0 * S, x1 * S, y1 * S]
        if r > 0:
            s.d.rounded_rectangle(bb, radius=r * S, fill=fill, outline=outline,
                                  width=max(1, round(w * S)))
        else:
            s.d.rectangle(bb, fill=fill, outline=outline, width=max(1, round(w * S)))

    def poly(s, pts, fill):
        s.d.polygon([(x * S, y * S) for x, y in pts], fill=fill)

    def measure(s, t, w, sz):
        return F(w, sz).getlength(t) / S

    def save(s, n):
        s.img.save(OUT + n, "PNG")
        return OUT + n


def fit(s, t, w, sz, maxw, where):
    """카드 안 글자가 테두리를 넘는지. 2px 넘침도 인쇄하면 붙어 보이는데 눈으로는 못 잡는다."""
    got = s.measure(t, w, sz)
    if got > maxw:
        OVERFLOW.append(f"{where}: {got:.1f} > {maxw:.1f}  \"{t}\"")
    return t


# ── furniture ──────────────────────────────────────────────────────────
def header(s, kicker, num, title, sub=None):
    s.T(MX, 42, kicker, "Medium", TYPE["kicker"], G2, track=1.6)
    s.T(W - MX, 42, num, "Bold", TYPE["kicker"], G2, anchor="ra", track=1.6)
    s.line(MX, 70, W - MX, 70, G3, 1.0)
    s.T(MX, 88, title, "Bold", TYPE["head"], INK)
    if sub:
        s.T(MX, 134, sub, "Regular", TYPE["sub"], G1)


def footer(s, src):
    s.line(MX, 676, W - MX, 676, G3, 1.0)
    s.T(MX, 688, src, "Regular", TYPE["foot"], G2)


def zone(s, x, y, label):
    s.T(x, y, label, "Medium", TYPE["zone"], G2, track=1.4)


def box(s, x, y, w, h, title, sub=None):
    s.rect(x, y, x + w, y + h, fill=CARD, outline=G3, w=1.0, r=9)
    inner = w - 30
    if sub:
        s.T(x + 15, y + h / 2 - 19, fit(s, title, "Bold", TYPE["bxt"], inner, "box"),
            "Bold", TYPE["bxt"], INK)
        s.T(x + 15, y + h / 2 + 2, fit(s, sub, "Regular", TYPE["bxs"], inner, "box"),
            "Regular", TYPE["bxs"], G1)
    else:
        s.T(x + 15, y + h / 2 - 9, fit(s, title, "Bold", TYPE["bxt"], inner, "box"),
            "Bold", TYPE["bxt"], INK)


def chevron(s, x, y, sz=11):
    s.poly([(x, y - sz), (x + sz * 0.85, y), (x, y + sz)], CHEV)


def bracket(s, x0, x1, y, label):
    """되먹임·검증 라벨. 나인와트 8장의 Validation 자리. 부제는 빼고 한 줄만."""
    s.line(x0, y, x1, y, G3, 1.0)
    s.line(x0, y, x0, y - 6, G3, 1.0)
    s.line(x1, y, x1, y - 6, G3, 1.0)
    s.T((x0 + x1) / 2, y + 10, label, "Bold", TYPE["body"], GREEN, anchor="ma")


def conclusion(s, y, text):
    s.rect(MX, y, W - MX, y + 46, fill=CARD, outline=G3, w=1.0, r=8)
    s.rect(MX, y, MX + 4, y + 46, fill=GREEN, r=0)
    s.T(MX + 22, y + 15, text, "Bold", TYPE["concl"], INK)


# ── 05 · 아키텍처 ──────────────────────────────────────────────────────
def s05_architecture():
    s = Slide()
    header(s, "CORE TECHNOLOGY  |  구조", "05",
           "판정은 분리하고, 기반은 공유합니다",
           "판정만 두 갈래로 나누고, 해석·단가·법령은 하나만 둡니다.")

    TOP, BY, BB = 184, 210, 478
    # 판정 칼럼(카드 2장)은 06장이 통째로 다루므로 여기선 '갈라진다'만 선으로 보인다.
    # 칼럼 하나를 걷어낸 만큼 남은 셋이 넓어지고 글자를 12pt로 올릴 수 있었다.
    cx = [MX, 380, 890]
    cw = [250, 330, 326]
    FX = 762                      # 분기점 x

    zone(s, cx[0], TOP, "INPUT")
    zone(s, cx[1], TOP, "공유 코어  ·  하나만 존재")
    zone(s, 726, TOP, "판정 · 두 갈래")
    zone(s, cx[2], TOP, "OUTPUT")

    # INPUT — 이름만. 부제를 붙이면 읽을 게 늘 뿐 뜻이 더해지지 않는다.
    ins = ["gbXML (Revit)", "데모 케이스 4종", "자연어 문장"]
    g, hh = 26, (BB - BY - 26 * 2) / 3
    for i, t in enumerate(ins):
        box(s, cx[0], BY + i * (hh + g), cw[0], hh, t)

    # 공유 코어 — 숫자가 곧 근거라 부제로 남긴다.
    core = [("gbXML 파서", "부재 · 좌표 · 열관류율"),
            ("EnergyPlus 25.1", "IDF 직접 생성 · 별도 서비스에서 실행"),
            ("단가 DB", "조달청 자재 442종"),
            ("법령 RAG", "원문 19건 · 1,300청크")]
    g, hh = 18, (BB - BY - 18 * 3) / 4
    for i, (t, u) in enumerate(core):
        box(s, cx[1], BY + i * (hh + g), cw[1], hh, t, u)

    outs = ["ZEB 인증 등급", "GR 정량평가 점수", "보강 우선순위",
            "공사비 · 보조금 · 자부담", "NPV · IRR · B/C · 회수", "신청서 초안 · 근거·출처"]
    g = 11
    hh = (BB - BY - g * 5) / 6
    for i, t in enumerate(outs):
        y = BY + i * (hh + g)
        s.rect(cx[2], y, cx[2] + cw[2], y + hh, fill=GREEN, r=8)
        fit(s, t, "Medium", TYPE["outc"], cw[2] - 32, "output")
        s.T(cx[2] + 16, y + hh / 2 - 10, t, "Medium", TYPE["outc"], CARD)

    # 분기 — 판정만 두 갈래로 갈라졌다가 다시 한 화면으로 모인다
    mid = (BY + BB) / 2
    up, dn = mid - 74, mid + 74
    s.line(cx[0] + cw[0] + 12, mid, cx[1] - 12, mid, G3, 1.2)
    chevron(s, cx[1] - 26, mid)
    s.line(cx[1] + cw[1] + 12, mid, FX, mid, G3, 1.2)
    s.line(FX, up, FX, dn, G3, 1.2)
    for yy, lab in ((up, "ZEB 인증"), (dn, "그린리모델링")):
        s.line(FX, yy, cx[2] - 26, yy, G3, 1.2)
        chevron(s, cx[2] - 26, yy)
        s.T(FX + 10, yy - 25, fit(s, lab, "Bold", TYPE["bxs"], cx[2] - FX - 34, "rail"),
            "Bold", TYPE["bxs"], GREEN)

    bracket(s, MX, cx[1] + cw[1], 522, "입력 검증 — 못 믿을 파일은 진단을 시작하지 않는다")

    s.T(MX, 576, "※  좌표가 없는 모델은 에너지 해석을 실행하지 않고 진단·공사비·경제성까지만 수행합니다.",
        "Regular", TYPE["note"], G2)
    conclusion(s, 608, "해석·단가·법령을 하나만 두었기에, 두 제도의 답이 같은 건물에서 어긋나지 않습니다.")
    footer(s, "근거  ·  ZEB 인증기준 공동고시 [별표2]  |  GR 지원사업 운영고시 §9  |  2026 공공 GR 2.0 가이드라인 p.18")
    return s.save("05_architecture.png")


# ── 06 · 두 트랙 ───────────────────────────────────────────────────────
def s06_tracks():
    s = Slide()
    header(s, "CORE TECHNOLOGY  |  두 트랙", "06",
           "같은 건물인데, 두 제도는 서로 다른 것을 묻습니다",
           "ZEB는 기준선을 넘었는지를 묻고, 그린리모델링은 얼마나 나아졌는지를 묻습니다.")

    CY, CH_ = 202, 288      # 행을 5→4로 줄인 만큼 카드도 낮춘다
    cwid = 508
    lx, rx = MX, W - MX - cwid

    cards = [
        (lx, "Track A", "ZEB 인증", "절대 성능 — 기준선을 넘었는가",
         [("근거", "ZEB 인증기준 공동고시 [별표2]"),
          ("판정", "제1호 에너지자립률  또는  제2호 1차에너지소요량"),
          ("규칙", "둘 중 상위 등급으로 확정 · 제3호 BEMS는 필수"),
          ("결과", "+등급 ~ 5등급")],
         "기준을 넘으면 등급이 나온다. 남과 비교하지 않는다."),
        (rx, "Track B", "그린리모델링 지원사업", "상대 개선 — 얼마나 나아졌는가",
         [("근거", "GR 지원사업 운영고시 §9 · 2026 공공 GR 2.0 [표1]"),
          ("판정", "정량평가 100점 = 요소 80 + 사업여건 20"),
          ("규칙", "가점 14 · 감점 −10"),
          ("결과", "등급 없음 — 고득점 순으로 선정")],
         "등급이 아니라 순위다. 남보다 높아야 뽑힌다."),
    ]

    for x, badge, title, lead, rows, tail in cards:
        s.rect(x, CY, x + cwid, CY + CH_, fill=CARD, outline=G3, w=1.0, r=10)
        s.rect(x, CY, x + 4, CY + CH_, fill=GREEN, r=0)
        # 배지
        bw = s.measure(badge, "Bold", TYPE["zone"]) + 24
        s.rect(x + 26, CY + 24, x + 26 + bw, CY + 50, fill=GREEN, r=13)
        s.T(x + 26 + bw / 2, CY + 30, badge, "Bold", TYPE["zone"], CARD, anchor="ma")
        s.T(x + 26 + bw + 14, CY + 28, fit(s, title, "Bold", TYPE["bxt"], cwid - bw - 80, "t"),
            "Bold", TYPE["bxt"], INK)
        s.T(x + 26, CY + 66, lead, "Bold", TYPE["body"], GREEN)
        s.line(x + 26, CY + 96, x + cwid - 26, CY + 96, G3, 1.0)
        for i, (k, v) in enumerate(rows):
            y = CY + 112 + i * 34
            s.T(x + 26, y, k, "Medium", TYPE["bxs"], G2)
            s.T(x + 84, y, fit(s, v, "Regular", TYPE["body"], cwid - 116, "row"),
                "Regular", TYPE["body"], INK)
        s.line(x + 26, CY + 248, x + cwid - 26, CY + 248, G3, 1.0)
        s.T(x + 26, CY + 260, tail, "Bold", TYPE["bxs"], G1)

    # 가운데 연결 — 같은 건물
    mid = W / 2
    s.T(mid, 170, "같은 건물", "Bold", TYPE["bxs"], G2, anchor="ma")
    s.line(lx + cwid + 8, 346, rx - 8, 346, G3, 1.0)
    s.poly([(lx + cwid + 8, 346), (lx + cwid + 18, 340), (lx + cwid + 18, 352)], CHEV)
    s.poly([(rx - 8, 346), (rx - 18, 340), (rx - 18, 352)], CHEV)

    s.T(MX, 542, "두 값을 섞으면 조용히 틀립니다 — 같은 대상 건물에서도 기준이 다르면 결과가 갈립니다.",
        "Bold", TYPE["body"], INK)
    # 실제 저장소 값 (core/gr_evaluator.py · modes/mode6_glossary.py)
    facts = [("ZEB 절감률", "50.5%", ""),
             ("GR 성능개선비율", "41.2%", "")]
    for i, (k, v, d) in enumerate(facts):
        x = MX + i * 560
        s.rect(x, 566, x + 520, 616, fill=CARD, outline=G3, w=1.0, r=8)
        s.T(x + 18, 580, k, "Medium", TYPE["bxs"], G2)
        s.T(x + 175, 572, v, "Bold", 26, GREEN)
        s.T(x + 268, 582, d, "Regular", TYPE["note"], G1)

    conclusion(s, 628, "같은 건물에서 9.3%p가 갈립니다. 그래서 판정을 하나로 합칠 수 없습니다.")
    footer(s, "근거  ·  ZEB 인증기준 공동고시 [별표2]  |  GR 지원사업 운영고시 §9  |  2026 공공 GR 2.0 가이드라인 [표1] p.18")
    return s.save("06_tracks.png")


if __name__ == "__main__":
    for f in (s05_architecture, s06_tracks):
        print(f())
    print("\n" + ("!! 글자가 상자를 넘음:" if OVERFLOW else "글자 넘침 없음"))
    for o in OVERFLOW:
        print("  ", o)
    if MISSING:
        print("!! 폰트에 없는 글자 (두부로 찍힘):", sorted(MISSING))
    else:
        print("폰트에 없는 글자 없음")
    print(f"\n본문 {TYPE['body']}단위 = {TYPE['body']*0.75:.1f}pt (배포용 하한 11pt)")
