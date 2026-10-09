// Poll the job status on the meeting page; reload when it finishes or fails.
(function () {
  const job = document.getElementById("job");
  if (job && ["queued", "processing"].includes(job.dataset.status)) {
    const stage = document.getElementById("stage");
    const tick = async () => {
      try {
        const r = await fetch(`/meetings/${job.dataset.id}/status`);
        const s = await r.json();
        if (s.status === "done" || s.status === "failed" || s.status === "missing") {
          location.reload();
          return;
        }
        if (stage && s.stage) stage.textContent = s.stage + "...";
      } catch (e) { /* server busy; try again */ }
      setTimeout(tick, 2000);
    };
    setTimeout(tick, 2000);
  }

  const form = document.getElementById("upload-form");
  if (form) {
    form.addEventListener("submit", () => {
      form.querySelector("button").disabled = true;
      document.getElementById("upload-note").hidden = false;
    });
  }
})();
