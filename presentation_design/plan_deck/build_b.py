# -*- coding: utf-8 -*-
"""09~18 슬라이드를 index.html에 붙인다.

캡처 확대는 원본(3000×1900)의 사각형을 상자에 맞춰 넣는 계산을 코드로 한다.
손으로 offset을 적으면 반드시 어긋난다 — 홍보영상에서 이미 두 번 당했다.
숫자는 전부 저장소 코드/리서치에서 확인한 값이다.
"""
import io

P = 'index.html'
s = io.open(P, encoding='utf-8').read()
if 'slides-b.css' not in s:
    s = s.replace('<link rel="stylesheet" href="slides-a.css">',
                  '<link rel="stylesheet" href="slides-a.css">\n<link rel="stylesheet" href="slides-b.css">', 1)

IW, IH = 3000, 1900
ZW, ZH = 660, 155          # .zoom 상자 실측에 맞춘 기준 크기


def zoom(img, rect, label, bw=ZW, bh=ZH):
    """원본 rect=[x,y,w,h]가 상자를 가득 채우도록 확대·이동시킨다."""
    x, y, w, h = rect
    sc = max(bw / w, bh / h)                 # 상자를 덮는 배율
    iw = IW * sc
    left = -(x * sc) + (bw - w * sc) / 2     # rect 중심을 상자 중심에
    top = -(y * sc) + (bh - h * sc) / 2
    left = min(0, max(left, bw - iw))        # 이미지 밖으로 나가면 가장자리에 붙인다
    top = min(0, max(top, bh - IH * sc))
    return (f'<div class="zoom"><img src="img/{img}.png" '
            f'style="width:{iw:.0f}px; left:{left:.0f}px; top:{top:.0f}px">'
            f'<span class="lb">{label}</span></div>')


def shot_slide(sid, num, kicker, title, sub, full, ftag, zooms, concl, ft):
    z = "\n      ".join(zoom(i, r, l) for i, r, l in zooms)
    return f'''
<section class="slide" id="{sid}">
  <div class="hd"><span>{kicker}</span><span>{num}</span></div>
  <div class="rule"></div>
  <h1>{title}</h1>
  <div class="sub">{sub}</div>
  <div class="shots">
    <div class="shot"><img src="img/{full}.png"><span class="tag">{ftag}</span></div>
    <div class="zooms">
      {z}
    </div>
  </div>
  <div class="concl" style="margin-top:26px">{concl}</div>
  <div class="ft">{ft}</div>
</section>
'''


OUT = []

# ── 09 BIM 진단 ────────────────────────────────────────────────
OUT.append(shot_slide(
    "s09", "09", "SOLUTION&nbsp; |&nbsp; BIM 진단 + ROI",
    "파일 하나를 올리면 두 제도의 판정이 나란히 나옵니다",
    "gbXML을 올리면 벽·창·설비를 11개 그린리모델링 기술요소로 나눠 진단합니다.",
    "bim_tabs", "진단 결과 화면",
    [("bim_tabs", [756, 238, 2084, 177], "TRACK A · B 판정이 나란히"),
     ("bim_tabs", [758, 536, 962, 96], "여섯 개 탭 — 등급·진단·비용·최적화·민감도·리포트")],
    "여기 나오는 등급은 <b>설계 검토용 추정</b>입니다. 공식 등급은 ECO2 해석으로만 확정됩니다.",
    "근거 · ZEB 인증기준 공동고시 [별표2] &nbsp;|&nbsp; 2026 공공 GR 2.0 가이드라인 [표1] · 요소 80 + 사업여건 20"))

