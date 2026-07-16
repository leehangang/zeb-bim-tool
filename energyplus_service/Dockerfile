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
# HF Spaces는 Docker + 2 vCPU / 16GB RAM 무료라 0.078코어와 비교가 안 된다.
#
# ⚠️ 확인 필요 — 2026-07-09 HF 포럼에 "신규 무료 계정은 CPU Basic 선택 불가,
#    Docker가 Paid로 표시"된다는 보고가 있다(미해결). 공식 문서는 여전히 CPU Basic FREE라
#    적혀 있어 문서와 실제가 어긋난 상태다. 계정에서 직접 확인할 것.
#    막혀 있으면 이 Dockerfile 그대로 Modal($30/월 무료)·Cloud Run에 올리면 된다.
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
