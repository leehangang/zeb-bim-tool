# -*- coding: utf-8 -*-
"""숫자를 화면에 적는 법 — 한 곳에서만 정한다.

왜 있나: NPV를 홈은 `{'+' if npv>=0 else '−'}{abs(npv)/1e8:.2f}억`으로 제대로 찍었는데
BIM 민감도 탭은 템플릿에 `+`를 박아뒀다. 그래서 기본 데모에서 **`NPV: +-0.48억`**이
떴다 — 손실 앞에 플러스가 붙은 것이다. 같은 값을 두 곳에서 각자 포맷하면 갈라진다.

부호를 왜 직접 붙이나: 음수는 `-0.48`로 알아서 나오지만 양수는 아무 표시가 없다.
NPV는 **부호가 결론**이다 — "0.48억"만 보면 이득인지 손실인지 알 수 없다.
그래서 양수엔 `+`를, 음수엔 유니코드 빼기(−, U+2212)를 붙인다. ASCII 하이픈(-)은
글꼴에서 너무 짧아 투사하면 안 보인다.
"""

from typing import Optional

EOK = 100_000_000  # 1억


def signed_eok(won: Optional[float], digits: int = 2) -> str:
    """원 → 부호가 붙은 '억' 문자열. None이면 '—'.

    >>> signed_eok(87_000_000)
    '+0.87억'
    >>> signed_eok(-48_300_000)
    '−0.48억'
    >>> signed_eok(0)
    '+0.00억'
    >>> signed_eok(None)
    '—'
    """
    if won is None:
        return "—"
    sign = "+" if won >= 0 else "−"
    return f"{sign}{abs(won) / EOK:.{digits}f}억"


def signed_eok_from_eok(eok: Optional[float], digits: int = 2) -> str:
    """이미 '억' 단위인 값용. 엔진이 두 단위를 섞어 내보내서 둘 다 필요하다."""
    if eok is None:
        return "—"
    sign = "+" if eok >= 0 else "−"
    return f"{sign}{abs(eok):.{digits}f}억"
