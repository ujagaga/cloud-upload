document.addEventListener('DOMContentLoaded', function () {
  const ssidInput = document.getElementById('ssid_input');
  const wifiPassword = document.getElementById('wifi_password');
  const connectForm = document.getElementById('connect_form');
  const connectBtn = document.getElementById('connect_btn');
  const connectStatus = document.getElementById('connect_status');
  const networkList = document.getElementById('network_list');

  let polling = null;

  if (networkList) {
    networkList.querySelectorAll('li').forEach(function (li) {
      li.style.cursor = 'pointer';
      li.addEventListener('click', function () {
        ssidInput.value = li.dataset.ssid;
        wifiPassword.focus();
      });
    });
  }

  function pollStatus() {
    fetch('/wifi/status')
      .then(r => r.json())
      .then(function (s) {
        connectStatus.textContent = s.message || '';
        if (s.phase === 'connecting') return;
        connectStatus.className = s.phase === 'connected' ? 'ok' : 'err';
        connectBtn.disabled = false;
        connectBtn.textContent = 'Connect';
        if (polling) { clearInterval(polling); polling = null; }
      })
      .catch(() => {});
  }

  connectForm.addEventListener('submit', function (e) {
    e.preventDefault();
    connectBtn.disabled = true;
    connectBtn.textContent = 'Connecting…';
    connectStatus.className = 'muted';
    connectStatus.textContent = 'Connecting… this can take up to 30 seconds. If you were on the setup ' +
      'WiFi, you will lose that connection now — reconnect your phone to your normal WiFi afterward.';

    fetch('/wifi/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'csrf_token=' + encodeURIComponent(CSRF_TOKEN) +
            '&ssid=' + encodeURIComponent(ssidInput.value) +
            '&password=' + encodeURIComponent(wifiPassword.value),
    })
      .then(r => r.json())
      .then(function (s) {
        if (!s.ok) {
          connectStatus.className = 'err';
          connectStatus.textContent = s.message;
          connectBtn.disabled = false;
          connectBtn.textContent = 'Connect';
          return;
        }
        polling = setInterval(pollStatus, 2000);
      })
      .catch(function () {
        // Expected if we were on the setup AP: the browser's own WiFi just
        // dropped along with it, so this request may never get a response.
        connectStatus.textContent = 'Request sent. If you were on the setup WiFi, reconnect your phone ' +
          'to your normal network to check whether it worked.';
      });
  });
});
