/* MORU 웹 데모: 서버 없이 동작하는 정적 페이지. 데이터는 data.js(가상 예시)에서 읽는다. */
(() => {
  const D = window.MORU;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem("moru:" + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("moru:" + k, JSON.stringify(v)); } catch { /* 저장 불가 환경 */ } },
  };

  const item = Object.fromEntries(D.items.map((i) => [i.id, i]));
  const dom = Object.fromEntries(D.domains.map((d) => [d.id, d]));
  const clue = {};
  D.diaries.forEach((d) => d.clues.forEach((c) => (clue[c.id] = { ...c, diary: d })));
  const R = D.results;
  const md = (iso) => { const [, m, d] = iso.split("-"); return `${+m}/${+d}`; };
  const mdKo = (iso) => { const [, m, d] = iso.split("-"); return `${+m}월 ${+d}일`; };
  const SRC = { parent: "부모 일기", caption: "AI 영상 묘사" };

  // ---------- 집계 (리포트·홈 공통) ----------
  function summary(domainId) {
    const its = D.items.filter((i) => i.domain === domainId);
    const scored = its.filter((i) => R[i.id].score !== null);
    const sum = scored.reduce((a, i) => a + R[i.id].score, 0);
    const hold = its.length - scored.length;
    return { its, scored: scored.length, hold, total: its.length, sum, avg: scored.length ? sum / scored.length : null,
      status: hold / its.length >= 0.5 ? "정보 부족" : "평가" };
  }
  const holdItems = D.items.filter((i) => R[i.id].score === null);
  const insufficient = D.domains.filter((d) => summary(d.id).status === "정보 부족");

  // ---------- 아이콘 ----------
  const I = {
    link: '<path d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>',
    home: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/>',
    book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5"/>',
    chart: '<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/>',
    check: '<rect x="3" y="3" width="18" height="18" rx="4"/><path d="M8 12l3 3 5-6"/>',
    chat: '<path d="M21 12a8 8 0 0 1-11.5 7.2L4 20l1-4.5A8 8 0 1 1 21 12z"/>',
    heart: '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>',
    flow: '<rect x="3" y="3" width="7" height="6" rx="2"/><rect x="14" y="15" width="7" height="6" rx="2"/><path d="M6.5 9v3a3 3 0 0 0 3 3h4.5"/>',
    baby: '<circle cx="12" cy="8" r="4"/><path d="M5 21a7 7 0 0 1 14 0"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    video: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/>',
    down: '<path d="M12 5v14"/><path d="M6 13l6 6 6-6"/>',
    plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
    send: '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/>',
    play: '<path d="M8 5v14l11-7z"/>',
    pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    upload: '<path d="M12 16V4"/><path d="M6 10l6-6 6 6"/><path d="M4 20h16"/>',
  };
  const icon = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${I[n]}</svg>`;

  // ---------- 공통 조각 ----------
  const pips = (s) => `<span class="pips" aria-label="${s}점">${[1, 2, 3].map((n) => `<i class="${n <= s ? "f" : ""}"></i>`).join("")}</span>`;
  const conf = (c) => `<span class="conf" title="신뢰도">신뢰도 <span class="bar"><b style="width:${Math.round(c * 100)}%"></b></span>${Math.round(c * 100)}%</span>`;
  const srcTag = (s) => `<span class="tag ${s}">${SRC[s]}</span>`;
  const SCORE_LABEL = { 3: "잘 할 수 있다", 2: "할 수 있는 편이다", 1: "하지 못하는 편이다", 0: "전혀 할 수 없다" };
  const head = (eyebrow, title, sub, right = "") => `<div class="page-head"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1>${sub ? `<p class="sub">${sub}</p>` : ""}</div>${right}</div>`;
  const foot = `<p class="foot">MORU 웹 데모 · 아이·일기·영상 묘사는 모두 가상 예시이고, 영상 원본은 싣지 않았습니다. 관찰 항목은 이해를 돕기 위해 새로 쓴 설명이며 K-DST 문항 원문이 아닙니다. 점수는 참고 평가값이며 공식 검사 결과나 진단이 아닙니다.</p>`;

  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toast.t);
    toast.t = setTimeout(() => t.classList.remove("show"), 2200);
  }

  function highlight(text, clues, notUsed = []) {
    const spans = [];
    clues.forEach((c) => { const at = text.indexOf(c.text); if (at >= 0) spans.push({ at, end: at + c.text.length, c }); });
    notUsed.forEach((n) => { const at = text.indexOf(n.text); if (at >= 0) spans.push({ at, end: at + n.text.length, n }); });
    spans.sort((a, b) => a.at - b.at);
    let out = "", pos = 0;
    for (const s of spans) {
      if (s.at < pos) continue;
      out += esc(text.slice(pos, s.at));
      const body = esc(text.slice(s.at, s.end));
      if (s.c) {
        const it = item[s.c.item];
        out += `<mark class="clue ${s.c.field}" data-clue="${s.c.id}" data-item="${s.c.item}" tabindex="0" title="${esc(dom[it.domain].short + " · " + it.text)}">${body}<sup>${dom[it.domain].short}</sup></mark>`;
      } else {
        out += `<mark class="notused" title="관련은 있지만 행동이 아니어서 근거로 쓰지 않은 문장">${body}</mark>`;
      }
      pos = s.end;
    }
    return out + esc(text.slice(pos));
  }

  // ---------- 드로어(점수 근거) ----------
  function openEvidence(itemId) {
    const it = item[itemId], r = R[itemId], d = dom[it.domain];
    const body = r.score === null
      ? `<div class="notice" style="background:var(--hold-bg);color:var(--hold-ink)">${icon("info")}<div><b>판단 보류 (정보 없음)</b><br>${esc(r.reason)}</div></div>
         ${r.near ? `<div class="quote" style="margin-top:12px"><div class="src"><span class="tag plain">근거로 쓰지 않은 문장</span></div>${esc(r.near)}</div>` : ""}
         <a class="btn primary" style="margin-top:16px" href="#/checklist">${icon("check")} 체크리스트에서 관찰하기</a>`
      : `<div class="row" style="margin-bottom:14px"><span class="score-num" style="font-size:30px">${r.score}</span><span class="muted">/ 3 · ${SCORE_LABEL[r.score]}</span><span class="grow"></span>${conf(r.conf)}</div>
         ${r.conflict ? `<div class="notice warm" style="margin-bottom:12px">${icon("info")}<div>부모 일기와 영상 묘사가 달라 출처를 비교해 보수적으로 판단했어요.</div></div>` : ""}
         <h4 class="small muted" style="margin-bottom:8px">근거 문장</h4>
         <div class="stack">${r.clues.map((cid) => { const c = clue[cid]; return `<div class="quote ${c.field}"><div class="src">${srcTag(c.field)}<span>${mdKo(c.diary.date)} (${c.diary.weekday}) 기록</span></div>${esc(c.text)}</div>`; }).join("")}</div>
         <h4 class="small muted" style="margin:16px 0 6px">판단 이유</h4>
         <p style="font-size:14px">${esc(r.reason)}</p>
         <div class="row" style="margin-top:18px"><a class="btn" href="#/clues?item=${itemId}">${icon("link")} 단서 연결에서 보기</a></div>`;
    const dr = $("#drawer");
    dr.innerHTML = `<button class="close" aria-label="닫기">×</button>
      <div class="eyebrow" style="color:${d.color}">${d.name} · ${itemId.toUpperCase()}</div>
      <h2 id="drawerTitle" style="font-size:19px;margin:2px 36px 16px 0">${esc(it.text)}</h2>${body}
      <p class="tiny muted" style="margin-top:22px">관찰 항목 설명은 새로 쓴 쉬운 문장이며 K-DST 문항 원문이 아닙니다. 점수는 참고 평가값입니다.</p>`;
    dr.hidden = false; $("#backdrop").hidden = false;
    $(".close", dr).focus();
  }
  function closeDrawer() { $("#drawer").hidden = true; $("#backdrop").hidden = true; }
  document.addEventListener("click", (e) => {
    if (e.target.closest("#drawer .close") || e.target.id === "backdrop" || (e.target.closest("#drawer a"))) closeDrawer();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

  // ---------- 화면: 단서 연결 보기 ----------
  function viewClues(params) {
    const filter = params.get("d") || "all";
    const scoredCount = D.items.length - holdItems.length;
    const clueCount = Object.keys(clue).length;
    const doms = D.domains.filter((d) => filter === "all" || d.id === filter);
    const diaries = D.diaries.filter((d) => filter === "all" || d.clues.some((c) => item[c.item].domain === filter));

    const diaryHtml = diaries.map((d) => {
      const cl = d.clues.filter((c) => filter === "all" || item[c.item].domain === filter);
      const nu = (d.notUsed || []).filter((n) => filter === "all" || item[n.item].domain === filter);
      return `<article class="card diary" data-diary="${d.id}">
        <div class="diary-head"><span class="date">${mdKo(d.date)}</span><span class="wd">${d.weekday}요일 · 생후 ${D.child.ageMonths}개월</span><span class="grow"></span><span class="tag plain">단서 ${cl.length}</span></div>
        <div class="src-label"><span class="tag parent">부모 일기</span></div>
        <p class="diary-body">${highlight(d.parent, cl.filter((c) => c.field === "parent"), nu)}</p>
        ${d.caption ? `<div class="media-box"><div class="media-title">${icon("video")}<span>${esc(d.media.title)} · ${d.media.length}</span><span class="grow"></span><span class="tag caption">AI 영상 묘사</span></div>
          <p class="diary-body" style="margin-top:6px;font-size:14.5px">${highlight(d.caption, cl.filter((c) => c.field === "caption"))}</p></div>` : ""}
      </article>`;
    }).join("") || `<div class="card pad muted">이 영역의 단서가 있는 기록이 없어요.</div>`;

    const itemsHtml = doms.map((d) => {
      const its = D.items.filter((i) => i.domain === d.id && R[i.id].score !== null);
      if (!its.length) return "";
      return `<div class="dom-block"><div class="dom-title"><span class="dot" style="background:${d.color}"></span>${d.name}<span class="muted tiny" style="font-weight:500">${its.length}개 연결</span></div>
        ${its.map((i) => { const r = R[i.id]; return `<button class="item-card" data-item="${i.id}">
          <div class="top"><span class="txt">${esc(i.text)}</span><span class="score-box">${pips(r.score)} <span class="score-num">${r.score}</span></span></div>
          <div class="meta">${conf(r.conf)}${[...new Set(r.clues.map((c) => clue[c].field))].map(srcTag).join("")}<span class="tiny muted">${md(r.date)}</span>${r.conflict ? '<span class="tag warn">출처 불일치</span>' : ""}</div>
          <div class="why">${esc(r.reason)}</div></button>`; }).join("")}</div>`;
    }).join("");

    const holds = holdItems.filter((i) => filter === "all" || i.domain === filter);
    const holdHtml = holds.length ? `<section class="hold-zone" id="holdZone">
      <div class="row"><h3>판단 보류 ${holds.length}개</h3><span class="tag hold">정보 없음</span></div>
      <p class="small" style="color:var(--hold-ink);margin-top:4px">기록에서 직접 근거를 찾지 못한 항목이에요. 점수를 주지 않고 관찰 체크리스트로 넘겼어요.</p>
      <div class="hold-list">${holds.map((i) => `<div class="hold-item"><b>${dom[i.domain].short}</b> · ${esc(i.text)}<p>${esc(R[i.id].reason)}</p></div>`).join("")}</div>
      <a class="btn primary" href="#/checklist">${icon("check")} 관찰 체크리스트로 이어 보기</a>
    </section>` : "";

    $("#main").innerHTML = `${head(`${D.period.label} · ${md(D.period.start)} ~ ${md(D.period.end)}`, "단서 연결 보기",
      "육아일기와 AI 영상 묘사에서 찾은 단서 문장이 어떤 관찰 항목으로 이어졌는지 보여 줘요. 문장이나 항목을 눌러 보세요.",
      `<a class="btn" href="#/agents">${icon("flow")} 어떻게 연결했나요?</a>`)}
      <div class="stats">
        <div class="card stat"><div class="k">이번 주 기록</div><div class="v">${D.diaries.length}<small>편 · 영상 ${D.diaries.filter((d) => d.media).length}</small></div></div>
        <div class="card stat"><div class="k">찾은 단서 문장</div><div class="v">${clueCount}<small>개</small></div></div>
        <div class="card stat"><div class="k">연결된 관찰 항목</div><div class="v">${scoredCount}<small>/ ${D.items.length}</small></div></div>
        <div class="card stat"><div class="k">판단 보류</div><div class="v" style="color:var(--hold-ink)">${holdItems.length}<small>개 → 체크리스트</small></div></div>
      </div>
      <div class="row" style="justify-content:space-between;margin-bottom:14px">
        <div class="row" role="group" aria-label="영역 필터">
          <button class="chip ${filter === "all" ? "on" : ""}" data-filter="all">전체</button>
          ${D.domains.map((d) => `<button class="chip ${filter === d.id ? "on" : ""}" data-filter="${d.id}"><span class="dot" style="background:${d.color}"></span>${d.short}</button>`).join("")}
        </div>
        <div class="legend"><span><i style="background:var(--parent-bg)"></i>부모 일기 단서</span><span><i style="background:var(--caption-bg)"></i>AI 영상 묘사 단서</span><span><i style="border-bottom:2px dashed #A79CC0;height:6px;border-radius:0"></i>근거로 쓰지 않은 문장</span></div>
      </div>
      <div class="clue-grid">
        <section aria-label="이번 주 기록" id="diaryCol">${diaryHtml}</section>
        <section class="item-panel" aria-label="연결된 관찰 항목">${itemsHtml}${holdHtml}</section>
      </div>${foot}`;

    $$("[data-filter]").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.filter === "all" ? "#/clues" : `#/clues?d=${b.dataset.filter}`; }));
    const select = (itemId, from) => {
      $$(".item-card").forEach((c) => c.classList.toggle("active", c.dataset.item === itemId));
      $$("mark.clue").forEach((m) => m.classList.toggle("active", m.dataset.item === itemId));
      $("#diaryCol").classList.toggle("dim", !!itemId);
      if (from === "mark") $(`.item-card[data-item="${itemId}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      if (from === "card") $(`mark.clue[data-item="${itemId}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    };
    $$(".item-card").forEach((c) => c.addEventListener("click", () => select(c.classList.contains("active") ? null : c.dataset.item, "card")));
    $$("mark.clue").forEach((m) => {
      m.addEventListener("click", () => select(m.dataset.item, "mark"));
      m.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(m.dataset.item, "mark"); } });
    });
    if (params.get("item")) setTimeout(() => select(params.get("item"), "card"), 50);
  }

  // ---------- 화면: 홈 ----------
  function viewHome() {
    const latest = D.diaries.slice(-3).reverse();
    $("#main").innerHTML = `${head("2026년 11월 2일 월요일", `안녕하세요, ${D.child.nickname} 보호자님`, "")}
      <section class="card home-hero">
        <div><h2>${D.period.label} 발달 리포트가 도착했어요</h2>
          <p>기록 ${D.diaries.length}편에서 관찰 항목 ${D.items.length - holdItems.length}개의 단서를 찾았어요. ${insufficient.map((d) => d.name).join(", ")} 영역은 기록이 더 필요해요.</p></div>
        <a class="btn" href="#/report">${icon("chart")} 리포트 보기</a>
      </section>
      <div class="section-title">바로가기</div>
      <div class="grid-3">
        <a class="card quick" href="#/diary/new"><div class="ic">${icon("pen")}</div><b>오늘 일기 쓰기</b><span>글과 짧은 영상을 남겨요</span></a>
        <a class="card quick" href="#/clues"><div class="ic">${icon("link")}</div><b>단서 연결 보기</b><span>기록이 어떤 항목으로 이어졌는지</span></a>
        <a class="card quick" href="#/checklist"><div class="ic">${icon("check")}</div><b>관찰 체크리스트</b><span>판단 보류 ${holdItems.length}개 · 이번 주에 살펴볼 것</span></a>
        <a class="card quick" href="#/chat"><div class="ic">${icon("chat")}</div><b>AI에게 물어보기</b><span>기록을 근거로 답해요</span></a>
        <a class="card quick" href="#/counsel"><div class="ic">${icon("heart")}</div><b>상담사 연결</b><span>기록 요약을 함께 보내요</span></a>
        <a class="card quick" href="#/agents"><div class="ic">${icon("flow")}</div><b>에이전트 흐름</b><span>MORU가 일하는 방식</span></a>
      </div>
      <div class="section-title">이번 주 영역별 참고 평가값 <a class="btn ghost small" href="#/report">자세히</a></div>
      <div class="mini-dom">${D.domains.map((d) => { const s = summary(d.id); return `<a class="card" href="#/report" style="text-decoration:none"><b style="color:${d.color}">${d.short}</b>
        <div class="v">${s.status === "정보 부족" ? '<span class="tag warn">정보 부족</span>' : s.avg.toFixed(1)}</div><span class="tiny muted">${s.scored}/${s.total} 항목 평가</span></a>`; }).join("")}</div>
      <div class="section-title">최근 기록 <a class="btn ghost small" href="#/diary">전체 보기</a></div>
      <div>${latest.map(diaryListItem).join("")}</div>${foot}`;
  }

  // ---------- 화면: 육아일기 ----------
  function diaryListItem(d) {
    const [, m, day] = d.date.split("-");
    return `<article class="card list-item"><div class="date-badge"><b>${+day}</b><span>${+m}월 · ${d.weekday}</span></div>
      <div><p>${esc(d.parent)}</p>
      ${d.media ? `<div class="row" style="margin-top:8px"><span class="tag caption">${icon("video").replace("<svg", '<svg style="width:13px;height:13px"')} ${esc(d.media.title)} ${d.media.length}</span>${d.clues ? `<span class="tag plain">단서 ${d.clues.length}</span>` : ""}</div>` : (d.clues ? `<div class="row" style="margin-top:8px"><span class="tag plain">단서 ${d.clues.length}</span></div>` : "")}
      ${d.caption ? `<details class="cap"><summary>${icon("down").replace("<svg", '<svg style="width:13px;height:13px"')} AI 영상 묘사 보기</summary><p>${esc(d.caption)}</p></details>` : ""}
      </div></article>`;
  }
  function viewDiary(params) {
    const tab = params.get("w") || "this";
    const list = tab === "this" ? [...D.diaries].reverse() : D.pastDiaries;
    $("#main").innerHTML = `${head("육아일기", "기록 목록", "일기 1편과 첨부 영상의 AI 묘사가 하나의 기록으로 저장돼요.", `<a class="btn primary" href="#/diary/new">${icon("plus")} 일기 쓰기</a>`)}
      <div class="row" style="margin-bottom:14px"><div class="tabs" role="tablist">
        <button role="tab" class="${tab === "this" ? "on" : ""}" data-w="this">이번 주 (${md(D.period.start)}~${md(D.period.end)})</button>
        <button role="tab" class="${tab === "prev" ? "on" : ""}" data-w="prev">지난주 (${md(D.prevPeriod.start)}~${md(D.prevPeriod.end)})</button></div></div>
      <div>${list.map(diaryListItem).join("")}</div>${foot}`;
    $$("[data-w]").forEach((b) => b.addEventListener("click", () => { location.hash = `#/diary?w=${b.dataset.w}`; }));
  }
  function viewDiaryNew() {
    $("#main").innerHTML = `${head("육아일기", "일기 쓰기", "있었던 일을 편하게 적어 주세요. 행동이 구체적일수록 단서를 잘 찾아요.")}
      <div class="grid-2" style="align-items:start">
        <form class="card pad form" id="diaryForm">
          <div class="field"><label for="dDate">날짜</label><input class="input" id="dDate" type="date" value="2026-11-02"></div>
          <div class="field"><label for="dText">오늘의 기록</label>
            <textarea class="input" id="dText" placeholder="예) 놀이터에서 미끄럼틀 계단을 손잡고 올라갔다. 내려와서는 '또!' 하고 다시 가리켰다."></textarea>
            <div class="hint" id="dCount">0자</div></div>
          <div class="field"><label>영상 첨부 (선택)</label>
            <div class="drop">${icon("upload")}10~30초 영상이면 충분해요<br><span class="tiny">데모에서는 업로드되지 않습니다</span></div></div>
          <div class="row"><button class="btn primary" type="submit">저장하기</button><a class="btn" href="#/diary">취소</a></div>
        </form>
        <aside class="stack">
          <div class="card pad"><h3 style="font-size:15px;margin-bottom:8px">이렇게 쓰면 좋아요</h3>
            <ul class="small" style="margin:0;padding-left:18px;color:var(--ink-2)">
              <li>"잘한다"보다 <b>무엇을 어떻게 했는지</b> 적어 주세요.</li>
              <li>"어제"처럼 쓰셔도 괜찮아요. 기록 날짜를 기준으로 처리해요.</li>
              <li>못 했던 일, 도와줬던 일도 그대로 적어 주세요.</li></ul></div>
          <div class="notice">${icon("info")}<div>영상은 <b>캡션 에이전트</b>가 행동 묘사 문장으로 바꿔 저장해요. 이때 일기 내용은 보지 않아서, 부모 서술과 영상 묘사를 따로 비교할 수 있어요.</div></div>
          <div class="notice warm">${icon("info")}<div>아이 얼굴이 나오는 영상은 리포트에 쓰지 않고, 묘사 문장만 보여 드려요.</div></div>
        </aside>
      </div>${foot}`;
    $("#dText").addEventListener("input", (e) => ($("#dCount").textContent = `${e.target.value.length}자`));
    $("#diaryForm").addEventListener("submit", (e) => { e.preventDefault(); toast("데모에서는 저장되지 않아요. 화면 구성만 보여 드려요."); });
  }

  // ---------- 화면: 발달 리포트 ----------
  function viewReport() {
    const cards = D.domains.map((d) => {
      const s = summary(d.id), p = D.prevSummary[d.id];
      const prevInsuff = (4 - p.scored) / 4 >= 0.5;
      let change = "";
      if (s.status === "정보 부족") change = `<span class="tag warn">정보 부족 · 보류 ${s.hold}/${s.total}</span>`;
      else if (prevInsuff) change = `<span class="tag ok">지난주 정보 부족 → 평가</span>`;
      else { const diff = s.avg - p.avg; change = `<span class="tag ${Math.abs(diff) < 0.25 ? "plain" : "ok"}">지난주 ${p.avg.toFixed(1)} → ${s.avg.toFixed(1)}</span>`; }
      return `<article class="card dom-card">
        <div class="head"><span class="dot" style="width:10px;height:10px;border-radius:3px;background:${d.color}"></span><h3>${d.name}</h3><span class="grow"></span>${change}</div>
        <div class="val"><b>${s.avg === null ? "-" : s.avg.toFixed(2)}</b><span class="muted small">/ 3 · ${s.scored}개 항목 평가${s.status === "정보 부족" ? " (참고만)" : ""}</span></div>
        <div class="meter"><b style="width:${s.avg === null ? 0 : (s.avg / 3) * 100}%;background:${s.status === "정보 부족" ? "#C9BFD9" : d.color}"></b>${prevInsuff ? "" : `<span class="prev" style="left:${(p.avg / 3) * 100}%" title="지난주"></span>`}</div>
        <div class="score-list">${s.its.map((i) => { const r = R[i.id]; return `<button class="score-row" data-ev="${i.id}"><span class="t">${esc(i.text)}</span>${r.score === null ? '<span class="score-pill hold">정보 없음</span>' : `<span class="score-pill">${r.score}점</span>`}</button>`; }).join("")}</div>
      </article>`;
    }).join("");
    $("#main").innerHTML = `${head(`${D.period.label} · ${md(D.period.start)} ~ ${md(D.period.end)}`, "발달 리포트", "점수를 누르면 근거 문장, 날짜, 출처를 볼 수 있어요.",
      `<div class="row"><span class="tag plain">${D.child.sheet} 관찰 항목 기준</span><a class="btn" href="#/clues">${icon("link")} 단서 연결</a></div>`)}
      <section class="card opinion">
        <div class="row" style="margin-bottom:10px"><h3 style="font-size:16px">종합 소견</h3><span class="tag plain">리포트 에이전트</span></div>
        ${D.report.opinion.map((p) => `<p>${esc(p)}</p>`).join("")}
        <div class="notice" style="margin-top:14px">${icon("info")}<div>${esc(D.report.nextWeek)}</div></div>
      </section>
      <div class="row" style="margin:18px 0 12px;justify-content:space-between"><h2 style="font-size:17px">영역별 참고 평가값</h2>
        <div class="legend"><span><i style="background:var(--primary)"></i>이번 주</span><span><i style="width:2px;height:12px;background:var(--ink);opacity:.45"></i>지난주</span></div></div>
      <div class="grid-3" style="align-items:start">${cards}</div>
      <div class="notice warm" style="margin-top:18px">${icon("info")}<div>판단 보류(정보 없음) 항목이 절반 이상인 영역은 <b>정보 부족</b>으로 표시해요. 기록이 부족하다는 뜻이지 발달이 늦다는 뜻이 아니에요. 점수는 참고 평가값이며 공식 K-DST 결과나 진단이 아니에요.</div></div>${foot}`;
    $$("[data-ev]").forEach((b) => b.addEventListener("click", () => openEvidence(b.dataset.ev)));
  }

  // ---------- 화면: 관찰 체크리스트 ----------
  function viewChecklist() {
    const done = store.get("checks", {});
    const all = D.checklist.flatMap((g) => g.behaviors.map((b) => b.item));
    const render = () => {
      const n = all.filter((id) => done[id]).length;
      $("#main").innerHTML = `${head("이번 주에 살펴볼 것", "관찰 체크리스트", "기록에서 근거를 찾지 못한 항목을 바탕으로 만들었어요. 새로 검색하지 않고 판단 보류 항목과 월령만 사용해요.")}
        <div class="card pad" style="margin-bottom:16px"><div class="row" style="margin-bottom:8px"><b>${n} / ${all.length} 관찰함</b><span class="grow"></span><span class="tiny muted">관찰한 뒤 일기로 남기면 다음 리포트에 반영돼요</span></div>
          <div class="progress"><b style="width:${(n / all.length) * 100}%"></b></div></div>
        ${D.checklist.map((g) => { const d = dom[g.domain]; return `<section class="card check-dom">
          <div class="row" style="margin-bottom:6px"><span class="dot" style="width:10px;height:10px;border-radius:3px;background:${d.color}"></span><h3 style="font-size:16px">${d.name}</h3>
            <span class="tag ${g.reasonTag === "정보 부족 영역" ? "warn" : "hold"}">${g.reasonTag}</span></div>
          ${g.reasonTag === "정보 부족 영역" ? `<p class="small muted" style="margin-bottom:4px">조율 규칙 ①: 판단 보류가 절반 이상이라 대표 관찰 행동 ${g.behaviors.length}개를 골랐어요.</p>` : ""}
          ${g.behaviors.map((b) => `<label class="check ${done[b.item] ? "done" : ""}"><input type="checkbox" data-c="${b.item}" ${done[b.item] ? "checked" : ""}>
            <div><div class="obs">${esc(b.observe)}</div><div class="play">🧸 <span>${esc(b.play)}</span></div>
            <div class="from">관련 항목: ${esc(item[b.item].text)} · 판단 보류</div></div></label>`).join("")}
          <div class="row" style="margin-top:8px"><a class="btn ghost small" href="#/diary/new">${icon("pen")} 관찰한 내용 기록하기</a></div>
        </section>`; }).join("")}${foot}`;
      $$("[data-c]").forEach((c) => c.addEventListener("change", () => { done[c.dataset.c] = c.checked; store.set("checks", done); render(); }));
    };
    render();
  }

  // ---------- 화면: AI 채팅 ----------
  const chatLog = [];
  function viewChat() {
    $("#main").innerHTML = `${head("AI 채팅", "기록에게 물어보기", "아이의 기록만 근거로, 날짜와 출처를 밝혀 답해요. 기록에 없는 내용은 없다고 말해요.")}
      <section class="card chat-wrap">
        <div class="chat-log" id="log" aria-live="polite"></div>
        <div class="chat-input">
          <div class="suggest">${D.chat.map((c, i) => `<button class="chip" data-q="${i}">${esc(c.q)}</button>`).join("")}</div>
          <form class="chat-form" id="chatForm"><input class="input" id="chatIn" placeholder="예시 질문을 누르거나 직접 입력해 보세요" autocomplete="off"><button class="btn primary" type="submit" aria-label="보내기">${icon("send")}</button></form>
        </div>
      </section>${foot}`;
    const log = $("#log");
    const bubble = (m) => m.me
      ? `<div class="msg me">${esc(m.text)}</div>`
      : `<div class="msg bot"><div>${esc(m.text)}</div>
        ${m.cites && m.cites.length ? `<div class="cites">${m.cites.map((c) => `<div class="cite"><div class="row">${srcTag(c.source)}<span class="tiny muted">${mdKo(c.date)} 기록</span></div>"${esc(c.quote)}"</div>`).join("")}</div>` : ""}
        ${m.noev ? `<div class="noev"><span class="tag hold">관련 기록 없음</span></div>` : ""}
        ${m.link ? `<a class="btn ghost small" style="margin-top:6px;padding-left:0" href="${m.link.to}">${esc(m.link.label)} →</a>` : ""}</div>`;
    const draw = () => {
      log.innerHTML = `<div class="msg bot">안녕하세요! ${D.child.nickname}의 ${md(D.prevPeriod.start)}~${md(D.period.end)} 기록 ${D.diaries.length + D.pastDiaries.length}편을 바탕으로 답해 드려요. 저는 진단을 하지 않고, 기록에 적힌 내용만 이야기해요.</div>` + chatLog.map(bubble).join("");
      log.scrollTop = log.scrollHeight;
    };
    const ask = (text) => {
      if (!text.trim()) return;
      chatLog.push({ me: true, text });
      draw();
      log.insertAdjacentHTML("beforeend", '<div class="msg bot" id="typing"><span class="typing"><i></i><i></i><i></i></span></div>');
      log.scrollTop = log.scrollHeight;
      const hit = D.chat.find((c) => c.q === text) || D.chat.find((c) => c.keys.some((k) => text.includes(k)));
      setTimeout(() => {
        chatLog.push(hit ? { text: hit.a, cites: hit.cites, noev: !hit.cites.length, link: hit.link }
          : { text: "이 데모에서는 아래 예시 질문에만 답할 수 있어요. 실제 서비스에서는 질문으로 기록을 검색한 뒤, 찾은 기록만 근거로 답하고 관련 기록이 없으면 없다고 말해요.", noev: true });
        draw();
      }, 750);
    };
    $$("[data-q]").forEach((b) => b.addEventListener("click", () => ask(D.chat[+b.dataset.q].q)));
    $("#chatForm").addEventListener("submit", (e) => { e.preventDefault(); const v = $("#chatIn").value; $("#chatIn").value = ""; ask(v); });
    draw();
  }

  // ---------- 화면: 상담사 연결 ----------
  function viewCounsel() {
    const C = D.counsel, d = dom[C.domain];
    $("#main").innerHTML = `${head("상담사 연결", "상담 전에 기록을 정리했어요", "상담 요약 에이전트가 기록에서 관찰 사실만 모았어요. 보낼 내용을 확인하고 상담사를 고르세요.")}
      <div class="grid-2" style="align-items:start">
        <section class="card pad">
          <div class="row" style="margin-bottom:6px"><span class="dot" style="width:10px;height:10px;border-radius:3px;background:${d.color}"></span><h3 style="font-size:17px">${d.name} 관찰 요약</h3><span class="grow"></span><span class="tag plain">상담 요약 에이전트</span></div>
          <p class="tiny muted" style="margin-bottom:12px">${esc(C.period)} · ${esc(C.trigger)}</p>
          <p style="font-size:14.5px">${esc(C.summary)}</p>
          <hr class="sep">
          <h4 class="small muted" style="margin-bottom:8px">참고 평가값</h4>
          <div class="score-list" style="margin-top:0">${C.scores.map((s) => `<button class="score-row" data-ev="${s.item}"><span class="t">${esc(item[s.item].text)}</span>${s.score === null ? '<span class="score-pill hold">정보 없음</span>' : `<span class="score-pill">${s.score}점 · ${md(s.date)}</span>`}</button>`).join("")}</div>
          <h4 class="small muted" style="margin:16px 0 8px">근거 기록</h4>
          <div class="stack">${C.observations.map((o) => `<div class="quote ${o.source}"><div class="src">${srcTag(o.source)}<span>${mdKo(o.date)} 기록</span></div>${esc(o.quote)}</div>`).join("")}</div>
          <h4 class="small muted" style="margin:16px 0 6px">상담에서 확인해 볼 점</h4>
          <ul style="margin:0;padding-left:18px;font-size:14px">${C.questions.map((q) => `<li>${esc(q)}</li>`).join("")}</ul>
          <div class="notice warm" style="margin-top:14px">${icon("info")}<div><b>요약의 한계</b><br>${esc(C.limitations)}</div></div>
        </section>
        <aside class="stack">
          <section class="card pad">
            <h3 style="font-size:15px;margin-bottom:10px">함께 보낼 내용</h3>
            <div class="share-list">
              <label><input type="checkbox" checked> 언어 영역 관찰 요약과 근거 기록 4개</label>
              <label><input type="checkbox" checked> 최근 2주 영역별 참고 평가값</label>
              <label><input type="checkbox"> 일기 원문 전체 (12편)</label>
              <label><input type="checkbox" disabled> 영상 원본 <span class="tiny muted">— 보내지 않아요</span></label>
            </div>
          </section>
          <section>
            <h3 style="font-size:15px;margin:4px 2px 10px">상담사 선택</h3>
            ${C.counselors.map((c, i) => `<button class="card counselor" style="width:100%;text-align:left" data-cs="${i}"><span class="ic">${icon("heart")}</span>
              <span class="grow"><b style="display:block;font-size:14.5px">${esc(c.name)} <span class="tag plain">가상</span></b><span class="tiny muted">${esc(c.kind)} · ${esc(c.place)}</span></span>
              <span class="tiny" style="text-align:right">가장 빠른 시간<br><b>${esc(c.next)}</b></span></button>`).join("")}
          </section>
          <button class="btn primary" id="book" style="width:100%;padding:12px">요약 보내고 예약 요청하기</button>
          <p class="tiny muted">상담사 연결(예약·전송)은 구현하지 않은 기획 기능이에요. 이 화면은 흐름만 보여 줘요.</p>
        </aside>
      </div>${foot}`;
    $$("[data-ev]").forEach((b) => b.addEventListener("click", () => openEvidence(b.dataset.ev)));
    $$("[data-cs]").forEach((b) => b.addEventListener("click", () => { $$("[data-cs]").forEach((x) => x.classList.toggle("sel", x === b)); }));
    $("#book").addEventListener("click", () => toast("데모에서는 예약과 전송이 동작하지 않아요."));
  }

  // ---------- 화면: 에이전트 흐름 ----------
  function viewAgents(params) {
    const A = Object.fromEntries(D.agents.map((a) => [a.id, a]));
    const sel = params.get("a") || "score";
    const box = (id) => { const a = A[id]; return `<button class="agent ${id === "aggregate" ? "rule" : ""} ${id === sel ? "sel" : ""}" data-a="${id}"><b>${a.name}</b><span>${esc(a.when)}</span><br><span class="llm ${a.llm.startsWith("Gemini") ? "on" : ""}">${esc(a.llm)}</span></button>`; };
    const arrow = `<div class="flow-arrow">${icon("down")}</div>`;
    const a = A[sel];
    $("#main").innerHTML = `${head("MORU가 일하는 방식", "에이전트 흐름 보기", "역할을 나눈 에이전트가 고정된 순서와 규칙(if 문)으로 이어져요. 각 에이전트는 자기 역할에 필요한 정보만 받아요. 스스로 계획을 세우는 자율 에이전트는 아니에요.",
      `<button class="btn primary" id="run">${icon("play")} 이번 주 흐름 재생</button>`)}
      <div class="grid-2" style="grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);align-items:start">
        <section class="card pad">
          <div class="flow">
            <div class="flow-row" style="--n:2">${box("caption")}${box("index")}</div>${arrow}
            <div class="flow-row" style="--n:1">${box("retrieve")}</div>${arrow}
            <div class="flow-row" style="--n:1">${box("score")}</div>${arrow}
            <div class="flow-row" style="--n:1">${box("aggregate")}</div>${arrow}
            <div class="flow-row" style="--n:3">${box("report")}${box("checklist")}${box("counsel")}</div>
          </div>
          <div class="side-branch">${box("chat")}<div class="notice" style="font-size:12.5px">${icon("info")}<div>채팅·상담 요약은 채점과 <b>같은 검색 모듈</b>을 다시 써요.</div></div></div>
          <p class="tiny muted" style="margin-top:14px">실제 파이프라인은 월령 검사지의 모든 문항(18~19개월: 6개 영역 48문항)을 쓰고, 이 데모는 영역당 4개 관찰 항목만 보여 줘요.</p>
        </section>
        <section class="card pad" id="detail">
          <div class="row" style="margin-bottom:12px"><h2 style="font-size:19px">${a.name}</h2><span class="grow"></span><span class="tag plain">${esc(a.when)}</span></div>
          <div class="detail-grid" style="margin-bottom:14px">
            <div class="kv"><div><h4>받는 정보</h4><ul>${a.gets.map((g) => `<li>${esc(g)}</li>`).join("")}</ul></div></div>
            <div class="kv"><div><h4>받지 않는 정보</h4>${a.not.length ? `<ul class="no">${a.not.map((g) => `<li>${esc(g)}</li>`).join("")}</ul>` : '<p class="small muted">-</p>'}</div></div>
          </div>
          <div class="kv" style="margin-bottom:14px"><div><h4>출력</h4><p style="font-size:13.5px;font-family:ui-monospace,Menlo,monospace">${esc(a.out)}</p></div></div>
          <h4 class="small muted" style="margin-bottom:6px">입력 컨텍스트 (예시)</h4>
          <pre class="code">${esc(a.input)}</pre>
          <h4 class="small muted" style="margin:14px 0 6px">출력 (예시)</h4>
          <pre class="code">${esc(a.output)}</pre>
        </section>
      </div>
      <div class="grid-3" style="margin-top:16px">
        <div class="card pad"><b>조율 규칙 ①</b><p class="small muted" style="margin-top:4px">판단 보류가 절반 이상인 '정보 부족' 영역이 있으면 → 체크리스트 에이전트</p><p class="small" style="margin-top:8px">이번 주: <b>${insufficient.map((d) => d.name).join(", ") || "없음"}</b> → 호출함</p></div>
        <div class="card pad"><b>조율 규칙 ②</b><p class="small muted" style="margin-top:4px">0~1점 문항이 있는 영역이 2주 연속이면 → 상담 요약 에이전트</p><p class="small" style="margin-top:8px">이번 주: 해당 없음 (상담 요약은 보호자 요청으로 생성)</p></div>
        <div class="card pad"><b>판단 보류 원칙</b><p class="small muted" style="margin-top:4px">직접 근거가 없으면 점수를 주지 않아요. 채점·채팅·상담 요약이 같은 원칙을 따라요.</p><p class="small" style="margin-top:8px">이번 주: <b>${holdItems.length}개</b> 판단 보류</p></div>
      </div>${foot}`;
    $$("[data-a]").forEach((b) => b.addEventListener("click", () => { location.hash = `#/agents?a=${b.dataset.a}`; }));
    $("#run").addEventListener("click", () => {
      const order = ["caption", "index", "retrieve", "score", "aggregate", "report", "checklist"];
      const msgs = ["영상 7개 → 행동 묘사 7개", "기록 7편 → 청크 7개", `관찰 항목 ${D.items.length}개 × top-3 검색`, `${D.items.length - holdItems.length}개 채점 · ${holdItems.length}개 판단 보류`, `${insufficient.map((d) => d.short).join(", ")} 정보 부족 → 체크리스트 호출`, "종합 소견 작성", "관찰 행동 생성"];
      $$(".agent").forEach((x) => x.classList.remove("lit"));
      order.forEach((id, i) => setTimeout(() => { $(`.agent[data-a="${id}"]`)?.classList.add("lit"); toast(`${A[id].name}: ${msgs[i]}`); }, i * 900));
    });
  }

  // ---------- 화면: 아이 등록 ----------
  function viewRegister() {
    $("#main").innerHTML = `${head("시작하기", "아이 등록", "월령에 맞는 관찰 항목을 고르기 위해 생년월일이 필요해요. 이름은 화면 표시용이며 AI 분석에는 쓰지 않아요.")}
      <div class="grid-2" style="align-items:start">
        <form class="card pad form" id="regForm">
          <div class="steps"><span class="on"></span><span class="on"></span><span></span></div>
          <div class="field"><label for="rName">부르는 이름</label><input class="input" id="rName" value="${esc(D.child.nickname)}"><div class="hint">애칭도 괜찮아요. AI에게는 전달되지 않아요.</div></div>
          <div class="field"><label for="rBirth">생년월일</label><input class="input" id="rBirth" type="date" value="${D.child.birth}"><div class="hint" id="rAge"></div></div>
          <div class="field"><label>출생 주수</label><div class="seg">
            <label><input type="radio" name="term" checked><span>만삭 (37주 이상)</span></label>
            <label><input type="radio" name="term"><span>조산 (37주 미만)</span></label></div>
            <div class="hint">조산이면 교정 월령으로 관찰 항목을 골라요.</div></div>
          <div class="field"><label>보호자 관계</label><div class="seg">
            <label><input type="radio" name="rel" checked><span>엄마</span></label><label><input type="radio" name="rel"><span>아빠</span></label><label><input type="radio" name="rel"><span>그 외 보호자</span></label></div></div>
          <div class="card" style="padding:4px 14px;box-shadow:none;background:var(--surface-2)">
            <div class="switch"><div class="grow"><b>AI 분석 동의 (필수)</b><span>일기와 영상 묘사로 관찰 항목의 근거를 찾는 데 동의해요.</span></div><label class="toggle"><input type="checkbox" checked><i></i></label></div>
            <div class="switch"><div class="grow"><b>영상 원본 보관</b><span>끄면 행동 묘사 문장만 남기고 영상은 분석 후 지워요.</span></div><label class="toggle"><input type="checkbox"><i></i></label></div>
          </div>
          <div class="row"><button class="btn primary" type="submit">등록하고 시작하기</button></div>
        </form>
        <aside class="stack">
          <div class="card pad"><div class="row" style="gap:12px"><span class="avatar" style="width:52px;height:52px;font-size:20px" id="rAvatar">${esc(D.child.nickname[0])}</span>
            <div><b style="font-size:17px" id="rPreview">${esc(D.child.nickname)}</b><div class="small muted" id="rSheet"></div></div></div>
            <hr class="sep"><p class="small" style="color:var(--ink-2)">MORU는 부모님의 기록에서 <b>근거가 있을 때만</b> 참고 평가값을 보여 드려요. 기록이 없는 항목은 "정보 없음"으로 남기고, 관찰해 볼 방법을 알려 드려요.</p></div>
          <div class="notice">${icon("info")}<div>MORU는 진단 도구가 아니에요. 걱정되는 점이 있으면 영유아 건강검진이나 전문가 상담을 함께 이용해 주세요.</div></div>
        </aside>
      </div>${foot}`;
    const upd = () => {
      const b = new Date($("#rBirth").value), now = new Date("2026-11-02");
      const m = (now.getFullYear() - b.getFullYear()) * 12 + now.getMonth() - b.getMonth() - (now.getDate() < b.getDate() ? 1 : 0);
      const ok = Number.isFinite(m) && m >= 0;
      $("#rAge").textContent = ok ? `오늘 기준 생후 ${m}개월` : "";
      $("#rSheet").textContent = ok ? `생후 ${m}개월 · ${m >= 18 && m <= 19 ? "18~19개월" : "월령별"} 관찰 항목 사용` : "";
      const n = $("#rName").value.trim() || "아이";
      $("#rPreview").textContent = n; $("#rAvatar").textContent = n[0];
    };
    $("#rBirth").addEventListener("input", upd); $("#rName").addEventListener("input", upd); upd();
    $("#regForm").addEventListener("submit", (e) => { e.preventDefault(); toast("데모에서는 등록되지 않아요. 홈으로 이동할게요."); setTimeout(() => (location.hash = "#/home"), 900); });
  }

  // ---------- 화면: 설정 ----------
  function viewSettings() {
    const sw = (t, s, on) => `<div class="switch"><div class="grow"><b>${t}</b><span>${s}</span></div><label class="toggle"><input type="checkbox" ${on ? "checked" : ""}><i></i></label></div>`;
    $("#main").innerHTML = `${head("설정", "설정", "")}
      <div class="grid-2" style="align-items:start">
        <div class="stack">
          <section class="card pad"><h3 style="font-size:15px;margin-bottom:10px">아이 정보</h3>
            <div class="row" style="gap:12px"><span class="avatar" style="width:44px;height:44px">${esc(D.child.nickname[0])}</span><div class="grow"><b>${esc(D.child.nickname)}</b><div class="small muted">${D.child.birth} 출생 · 생후 ${D.child.ageMonths}개월 · ${D.child.sheet} 관찰 항목</div></div><a class="btn" href="#/register">수정</a></div></section>
          <section class="card pad"><h3 style="font-size:15px;margin-bottom:4px">알림</h3>
            ${sw("주간 리포트 알림", "매주 월요일 아침에 지난주 리포트를 알려 드려요.", true)}
            ${sw("체크리스트 알림", "정보 부족 영역이 있을 때 관찰할 거리를 알려 드려요.", true)}
            ${sw("일기 쓰기 알림", "저녁 9시에 오늘 기록을 남기도록 알려 드려요.", false)}</section>
        </div>
        <div class="stack">
          <section class="card pad"><h3 style="font-size:15px;margin-bottom:4px">데이터와 개인정보</h3>
            ${sw("영상 원본 보관", "끄면 행동 묘사 문장만 남기고 영상은 분석 후 지워요.", false)}
            ${sw("AI 분석에 이름 보내지 않기", "이름 대신 월령과 기록만 사용해요. (항상 켜짐)", true)}
            <div class="row" style="margin-top:10px"><button class="btn" data-t="데모에서는 내보내기가 동작하지 않아요.">기록 내보내기</button><button class="btn" style="color:var(--warn)" data-t="데모에서는 삭제가 동작하지 않아요.">모든 기록 삭제</button></div></section>
          <section class="card pad"><h3 style="font-size:15px;margin-bottom:8px">MORU 정보</h3>
            <dl class="small" style="display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin:0">
              <dt class="muted">분석 모델</dt><dd style="margin:0">Gemini 3.6 Flash (캡션·채점·리포트·체크리스트)</dd>
              <dt class="muted">검색</dt><dd style="margin:0">KURE-v2 + Qdrant (토큰 단위 유사도)</dd>
              <dt class="muted">점수</dt><dd style="margin:0">참고 평가값 · 공식 검사 결과나 진단이 아님</dd>
              <dt class="muted">버전</dt><dd style="margin:0">캡스톤 데모 (가상 데이터)</dd></dl></section>
        </div>
      </div>${foot}`;
    $$("[data-t]").forEach((b) => b.addEventListener("click", () => toast(b.dataset.t)));
  }

  // ---------- 라우팅 ----------
  const NAV = [
    ["clues", "단서 연결 보기", "link"], ["home", "홈", "home"], ["diary", "육아일기", "book"], ["report", "발달 리포트", "chart"],
    ["checklist", "관찰 체크리스트", "check", holdItems.length], ["chat", "AI 채팅", "chat"], ["counsel", "상담사 연결", "heart"],
    ["|", "MORU 안쪽"], ["agents", "에이전트 흐름 보기", "flow"], ["|", "계정"], ["register", "아이 등록", "baby"], ["settings", "설정", "gear"],
  ];
  const VIEWS = { clues: viewClues, home: viewHome, diary: viewDiary, "diary/new": viewDiaryNew, report: viewReport, checklist: viewChecklist, chat: viewChat, counsel: viewCounsel, agents: viewAgents, register: viewRegister, settings: viewSettings };

  $("#childChip").innerHTML = `<span class="avatar">${esc(D.child.nickname[0])}</span><div><b>${esc(D.child.nickname)}</b><span>생후 ${D.child.ageMonths}개월 · ${D.child.sheet}</span></div>`;
  function route() {
    const [path, qs] = (location.hash.replace(/^#\/?/, "") || "clues").split("?");
    const key = VIEWS[path] ? path : "clues";
    const navKey = key.split("/")[0];
    $("#nav").innerHTML = NAV.map(([id, label, ic, badge]) => id === "|" ? `<div class="group">${label}</div>`
      : `<a href="#/${id}" class="${id === navKey ? "on" : ""}" ${id === navKey ? 'aria-current="page"' : ""}>${icon(ic)}<span>${label}</span>${badge ? `<span class="badge">${badge}</span>` : ""}</a>`).join("");
    closeDrawer();
    VIEWS[key](new URLSearchParams(qs || ""));
    document.title = `${NAV.find((n) => n[0] === navKey)?.[1] || "MORU"} · MORU 데모`;
    $("#nav a.on")?.scrollIntoView({ block: "nearest", inline: "center" });
    if (!qs || !qs.includes("item")) window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);
  route();
})();
