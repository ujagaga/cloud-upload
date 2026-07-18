document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.toggle_pw').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const input = document.getElementById(btn.dataset.target);
      const icon = btn.querySelector('i');
      const showing = input.type === 'text';
      input.type = showing ? 'password' : 'text';
      icon.classList.toggle('fa-eye', showing);
      icon.classList.toggle('fa-eye-slash', !showing);
    });
  });
});
