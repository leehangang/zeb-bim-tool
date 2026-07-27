# 프레임 검수용 컨택트 시트 — PNG 여러 장을 라벨 붙여 한 장으로 합친다.
#
# 왜: 검수 프레임을 한 장씩 읽으면 이미지당 1~2천 토큰이 나간다.
#     일곱 시점 확인 = 대화 컨텍스트 1만 토큰. 영상 한 판 고치는 데 이걸 대여섯 바퀴 돈다.
#     격자 한 장으로 합치면 같은 정보가 1/5 값에 들어온다.
#
# 사용: python qa_sheet.py out.png a.png b.png c.png ...
#       python qa_sheet.py out.png "frames/*.png"      (glob도 받는다)
#       python qa_sheet.py out.png --cols 4 ...        (기본 3열)
#
# 라벨은 파일 이름 그대로 쓴다. 시점을 이름에 넣어 두면(vchk_2.0.png) 그대로 읽힌다.

import glob
import os
import sys

from PIL import Image, ImageDraw, ImageFont

SHEET_W = 1600          # 완성 시트 가로. 이보다 키워도 읽히는 정보가 늘지 않는다.
LABEL_H = 26
GAP = 8
BG = (24, 24, 24)
FG = (240, 240, 240)


def load_font():
    # 라벨에 한글 파일명이 섞일 수 있어 맑은 고딕을 먼저 찾는다.
    for p in ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/arial.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, 15)
    return ImageFont.load_default()


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit("사용: python qa_sheet.py out.png <png들...> [--cols N]")

    cols = 3
    if "--cols" in args:
        i = args.index("--cols")
        cols = int(args[i + 1])
        del args[i:i + 2]

    out = args[0]
    paths = []
    for a in args[1:]:
        # 셸이 glob을 안 풀어 주는 경우(PowerShell 등)를 대비해 직접 푼다.
        hits = sorted(glob.glob(a)) if any(c in a for c in "*?[") else [a]
        if not hits:
            sys.exit(f"매칭 없음: {a}")
        paths += hits

    if not paths:
        sys.exit("입력 이미지가 없다")

    imgs = [(os.path.basename(p), Image.open(p).convert("RGB")) for p in paths]

    rows = (len(imgs) + cols - 1) // cols
    cell_w = (SHEET_W - GAP * (cols + 1)) // cols
    # 셀 높이는 가장 세로로 긴 이미지에 맞춘다. 종횡비가 섞이면 남는 칸은 여백으로 둔다 —
    # 늘려 채우면 레이아웃 결함(겹침·잘림)이 왜곡돼서 검수 자체가 못 쓰게 된다.
    cell_h = max(int(im.height * cell_w / im.width) for _n, im in imgs)

    sheet_h = GAP + rows * (cell_h + LABEL_H + GAP)
    sheet = Image.new("RGB", (SHEET_W, sheet_h), BG)
    dr = ImageDraw.Draw(sheet)
    font = load_font()

    for i, (name, im) in enumerate(imgs):
        r, c = divmod(i, cols)
        x = GAP + c * (cell_w + GAP)
        y = GAP + r * (cell_h + LABEL_H + GAP)
        dr.text((x + 2, y + 4), name, font=font, fill=FG)
        h = int(im.height * cell_w / im.width)
        sheet.paste(im.resize((cell_w, h), Image.LANCZOS), (x, y + LABEL_H))

    sheet.save(out)
    print(f"{out}  {SHEET_W}x{sheet_h}  {len(imgs)}장 / {cols}열")


if __name__ == "__main__":
    main()
