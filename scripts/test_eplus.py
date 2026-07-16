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

# service_url()은 st.secrets → 환경변수 순으로 읽는다. 개발자 PC의 .streamlit/secrets.toml이
# 있으면 "미설정" 테스트가 조용히 무의미해진다 — 실제로 secrets.toml을 만들자마자 깨졌다.
# 그래서 streamlit을 스텁으로 갈아끼워 secrets를 테스트가 직접 통제한다.
import types  # noqa: E402


class _FakeSecrets(dict):
    def get(self, k, default=None):   # st.secrets.get과 같은 모양
        return dict.get(self, k, default)


_fake_st = types.ModuleType("streamlit")
_fake_st.secrets = _FakeSecrets()
sys.modules["streamlit"] = _fake_st


def _set_secret(url: str) -> None:
    _fake_st.secrets.clear()
    if url:
        _fake_st.secrets["EPLUS_SERVICE_URL"] = url


print("\n① 서비스가 없어도 앱이 안 죽는다")
os.environ.pop("EPLUS_SERVICE_URL", None)
_set_secret("")
check("service_url() → None", EC.service_url() is None)

h = EC.health()
check("health()가 예외 없이 dict 반환", isinstance(h, dict))
check("configured=False로 미설정을 알린다", h["configured"] is False and h["ok"] is False)
check("health()에 필수 키가 다 있다",
      {"configured", "ok", "error", "energyplus", "weather_files"} <= set(h))

r = EC.run_idf("Version, 25.1;")
check("run_idf()가 예외 없이 실패를 반환", isinstance(r, dict) and r["ok"] is False)
check("실패 사유에 대안을 안내한다 (IDF 로컬 실행)",
      "IDF" in r["error"] and "로컬" in r["error"], r["error"][:60])

print("\n①-b 설정 경로 — secrets가 환경변수보다 우선")
_set_secret("https://from-secrets.example/")
check("st.secrets에서 읽는다 (이 경로는 그동안 아무도 안 지켰다)",
      EC.service_url() == "https://from-secrets.example")
os.environ["EPLUS_SERVICE_URL"] = "https://from-env.example"
check("secrets가 있으면 secrets가 이긴다", EC.service_url() == "https://from-secrets.example")
_set_secret("")
check("secrets가 비면 환경변수로 물러선다", EC.service_url() == "https://from-env.example")
check("끝 슬래시는 떼어낸다 (URL 이어붙일 때 //가 되면 404)",
      not (EC.service_url() or "").endswith("/"))
os.environ.pop("EPLUS_SERVICE_URL", None)

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
import re  # noqa: E402

from core.idf_writer import EP_VERSION, write_idf  # noqa: E402

svc = PROJECT_ROOT / "energyplus_service"
check("Dockerfile 존재", (svc / "Dockerfile").exists())
_df = (svc / "Dockerfile").read_text(encoding="utf-8")
_app = (svc / "app.py").read_text(encoding="utf-8")
# 태그를 latest로 두면 E+ 버전이 조용히 바뀌어 IDF 스키마와 어긋난다
check("E+ 이미지 태그가 고정돼 있다 (latest 금지)",
      "FROM nrel/energyplus:" in _df and "FROM nrel/energyplus:latest" not in _df)
check("HF Spaces 포트 7860", "7860" in _df)

# Modal이 실제 배포 경로다 (HF Docker는 2026-07-16 확인 결과 Paid로 잠김).
# Dockerfile만 검사하면 정작 쓰는 쪽이 안 지켜진다.
_mod = (svc / "modal_app.py").read_text(encoding="utf-8")
ast.parse(_mod)
check("modal_app.py도 E+ 태그 고정 (latest 금지)",
      'from_registry("nrel/energyplus:' in _mod
      and "nrel/energyplus:latest" not in _mod)
# 두 경로가 같은 이미지를 써야 한다 — 어긋나면 로컬에서 되던 게 배포에서 깨진다
_tag_df = _df.split("FROM nrel/energyplus:", 1)[1].split()[0].strip()
_tag_md = _mod.split('from_registry("nrel/energyplus:', 1)[1].split('"', 1)[0].strip()
check(f"Dockerfile·modal_app 이미지 태그 일치 ({_tag_df})", _tag_df == _tag_md)
check("modal_app이 app.py를 공용한다 (로직 복제 금지)",
      "from app import app" in _mod)

# 우리 IDF의 Version과 서비스가 도는 E+ 버전이 어긋나면 E+가 경고를 내고,
# 스키마가 바뀐 버전이면 조용히 틀린 결과가 나온다. 실제로 26.1 vs 25.1로 어긋나 있었다.
check(f"IDF Version이 이미지 태그와 일치 (IDF {EP_VERSION} · 이미지 {_tag_df})",
      _tag_df.startswith(EP_VERSION + "."))
_idf_probe = write_idf({"walls": [], "roofs": [], "floors": [],
                        "windows": [], "doors": []})["idf"]
check(f"생성된 IDF에 Version, {EP_VERSION}; 이 박힌다",
      f"Version, {EP_VERSION};" in _idf_probe)

# E+ 실제 출력은 '**  Fatal  **'로 Fatal 앞 공백이 둘이다(Severe·Warning은 하나).
# 공백 수에 기댄 정규식이 fatal을 통째로 놓쳐, 프로그램이 죽었는데 화면엔 fatal 0건으로
# 보였다. app.py는 fastapi에 의존하므로 import하지 않고 정규식만 뽑아 실물로 검증한다.
_ERR_FIXTURE = (
    '   ** Severe  ** <root>[Zone][sp-1] - bad enum.\n'
    '   ** Warning ** Version: in IDF="26.1" not the same as expected="25.1"\n'
    '   **  Fatal  ** Errors occurred on processing input file.\n'
)
check("app.py가 공백 수에 기대지 않는 정규식을 쓴다",
      r'r"\*\*\s*"' in _app or r"\*\*\s*Warning\s*\*\*" in _app)
check("'**  Fatal  **'(공백 2)를 놓치지 않는다",
      len(re.findall(r"\*\*\s*Fatal\s*\*\*\s*(.+)", _ERR_FIXTURE)) == 1)
check("예전 정규식이었다면 놓쳤다는 것도 확인 (테스트가 진짜 재현하는가)",
      len(re.findall(r"\*\* Fatal  \*\* (.+)", _ERR_FIXTURE)) == 0)
check("severe·warning도 같이 잡힌다",
      len(re.findall(r"\*\*\s*Severe\s*\*\*\s*(.+)", _ERR_FIXTURE)) == 1
      and len(re.findall(r"\*\*\s*Warning\s*\*\*", _ERR_FIXTURE)) == 1)

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
