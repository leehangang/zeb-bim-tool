# 대상 건물 매스를 등각투상(isometric)으로 계산해 SVG 라인드로잉을 뽑는다.
# path의 d를 눈대중으로 찍지 않는다 — 3D 상자를 정의하고 투영식으로 좌표를 만든다.
#
# 투영: sx = (x-y)*cos30, sy = (x+y)*sin30 - z
#   → x 커지면 오른쪽-아래, y 커지면 왼쪽-아래, z 커지면 위.
#   → 보이는 면은 윗면(z=max), 오른쪽면(x=max), 앞면(y=max) 셋.
# 은선 제거는 계산하지 않는다. 면을 배경색으로 채우고 먼 상자부터 그려
# 가까운 상자가 덮게 하는 화가 알고리즘으로 처리한다.
#
# 사용: python axo.py         → axo.svg (영상용)
#       python axo.py debug   → axo_dbg.svg (볼륨별 색, 기하 검증용)

import math
import sys

DEBUG = "debug" in sys.argv
C30, S30 = math.cos(math.radians(30)), math.sin(math.radians(30))


def P(x, y, z):
    return ((x - y) * C30, (x + y) * S30 - z)


# 사진(2층·평지붕·수평 띠창·돌출 캐노피)과 Revit 매스(단차진 볼륨)에서 잡은 비례.
# 단위 m. 앞면은 y가 큰 쪽이다.
BOXES = [
    # name,   x0,  x1,   y0,  y1,   z0,    z1
    # 뒤채는 뺐다. 본채 오른쪽으로 삐져나와 끝동과 겹치면서
    # 어느 볼륨에도 속하지 않는 노치를 만들었고, 매스에 보태는 것도 없었다.
    ("main",   0,  24,    9,  22,    0,   7.6),   # 본채
    # 현관은 떠 있는 얇은 슬래브 대신 바닥까지 내려오는 포치 볼륨으로.
    # 두께 0.4m짜리 판은 등각투상에서 긁힌 자국처럼 보인다.
    ("porch",  2,  13,   22, 25.4,   0,   3.6),   # 현관 포치
    ("core",   8,  13,   13,  18,  7.6,  10.0),   # 옥탑 계단실
    ("tall",  24,  34,    9,  22,    0,   9.6),   # 높은 끝동
]

# 띠창: (볼륨, 어느면, 층별 z범위)
BANDS = [
    ("main", "front", [(1.3, 2.9), (4.9, 6.5)]),
    ("tall", "front", [(1.3, 2.9), (4.9, 6.5)]),
    ("tall", "right", [(1.3, 2.9), (4.9, 6.5)]),

    ("porch", "front", [(1.4, 2.8)]),
]

FACES, WINS, EDGES = [], [], []
BX = {b[0]: b for b in BOXES}


def visible_faces(x0, x1, y0, y1, z0, z1):
    return [
        ("top",   [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
        ("front", [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)]),
        ("right", [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),
    ]


for name, x0, x1, y0, y1, z0, z1 in BOXES:
    key = x0 + y0 + z0          # 최소 코너 합 = 시선 깊이. 작을수록 멀다.
    for _side, f in visible_faces(x0, x1, y0, y1, z0, z1):
        FACES.append((key, [P(*p) for p in f], name))

for name, side, zs in BANDS:
    _n, x0, x1, y0, y1, z0, z1 = BX[name]
    key = BX[name][1] + BX[name][3] + BX[name][5] + 0.4   # 그 볼륨 바로 뒤에
    for zb, zt in zs:
        if zt > z1 - 0.5:
            continue
        if side == "front":   # y = y1 평면, x 방향으로 뻗는다
            a, b = x0 + 1.2, x1 - 1.2
            quad = [(a, y1, zb), (b, y1, zb), (b, y1, zt), (a, y1, zt)]
        else:                 # x = x1 평면, y 방향으로 뻗는다
            a, b = y0 + 1.2, y1 - 1.2
            quad = [(x1, a, zb), (x1, b, zb), (x1, b, zt), (x1, a, zt)]
        WINS.append((key, [P(*p) for p in quad], name))

# 슬래브 구분선 — 앞면 2층 바닥 높이에 한 줄.
for name in ("main", "tall"):
    _n, x0, x1, y0, y1, z0, z1 = BX[name]
    key = x0 + y0 + z0 + 0.4
    EDGES.append((key, [P(x0, y1, 3.9), P(x1, y1, 3.9)]))

# 면·창·선을 한 목록에 합쳐 깊이순으로 그린다.
# 종류별로 나눠 몰아 그리면, 가까운 볼륨의 면이 먼 볼륨의 창·선을 못 덮어
# 슬래브선이 앞 볼륨을 관통해 지나간다.
ITEMS = ([(k, "fc", f) for k, f, _n in FACES]
         + [(k, "win", f) for k, f, _n in WINS]
         + [(k, "thin", l) for k, l in EDGES])
ITEMS.sort(key=lambda it: it[0])

# ── 뷰박스 ──────────────────────────────────────
groups = ([f for _k, f, _n in FACES] + [f for _k, f, _n in WINS]
          + [l for _k, l in EDGES])
pts = [p for g in groups for p in g]
xs, ys = [p[0] for p in pts], [p[1] for p in pts]
S, PAD = 13.2, 16          # 영상 오프닝 오른쪽 여백(약 580px)에 맞춘 축척
W = (max(xs) - min(xs)) * S + PAD * 2
H = (max(ys) - min(ys)) * S + PAD * 2
ox, oy = -min(xs) * S + PAD, -min(ys) * S + PAD


def d(points, close=True):
    seg = " ".join(f"{'M' if i == 0 else 'L'}{x*S+ox:.1f},{y*S+oy:.1f}"
                   for i, (x, y) in enumerate(points))
    return seg + ("Z" if close else "")


COL = {"wing": "#e74c3c", "main": "#3498db", "porch": "#f1c40f",
       "core": "#9b59b6", "tall": "#2ecc71"}

DEPTH = {k: nm for k, _f, nm in FACES}
out = [f'<svg id="plan" width="{W:.0f}" height="{H:.0f}" '
       f'viewBox="0 0 {W:.0f} {H:.0f}">']
for k, kind, g in ITEMS:
    if DEBUG and kind == "fc":
        out.append(f'  <path d="{d(g)}" fill="{COL[DEPTH[k]]}" fill-opacity=".75" '
                   f'stroke="#000" stroke-width="2"/>')
    else:
        out.append(f'  <path class="{kind}" d="{d(g, close=kind != "thin")}"/>')
out.append("</svg>")

name = "axo_dbg.svg" if DEBUG else "axo.svg"
open(name, "w", encoding="utf-8").write("\n".join(out))
print(f"{name}  {W:.0f}x{H:.0f}  faces={len(FACES)} wins={len(WINS)} edges={len(EDGES)}")
