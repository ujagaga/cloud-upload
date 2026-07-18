document.addEventListener('DOMContentLoaded', function () {
  const retryForm = document.getElementById('retry_form');
  if (!retryForm) return;

  function poll() {
    fetch('/drive_status')
      .then(r => r.json())
      .then(data => retryForm.classList.toggle('hidden', !data.authorized))
      .catch(() => {});
  }

  setInterval(poll, 3000);
});
