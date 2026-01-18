// ---------- Simple modal handling ----------
document.addEventListener("click", (e) => {
  const openBtn = e.target.closest("[data-open-modal]");
  const closeBtn = e.target.closest("[data-close-modal]");

  if (openBtn) {
    const sel = openBtn.getAttribute("data-open-modal");
    const modal = document.querySelector(sel);
    if (modal) modal.classList.add("show");
  }

  if (closeBtn) {
    const modal = closeBtn.closest(".modal");
    if (modal) modal.classList.remove("show");
  }

  // click outside card closes
  const modal = e.target.classList && e.target.classList.contains("modal") ? e.target : null;
  if (modal) modal.classList.remove("show");
});


// ---------- Slide Player ----------
(function initSlidePlayer() {
  if (!window.__SLIDE__) return;

  const slide = window.__SLIDE__;
  let idx = 0;

  const titleEl = document.getElementById("pageTitle");
  const contentEl = document.getElementById("pageContent");
  const countEl = document.getElementById("pageCount");
  const monoEl = document.getElementById("pageMono");
  const prevBtn = document.getElementById("prevBtn");
  const nextBtn = document.getElementById("nextBtn");

  function normalizePage(p) {
    if (typeof p === "string") return { title: p, content: "" };
    return p || { title: "Page", content: "" };
  }

  function render() {
    const total = slide.pages.length;
    const p = normalizePage(slide.pages[idx]);
    titleEl.textContent = p.title || "";
    contentEl.textContent = p.content || "";
    countEl.textContent = `${idx + 1}/${total}`;
    monoEl.textContent = `${idx + 1} / ${total}`;
    prevBtn.disabled = idx === 0;
    nextBtn.disabled = idx === total - 1;
  }

  prevBtn?.addEventListener("click", () => { idx = Math.max(0, idx - 1); render(); });
  nextBtn?.addEventListener("click", () => { idx = Math.min(slide.pages.length - 1, idx + 1); render(); });

  window.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") { idx = Math.max(0, idx - 1); render(); }
    if (e.key === "ArrowRight") { idx = Math.min(slide.pages.length - 1, idx + 1); render(); }
    if (e.key === "Escape") {
      // let the user use browser back or Exit
    }
  });

  render();
})();


// ---------- Game Board ----------
(async function initGameBoard() {
  if (!window.__GAME__) return;

  const game = window.__GAME__;
  const gameId = window.__GAME_ID__;
  let scoreA = (window.__SCORES__ && window.__SCORES__.scoreA) || 0;
  let scoreB = (window.__SCORES__ && window.__SCORES__.scoreB) || 0;

  const scoreAEl = document.getElementById("scoreA");
  const scoreBEl = document.getElementById("scoreB");
  const grid = document.getElementById("cardsGrid");

  const qModal = document.getElementById("qModal");
  const qBadge = document.getElementById("qBadge");
  const qTitle = document.getElementById("qTitle");
  const qAnswer = document.getElementById("qAnswer");

  const aCorrect = document.getElementById("aCorrect");
  const aWrong = document.getElementById("aWrong");
  const bCorrect = document.getElementById("bCorrect");
  const bWrong = document.getElementById("bWrong");
  const skipBtn = document.getElementById("skipBtn");
  const resetBtn = document.getElementById("resetGameBtn");

  // revealed state (client-side)
  const revealed = {};
  let currentIndex = null;

  function renderScores() {
    scoreAEl.textContent = scoreA;
    scoreBEl.textContent = scoreB;
  }

  async function saveScores() {
    await fetch(`/api/games/${encodeURIComponent(gameId)}/scores`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scoreA, scoreB })
    });
  }

  function openModalFor(index) {
    currentIndex = index;
    const item = game.questions[index];

    const type = item.type || "normal";
    if (type === "trap") {
      qBadge.className = "pill pink";
      qBadge.textContent = "⚠️ Trap!";
    } else if (type === "bonus") {
      qBadge.className = "pill";
      qBadge.textContent = "🌟 Bonus!";
    } else {
      qBadge.className = "pill";
      qBadge.textContent = `${item.points} Points`;
    }

    qTitle.textContent = item.q;
    qAnswer.textContent = item.a;

    qModal.classList.add("show");
  }

  function closeModalMarkRevealed() {
    if (currentIndex !== null) revealed[currentIndex] = true;
    qModal.classList.remove("show");
    currentIndex = null;
    renderGrid();
  }

  function renderGrid() {
    grid.innerHTML = "";
    game.questions.forEach((_, i) => {
      const btn = document.createElement("button");
      const isRev = !!revealed[i];
      btn.className = isRev ? "cardbtn disabled" : "cardbtn";
      btn.textContent = isRev ? "" : String(i + 1);
      btn.disabled = isRev;
      btn.addEventListener("click", () => openModalFor(i));
      grid.appendChild(btn);
    });
  }

  function award(team, pointsOrZero) {
    const points = pointsOrZero;
    if (team === "A") scoreA += points;
    if (team === "B") scoreB += points;
    renderScores();
    saveScores().catch(()=>{});
    closeModalMarkRevealed();
  }

  aCorrect?.addEventListener("click", () => {
    const p = game.questions[currentIndex].points;
    award("A", p);
  });
  aWrong?.addEventListener("click", () => award("A", 0));
  bCorrect?.addEventListener("click", () => {
    const p = game.questions[currentIndex].points;
    award("B", p);
  });
  bWrong?.addEventListener("click", () => award("B", 0));

  skipBtn?.addEventListener("click", () => closeModalMarkRevealed());

  resetBtn?.addEventListener("click", async () => {
    if (!confirm("รีเซ็ตคะแนนและการ์ด?")) return;
    scoreA = 0; scoreB = 0;
    for (const k of Object.keys(revealed)) delete revealed[k];
    renderScores();
    renderGrid();
    await saveScores().catch(()=>{});
  });

  // close modal button
  qModal?.addEventListener("click", (e) => {
    if (e.target === qModal) qModal.classList.remove("show");
  });

  renderScores();
  renderGrid();
})();
