# -*- coding: utf-8 -*-
"""
EnergyPlus 실행 서비스 — Modal 배포용 진입점.

왜 Modal인가
------------
Hugging Face Spaces가 1순위였으나 **2026-07-16 계정에서 확인 결과 Docker SDK가
"Paid"로 잠겨 있었다** (Static만 무료). 2026-07-09 포럼 이슈가 실제로 재현된 것이다.
HF 공식 문서는 여전히 "CPU Basic FREE"라 적혀 있어 문서와 실제가 어긋나 있다.
→ 같은 NREL 이미지를 Modal에 올린다. $30/월 컴퓨트 크레딧 무료, 유휴 시 과금 0.

Dockerfile과의 관계
-------------------
`Dockerfile`(HF용)과 이 파일은 **같은 베이스 이미지 · 같은 app.py**를 쓴다.
HF Docker가 무료로 풀리면 Dockerfile 경로로 돌아가면 된다. 둘 중 하나만 쓰면 된다.

⚠️ 이 스크립트는 아직 Modal에 배포된 적이 없다 — 로컬 문법 검사만 통과했다.
   첫 배포에서 깨질 수 있고, 그때는 `modal deploy` 출력이 원인을 알려준다.

배포
----
    pip install modal
    modal setup                                  # 브라우저 인증 (1회)
    modal deploy energyplus_service/modal_app.py
    → https://<사용자>--zeb-energyplus-web.modal.run

그 다음 Streamlit Secrets에:
    EPLUS_SERVICE_URL = "https://<사용자>--zeb-energyplus-web.modal.run"
"""

import pathlib

import modal

HERE = pathlib.Path(__file__).parent

# 태그를 latest로 두지 않는다 — E+는 버전마다 IDF 스키마가 바뀐다.
# 우리 idf_writer가 쓰는 Version과 어긋나면 조용히 실패한다.
image = (
    modal.Image.from_registry("nrel/energyplus:25.1.0", add_python="3.11")
    .env({"EPLUS_DIR": "/usr/local/EnergyPlus-25-1-0", "PYTHONUNBUFFERED": "1"})
    .pip_install("fastapi==0.115.6", "python-multipart==0.0.20")
    .add_local_file(HERE / "app.py", "/app/app.py")
    .add_local_dir(HERE / "weather", "/app/weather")
)

app = modal.App("zeb-energyplus")


@app.function(
    image=image,
    timeout=900,        # app.py의 E+ 타임아웃 600초 + 여유
    scaledown_window=300,
)
@modal.concurrent(max_inputs=4)
@modal.asgi_app()
def web():
    import sys

    sys.path.insert(0, "/app")
    from app import app as fastapi_app  # energyplus_service/app.py — HF와 공용

    return fastapi_app
