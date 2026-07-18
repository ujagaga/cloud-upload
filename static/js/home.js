document.addEventListener('DOMContentLoaded', function () {
  const cardStatus = document.getElementById('card_status');
  const startBtn = document.getElementById('start_btn');
  const progressWrap = document.getElementById('progress_wrap');
  const progressFill = document.getElementById('progress_fill');
  const progressText = document.getElementById('progress_text');
  const folderText = document.getElementById('folder_text');
  const transferredCount = document.getElementById('transferred_count');
  const transferredList = document.getElementById('transferred_list');
  const errorList = document.getElementById('error_list');

  let polling = null;

  function scanCard() {
    fetch('/scan')
      .then(r => r.json())
      .then(data => {
        if (data.found) {
          cardStatus.textContent = `Found ${data.count} image(s) at ${data.root}.`;
          startBtn.disabled = false;
        } else {
          cardStatus.textContent = 'No SD card with images found.';
          startBtn.disabled = true;
        }
      })
      .catch(() => { cardStatus.textContent = 'Could not scan for SD card.'; });
  }

  function renderStatus(s) {
    progressWrap.classList.remove('hidden');
    const pct = s.total ? Math.round((s.done / s.total) * 100) : 0;
    progressFill.style.width = pct + '%';

    folderText.textContent = s.folder ? `Folder: ${s.folder}` : '';

    let counts = `uploaded ${s.uploaded}, skipped ${s.skipped}, remaining ${s.remaining}`;
    if (s.deleted) counts += `, deleted ${s.deleted}`;
    progressText.textContent = s.running
      ? `${s.done}/${s.total} (${counts}) — ${s.current || '…'}`
      : (s.message || `${s.done}/${s.total} done`);

    transferredCount.textContent = (s.transferred || []).length;
    transferredList.innerHTML = '';
    (s.transferred || []).forEach(n => {
      const li = document.createElement('li');
      li.textContent = n;
      transferredList.appendChild(li);
    });

    errorList.innerHTML = '';
    (s.errors || []).forEach(e => {
      const li = document.createElement('li');
      li.textContent = e;
      errorList.appendChild(li);
    });

    startBtn.disabled = s.running;
  }

  function pollStatus() {
    fetch('/status')
      .then(r => r.json())
      .then(s => {
        if (s.running || s.finished) renderStatus(s);
        if (!s.running && polling) {
          clearInterval(polling);
          polling = null;
          scanCard();
        }
      })
      .catch(() => {});
  }

  function startPolling() {
    if (polling) return;
    polling = setInterval(pollStatus, 1500);
    pollStatus();
  }

  scanCard();
  // If a run is already in progress (e.g. page reloaded), pick it up.
  fetch('/status').then(r => r.json()).then(s => {
    if (s.running) { renderStatus(s); startPolling(); }
  }).catch(() => {});

  // After submitting the start form the page redirects; begin polling on load
  // whenever the server reports a run. Also start polling right after submit.
  const startForm = document.getElementById('start_form');
  if (startForm) {
    startForm.addEventListener('submit', function () {
      setTimeout(startPolling, 500);
    });
  }
});
