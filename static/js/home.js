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
  const mountStatus = document.getElementById('mount_status');
  const mountIcon = document.getElementById('mount_icon');
  const mountStatusText = document.getElementById('mount_status_text');
  const mountBtn = document.getElementById('mount_btn');

  let polling = null;
  let autoUploadedRoot = null;

  function triggerAutoUpload() {
    fetch('/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'csrf_token=' + encodeURIComponent(CSRF_TOKEN),
    }).then(() => setTimeout(startPolling, 500));
  }

  function deviceName(device) {
    return device ? device.split('/').pop() : '';
  }

  function setMountStatus(mounted, device) {
    const suffix = device ? ` (${deviceName(device)})` : '';
    if (mounted) {
      mountStatus.classList.remove('hidden');
      mountIcon.className = 'fa-solid fa-sd-card ok';
      mountStatusText.textContent = `Mounted${suffix}`;
      mountBtn.classList.add('hidden');
    } else if (device) {
      mountStatus.classList.remove('hidden');
      mountIcon.className = 'fa-solid fa-sd-card err';
      mountStatusText.textContent = `Not mounted${suffix}`;
      mountBtn.classList.remove('hidden');
      mountBtn.dataset.device = device;
    } else {
      mountStatus.classList.add('hidden');
    }
  }

  function scanCard() {
    fetch('/scan')
      .then(r => r.json())
      .then(data => {
        setMountStatus(data.mounted, data.device);
        if (data.found) {
          cardStatus.textContent = `Found ${data.count} image(s) at ${data.root}.`;
          startBtn.disabled = false;
          if (AUTO_UPLOAD && data.root !== autoUploadedRoot) {
            autoUploadedRoot = data.root;
            triggerAutoUpload();
          }
        } else {
          cardStatus.textContent = 'No SD card with images found.';
          startBtn.disabled = true;
          autoUploadedRoot = null;
        }
      })
      .catch(() => { cardStatus.textContent = 'Could not scan for SD card.'; });
  }

  mountBtn.addEventListener('click', function () {
    mountBtn.disabled = true;
    mountBtn.textContent = 'Mounting…';
    fetch('/mount_card', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'csrf_token=' + encodeURIComponent(CSRF_TOKEN) + '&device=' + encodeURIComponent(mountBtn.dataset.device || ''),
    })
      .then(r => r.json())
      .then(() => {
        mountBtn.disabled = false;
        mountBtn.innerHTML = '<i class="fa-solid fa-plug"></i> Mount';
        scanCard();
      })
      .catch(() => {
        mountBtn.disabled = false;
        mountBtn.innerHTML = '<i class="fa-solid fa-plug"></i> Mount';
      });
  });

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
  setInterval(scanCard, 3000);
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
