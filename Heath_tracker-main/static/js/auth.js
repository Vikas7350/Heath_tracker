document.addEventListener('DOMContentLoaded', () => {
  const boxes = [...document.querySelectorAll('.otp-box')];
  boxes.forEach((box, index) => {
    box.addEventListener('input', () => {
      box.value = box.value.replace(/\D/g, '').slice(0, 1);
      if (box.value && boxes[index + 1]) boxes[index + 1].focus();
    });
    box.addEventListener('keydown', (event) => {
      if (event.key === 'Backspace' && !box.value && boxes[index - 1]) boxes[index - 1].focus();
    });
  });

  document.querySelectorAll('form.auth-form').forEach((form) => {
    form.addEventListener('submit', () => {
      const codeInput = form.querySelector('input[name="otp_code"]');
      if (codeInput && !codeInput.value.trim()) {
        codeInput.value = [...form.querySelectorAll('.otp-box')].map(input => input.value.trim()).join('');
      }
      const submit = form.querySelector('button[type="submit"]');
      if (submit) {
        submit.disabled = true;
        submit.dataset.originalText = submit.textContent;
        submit.textContent = 'Please wait...';
      }
    }, { once: true });
  });

  document.querySelectorAll('.password-toggle').forEach((button) => {
    button.addEventListener('click', () => {
      const input = button.parentElement?.querySelector('input[type="password"], input[type="text"]');
      const icon = button.querySelector('i');
      if (!input) return;
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      if (icon) icon.className = show ? 'bi bi-eye-slash' : 'bi bi-eye';
      button.title = show ? 'Hide password' : 'Show password';
    });
  });

  const timer = document.getElementById('otp-countdown');
  if (!timer) return;
  let seconds = 300;
  setInterval(() => {
    seconds = Math.max(0, seconds - 1);
    const mm = String(Math.floor(seconds / 60)).padStart(2, '0');
    const ss = String(seconds % 60).padStart(2, '0');
    timer.textContent = `${mm}:${ss}`;
  }, 1000);
});
