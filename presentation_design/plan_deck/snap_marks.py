# -*- coding: utf-8 -*-
"""
09~12장 확대 영역의 경계를 '글자 없는 줄'에 맞춘다.

무엇이 문제였나
---------------
확대 상자에 보여 줄 원본 영역을 눈으로 골랐더니 위·아래 경계가 글줄 한가운데에
떨어졌다. 그러면 (1) 전체 캡처 위에 그린 초록 사각형의 테두리가 글자를 관통하고
(2) 확대 상자 안에서도 글줄이 가로로 반 잘린다. 좌표를 손으로 옮겨 고치면
다음 캡처에서 또 어긋나므로, 이미지에서 직접 빈 줄을 찾아 거기에 스냅한다.

어떻게
------
· 잉크 = 밝기 150 미만 픽셀. 글자는 어둡고 카드 테두리(~200)는 잉크가 아니다.
· 빈 줄 = 대상 x구간 안에 잉크가 하나도 없는 행. 연속된 빈 줄을 묶어 '틈'으로 본다.
· 위 경계는 가장 가까운 틈의 한가운데로, 아래 경계도 마찬가지로 옮긴다.
· 상자 비율(660×161)이 고정이라 높이가 정해지면 배율과 폭이 따라 정해진다.
  남은 자유도는 좌우 위치뿐이라, 오른쪽 끝을 '글자 없는 열'에 맞춰 낱자가
  가운데서 잘리지 않게 한다.
· 전체 캡처의 초록 사각형(.mk)은 같은 숫자에서 다시 계산한다 — 두 개가 어긋나면
  '여기를 확대했다'는 말이 거짓이 된다.
"""
import io, re, sys
import numpy as np
from PIL import Image

DIR = "C:/Users/이혁주/Desktop/zeb-chatbot/presentation_design/plan_deck"
SRC_W, SRC_H = 3000, 1900
BOX_W, BOX_H = 660, 161          # .zoom 한 칸
VIEW_W = 466                     # .view 폭 (.shot = 1152 - 26 - 660)
K = VIEW_W / SRC_W               # 전체 캡처가 화면에서 줄어드는 비율
INK = 150                        # 이보다 어두우면 글자로 본다
SEARCH = 70                      # 경계를 옮겨도 되는 최대 거리(원본 px)

_cache = {}
def gray(name):
    if name not in _cache:
        _cache[name] = np.asarray(Image.open(f"{DIR}/img/{name}").convert("L"), dtype=np.uint8)
    return _cache[name]


def runs(mask):
    """True가 연속된 구간 [(시작, 끝), ...]"""
    out, s = [], None
    for i, v in enumerate(mask):
        if v and s is None: s = i
        elif not v and s is not None: out.append((s, i)); s = None
    if s is not None: out.append((s, len(mask)))
    return out


def snap(target, gaps, lo, hi):
    """target에서 SEARCH 안에 있는 틈 중 가장 가까운 것의 한가운데."""
    best, bd = target, SEARCH + 1
    for a, b in gaps:
        if b - a < 3: continue           # 1~2px짜리는 틈이 아니라 글자 사이 여백
        c = (a + b) / 2
        if not (lo <= c <= hi): continue
        d = abs(c - target)
        if d < bd: best, bd = c, d
    return round(best)


def fix(name, x0, y0, w, h):
    g = gray(name)
    xs, xe = int(max(0, x0)), int(min(SRC_W, x0 + w))

    # ── 위·아래를 빈 줄에 맞춘다 ──────────────────────────────
    ink_rows = (g[:, xs:xe] < INK).any(axis=1)
    row_gaps = runs(~ink_rows)
    ny0 = snap(y0,     row_gaps, 0, SRC_H)
    ny1 = snap(y0 + h, row_gaps, ny0 + 60, SRC_H)
    nh = ny1 - ny0
    nw = nh * BOX_W / BOX_H                      # 상자 비율이 폭을 정한다

    # ── 가로는 건드리지 않는다 ────────────────────────────────
    # 오른쪽 끝을 빈 열에 맞춰 봤더니 폭이 고정이라 왼쪽 끝이 딸려 갔다.
    # s10#1은 왼쪽이 통째로 비었고 s12#1은 '필수 항목' 카드가 잘려 나갔다.
    # 왼쪽 시작점은 화면 본문이 시작하는 자리라 원래 값이 맞다. 그대로 둔다.
    # (오른쪽에서 낱자가 잘리는 건 .zoom::after 흰색 그러데이션이 받는다.)
    nx0 = max(0, min(x0, SRC_W - nw))

    s = BOX_W / nw                                # 확대 배율
    return {
        "zoom": (round(SRC_W * s), round(-nx0 * s), round(-ny0 * s)),   # width, left, top
        "mk":   (nx0 * K, ny0 * K, nw * K, nh * K),
        "src":  (round(nx0), ny0, round(nw), nh),
        "was":  (round(x0), round(y0), round(w), round(h)),
    }


# 지금 값 (index.html에서 그대로 옮겨 적은 것)
JOBS = [
    ("s09", 1, "bim_tabs.png",   945, -236,  -62),
    ("s09", 2, "bim_tabs.png",  1800, -444, -305),
    ("s10", 1, "qa2_open.png",  1800, -450, -144),
    ("s10", 2, "qa2_open.png",  1800, -468, -258),
    ("s11", 1, "roi2_strt.png",  961, -250, -178),
    ("s11", 2, "roi2_strt.png", 1800, -468, -840),
    ("s12", 1, "intake_top.png", 934, -232, -448),
    ("s12", 2, "intake_ask.png",1800, -462, -156),
]

if __name__ == "__main__":
    html = io.open(f"{DIR}/index.html", encoding="utf8").read()
    for sid, n, name, iw, left, top in JOBS:
        s = iw / SRC_W
        r = fix(name, -left / s, -top / s, BOX_W / s, BOX_H / s)
        zw, zl, zt = r["zoom"]
        print(f'{sid}#{n} {name:<16} 원본영역 {r["was"]} → {r["src"]}')
        print(f'          zoom  width:{zw}px; left:{zl}px; top:{zt}px')
        print(f'          mk    left:{r["mk"][0]:.1f}px; top:{r["mk"][1]:.1f}px; '
              f'width:{r["mk"][2]:.1f}px; height:{r["mk"][3]:.1f}px')
