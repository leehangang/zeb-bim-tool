// 기획서 슬라이드를 HTML에서 뽑는다.
//  · PNG  : deviceScaleFactor 3 → 3840×2160 (원하면 4로 올려 5120×2880)
//  · PDF  : Chrome printToPDF → 글자가 벡터라 확대해도 선명하고 파일도 가볍다 (배포용은 이쪽)
//  · 검사 : 글자가 상자를 넘는지 DOM에서 직접 본다(scrollWidth/Height). 폭 계산보다 정확하다.
const puppeteer = require("puppeteer-core");
const path = require("path");
const fs = require("fs");

const DIR = path.resolve("C:/Users/이혁주/Desktop/zeb-chatbot/presentation_design/plan_deck");
const OUT = path.join(DIR, "out");      // 결과물 — PDF
const QA  = path.join(OUT, "qa");        // 검수용 — PNG (렌더를 눈으로 보려고 뽑는다)
const SRC = "file:///" + path.join(DIR, "index.html").replace(/\\/g, "/");
const DSF = Number(process.argv[2] || 3);
const PNG = !process.argv.includes("--no-png");   // 검수 PNG가 필요 없으면 --no-png
// 글꼴 비교용 — --font=pre(프리텐다드) / --font=prew(굵기 폭까지 확대). 없으면 Noto Sans KR.
const arg = (k) => (process.argv.find(a => a.startsWith(k)) || "").split("=")[1] || "";
const VAR = arg("--font=");
const ONLY = arg("--only=").split(",").filter(Boolean);   // 특정 장만 뽑을 때
// PDF를 뷰어로 열어 둔 채 다시 돌리면 Windows가 파일을 잠가 EBUSY로 죽는다.
// 검수 중에는 --no-pdf로 PNG만 뽑는다.
const PDF = !process.argv.includes("--no-pdf");