# ── 10 정책 Q&A ────────────────────────────────────────────────
OUT.append(shot_slide(
    "s10", "10", "SOLUTION&nbsp; |&nbsp; 정책 Q&amp;A",
    "찾은 조문을 원문 그대로 인용해 답합니다",
    "법과 고시와 공고 원문 19건을 조항 단위 1,300개로 잘라 두고, 질문이 오면 관련 조항만 찾아 인용합니다.",
    "qa2_open", "질문에 답하고 출처를 붙인 화면",
    [("qa2_open", [756, 250, 2088, 200], "출처 5건 — 파일명 · 쪽수 · 유사도"),
     ("qa2_open", [760, 361, 2080, 421], "누르면 인용한 원문이 그대로 펼쳐진다")],
    "근거 조항을 찾지 못하면 <b>아는 척하지 않고 자료에 없다고 답합니다.</b>",
    "색인 원문 19건 · 1,300청크 &nbsp;|&nbsp; 무료 티어 메모리 제약으로 임베딩 대신 키워드(TF-IDF) 검색 사용"))

# ── 11 ROI 시뮬레이션 ──────────────────────────────────────────
OUT.append(shot_slide(
    "s11", "11", "SOLUTION&nbsp; |&nbsp; ROI 시뮬레이션",
    "도면이 없어도 문장 하나로 사업성을 계산합니다",
    "면적과 용도와 목표 등급을 문장에서 읽어 계산 프로그램에 넘기고, 계산은 프로그램이 합니다.",
    "roi2_strt", "ROI 시뮬레이션 시작 화면",
    [("roi2_strt", [792, 578, 2016, 230], "나오는 수치 — Max Cost · 보조금 · NPV · 회수기간"),
     ("roi2_strt", [794, 1170, 2012, 290], "예시를 누르면 그 조건이 그대로 입력된다")],
    "도담 기준 외피 보강 <b>1.81억</b> · 보조 50% 적용 시 자부담 <b>0.91억</b> · 회수 <b>12.2년</b>(에너지 가격 연 2.5% 상승 가정).",
    "근거 · 조달청 시설공통자재 단가 442종 · 간접공사비 기준(2026) &nbsp;|&nbsp; 한국전력 기본공급약관 140.9원/kWh &nbsp;|&nbsp; 할인율 4.5% · 20년"))

# ── 12 사업 신청 인테이크 ──────────────────────────────────────
OUT.append(shot_slide(
    "s12", "12", "SOLUTION&nbsp; |&nbsp; 사업 신청 인테이크",
    "대화가 신청서 초안이 됩니다",
    "공공과 민간은 근거 조항도 지원 방식도 서식도 제출처도 다릅니다. 고른 쪽에 맞는 항목만 묻습니다.",
    "intake_top", "공공 · 민간을 나눠 접수하는 첫 화면",
    [("intake_top", [750, 1470, 2110, 300], "필수 · 선택 항목 완성도를 그때그때 집계"),
     ("intake_ask", [750, 235, 2120, 560], "모자란 항목을 되물어 채운다")],
    "필수 항목이 다 차기 전에는 초안을 만들지 않고, <b>공식 양식은 창조센터에서 받아 대조하라</b>고 안내합니다.",
    "공공 필수 16 · 선택 9 &nbsp;|&nbsp; 민간 필수 22 · 선택 8 &nbsp;|&nbsp; 근거 · GR 지원사업 운영고시 · 2026 민간 GR 이자지원 공고"))

