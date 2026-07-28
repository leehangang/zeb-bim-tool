// 홍보영상 에셋 재촬영 — 익명화 이후 화면.
//
// 왜: v34/v35 영상에 건물명·기관명·주소·담당자 전화번호가 픽셀로 박혀 있었다.
//     영상은 앱 화면 캡처를 이어 붙인 것이라, 화면을 다시 찍으면 해결된다.
//     감사 결과 25장 중 8장에만 식별정보가 있었다 — 그 8장만 다시 찍는다.
//
// 규격: 1500×950 CSS × DSF 2 = 3000×1900 (원본 에셋과 동일).
// 출력: --out= 으로 받은 폴더 (기본은 zebpromo4/assets)
const puppeteer = require("puppeteer-core");
const path = require("path");
const fs = require("fs");

const arg = (k, d) => (process.argv.find((a) => a.startsWith(k)) || "").split("=")[1] || d;
const OUT = path.resolve(arg("--out=", "."));
const URL = arg("--url=", "http://localhost:8599");
const ONLY = arg("--only=", "").split(",").filter(Boolean);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const want = (n) => !ONLY.length || ONLY.includes(n);

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

// details만 연다 — aria-expanded로 훑으면 우상단 햄버거까지 열려 개발 메뉴가 찍힌다.
const openAll = (p) =>
  p.evaluate(() => { for (const d of document.querySelectorAll("details")) d.open = true; });

// Streamlit은 window가 아니라 section[data-testid="stMain"]을 스크롤한다.
const scrollTo = (p, needle, pad) =>
  p.evaluate((n, q) => {
    const sc = document.querySelector('[data-testid="stMain"]') || document.scrollingElement;
    const el = [...sc.querySelectorAll("div,p,h1,h2,h3,span,button,textarea")]
      .reverse()
      .find((x) => (x.innerText || x.placeholder || "").trim().startsWith(n));
    if (!el) throw new Error("스크롤 기준 없음: " + n);
    sc.scrollTop += el.getBoundingClientRect().top - sc.getBoundingClientRect().top - q;
  }, needle, pad);

const scrollTop = (p) =>
  p.evaluate(() => {
    const sc = document.querySelector('[data-testid="stMain"]');
    if (sc) sc.scrollTop = 0;
  });

const shoot = async (p, name) => {
  await sleep(700);
  await p.screenshot({ path: path.join(OUT, name + ".png") });
  console.log("  ▸ " + name + ".png");
};

// 모델 답변이 다 붙을 때까지 — 길이가 안 늘면 끝난 것으로 본다.
const waitAnswer = async (p) => {
  let last = 0, still = 0;
  for (let i = 0; i < 60; i++) {
    await sleep(2000);
    const n = (await p.evaluate(() => document.body.innerText)).length;
    if (n > last) { last = n; still = 0; } else if (++still >= 6) break;
  }
  await sleep(2000);
};

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await puppeteer.launch({
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    args: ["--font-render-hinting=none", "--force-color-profile=srgb", "--hide-scrollbars"],
  });
  const p = await b.newPage();
  await p.setViewport({ width: 1500, height: 950, deviceScaleFactor: 2 });
  await p.goto(URL, { waitUntil: "networkidle0" });
  await sleep(4000);

  // ── 홈 ────────────────────────────────────────────────────
  if (want("home")) {
    await clickLabel(p, "🏠 홈");
    await sleep(4500); await scrollTop(p);
    await shoot(p, "home");
  }

  // ── BIM 진단 ──────────────────────────────────────────────
  if (want("bim_start") || want("bim_pick")) {
    await clickLabel(p, "🏢 BIM 진단 + ROI");
    await sleep(5000); await openAll(p); await sleep(2000);

    if (want("bim_start")) {          // 데모 카드가 화면 아래쪽에 오는 컷
      // pad를 120으로 두면 위에 있는 'BIM 진단 + ROI 분석' 제목이 화면 밖으로 날아간다.
      // 영상이 그 제목까지 담는 컷을 쓰므로 229 CSS px만큼 더 내려서 잡는다.
      await scrollTo(p, "🏢 분석할 건물 선택", 349);
      await shoot(p, "bim_start");
    }
    if (want("bim_pick")) {           // 데모를 고른 뒤 — 카드가 위로, 안내 박스가 보인다
      await clickButton(p, "실증 케이스(어린이집)");
      await sleep(4000); await openAll(p); await sleep(1500);
      await scrollTo(p, "🏫 실증 케이스(어린이집)", 100);
      await shoot(p, "bim_pick");
    }
  }

  // ── ROI 시뮬레이션 ────────────────────────────────────────
  if (want("roi_start") || want("roi2_strt") || want("roi_input") || want("roi_cost")) {
    await clickLabel(p, "💰 ROI 시뮬레이션");
    await sleep(5000); await openAll(p); await sleep(2000);

    if (want("roi_start")) {          // 예시 카드가 화면 아래쪽
      await scrollTop(p);
      await shoot(p, "roi_start");
    }
    if (want("roi2_strt")) {          // 예시 카드가 화면 가운데
      await scrollTo(p, "나오는 수치", 120);
      await shoot(p, "roi2_strt");
    }
    if (want("roi_input") || want("roi_cost")) {
      await clickButton(p, "공공기관이 소유한 실제 어린이집");   // 예시 → 입력창에 채워진다
      await sleep(3500); await openAll(p); await sleep(1500);
      if (want("roi_input")) {
        await scrollTo(p, "🏫 우리 검증 케이스", 60);
        await shoot(p, "roi_input");
      }
      // 실행 → 답변
      // 🔴 여기서 한 번 실패했다. 예시를 누르자마자 실행을 눌러 입력이 비어 있었고,
      //    결과가 없으니 '📊'로 스크롤도 못 해 페이지 맨 위가 찍혔다.
      //    입력이 실제로 채워졌는지 보고 누른다.
      await p.waitForFunction(
        () => [...document.querySelectorAll("textarea")].some((x) => x.value.trim().length > 30),
        { timeout: 30000 });
      await clickButton(p, "시뮬레이션 실행");
      console.log("  … 모델 응답 대기");
      await waitAnswer(p);
      // 결과가 실제로 붙었는지 확인하고 나서 찍는다.
      await p.waitForFunction(() => document.body.innerText.includes("ROI 분석"), { timeout: 120000 });
      if (want("roi_cost")) {
        await openAll(p); await sleep(1200);
        await scrollTo(p, "📊", 60);
        await shoot(p, "roi_cost");
      }
    }
  }

  // ── 사업 신청 인테이크 ────────────────────────────────────
  if (want("intake_ask")) {
    await clickLabel(p, "📋 사업 신청 인테이크");
    await sleep(5000); await openAll(p); await sleep(2000);
    await clickButton(p, "○○시청에서 시립 어린이집");
    console.log("  … 모델 응답 대기");
    await waitAnswer(p);
    await scrollTo(p, "○○시청에서 시립 어린이집", 90);
    await shoot(p, "intake_ask");
  }

  const t = await p.evaluate(() => document.body.innerText);
  let words = null;
  try {
    words = fs.readFileSync(path.join(__dirname, ".anonymity-guard.txt"), "utf8")
      .split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  } catch { /* 목록이 없으면 검사 생략 */ }
  if (!words) console.log("(!) .anonymity-guard.txt 없음 — 식별어 검사 건너뜀");
  else {
    const bad = words.filter((w) => t.includes(w));
    console.log(bad.length ? "!! 마지막 화면에 식별어: " + bad.join(", ") : "마지막 화면 식별어 0건");
  }
  await b.close();
})();
