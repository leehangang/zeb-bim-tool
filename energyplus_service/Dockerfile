# EnergyPlus 실행 서비스 — Hugging Face Spaces (Docker SDK) 용
#
# 왜 별도 서비스인가
# ------------------
# Streamlit Community Cloud 무료 티어에서는 EnergyPlus를 못 돌린다:
#   · Debian apt 저장소에 energyplus 패키지 없음 → packages.txt 불가
#   · sudo 없음 → 런타임 apt-get 불가
#   · CPU 하한 0.078코어 → 설치를 뚫어도 연간 해석이 실용 속도가 안 남
#   · 12시간 무트래픽 슬립 → 깨어날 때마다 재설치
# 그런데 이 장벽들은 **Docker 경로에선 전부 무효**다. NREL 공식 이미지가 있고
# (nrel/energyplus, 압축 106.5MB) `FROM` 한 줄이면 끝이다.
#
# ❌ HF는 막혔다 (2026-07-16 계정에서 확인) — new-space 화면에서 Docker에 "Paid" 배지가
#    붙고 Static만 무료로 선택된다. 2026-07-09 포럼 이슈가 실제로 재현됐다.
#    공식 문서는 여전히 CPU Basic FREE라 적고 있어 문서와 실제가 어긋나 있다.
#    → 현재 배포 경로는 Modal이다: `modal_app.py` (같은 베이스 이미지·같은 app.py).
#    이 파일은 지운 게 아니라 남겨둔 것이다 — HF Docker가 무료로 풀리면 그대로 쓴다.
#
# 태그를 latest로 두지 않는 이유: E+는 버전마다 IDF 스키마가 바뀐다.
# 우리 idf_writer가 쓰는 Version과 여기 태그가 어긋나면 조용히 실패한다.
FROM nrel/energyplus:25.1.0

# HF Spaces는 7860 포트를 노출한다
ENV PORT=7860 \
    PYTHONUNBUFFERED=1 \
    EPLUS_DIR=/usr/local/EnergyPlus-25-1-0

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir "fastapi==0.115.6" "uvicorn[standard]==0.34.0" \
                               "python-multipart==0.0.20"

WORKDIR /app
COPY app.py /app/app.py

# 기상파일. 없으면 요청 시 사용자가 올린 .epw를 쓴다.
# (추풍령 471350 = 김천 최근접 관측소. climate.onebuilding.org 배포)
COPY weather/ /app/weather/

# HF Spaces는 비root로 돌린다 — E+ 산출물 쓰기 경로를 미리 열어둔다
RUN useradd -m -u 1000 user && mkdir -p /tmp/runs && chown -R user:user /app /tmp/runs
USER user

EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
