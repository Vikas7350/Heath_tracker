/**
 * Profile Setup Wizard — multi-step form navigation
 */

let currentStep = 1;
const totalSteps = 6;

const stepLabels = [
  'Basic Information',
  'Health Information',
  'Fitness Goals',
  'Lifestyle Details',
  'Dietary Preferences',
  'Fitness Level',
];

function getStep(n) {
  return document.querySelector(`.wizard-step[data-step="${n}"]`);
}

function changeStep(direction) {
  const next = currentStep + direction;
  if (next < 1 || next > totalSteps) return;

  // Validate current step fields
  if (direction > 0) {
    const current = getStep(currentStep);
    const inputs  = current.querySelectorAll('input[required], select[required]');
    let valid = true;
    inputs.forEach(inp => {
      if (!inp.value) {
        inp.classList.add('is-invalid');
        valid = false;
      } else {
        inp.classList.remove('is-invalid');
      }
    });
    if (!valid) return;
  }

  // Hide current, show next
  getStep(currentStep).classList.add('d-none');
  currentStep = next;
  getStep(currentStep).classList.remove('d-none');

  // Update progress
  const pct = (currentStep / totalSteps) * 100;
  document.getElementById('progress-bar').style.width = pct + '%';
  document.getElementById('step-num').textContent    = currentStep;
  document.getElementById('step-label').textContent  = stepLabels[currentStep - 1];

  // Show/hide nav buttons
  document.getElementById('btn-prev').disabled = (currentStep === 1);
  document.getElementById('btn-next').classList.toggle('d-none', currentStep === totalSteps);
  document.getElementById('btn-submit').classList.toggle('d-none', currentStep !== totalSteps);
}

// Remove invalid class on input
document.querySelectorAll('input, select').forEach(el => {
  el.addEventListener('input', () => el.classList.remove('is-invalid'));
});