# ── 13 역할 분리 ───────────────────────────────────────────────
OUT.append('''
<section class="slide" id="s13">
  <div class="hd"><span>RELIABILITY&nbsp; |&nbsp; 역할 분리</span><span>13</span></div>
  <div class="rule"></div>
  <h1>계산은 코드가, 설명만 AI가 맡습니다</h1>
  <div class="sub">돈이 걸린 답에서 지어낸 조항 하나는 그대로 손해가 됩니다. 그래서 계산에는 AI를 두지 않았습니다.</div>

  <div class="roles">
    <div class="role code">
      <k>프로그램이 한다</k>
      <b>판정과 계산</b>
      <ul>
        <li>ZEB 등급 판정 · 자립률 · 1차에너지소요량</li>
        <li>GR 정량평가 100점 채점</li>
        <li>공사비 · 보조금 · NPV · IRR · 회수기간</li>
      </ul>
    </div>
    <div class="role ai">
      <k>AI가 한다</k>
      <b>읽기와 설명</b>
      <ul>
        <li>문장에서 면적 · 용도 · 목표 등급을 읽기</li>
        <li>찾은 조문을 인용해 답하기</li>
        <li>결과를 사람 말로 풀어 쓰기</li>
      </ul>
    </div>
  </div>

  <div class="rules">
    <div><b>같은 입력 → 같은 결과</b>계산이 코드에 있으니 실행할 때마다 값이 흔들리지 않습니다.</div>
    <div><b>틀리면 추적된다</b>결과가 이상할 때 어느 단계가 틀렸는지 되짚을 수 있습니다.</div>
    <div><b>근거가 없으면 없다고</b>조항을 못 찾으면 지어내지 않고 자료에 없다고 답합니다.</div>
  </div>
  <div class="ft">설계 원칙 · 파인튜닝 대신 에이전트 — 단가표 · 공고 · 법령 원문만 갈아 끼우면 되도록 계산 파라미터를 YAML로 분리</div>
</section>
''')

# ── 14 근거 공개 ───────────────────────────────────────────────
OUT.append('''
<section class="slide" id="s14">
  <div class="hd"><span>RELIABILITY&nbsp; |&nbsp; 근거 공개</span><span>14</span></div>
  <div class="rule"></div>
  <h1>값마다 조항과 시행일, 그리고 상태를 붙였습니다</h1>
  <div class="sub">계산 도구가 자기가 아는 것과 모르는 것을 화면에 스스로 표시하게 만들었습니다.</div>

  <div class="tbl">
    <div class="hrow"><span class="c1">상태</span><span class="c2">값</span><span class="c3">근거</span><span class="c4">계산에서</span></div>
    <div class="row">
      <span class="c1"><span class="pill ok">확정</span></span>
      <span class="c2">취득세 감면율</span>
      <span class="c3">지방세특례제한법 제47조의2</span>
      <span class="c4">3등급↑ 20% · 4등급 18% · 5등급 15% — 그대로 사용</span>
    </div>
    <div class="row">
      <span class="c1"><span class="pill dead">폐지</span></span>
      <span class="c2">재산세 감면</span>
      <span class="c3">근거 조항 2018년 종료</span>
      <span class="c4">계산에서 제외 — 남겨 두면 회수기간이 실제보다 짧게 나옵니다</span>
    </div>
    <div class="row">
      <span class="c1"><span class="pill tbd">확인 필요</span></span>
      <span class="c2">전기 요금 단가</span>
      <span class="c3">한국전력 기본공급약관 140.9원/kWh</span>
      <span class="c4">계약 종별에 따라 달라져 하나로 고정하지 않음</span>
    </div>
  </div>

  <div class="concl" style="margin-top:26px">받지 못할 혜택을 편익으로 잡으면 회수기간이 짧아 보입니다. <b>덜 유리하게 나오더라도 지웠습니다.</b></div>
  <div class="ft">근거·출처 화면에 파라미터마다 조항 · 시행일 · 원문 링크를 함께 표시 &nbsp;|&nbsp; 계산 파라미터는 코드가 아닌 YAML에 분리</div>
</section>
''')

