"""
scripts/test_eplus.py — EnergyPlus 서비스 클라이언트 검증
=========================================================
E+ 자체는 여기서 못 돌린다(Docker·E+ 로컬에 없음). 대신 **서비스가 없을 때 앱이
멀쩡한가**를 지킨다 — 지금이 정확히 그 상태이므로 이게 실전 조건이다.

🔴 이 모듈이 예외를 던지면 BIM 진단 화면 전체가 죽는다. 서비스 미설정/다운/타임아웃은
   전부 **정상 상태**로 취급하고 IDF 다운로드 경로로 물러서야 한다.
"""

import io
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import os  # noqa: E402

from core import eplus_client as EC  # noqa: E402

fails = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)


print("=" * 70)
print("EnergyPlus 서비스 클라이언트")
print("=" * 70)

print("\n① 서비스가 없어도 앱이 안 죽는다 (현재 실제 상태)")
os.environ.pop("EPLUS_SERVICE_URL", None)
check("service_url() → None", EC.service_url() is None)

h = EC.health()
check("health()가 예외 없이 dict 반환", isinstance(h, dict))
check("configured=False로 미설정을 알린다", h["configured"] is False and h["ok"] is False)
check("health()에 필수 키가 다 있다",
      {"configured", "ok", "error", "energyplus", "weather_files"} <= set(h))

r = EC.run_idf("Version, 26.1;")
check("run_idf()가 예외 없이 실패를 반환", isinstance(r, dict) and r["ok"] is False)
check("실패 사유에 대안을 안내한다 (IDF 로컬 실행)",
      "IDF" in r["error"] and "로컬" in r["error"], r["error"][:60])

print("\n② 서비스가 죽어 있어도 안 죽는다")
os.environ["EPLUS_SERVICE_URL"] = "http://127.0.0.1:9/nonexistent"   # 포트 9 = discard
h2 = EC.health()
check("죽은 서비스 → ok=False, 예외 없음", h2["configured"] is True and h2["ok"] is False)
check("에러 사유를 담아 돌려준다", bool(h2["error"]), str(h2["error"])[:50])
r2 = EC.run_idf("Version, 26.1;")
check("run_idf()도 예외 없이 실패 반환", isinstance(r2, dict) and r2["ok"] is False)
os.environ.pop("EPLUS_SERVICE_URL", None)

print("\n③ 성능개선비율 — 분모가 '개선 전'인가")
# 🔑 ZEB 절감률(분모=base)과 다르다. 섞으면 조용히 틀린다 → 📖 용어사전
before = {"meters": {"Electricity:Facility": {"annual_kWh": 100.0}}}
after = {"meters": {"Electricity:Facility": {"annual_kWh": 59.0}}}
imp = EC.improvement_ratio(before, after)
check("(100−59)/100 = 41.0%", imp and abs(imp["성능개선비율_pct"] - 41.0) < 0.01,
      f'{imp["성능개선비율_pct"] if imp else None}%')
check("분모가 '개선 전'임을 명시", imp and "개선 전" in imp["분모"])
check("20% 기준 충족 판정", imp and imp["충족"] is True)

low = EC.improvement_ratio(before, {"meters": {"E": {"annual_kWh": 85.0}}})
check("15%면 미충족 (기준 20%)", low and low["충족"] is False, f'{low["성능개선비율_pct"]}%')

check("여러 미터를 합산한다",
      EC.improvement_ratio(
          {"meters": {"A": {"annual_kWh": 60.0}, "B": {"annual_kWh": 40.0}}},
          {"meters": {"A": {"annual_kWh": 30.0}, "B": {"annual_kWh": 30.0}}},
      )["성능개선비율_pct"] == 40.0)

print("\n④ 빈 결과에 0을 지어내지 않는다")
check("미터 없으면 None (0%가 아니라)", EC.improvement_ratio({}, {}) is None)
check("개선전 0이면 None (0으로 나누기 방지)",
      EC.improvement_ratio({"meters": {"A": {"annual_kWh": 0.0}}},
                           {"meters": {"A": {"annual_kWh": 0.0}}}) is None)

print("\n⑤ 서비스 코드가 성립하는가 (Docker 없이 검증 가능한 범위)")
import ast  # noqa: E402

svc = PROJECT_ROOT / "energyplus_service"
check("Dockerfile 존재", (svc / "Dockerfile").exists())
_df = (svc / "Dockerfile").read_text(encoding="utf-8")
# 태그를 latest로 두면 E+ 버전이 조용히 바뀌어 IDF 스키마와 어긋난다
check("E+ 이미지 태그가 고정돼 있다 (latest 금지)",
      "FROM nrel/energyplus:" in _df and "FROM nrel/energyplus:latest" not in _df)
check("HF Spaces 포트 7860", "7860" in _df)
_app = (svc / "app.py").read_text(encoding="utf-8")
ast.parse(_app)
check("app.py 문법 정상 + /health·/run 존재",
      '@app.get("/health")' in _app and '@app.post("/run")' in _app)
# E+ 실패는 대부분 eplusout.err 몇 줄로 원인이 잡힌다 — 감추면 안 된다
check("실패 시 eplusout.err를 그대로 돌려준다",
      "eplusout.err" in _app and "fatal" in _app and "severe" in _app)

print()
if fails:
    print(f"❌ 실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("✅ 전부 통과 — 서비스가 없어도 앱은 멀쩡하다")
