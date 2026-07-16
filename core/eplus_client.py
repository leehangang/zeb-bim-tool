# -*- coding: utf-8 -*-
"""
EnergyPlus 실행 서비스 클라이언트.

E+는 Streamlit Community Cloud 무료 티어에서 못 돈다(240MB가 아니라 **CPU 0.078코어 하한**과
apt 부재가 원인 — energyplus_service/README.md 참고). 그래서 별도 Docker 서비스에 던진다.

설계 원칙 — **서비스가 없어도 앱은 멀쩡해야 한다.**
  URL 미설정/다운/타임아웃은 정상 상태로 취급하고, 화면은 IDF 다운로드 경로로 물러선다.
  이 모듈은 예외를 밖으로 던지지 않는다.
"""

from typing import Optional

_TIMEOUT_HEALTH = 8
_TIMEOUT_RUN = 620          # 서비스측 600초 + 여유


def service_url() -> Optional[str]:
    """
    설정된 서비스 URL. 없으면 None.

    st.secrets → 환경변수 순. secrets가 없으면 Streamlit이 예외를 던지므로 삼킨다.
    """
    import os

    try:
        import streamlit as st

        url = st.secrets.get("EPLUS_SERVICE_URL", "")
        if url:
            return str(url).rstrip("/")
    except Exception:
        pass
    url = os.environ.get("EPLUS_SERVICE_URL", "")
    return url.rstrip("/") or None


def health() -> dict:
    """
    서비스 상태. 항상 dict를 돌려준다 (예외 없음).

    Returns:
        {"configured": bool, "ok": bool, "error": str|None, "energyplus": str, "weather_files": []}
    """
    url = service_url()
    if not url:
        return {"configured": False, "ok": False,
                "error": "EPLUS_SERVICE_URL 미설정", "energyplus": "", "weather_files": []}
    try:
        import requests

        r = requests.get(f"{url}/health", timeout=_TIMEOUT_HEALTH)
        d = r.json()
        return {
            "configured": True,
            "ok": bool(d.get("ok")),
            "error": d.get("error"),
            "energyplus": d.get("energyplus", ""),
            "weather_files": d.get("weather_files", []),
        }
    except Exception as e:
        return {"configured": True, "ok": False,
                "error": f"{type(e).__name__}: {e}", "energyplus": "", "weather_files": []}


def run_idf(idf_text: str, epw_bytes: Optional[bytes] = None,
            weather_name: str = "") -> dict:
    """
    IDF를 서비스에 보내 EnergyPlus로 실행.

    Returns:
        성공: {"ok": True, "meters": {...}, "errors": {...}, "weather": str}
        실패: {"ok": False, "error": str, ...}  — **예외를 던지지 않는다**

    실패해도 errors.fatal/severe를 그대로 담아 돌려준다. E+ 실패는 대부분
    eplusout.err 몇 줄로 원인이 특정되는데, 그걸 감추면 사용자는 "실패"만 보고 끝난다.
    """
    url = service_url()
    if not url:
        return {"ok": False, "error": "EPLUS_SERVICE_URL 미설정 — IDF를 내려받아 로컬 EnergyPlus로 실행하세요"}
    try:
        import requests

        files = {"idf": ("model.idf", idf_text.encode("utf-8"), "text/plain")}
        if epw_bytes:
            files["epw"] = ("weather.epw", epw_bytes, "text/plain")
        r = requests.post(f"{url}/run", files=files,
                          data={"weather_name": weather_name}, timeout=_TIMEOUT_RUN)
        if r.status_code != 200:
            return {"ok": False,
                    "error": f"HTTP {r.status_code}: {r.text[:300]}"}
        return r.json()
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def improvement_ratio(before: dict, after: dict) -> Optional[dict]:
    """
    개선 전·후 E+ 결과 → GR 성능개선비율.

    🔑 분모는 **개선 전**이다 (2026 민간 GR 공고 p.3: "그린리모델링 공사 이전 대비").
       ZEB 절감률(분모 = 용도별 기준요구량 base)과 **다르다** — 섞으면 조용히 틀린다.

    EnergyPlus는 GR 센터 **지정 프로그램**이므로(공고 p.3 각주) 이 값은 인정 대상이다.
    ⚠️ 단 ZEB 인증은 ECO2라 이 결과로는 안 된다.
    """
    def _total_kwh(res: dict) -> Optional[float]:
        m = (res or {}).get("meters") or {}
        vals = [v.get("annual_kWh") for v in m.values() if isinstance(v, dict)]
        vals = [v for v in vals if isinstance(v, (int, float))]
        return sum(vals) if vals else None

    b, a = _total_kwh(before), _total_kwh(after)
    if not b or a is None or b <= 0:
        return None
    ratio = (b - a) / b
    return {
        "개선전_kWh": b,
        "개선후_kWh": a,
        "성능개선비율_pct": round(ratio * 100, 1),
        "분모": "개선 전 (2026 민간 GR 공고 p.3)",
        "기준_pct": 20.0,
        "충족": ratio >= 0.20,
        "note": "EnergyPlus = GR 센터 지정 프로그램 (공고 p.3 각주). ZEB 인증은 ECO2로 별개.",
    }