# ── 15 검증 케이스 ─────────────────────────────────────────────
OUT.append('''
<section class="slide" id="s15">
  <div class="hd"><span>VALIDATION&nbsp; |&nbsp; 검증 케이스</span><span>15</span></div>
  <div class="rule"></div>
  <h1>KEPCO 김천 도담어린이집으로 검증했습니다</h1>
  <div class="sub">공공기관이 소유한 노후 건물이면서 연면적이 1,000㎡ 기준선을 넘어, 두 제도를 같은 건물에서 확인할 수 있습니다.</div>

  <div class="case">
    <div class="spec">
      <k>검증 표본</k>
      <b>한국전력기술<br>도담어린이집</b>
      <div class="kv">
        <div><span>연면적</span><span>1,251.44 ㎡</span></div>
        <div><span>사용승인</span><span>2014년</span></div>
        <div><span>용도</span><span>노유자시설 (어린이집)</span></div>
        <div><span>소유</span><span>공공기관 — 공사비 50% 지원 대상</span></div>
        <div><span>ZEB</span><span>의무 아님 — 자율 신청 대상</span></div>
      </div>
    </div>
    <div class="finds">
      <div class="find">
        <div class="big">12.5배</div>
        <div class="tx"><b>서측 외벽 6개에 단열재가 없었습니다</b>
          <i>열관류율 3.0 W/㎡·K — 중부2지역 기준 0.24의 12.5배. 벽체 574개를 재료 정보로 분류해 찾아냈습니다.</i></div>
      </div>
      <div class="find">
        <div class="big">96.8%</div>
        <div class="tx"><b>외피 열손실이 세 곳에 몰려 있었습니다</b>
          <i>최하층 바닥 50.7% · 외벽 28.5% · 창호 19.2% — 어디부터 고칠지가 여기서 정해집니다.</i></div>
      </div>
      <div class="find">
        <div class="big">태양열</div>
        <div class="tx"><b>사진으로는 태양광처럼 보였습니다</b>
          <i>BIM 객체를 확인하니 전기를 만드는 태양광이 아니라 물을 데우는 태양열집열판 27㎡였습니다.</i></div>
      </div>
    </div>
  </div>
  <div class="ft">근거 · 건축물의 에너지절약설계기준 [별표1] 중부2지역 외벽 0.24 W/㎡·K 이하 &nbsp;|&nbsp; 녹색건축물 조성 지원법 시행령 [별표1] — 의무 대상은 신축·재축·전부개축·별동증축</div>
</section>
''')

# ── 16 Before / After ─────────────────────────────────────────
OUT.append('''
<section class="slide" id="s16">
  <div class="hd"><span>VALIDATION&nbsp; |&nbsp; 개선 효과</span><span>16</span></div>
  <div class="rule"></div>
  <h1>11개 기술요소를 전부 보강하면 인증 미달에서 5등급으로 올라섭니다</h1>
  <div class="sub">BEMS 설치를 포함한 전체 보강 기준입니다. 산출 등급은 설계 검토용 추정입니다.</div>

  <div class="ba">
    <div class="hd2"><span class="l">현재</span><span class="m"></span><span class="r">전체 보강 후</span></div>
    <div class="row">
      <span class="l">168.5</span>
      <span class="m"><b>1차에너지소요량</b><i>kWh/㎡·년</i></span>
      <span class="r">99.1</span>
    </div>
    <div class="row">
      <span class="l">24점</span>
      <span class="m"><b>GR 정량평가</b><i>100점 만점 · 고득점 순 선정</i></span>
      <span class="r">76점</span>
    </div>
    <div class="row">
      <span class="l">인증 미달</span>
      <span class="m"><b>ZEB 등급</b><i>제2호 1차에너지소요량 기준</i></span>
      <span class="r">5등급</span>
    </div>
    <div class="row">
      <span class="l">—</span>
      <span class="m"><b>성능개선비율</b><i>지원 기준 20% 이상</i></span>
      <span class="r">41.2%</span>
    </div>
  </div>

  <div class="concl" style="margin-top:22px">자립률 기준으로 4등급까지 가려면 태양광을 <b>약 25kW 더</b> 달아야 합니다. 태양열집열판은 전기를 만들지 않기 때문입니다.</div>
  <div class="ft">근거 · ZEB 인증기준 공동고시 [별표2] &nbsp;|&nbsp; 2026 공공 GR 2.0 가이드라인 [표1] &nbsp;|&nbsp; 성능개선비율 = (개선전 − 개선후) ÷ 개선전 · 공고 산식</div>
</section>
''')

