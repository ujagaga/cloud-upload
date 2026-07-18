document.addEventListener('DOMContentLoaded', function () {
  const startBtn = document.getElementById('start_btn');
  const authArea = document.getElementById('auth_area');
  const doneArea = document.getElementById('done_area');
  const verifyLink = document.getElementById('verify_link');
  const userCode = document.getElementById('user_code');
  const authStatus = document.getElementById('auth_status');
  const doneMsg = document.getElementById('done_msg');

  let polling = null;

  function showPending(s) {
    authArea.classList.remove('hidden');
    verifyLink.href = s.verification_url;
    verifyLink.textContent = s.verification_url;
    userCode.textContent = s.user_code;
    authStatus.textContent = 'Waiting for you to authorize on your phone…';
  }

  function finish(s, cls) {
    if (polling) { clearInterval(polling); polling = null; }
    if (s.status === 'success') {
      authArea.classList.add('hidden');
      doneArea.classList.remove('hidden');
      doneMsg.textContent = s.message || 'Authorized.';
    } else {
      authStatus.textContent = s.message || s.status;
      authStatus.className = 'err';
      startBtn.disabled = false;
      startBtn.textContent = 'Try again';
    }
  }

  function poll() {
    fetch('/authorize/status')
      .then(r => r.json())
      .then(s => {
        if (s.status === 'pending') return;
        if (['success', 'denied', 'expired', 'error'].includes(s.status)) finish(s);
      })
      .catch(() => {});
  }

  startBtn.addEventListener('click', function () {
    startBtn.disabled = true;
    startBtn.textContent = 'Starting…';
    fetch('/authorize/start', {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf },
    })
      .then(r => r.json())
      .then(s => {
        if (!s.ok) {
          authStatus.textContent = s.message;
          authStatus.className = 'err';
          startBtn.disabled = false;
          startBtn.textContent = 'Try again';
          return;
        }
        showPending(s);
        polling = setInterval(poll, 3000);
      })
      .catch(() => {
        startBtn.disabled = false;
        startBtn.textContent = 'Try again';
      });
  });
});
