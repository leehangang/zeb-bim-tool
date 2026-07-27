# -*- coding: utf-8 -*-
"""01~04 · 07~08 슬라이드를 index.html에 끼워 넣는다.
숫자는 전부 리서치로 확인한 값이거나 저장소 코드에서 온 값이다."""
import io

P = 'index.html'
s = io.open(P, encoding='utf-8').read()

if 'slides-a.css' not in s:
    s = s.replace('</style>\n', '</style>\n<link rel="stylesheet" href="slides-a.css">\n', 1)

COVER_ART = '''<svg viewBox="0 0 470 720" fill="none">
  <g stroke="var(--g3)" stroke-width="1.4">
    <path d="M40 360 H150"/><path d="M150 250 V470"/>
    <path d="M150 250 H330"/><path d="M150 470 H330"/>
  </g>
  <circle cx="40" cy="360" r="7" fill="var(--green)"/>
  <rect x="330" y="228" width="96" height="44" rx="10" fill="var(--green)"/>
  <rect x="330" y="448" width="96" height="44" rx="10" fill="var(--green)"/>
  <text x="378" y="256" text-anchor="middle" fill="#fff"
        font-size="15" font-weight="700" font-family="Noto Sans KR">ZEB</text>
  <text x="378" y="476" text-anchor="middle" fill="#fff"
        font-size="15" font-weight="700" font-family="Noto Sans KR">GR</text>
  <text x="150" y="330" text-anchor="middle" fill="var(--g2)"
        font-size="13" font-family="Noto Sans KR">판정만 두 갈래</text>
</svg>'''

S01 = f'''
<section class="slide" id="s01">
  <div class="cover">
    <div class="left">
      <div class="eyebrow">IDEA PROPOSAL · 2026</div>
      <h1>ZEB-ROI</h1>
      <div class="tag">BIM 한 번으로 ZEB 인증 등급과<br>그린리모델링 사업성을 함께 판정하는 의사결정 플랫폼</div>
      <div class="meta">
        <b>성제건 (1398)</b> · 성균관대학교 건설환경공학부<br>
        zeb-bim-tool.streamlit.app
      </div>
    </div>
    <div class="art">{COVER_ART}</div>
  </div>
</section>
'''

S02 = '''
<section class="slide" id="s02">
  <div class="hd"><span>PROBLEM&nbsp; |&nbsp; 이어지지 않는 두 제도</span><span>02</span></div>
  <div class="rule"></div>
  <h1>같은 건물을 다루는데, 데이터가 평가로 넘어가지 않습니다</h1>
  <div class="sub">두 의무화가 나란히 굴러가지만, 둘을 잇는 자리는 비어 있습니다.</div>

  <div class="two">
    <div class="pillar">
      <div class="cap">의무화 &nbsp;01</div>
      <b>ZEB 인증</b>
      <ul>
        <li><b>2025.1.1</b> — 연면적 1,000㎡ 이상 공공건축물 <b>ZEB 4등급 이상</b></li>
        <li>민간 1,000㎡ 이상 · 30세대 이상 공동주택은 <b>5등급 수준 설계</b></li>
        <li>미취득 시 과태료 50만원</li>
      </ul>
    </div>
    <div class="gapzone">
      <svg viewBox="0 0 168 290"><g stroke="var(--g3)" stroke-width="1.2" fill="none">
        <path d="M4 145 H48"/><path d="M164 145 H120"/></g>
        <path d="M48 138 L58 145 L48 152 Z" fill="var(--chev)"/>
        <path d="M120 138 L110 145 L110 152 Z" fill="var(--chev)"/></svg>
      <div class="q">?</div>
    </div>
    <div class="pillar">
      <div class="cap">의무화 &nbsp;02</div>
      <b>BIM 적용</b>
      <ul>
        <li><b>1,000억원 이상</b> 신규 공공공사 전 과정 BIM</li>
        <li><b>2026년 500억</b> 이상 → <b>2028년 300억</b> 이상으로 확대</li>
        <li>공동주택은 2024년 100% 시행</li>
      </ul>
    </div>
  </div>

  <div class="concl" style="margin-top:30px">건물 정보는 이미 디지털로 쌓이는데, ZEB 평가는 그 값을 사람이 다시 손으로 입력합니다.</div>
  <div class="ft">근거 · 녹색건축물 조성 지원법 시행령 &nbsp;|&nbsp; 국토교통부 「건설산업 BIM 기본지침」 · 「2030 건축 BIM 활성화 로드맵」</div>
</section>
'''

