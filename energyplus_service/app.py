# -*- coding: utf-8 -*-
"""
EnergyPlus 실행 HTTP 서비스.

Streamlit 앱이 IDF를 POST하면 EnergyPlus를 돌려 결과를 돌려준다.
Streamlit Community Cloud 무료 티어에서 E+를 못 돌리는 이유는 Dockerfile 주석 참고.

법적 의미
---------
EnergyPlus는 **그린리모델링 창조센터 지정 시뮬레이션 프로그램**이다 —
「2026년 민간건축물 그린리모델링 이자지원사업 공고」(국토부공고 제2026-876호) p.3 각주:
  "지정 에너지 시뮬레이션 : ECO2, ECO2-OD, GR-E, Energy Studio, EnergyPlus, IES-VE"
→ 개선 전·후를 각각 돌려 비교하면 **성능개선비율이 인정 대상**이 된다.
⚠️ 단 ZEB 인증은 다르다. ECO2(ISO 13790 + DIN V 18599 월별법)를 쓰며,
   EnergyPlus 결과로는 ZEB 인증 숫자가 나오지 않는다.

⚠️ 지정 프로그램 목록은 **고시가 아니라 센터 연례 공고**로 정해진다 → 매년 확인할 것.
"""

import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

app = FastAPI(title="ZEB-ROI EnergyPlus Service")

EPLUS_DIR = pathlib.Path(os.environ.get("EPLUS_DIR", "/usr/local/EnergyPlus-25-1-0"))
WEATHER_DIR = pathlib.Path("/app/weather")
RUN_ROOT = pathlib.Path("/tmp/runs")
TIMEOUT_S = 600          # 연간 해석. 소규모 건물은 보통 1분 내지만 여유를 둔다.
MAX_IDF_BYTES = 10 * 1024 * 1024


def _energyplus_bin() -> pathlib.Path:
    for c in (EPLUS_DIR / "energyplus", pathlib.Path("/usr/local/bin/energyplus")):
        if c.exists():
            return c
    found = shutil.which("energyplus")
    if found:
        return pathlib.Path(found)
    raise RuntimeError("EnergyPlus 바이너리를 못 찾음")


@app.get("/health")
def health():
    """배포 확인용. E+가 실제로 실행 가능한지까지 본다 — 존재만 보면 안 된다."""
    try:
        exe = _energyplus_bin()
        out = subprocess.run([str(exe), "--version"], capture_output=True,
                             text=True, timeout=30)
        return {
            "ok": True,
            "energyplus": (out.stdout or out.stderr).strip()[:120],
            "weather_files": sorted(p.name for p in WEATHER_DIR.glob("*.epw")),
        }
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)


def _parse_err(run_dir: pathlib.Path) -> dict:
    """
    eplusout.err를 읽어 **왜 실패/성공했는지** 돌려준다.

    이게 없으면 사용자는 "실패했습니다"만 보고 끝난다. E+의 실패는 대부분
    err 파일 몇 줄로 원인이 특정된다 — 그걸 그대로 넘긴다.
    """
    err = run_dir / "eplusout.err"
    if not err.exists():
        return {"fatal": [], "severe": [], "warning_count": 0, "raw_tail": ""}
    text = err.read_text(encoding="utf-8", errors="replace")
    return {
        "fatal": re.findall(r"\*\* Fatal  \*\* (.+)", text)[:10],
        "severe": re.findall(r"\*\* Severe  \*\* (.+)", text)[:20],
        "warning_count": len(re.findall(r"\*\* Warning \*\*", text)),
        "raw_tail": text[-3000:],
    }


def _read_meters(run_dir: pathlib.Path) -> dict:
    """eplusout.csv(Output:Meter)에서 월별 값을 뽑는다. 없으면 빈 dict."""
    csv = run_dir / "eplusout.csv"
    if not csv.exists():
        return {}
    lines = csv.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 2:
        return {}
    header = [h.strip() for h in lines[0].split(",")]
    rows = [ln.split(",") for ln in lines[1:] if ln.strip()]
    out = {}
    for i, h in enumerate(header[1:], start=1):
        vals = []
        for r in rows:
            if i < len(r):
                try:
                    vals.append(float(r[i]))
                except ValueError:
                    pass
        if vals:
            out[h] = {"monthly": vals, "annual_J": sum(vals),
                      "annual_kWh": sum(vals) / 3_600_000.0}
    return out


@app.post("/run")
async def run(
    idf: UploadFile = File(..., description="EnergyPlus IDF"),
    epw: UploadFile | None = File(None, description="기상파일(.epw). 없으면 weather 기본값"),
    weather_name: str = Form("", description="서버 내장 .epw 파일명"),
):
    raw = await idf.read()
    if not raw:
        raise HTTPException(400, "IDF가 비어 있습니다")
    if len(raw) > MAX_IDF_BYTES:
        raise HTTPException(413, f"IDF가 너무 큽니다 ({len(raw)/1e6:.1f}MB > 10MB)")

    run_dir = RUN_ROOT / uuid.uuid4().hex[:12]
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        idf_path = run_dir / "in.idf"
        idf_path.write_bytes(raw)

        # 기상파일 결정 — 업로드 > 지정 이름 > 내장 첫 파일
        if epw is not None:
            epw_path = run_dir / "in.epw"
            epw_path.write_bytes(await epw.read())
        else:
            cands = sorted(WEATHER_DIR.glob("*.epw"))
            if weather_name:
                cands = [p for p in cands if p.name == weather_name] or cands
            if not cands:
                raise HTTPException(
                    400, "기상파일이 없습니다 — .epw를 함께 올리거나 서버에 넣으세요"
                )
            epw_path = cands[0]

        proc = subprocess.run(
            [str(_energyplus_bin()), "-w", str(epw_path), "-d", str(run_dir),
             "-r", str(idf_path)],
            capture_output=True, text=True, timeout=TIMEOUT_S, cwd=str(run_dir),
        )
        errs = _parse_err(run_dir)
        ok = proc.returncode == 0 and not errs["fatal"]
        return {
            "ok": ok,
            "returncode": proc.returncode,
            "weather": pathlib.Path(epw_path).name,
            "errors": errs,
            "meters": _read_meters(run_dir) if ok else {},
            "stdout_tail": (proc.stdout or "")[-1500:],
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"EnergyPlus가 {TIMEOUT_S}초 안에 안 끝났습니다")
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
