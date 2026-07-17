# -*- coding: utf-8 -*-
"""
EnergyPlus 실행 서비스 — Modal 배포용 진입점.

왜 Modal인가
------------
Hugging Face Spaces가 1순위였으나 **2026-07-16 계정에서 확인 결과 Docker SDK가
"Paid"로 잠겨 있었다** (Static만 무료). 2026-07-09 포럼 이슈가 실제로 재현된 것이다.
HF 공식 문서는 여전히 "CPU Basic FREE"라 적혀 있어 문서와 실제가 어긋나 있다.
→ 같은 NREL 이미지를 Modal에 올린다. 유휴 시 과금 0 (요청 없으면 컨테이너 0으로 내려감).

⚠️ 비용 — "$30/월 무료, 카드 불필요"는 틀렸다 (2026-07-17 대시보드 확인).
   실제: "You have $1 of $30/mo in free credits. Add a payment method to unlock the rest."
   카드 미등록 실사용 한도는 $1이다. $1이 몇 회 해석인지는 미실측 — 빌드도 컴퓨트를 쓴다.
   Modal은 초 단위 종량제라 "무료 티어"라는 말이 성립하지 않는다.

Dockerfile과의 관계
-------------------
`Dockerfile`(HF용)과 이 파일은 **같은 베이스 이미지 · 같은 app.py**를 쓴다.
HF Docker가 무료로 풀리면 Dockerfile 경로로 돌아가면 된다. 둘 중 하나만 쓰면 된다.

배포 상태 (2026-07-17)
---------------------
배포됐고 실제 해석이 완주했다 → https://leehangang--zeb-energyplus-web.modal.run
`modal deploy` 34초, `/health` 200 (4.1초 — 콜드스타트 포함).
첫 배포에서 IDF 버그 4개가 드러났다 (enum 필드의 autocalculate 2곳, People의
Activity Level Schedule 누락, Version 불일치). 넣어보기 전엔 하나도 안 보였다.

미검증: 4층 이상·지하층, 큰 모델의 타임아웃, $1 크레딧이 몇 회인지.

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
