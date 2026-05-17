/**
 * Dashboard Charts — Chart.js 4
 * Renders: weight trend, calorie bar, steps bar, water bar
 */

const COLORS = {
  primary:  '#4f46e5',
  success:  '#10b981',
  warning:  '#f59e0b',
  danger:   '#ef4444',
  info:     '#06b6d4',
  muted:    '#94a3b8',
};

function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

function makeLineChart(id, labels, data, color, label, unit='') {
  const ctx = document.getElementById(id);
  if (!ctx) return;
  new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label,
        data,
        borderColor: color,
        backgroundColor: color + '22',
        borderWidth: 2.5,
        pointRadius: 4,
        pointHoverRadius: 6,
        tension: 0.4,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: true, labels: { usePointStyle: true, boxWidth: 8, color: '#64748b' } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.parsed.y}${unit}`,
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 10, family: 'Poppins' }, color: '#64748b' } },
        y: { grid: { color: '#eef2f7' }, ticks: { font: { size: 10, family: 'Poppins' }, color: '#64748b' } },
      },
    },
  });
}

function makeBarChart(id, labels, data, color, label, targetLine=null, unit='') {
  const ctx = document.getElementById(id);
  if (!ctx) return;

  const datasets = [{
    label,
    data,
    backgroundColor: color + 'bb',
    borderColor: color,
    borderWidth: 1.5,
    borderRadius: 6,
  }];

  if (targetLine) {
    datasets.push({
      label: 'Target',
      data: Array(labels.length).fill(targetLine),
      type: 'line',
      borderColor: '#ef444488',
      borderWidth: 1.5,
      borderDash: [4, 4],
      pointRadius: 0,
      fill: false,
    });
  }

  new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      responsive: true,
      plugins: {
        legend: { display: true, labels: { usePointStyle: true, boxWidth: 8, color: '#64748b' } },
        tooltip: {
          callbacks: { label: ctx => `${ctx.parsed.y}${unit}` },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 10, family: 'Poppins' }, color: '#64748b' } },
        y: { grid: { color: '#eef2f7' }, ticks: { font: { size: 10, family: 'Poppins' }, color: '#64748b' } },
      },
    },
  });
}

// Format date labels: 'Mon 3/27' style
function formatLabels(dateStrings) {
  return dateStrings.map(d => {
    if (!d) return '';
    const dt = new Date(d);
    const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    return `${days[dt.getDay()]} ${dt.getMonth()+1}/${dt.getDate()}`;
  });
}

// ── Render all charts ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (typeof chartData === 'undefined') return;

  const labels = formatLabels(chartData.dates);

  makeLineChart('weightChart', labels,
                chartData.weights,
                COLORS.primary, 'Weight', ' kg');

  makeBarChart('calorieChart', labels,
               chartData.calories,
               COLORS.warning, 'Calories',
               typeof targetCal !== 'undefined' ? targetCal : null, ' kcal');

  makeBarChart('stepsChart', labels,
               chartData.steps,
               COLORS.success, 'Steps',
               8000, '');

  makeBarChart('waterChart', labels,
               chartData.water,
               COLORS.info, 'Water',
               2.5, ' L');

  makeLineChart('predictionChart',
                formatLabels(chartData.prediction_dates || []),
                chartData.prediction_weights || [],
                COLORS.danger, 'Expected Weight', ' kg');

  makeBarChart('macroChart',
               chartData.macro_labels || [],
               chartData.macro_values || [],
               COLORS.primary, 'Macros', null, 'g');

  makeLineChart('moodChart',
                formatLabels(chartData.mood_dates || []),
                chartData.mood_scores || [],
                COLORS.info, 'Mood', '');
});

// ── Daily log save ───────────────────────────────────────────────────────────
async function saveLog() {
  const payload = {
    steps:    document.getElementById('inp-steps')?.value   || 0,
    water:    document.getElementById('inp-water')?.value   || 0,
    water_glasses: document.getElementById('inp-water-glasses')?.value || 0,
    sleep_hours: document.getElementById('inp-sleep')?.value || 0,
    calories: document.getElementById('inp-calories')?.value || 0,
    calories_burned: document.getElementById('inp-burned')?.value || 0,
    weight:   document.getElementById('inp-weight')?.value  || 0,
    mood: document.getElementById('inp-mood')?.value || 'neutral',
    exercise_completed: document.getElementById('inp-exercise')?.checked || false,
  };

  try {
    const res = await fetch('/log-daily', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    const msg = document.getElementById('log-msg');
    msg.classList.remove('d-none');
    msg.className = 'mt-2 small text-center ' + (data.status === 'ok' ? 'text-success' : 'text-danger');
    msg.textContent = data.message || 'Saved!';
    setTimeout(() => msg.classList.add('d-none'), 3000);
  } catch (e) {
    const msg = document.getElementById('log-msg');
    if (msg) {
      msg.classList.remove('d-none');
      msg.className = 'mt-2 small text-center text-danger';
      msg.textContent = 'Could not save log. Please try again.';
      setTimeout(() => msg.classList.add('d-none'), 4000);
    }
  }
}

// ── Feedback submit ──────────────────────────────────────────────────────────
async function submitFeedback() {
  const followed = document.querySelector('input[name="followed"]:checked')?.value || 'no';
  const notes    = document.getElementById('fb-notes')?.value || '';
  const weight   = document.getElementById('inp-weight')?.value || 0;

  try {
    const res = await fetch('/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify({ followed_diet: followed, notes, weight }),
    });
    const data = await res.json();
    const msg = document.getElementById('fb-msg');
    msg.classList.remove('d-none');
    msg.className = 'mt-2 small text-center text-success';
    msg.textContent = data.message || 'Thanks!';
    setTimeout(() => msg.classList.add('d-none'), 3000);
  } catch (e) {
    const msg = document.getElementById('fb-msg');
    if (msg) {
      msg.classList.remove('d-none');
      msg.className = 'mt-2 small text-center text-danger';
      msg.textContent = 'Could not send feedback. Please try again.';
    }
  }
}

async function addFood() {
  const payload = {
    food_name: document.getElementById('food-name')?.value || '',
    calories: document.getElementById('food-calories')?.value || '',
    protein_g: document.getElementById('food-protein')?.value || '',
    carbs_g: document.getElementById('food-carbs')?.value || '',
    fat_g: document.getElementById('food-fat')?.value || '',
  };
  const msg = document.getElementById('food-msg');
  try {
    const res = await fetch('/log-food', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    msg.className = 'mt-2 small text-center ' + (data.status === 'ok' ? 'text-success' : 'text-danger');
    msg.textContent = data.message || 'Saved';
    msg.classList.remove('d-none');
  } catch (e) {
    const msg = document.getElementById('food-msg');
    if (msg) {
      msg.classList.remove('d-none');
      msg.className = 'mt-2 small text-center text-danger';
      msg.textContent = 'Could not add food. Please try again.';
    }
  }
}

async function saveMood() {
  const payload = {
    mood: document.getElementById('mood-select')?.value || 'neutral',
    stress: document.getElementById('stress-level')?.value || 3,
    journal: document.getElementById('mood-journal')?.value || '',
    meditation_minutes: 5,
  };
  const msg = document.getElementById('mood-msg');
  try {
    const res = await fetch('/log-mood', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    msg.className = 'mt-2 small text-center text-success';
    msg.textContent = data.message || 'Saved';
    msg.classList.remove('d-none');
  } catch (e) {
    const msg = document.getElementById('mood-msg');
    if (msg) {
      msg.classList.remove('d-none');
      msg.className = 'mt-2 small text-center text-danger';
      msg.textContent = 'Could not save mood. Please try again.';
    }
  }
}
