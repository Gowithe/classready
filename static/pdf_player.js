import * as pdfjsLib from "/static/vendor/pdfjs/build/pdf.mjs";
pdfjsLib.GlobalWorkerOptions.workerSrc = "/static/vendor/pdfjs/build/pdf.worker.mjs";

(async function () {
  const url = window.__PDF_URL__;
  if (!url) return;

  const canvas = document.getElementById("pdfCanvas");
  const ctx = canvas?.getContext("2d");

  const pageCountEl = document.getElementById("pageCount");
  const pageMonoEl = document.getElementById("pageMono");
  const prevBtn = document.getElementById("prevBtn");
  const nextBtn = document.getElementById("nextBtn");
  const fsBtn = document.getElementById("fsBtn");

  if (!canvas || !ctx) {
    console.error("pdfCanvas not found");
    return;
  }

  let pdfDoc = null;
  let pageNum = 1;
  let totalPages = 1;
  let rendering = false;

  function setButtons() {
    if (prevBtn) prevBtn.disabled = pageNum <= 1;
    if (nextBtn) nextBtn.disabled = pageNum >= totalPages;
    if (pageCountEl) pageCountEl.textContent = `${pageNum}/${totalPages}`;
    if (pageMonoEl) pageMonoEl.textContent = `${pageNum} / ${totalPages}`;
  }

  async function renderPage(num) {
    if (!pdfDoc || rendering) return;
    rendering = true;

    const page = await pdfDoc.getPage(num);
    const containerWidth = Math.min(1100, window.innerWidth - 40);

    const viewport1 = page.getViewport({ scale: 1 });
    const scale = containerWidth / viewport1.width;
    const viewport = page.getViewport({ scale });

    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);

    await page.render({ canvasContext: ctx, viewport }).promise;

    rendering = false;
    setButtons();
  }

  try {
    pdfDoc = await pdfjsLib.getDocument(url).promise;
    totalPages = pdfDoc.numPages;
    setButtons();
    await renderPage(pageNum);
  } catch (err) {
    console.error("PDF load error:", err);
    alert("❌ โหลด PDF ไม่สำเร็จ (ดู Console)");
    return;
  }

  if (prevBtn) {
    prevBtn.onclick = async () => {
      if (pageNum <= 1) return;
      pageNum--;
      await renderPage(pageNum);
    };
  }

  if (nextBtn) {
    nextBtn.onclick = async () => {
      if (pageNum >= totalPages) return;
      pageNum++;
      await renderPage(pageNum);
    };
  }

  window.addEventListener("keydown", async (e) => {
    if (e.key === "ArrowLeft" && pageNum > 1) {
      pageNum--;
      await renderPage(pageNum);
    }
    if (e.key === "ArrowRight" && pageNum < totalPages) {
      pageNum++;
      await renderPage(pageNum);
    }
  });

  window.addEventListener("resize", async () => {
    await renderPage(pageNum);
  });

  if (fsBtn) {
    fsBtn.onclick = async () => {
      if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen?.();
      } else {
        await document.exitFullscreen?.();
      }
      setTimeout(() => renderPage(pageNum), 200);
    };
  }
})();