(async () => {
  fs.mkdirSync(QA, { recursive: true });
  const b = await puppeteer.launch({
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    args: ["--allow-file-access-from-files", "--font-render-hinting=none",
           "--force-color-profile=srgb"],
  });
  const p = await b.newPage();
  const errs = [];
  p.on("pageerror", e => errs.push(String(e)));
  await p.setViewport({ width: 1280, height: 720, deviceScaleFactor: DSF });
  await p.goto(SRC, { waitUntil: "networkidle0" });
  if (VAR) {
    // 클래스만 바꾸면 @font-face가 그제야 내려받는다. 실제로 쓸 굵기를 지정해 로드를 기다린다.
    await p.evaluate(v => { document.documentElement.className = v === "prew" ? "pre w" : "pre"; },
      VAR);
    await p.evaluate(() => Promise.all(
      [400, 500, 700, 800].map(w => document.fonts.load(`${w} 30px "Pretendard"`))));
  }
  await p.evaluateHandle("document.fonts.ready");

  // ── 글자 넘침 검사 ──────────────────────────────────────
  const bad = await p.evaluate(() => {
    const out = [];
    for (const e of document.querySelectorAll(".slide *")) {
      if (!e.children.length || getComputedStyle(e).display === "flex") {
        if (e.scrollWidth > e.clientWidth + 1 && e.clientWidth > 0)
          out.push(`가로 넘침 ${e.scrollWidth}>${e.clientWidth}  "${e.textContent.trim().slice(0, 44)}"`);
      }
    }
    for (const s of document.querySelectorAll(".slide")) {
      if (s.scrollHeight > s.clientHeight + 1)
        out.push(`세로 넘침 ${s.id}: ${s.scrollHeight} > ${s.clientHeight}`);
      // ★ 각주는 absolute라 흐름에서 빠져 있다. 넘치지 않아도 본문이 그 위에 올라탈 수 있다.
      //   실제로 05장 결론 박스가 각주와 23px 겹쳤는데 넘침 검사는 통과했다.
      const ft = s.querySelector(".ft");
      if (!ft) continue;
      const f = ft.getBoundingClientRect();
      const flow = [...s.children].filter(e =>
        e !== ft && getComputedStyle(e).position !== "absolute");
      // 결론 문장(.say)은 각주 바로 위에 고정이라 absolute다. 흐름에서 빠져 있어도
      // 각주와 겹칠 수 있고, 위 블록이 길어지면 그 블록과도 겹친다. 둘 다 본다.
      const say = s.querySelector(".say");
      if (say) {
        const r = say.getBoundingClientRect();
        if (r.bottom > f.top + 1)
          out.push(`결론이 각주와 겹침 ${s.id}: 아래끝 ${Math.round(r.bottom)} > 각주 위끝 ${Math.round(f.top)}`);
        for (const e of flow) {
          const q = e.getBoundingClientRect();
          if (q.bottom > r.top + 1 && q.top < r.bottom)
            out.push(`결론과 겹침 ${s.id}: "${e.textContent.trim().slice(0, 26)}" 아래끝 ${Math.round(q.bottom)} > 결론 위끝 ${Math.round(r.top)}`);
        }
      }
      for (const e of flow) {
        const r = e.getBoundingClientRect();
        if (r.bottom > f.top + 1)
          out.push(`각주와 겹침 ${s.id}: "${e.textContent.trim().slice(0, 30)}" 아래끝 ${Math.round(r.bottom)} > 각주 위끝 ${Math.round(f.top)}`);
      }
      // 형제끼리도 본다. absolute 라벨(브래킷의 em)이 다음 줄 위로 올라타는 걸 놓쳤었다.
      for (let i = 0; i + 1 < flow.length; i++) {
        const a = flow[i].getBoundingClientRect(), c = flow[i + 1].getBoundingClientRect();
        // ★ overflow:hidden으로 잘려 안 보이는 부분까지 재면 안 된다.
        //   캡처 확대(.zoom)의 이미지는 상자보다 몇 배 크지만 잘려 있어 겹치지 않는다.
        const visBottom = (x) => {
          let b = x.getBoundingClientRect().bottom;
          for (let n = x.parentElement; n && n !== flow[i].parentElement; n = n.parentElement) {
            if (getComputedStyle(n).overflow !== "visible")
              b = Math.min(b, n.getBoundingClientRect().bottom);
          }
          return b;
        };
        const aBottom = Math.max(a.bottom,
          ...[...flow[i].querySelectorAll("*")].map(visBottom));
        if (aBottom > c.top + 1)
          out.push(`형제 겹침 ${s.id}: "${flow[i].textContent.trim().slice(0, 22)}" 아래끝 ${Math.round(aBottom)} > "${flow[i + 1].textContent.trim().slice(0, 22)}" 위끝 ${Math.round(c.top)}`);
      }
    }
    // 폰트가 실제로 Noto Sans KR로 잡혔는지 (안 잡히면 자간이 통째로 달라진다)
    const h = document.querySelector("h1");
    out.push(`__font: ${getComputedStyle(h).fontFamily}`);
    return out;
  });

  // ── PNG ───────────────────────────────────────────────
  const ids = await p.evaluate(() =>
    [...document.querySelectorAll(".slide")].map(s => s.id));
  for (const id of ids) {
    if (ONLY.length && !ONLY.includes(id)) continue;
    const el = await p.$("#" + id);
    if (PNG) await el.screenshot({ path: path.join(QA, `${id}${VAR ? "_" + VAR : ""}.png`) });
  }

  // 글꼴 비교판은 검수용이라 PDF까지 새로 뽑지 않는다 (배포용 PDF를 덮어쓰면 안 된다)
  if (VAR) {
    console.log(`글꼴 ${VAR} 판 — ${ONLY.length || ids.length}장`);
    console.log("\n" + bad.find(x => x.startsWith("__font")));
    const o = bad.filter(x => !x.startsWith("__font"));
    console.log(o.length ? "!! 넘침:\n  " + o.join("\n  ") : "글자 넘침 없음");
    await b.close();
    return;
  }

  // ── PDF (벡터) ────────────────────────────────────────
  if (!PDF) {
    console.log(`PNG만 ${ONLY.length || ids.length}장 (PDF 건너뜀)`);
    const o = bad.filter(x => !x.startsWith("__font"));
    console.log(bad.find(x => x.startsWith("__font")));
    console.log(o.length ? "!! 넘침: " + o.join(" / ") : "글자 넘침 없음");
    await b.close();
    return;
  }
  await p.pdf({
    path: path.join(OUT, "plan_deck.pdf"),
    width: "1280px", height: "720px",
    printBackground: true, margin: { top: 0, right: 0, bottom: 0, left: 0 },
    pageRanges: `1-${ids.length}`,
  });

  console.log(`슬라이드 ${ids.length}장`);
  const kb = f => (fs.statSync(f).size / 1024).toFixed(0);
  console.log(`  [결과물] out/plan_deck.pdf  ${kb(path.join(OUT, "plan_deck.pdf"))}KB  · 글자 벡터`);
  if (PNG) for (const f of fs.readdirSync(QA))
    console.log(`  [검수]   out/qa/${f}  ${kb(path.join(QA, f))}KB  · ${DSF}배`);
  const font = bad.find(x => x.startsWith("__font"));
  const over = bad.filter(x => !x.startsWith("__font"));
  console.log("\n" + font);
  console.log(over.length ? "!! 넘침:\n  " + over.join("\n  ") : "글자 넘침 없음");
  if (errs.length) console.log("!! 에러: " + errs.join(" / "));
  await b.close();
})();