S03 = '''
<section class="slide" id="s03">
  <div class="hd"><span>PROBLEM&nbsp; |&nbsp; 수요는 확정됐고 모수는 이미 있다</span><span>03</span></div>
  <div class="rule"></div>
  <h1>제도가 밀고 예산도 열렸는데, 판단할 도구가 없습니다</h1>

  <div class="three">
    <div>
      <h3>제도가 민다</h3>
      <div class="num"><b>4등급</b><span>2025년 공공 의무</span></div>
      <ul>
        <li>연면적 <b>1,000㎡ 이상 공공</b>건축물</li>
        <li>민간은 <b>5등급 수준 설계</b> 의무</li>
        <li>BIM은 <b>2026년 500억 이상</b>으로 확대</li>
      </ul>
    </div>
    <div>
      <h3>모수가 크다</h3>
      <div class="num"><b>44.4%</b><span>전국 724만 동 중</span></div>
      <ul>
        <li>사용승인 후 <b>30년 초과</b> 건축물 비중</li>
        <li>비수도권 47.1% · 수도권 37.7%</li>
        <li>교육·사회용 <b>26.4%</b> — 어린이집이 여기</li>
      </ul>
    </div>
    <div>
      <h3>예산이 열렸다</h3>
      <div class="num"><b>1,688억</b><span>2026 공공 GR 2.0</span></div>
      <ul>
        <li>공공건축물 그린리모델링 총 사업규모</li>
        <li>민간 이자지원 <b>25억 → 135억</b></li>
        <li>공사비 보조 · 취득세 감면 · 용적률 완화</li>
      </ul>
    </div>
  </div>

  <div class="check">대상도 예산도 정해졌습니다. 남은 것은 “이 건물이 되는가”를 판단하는 일입니다.</div>
  <div class="ft">출처 · 국토교통부 건축물 현황 통계(2024년 말) &nbsp;|&nbsp; 2026년 「공공건축물 그린리모델링 2.0」 사업 공모 &nbsp;|&nbsp; 제로에너지건축물 인증 의무화 로드맵</div>
</section>
'''

S04 = '''
<section class="slide" id="s04">
  <div class="hd"><span>SOLUTION&nbsp; |&nbsp; End-to-End</span><span>04</span></div>
  <div class="rule"></div>
  <h1>gbXML로 시작해 신청서 초안으로 끝납니다</h1>
  <div class="sub">설치 없이 주소만으로 접속해, 파일 하나를 올리면 판정부터 신청서까지 한 흐름으로 이어집니다.</div>

  <div class="steps">
    <div class="step io"><k>INPUT</k><b>gbXML 업로드</b><i>Revit 내보내기 · 드래그앤드롭</i></div>
    <div class="stepgap"><svg width="14" height="16"><path d="M0 0 L12 8 L0 16 Z" fill="var(--chev)"/></svg></div>
    <div class="step"><k>STEP 01</k><b>읽고 거른다</b><i>부재 · 좌표 · 열관류율 추출<br>못 믿을 파일은 중지</i></div>
    <div class="stepgap"><svg width="14" height="16"><path d="M0 0 L12 8 L0 16 Z" fill="var(--chev)"/></svg></div>
    <div class="step"><k>STEP 02</k><b>두 제도로 판정</b><i>ZEB 등급 · GR 정량평가<br>근거 조항과 함께</i></div>
    <div class="stepgap"><svg width="14" height="16"><path d="M0 0 L12 8 L0 16 Z" fill="var(--chev)"/></svg></div>
    <div class="step"><k>STEP 03</k><b>보강과 경제성</b><i>공사비 · 보조금 · 자부담<br>NPV · IRR · 회수기간</i></div>
    <div class="stepgap"><svg width="14" height="16"><path d="M0 0 L12 8 L0 16 Z" fill="var(--chev)"/></svg></div>
    <div class="step io"><k>OUTPUT</k><b>신청서 초안</b><i>근거·출처를 붙여서</i></div>
  </div>

  <div class="modes">
    <span>BIM 진단 + ROI</span><span>정책 Q&amp;A</span><span>ROI 시뮬레이션</span>
    <span>사업 신청 인테이크</span><span>근거·출처</span>
  </div>
  <div class="concl" style="margin-top:26px">중간에 파일을 주고받거나 프로그램을 설치할 일이 없습니다.</div>
  <div class="ft">근거 · ZEB 인증기준 공동고시 &nbsp;|&nbsp; GR 지원사업 운영고시 §9 &nbsp;|&nbsp; 조달청 시설공통자재 단가 · 간접공사비 기준(2026)</div>
</section>
'''

