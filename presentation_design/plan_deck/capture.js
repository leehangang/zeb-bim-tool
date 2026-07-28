// 익명화 이후의 화면을 다시 찍는다.
//
// 왜 다시 찍나: 캡처 안에 옛 화면 글자가 픽셀로 박혀 있었다. 덱 왼쪽 전체 캡처에도
// 들어 있어서 확대 상자만 옮겨서는 안 지워진다. 가리는 것보다 실제 화면을 다시
// 찍는 쪽이 정직하다 — 발표에서 "이게 지금 화면입니다"가 참이어야 한다.
//
// 규격: 1500×950 CSS × deviceScaleFactor 2 = 3000×1900. 기존 캡처와 같다.
//   (index.html의 확대 좌표가 이 크기를 전제로 계산돼 있다)
const puppeteer = require("puppeteer-core");
const path = require("path");

const DIR = path.resolve("C:/Users/이혁주/Desktop/zeb-chatbot/presentation_design/plan_deck");
const URL = "http://localhost:8599";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Streamlit은 접근성 트리에 라디오를 안 흘려서 label 글자로 찾아 누른다.
const clickLabel = (p, text) =>
  p.evaluate((t) => {
    const el = [...document.querySelectorAll("label")].find((x) => x.innerText.trim() === t);
    if (!el) throw new Error("라벨 없음: " + t);
    el.click();
  }, text);

const clickButton = (p, needle) =>
  p.evaluate((n) => {
    const el = [...document.querySelectorAll("button")].find((x) => x.innerText.includes(n));
    if (!el) throw new Error("버튼 없음: " + n);
    el.click();
  }, needle);

const openAll = (p) =>
  p.evaluate(() => {
    // details만 건드린다. aria-expanded로 훑었더니 우측 상단 햄버거(Rerun/Clear cache…)
    // 까지 열려서 캡처에 개발 메뉴가 찍혔다.
    for (const d of document.querySelectorAll("details")) d.open = true;
  });

// Streamlit은 window가 아니라 section[data-testid="stMain"]을 스크롤한다.
// window.scrollTo는 아무 일도 안 일어난다 — 캡처가 계속 페이지 맨 위였던 이유다.
const scrollTo = (p, needle, pad) =>
  p.evaluate((n, q) => {
    const sc = document.querySelector('[data-testid="stMain"]') || document.scrollingElement;
    const el = [...sc.querySelectorAll("div,p,h1,h2,h3,span,button")]
      .reverse()
      .find((x) => x.innerText && x.innerText.trim().startsWith(n));
    if (!el) throw new Error("스크롤 기준 없음: " + n);
    sc.scrollTop += el.getBoundingClientRect().top - sc.getBoundingClientRect().top - q;
  }, needle, pad);

// 금지어 목록은 저장소에 두지 않는다 — 목록 자체가 식별정보다.
// plan_deck/.anonymity-guard.txt 에 한 줄에 하나씩 적는다 (.gitignore 대상).
const guardWords = () => {
  try {
    return require("fs").readFileSync(path.join(DIR, ".anonymity-guard.txt"), "utf8")
      .split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  } catch { return null; }
};

const bodyText = (p) => p.evaluate(() => document.body.innerText);

(async () => {
  const b = await puppeteer.launch({
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    args: ["--font-render-hinting=none", "--force-color-profile=srgb", "--hide-scrollbars"],
  });
  const p = await b.newPage();
  await p.setViewport({ width: 1500, height: 950, deviceScaleFactor: 2 });
  await p.goto(URL, { waitUntil: "networkidle0" });
  await sleep(4000);

  // ── 홈 (표지에 넣는다) ──────────────────────────────────────
  await clickLabel(p, "🏠 홈");
  await sleep(5000);
  await p.evaluate(() => {
    const sc = document.querySelector('[data-testid="stMain"]');
    if (sc) sc.scrollTop = 0;
  });
  await sleep(800);
  await p.screenshot({ path: path.join(DIR, "img/home.png") });
  console.log("home.png 저장");

  // ── ROI 시뮬레이션 시작 화면 ────────────────────────────────
  await clickLabel(p, "💰 ROI 시뮬레이션");
  await sleep(5000);
  await openAll(p);                              // 예시 입력 아코디언을 펼친다
  await sleep(2500);
  // '나오는 수치' 카드와 '검증 케이스' 예시가 한 화면에 같이 오게 맞춘다.
  // 스크롤 0이면 예시 카드가 아래 끝에 붙어 확대 상자를 못 잡는다.
  await scrollTo(p, "나오는 수치", 120);
  await sleep(800);
  await p.screenshot({ path: path.join(DIR, "img/roi2_strt.png") });
  console.log("roi2_strt.png 저장");

  // ── 사업 신청 인테이크 대화 ─────────────────────────────────
  await clickLabel(p, "📋 사업 신청 인테이크");
  await sleep(5000);
  await openAll(p);
  await sleep(2000);
  // 예시 버튼의 글자는 라벨이 아니라 프롬프트 본문이다 (Streamlit이 그렇게 넣었다)
  await clickButton(p, "○○시청에서 시립 어린이집");
  console.log("예시 클릭 — 모델 응답 대기");

  // 응답이 붙을 때까지 기다린다. 길이가 60초 동안 안 늘면 실패로 본다.
  let last = 0, still = 0;
  for (let i = 0; i < 60; i++) {
    await sleep(2000);
    const n = (await bodyText(p)).length;
    if (n > last) { last = n; still = 0; } else if (++still >= 6) break;
  }
  await sleep(2500);
  // 되묻는 대화가 이 장의 논지다 — 사용자 말풍선 위쪽으로 맞춘다.
  await scrollTo(p, "○○시청에서 시립 어린이집", 90);
  await sleep(800);
  await p.screenshot({ path: path.join(DIR, "img/intake_ask.png") });
  console.log("intake_ask.png 저장");

  const t = await bodyText(p);
  const words = guardWords();
  if (!words) console.log("(!) .anonymity-guard.txt 가 없어 식별어 검사를 건너뛴다");
  else {
    const bad = words.filter((w) => t.includes(w));
    console.log(bad.length ? "!! 화면에 남은 식별어: " + bad.join(", ") : "화면 식별어 0건");
  }
  await b.close();
})();
