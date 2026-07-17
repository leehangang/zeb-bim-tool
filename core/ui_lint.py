# -*- coding: utf-8 -*-
"""
화면 코드의 정적 검사 — 눈으로 놓치는 것을 기계가 잡는다.

왜 별도 모듈인가: 테스트 안에 정규식을 인라인으로 쓰면 이스케이프가 꼬이고,
무엇보다 **검사 규칙 자체를 테스트할 수 없다.** 여기 두면 규칙도 시험 대상이 된다.
"""

import pathlib
import re
from typing import List

# st.info/success/warning/error는 icon= 인자로 왼쪽에 배지를 그린다.
# 본문까지 같은 이모지로 시작하면 화면에 아이콘이 **두 개** 나온다.
_ALERT = re.compile(r'st\.(?:info|success|warning|error)\(\s*\n?\s*(?:f?"""|f?")(.{0,40})')
_EMOJI = re.compile("^[\U0001F300-\U0001FAFF☀-➿⬀-⯿]")


def _call_text(src: str, start: int, limit: int = 1600) -> str:
    """괄호 균형을 세어 호출 하나의 전체 텍스트를 잘라낸다."""
    seg = src[start:start + limit]
    depth = 0
    for i, ch in enumerate(seg):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return seg[: i + 1]
    return seg


def find_double_icons(text: str, label: str = "?") -> List[str]:
    """icon= 인자와 본문 이모지가 겹치는 지점을 찾는다. → ["파일:줄", ...]"""
    out = []
    for m in _ALERT.finditer(text):
        call = _call_text(text, m.start())
        if "icon=" not in call:
            continue
        if _EMOJI.match(m.group(1).lstrip()):
            out.append(f"{label}:{text[:m.start()].count(chr(10)) + 1}")
    return out


def scan_ui(root: pathlib.Path) -> List[str]:
    """modes/*.py + streamlit_app.py 전수 검사."""
    hits = []
    targets = sorted((root / "modes").glob("*.py")) + [root / "streamlit_app.py"]
    for p in targets:
        if not p.exists():
            continue
        hits += find_double_icons(p.read_text(encoding="utf-8"), p.name)
    return hits