# ── 17 정책 함의 (다크) ────────────────────────────────────────
OUT.append('''
<section class="slide dark" id="s17">
  <div class="hd"><span>IMPLICATION&nbsp; |&nbsp; 정책 함의</span><span>17</span></div>
  <div class="rule"></div>
  <h1>보조금이 사업의 성패를 가릅니다</h1>
  <div class="sub">같은 건물, 같은 공사입니다. 보조율만 바꿔 가며 회수기간을 계산했습니다.</div>

  <div class="bars">
    <div class="b"><k>보조금 없음</k><div class="track"><div class="fill" style="width:100%"></div></div><v>88.5년</v></div>
    <div class="b"><k>보조율 50%</k><div class="track"><div class="fill" style="width:50%"></div></div><v>44.3년</v></div>
    <div class="b"><k>보조율 70%</k><div class="track"><div class="fill" style="width:30%"></div></div><v>26.6년</v></div>
    <div class="b"><k>10년 안에 회수하려면</k><div class="track"><div class="fill hot" style="width:11%"></div></div><v>보조 89%</v></div>
  </div>

  <div class="dconcl">그린리모델링은 시장에만 맡겨 두면 퍼지지 않습니다. 공공의 보조가 있어야 성립한다는 것을 우리 손으로 계산해 확인했습니다.</div>
  <div class="ft">전체 보강 기준 · 자부담 = 공사비 × (1 − 보조율) ÷ 연간 절감액 &nbsp;|&nbsp; 2026 공공 GR 2.0은 공사비의 50%를 지원</div>
</section>
''')

# ── 18 로드맵 · 마무리 (다크) ──────────────────────────────────
OUT.append('''
<section class="slide dark" id="s18">
  <div class="hd"><span>SCALE UP&nbsp; |&nbsp; 로드맵</span><span>18</span></div>
  <div class="rule"></div>
  <h1>지금은 한 채, 다음은 여러 채, 끝은 지자체 단위입니다</h1>

  <div class="road">
    <div class="ph now">
      <k>PHASE 1 · 지금</k>
      <b>건물 한 채를<br>판정한다</b>
      <ul>
        <li>gbXML 한 건 → 두 제도 판정</li>
        <li>공사비 · 경제성 · 신청서 초안</li>
        <li>법령 원문 19건 색인</li>
      </ul>
    </div>
    <div class="ph">
      <k>PHASE 2</k>
      <b>여러 채를<br>줄 세운다</b>
      <ul>
        <li>동점자 우선순위 8단계 구현</li>
        <li>보유 건물 중 어디부터 고칠지</li>
        <li>예산 안에서 최적 조합 탐색</li>
      </ul>
    </div>
    <div class="ph">
      <k>PHASE 3</k>
      <b>공식 엔진과<br>맞춰 본다</b>
      <ul>
        <li>ECO2 산출값과 교차 검증</li>
        <li>태양열의 자립률 반영 산식 확정</li>
        <li>계약 종별 전기 단가 확정</li>
      </ul>
    </div>
    <div class="ph">
      <k>VISION</k>
      <b>지자체가<br>지도 위에서 고른다</b>
      <ul>
        <li>노후 건축물 44.4%가 대상</li>
        <li>진단 속도가 곧 감축 속도</li>
      </ul>
    </div>
  </div>

  <div class="close">
    <div class="big">건물 한 채의 개선안이 아니라,<br>여러 건물에 같은 방식으로 쓰는 진단 도구입니다.</div>
    <div class="url">zeb-bim-tool.streamlit.app<br><b>성제건 (1398)</b></div>
  </div>
</section>
''')

s = s.rstrip() + "\n" + "".join(OUT)
io.open(P, 'w', encoding='utf-8').write(s)
print(f'09~18 · {len(OUT)}장 삽입 완료')