S07 = '''
<section class="slide" id="s07">
  <div class="hd"><span>WHY US&nbsp; |&nbsp; 차별점</span><span>07</span></div>
  <div class="rule"></div>
  <h1>남들은 등급만 매기고, 우리는 근거까지 답합니다</h1>

  <div class="split">
    <div class="dcards">
      <div class="dcard">
        <div class="no">차별점 01</div>
        <b>두 제도를<br>한 번에 판정</b>
        <ul>
          <li>같은 입력으로 ZEB 인증과 GR 지원사업을 동시 판정</li>
          <li>판정은 분리, 해석·단가·법령은 공유</li>
        </ul>
      </div>
      <div class="dcard">
        <div class="no">차별점 02</div>
        <b>계산은 코드,<br>설명만 AI</b>
        <ul>
          <li>같은 입력에 항상 같은 결과</li>
          <li>틀렸을 때 어느 단계인지 추적 가능</li>
        </ul>
      </div>
      <div class="dcard">
        <div class="no">차별점 03</div>
        <b>값마다<br>근거를 공개</b>
        <ul>
          <li>조항 · 시행일 · 상태를 화면에 표시</li>
          <li>폐지된 조항은 계산에서 제외</li>
        </ul>
      </div>
    </div>

    <div class="side">
      <div class="st">경쟁군 대비 · 지금은 이렇게 한다</div>
      <div class="item">
        <b>ZEB 인증 대행 · 컨설팅</b>
        <i>ECO2에 방·외피·설비를 사람이 처음부터 입력</i>
        <em>→ 수일~수주 · 입력자에 따라 결과가 달라진다</em>
      </div>
      <div class="item">
        <b>범용 에너지 해석 도구</b>
        <i>성능은 계산하지만 제도 판정은 하지 않는다</i>
        <em>→ 보조금 · 세제 · 신청서로 이어지지 않는다</em>
      </div>
    </div>
  </div>
  <div class="ft">근거 · ZEB 인증기준 공동고시 [별표2] &nbsp;|&nbsp; 지방세특례제한법 제47조의2 &nbsp;|&nbsp; 녹색건축물 조성 지원법 제15조 · 시행령 제11조</div>
</section>
'''

S08 = '''
<section class="slide" id="s08">
  <div class="hd"><span>SOLUTION&nbsp; |&nbsp; 모드 라인업</span><span>08</span></div>
  <div class="rule"></div>
  <h1>네 개 모드가 하나의 의사결정 흐름이 됩니다</h1>

  <div class="lineup">
    <div class="mcard">
      <div class="top"><k>MODE 03</k><b>BIM 진단 + ROI</b></div>
      <div class="bd">
        <div class="q">무엇을 넣으면</div>
        <div class="a">gbXML 파일 또는 데모 케이스</div>
        <div class="q">무엇이 나오는가</div>
        <div class="a">11개 기술요소 진단 · ZEB 등급 · GR 100점 · 보강 우선순위</div>
      </div>
    </div>
    <div class="mcard">
      <div class="top"><k>MODE 01</k><b>정책 Q&amp;A</b></div>
      <div class="bd">
        <div class="q">무엇을 넣으면</div>
        <div class="a">법령 질문을 문장 그대로</div>
        <div class="q">무엇이 나오는가</div>
        <div class="a">원문 19건에서 찾은 조문 인용 · 파일명과 쪽수까지</div>
      </div>
    </div>
    <div class="mcard">
      <div class="top"><k>MODE 02</k><b>ROI 시뮬레이션</b></div>
      <div class="bd">
        <div class="q">무엇을 넣으면</div>
        <div class="a">도면 없이 조건을 문장으로</div>
        <div class="q">무엇이 나오는가</div>
        <div class="a">공사비 상한 · 보조금 · 자부담 · NPV · IRR · 회수기간</div>
      </div>
    </div>
    <div class="mcard">
      <div class="top"><k>MODE 04</k><b>사업 신청 인테이크</b></div>
      <div class="bd">
        <div class="q">무엇을 넣으면</div>
        <div class="a">공공 · 민간 중 해당 사업을 고르고 대화</div>
        <div class="q">무엇이 나오는가</div>
        <div class="a">필수 항목 완성도 집계 · 신청서 초안</div>
      </div>
    </div>
  </div>
  <div class="concl" style="margin-top:26px">화면마다 그 숫자가 어느 조항에서 왔는지 <b>근거·출처</b>에 모아 두었습니다.</div>
  <div class="ft">근거 · 2026 공공 GR 2.0 가이드라인 [표1] &nbsp;|&nbsp; GR 지원사업 운영고시 §7① 대상공사 7종 &nbsp;|&nbsp; 색인 원문 19건 · 1,300청크</div>
</section>
'''

anchor05 = '<!-- ══════════════ 05 · 아키텍처 ══════════════ -->'
assert s.count(anchor05) == 1
s = s.replace(anchor05, S01 + S02 + S03 + S04 + anchor05)
s = s.rstrip() + "\n" + S07 + S08
io.open(P, 'w', encoding='utf-8').write(s)
print('01~04 · 07~08 삽입 완료')
