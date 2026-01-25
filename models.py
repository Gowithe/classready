{% extends "base.html" %}
{% block title %}Fill in the Blanks | {{ topic.name }}{% endblock %}

{% block extra_css %}
<style>
  .wrap{max-width:1000px;margin:1.25rem auto;padding:0 1rem;}
  .card{background:#fff;border:1px solid rgba(0,0,0,.08);border-radius:16px;padding:16px;box-shadow:0 10px 24px rgba(0,0,0,.06);}
  .h1{font-size:1.25rem;font-weight:900;margin-bottom:.25rem;}
  .muted{color:#64748b;font-size:.95rem;}
  
  /* Student Info Form */
  .student-form{
    background: linear-gradient(135deg, #06b6d415, #0891b215);
    border:1px solid rgba(6,182,212,.2);
    border-radius:14px;
    padding:16px;
    margin-bottom:16px;
  }
  .student-form h3{ margin:0 0 12px; font-size:1rem; color:#0e7490; }
  
  /* Grid 5 Fields */
  .form-grid{ display:grid; grid-template-columns: 1fr 1fr; gap:12px; }
  @media(max-width:600px){ .form-grid{ grid-template-columns: 1fr; } }

  .inp{
    width:100%; padding:10px 14px;
    border:2px solid #e2e8f0; border-radius:10px;
    font-size:1rem; outline:none; transition:border-color .2s;
  }
  .inp:focus{border-color:#06b6d4;}
  .inp.error{border-color:#ef4444; background:#fef2f2;}

  /* Timer Bar */
  .timer-bar {
    position: sticky; top: 0; z-index: 100;
    background: #ef4444; color: white;
    text-align: center; padding: 10px;
    font-weight: 800; border-radius: 0 0 12px 12px;
    box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
    margin-bottom: 20px; display: none;
    animation: pulse 1s infinite;
  }
  .timer-bar.safe { background: #06b6d4; animation: none; box-shadow: 0 4px 12px rgba(6,182,212,0.3); }
  @keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.02); } 100% { transform: scale(1); } }

  /* Completed Overlay */
  .completed-overlay {
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: white; z-index: 999;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    text-align: center; display: none;
  }

  /* Progress & Question Styles */
  .progress-bar{ height:6px; background:#e2e8f0; border-radius:3px; margin-top:12px; overflow:hidden; }
  .progress-bar .fill{ height:100%; background: linear-gradient(90deg, #06b6d4, #0891b2); transition: width .3s ease; }
  .progress-text{ font-size:.85rem; color:#64748b; margin-top:6px; text-align:right; }
  
  .q{ margin-top:14px; padding:14px; border-radius:14px; border:1px solid rgba(0,0,0,.08); background:#f8fafc; transition: border-color .2s; }
  .q.answered{ border-color:#22c55e; background:#f0fdf4; }
  .q strong{display:block;margin-bottom:10px;font-size:1.02rem;}
  
  .sentence-display{ font-size:1.15rem; line-height:1.8; margin-bottom:1rem; text-align:center; padding:1rem; background:#fff; border-radius:10px; }
  .blank-slot{ display:inline-block; min-width:80px; padding:.2rem .5rem; border-bottom:3px solid #06b6d4; background:#ecfeff; border-radius:6px 6px 0 0; font-weight:700; color:#0891b2; }
  .blank-slot.correct{background:#dcfce7;border-color:#22c55e;color:#166534;}
  .blank-slot.wrong{background:#fee2e2;border-color:#ef4444;color:#991b1b;}
  
  .choices{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;}
  .choice{ display:flex; gap:10px; align-items:center; padding:12px 18px; border-radius:12px; border:2px solid rgba(0,0,0,.08); background:#fff; cursor:pointer; transition: all .15s; font-weight:600; }
  .choice:hover:not(.disabled){ border-color:#06b6d4; background:rgba(6,182,212,.04); }
  .choice.selected{ border-color:#06b6d4; background:rgba(6,182,212,.08); }
  .choice.correct{ border-color:#22c55e; background:#22c55e; color:#fff; }
  .choice.wrong{ border-color:#ef4444; background:#ef4444; color:#fff; }
  .choice.disabled{ opacity:.6; cursor:not-allowed; }
  
  .feedback{ margin-top:8px; font-size:.9rem; padding:8px 10px; border-radius:8px; display:none; text-align:center; }
  .feedback.show{display:block;}
  .feedback.correct{background:#dcfce7;color:#166534;}
  .feedback.wrong{background:#fef2f2;color:#991b1b;}
  
  /* Buttons */
  .btn{ display:inline-flex; align-items:center; justify-content:center; gap:.5rem; border:0; border-radius:12px; padding:.85rem 1.5rem; font-weight:900; font-size:1rem; cursor:pointer; transition: all .2s; }
  .btn-primary{ background: linear-gradient(135deg, #06b6d4, #0891b2); color:#fff; box-shadow: 0 4px 14px rgba(6,182,212,.35); }
  .btn-primary:hover{ transform: translateY(-2px); box-shadow: 0 6px 20px rgba(6,182,212,.45); }
  .btn-primary:disabled{ opacity:.6; cursor:not-allowed; transform:none; }
  .btn-secondary{ background:#e2e8f0; color:#0f172a; }
  .btn-secondary:hover{ background:#cbd5e1; }
  .bar{ display:flex; gap:10px; flex-wrap:wrap; margin-top:16px; padding-top:16px; border-top:1px solid rgba(0,0,0,.08); justify-content:center; }
  
  /* Result */
  .result{ margin-top:16px; padding:16px; border-radius:14px; display:none; text-align:center; }
  .result.show{display:block;}
  .result.success{ background: linear-gradient(135deg, #dcfce7, #bbf7d0); border:1px solid #22c55e; }
  .result.fail{ background: linear-gradient(135deg, #fef2f2, #fecaca); border:1px solid #ef4444; }
  .result h3{margin:0 0 8px;font-size:1.1rem;}
  .result .score{font-size:2.5rem;font-weight:900;margin:8px 0;}
  
  /* Sound Toggle */
  .sound-toggle{ position:fixed; bottom:15px; right:15px; width:45px; height:45px; border-radius:50%; background:#06b6d4; color:#fff; border:none; font-size:1.3rem; cursor:pointer; box-shadow:0 4px 12px rgba(6,182,212,.4); }
</style>
{% endblock %}

{% block content %}

<div id="timerBar" class="timer-bar safe">
  ⏳ เหลือเวลาอีก: <span id="timerDisplay">--:--</span>
</div>

<div id="completedScreen" class="completed-overlay">
  <div style="font-size:4rem;">✅</div>
  <h1 style="color:#1e293b;">คุณทำแบบทดสอบนี้ไปแล้ว</h1>
  <p style="color:#64748b;">ระบบอนุญาตให้ส่งคำตอบได้เพียง 1 ครั้งเท่านั้น</p>
</div>

<div class="wrap" id="mainContainer">
  <div class="card">
    <div class="h1">✍️ Fill in the Blanks</div>
    <div class="muted">{{ topic.name }} • เติมคำในช่องว่างให้ถูกต้อง</div>

    <div class="student-form">
      <h3>👤 ข้อมูลผู้ทำแบบทดสอบ</h3>
      
      {% if students %}
      <div class="form-group" style="margin-bottom:12px;">
        <label style="font-weight:700; color:#0e7490; display:block; margin-bottom:6px;">
          เลือกชื่อของคุณ <span style="color:#ef4444">*</span>
        </label>
        <select class="inp" id="studentSelect" onchange="autoFillStudent()">
          <option value="">-- ค้นหาหรือเลือกชื่อ --</option>
          {% for s in students %}
          <option value="{{ s.id }}" 
                  data-no="{{ s.student_no }}" 
                  data-name="{{ s.student_name }}" 
                  data-code="{{ s.student_id or '' }}"
                  data-class="{{ classroom.name if classroom else '' }}"
                  data-dept="{{ s.department or '' }}">
            {{ s.student_no }} {{ s.student_name }}
          </option>
          {% endfor %}
        </select>
      </div>
      
      <div class="form-grid" style="opacity:0.8; margin-top:10px;">
        <input class="inp" id="studentName" placeholder="ชื่อ-นามสกุล" readonly style="background:#f1f5f9; grid-column: span 2;">
        <input class="inp" id="studentNo" placeholder="เลขที่" readonly style="background:#f1f5f9;">
        <input class="inp" id="studentId" placeholder="รหัสนักศึกษา" readonly style="background:#f1f5f9;">
        <input class="inp" id="classroom" placeholder="ชั้นเรียน" readonly style="background:#f1f5f9;">
        <input class="inp" id="department" placeholder="แผนก" readonly style="background:#f1f5f9;">
      </div>
      <input type="hidden" id="realStudentId" value="">

      {% else %}
      <div class="form-grid">
        <input class="inp" id="studentName" placeholder="ชื่อ-นามสกุล (Name)" style="grid-column: span 2;">
        <input class="inp" id="studentNo" placeholder="เลขที่ (No.)">
        <input class="inp" id="studentId" placeholder="รหัสนักศึกษา (Student ID)">
        <input class="inp" id="classroom" placeholder="ชั้นเรียน (Class)">
        <input class="inp" id="department" placeholder="แผนก/สาขา (Department)">
      </div>
      <input type="hidden" id="realStudentId" value="">
      {% endif %}
    </div>

    <div class="progress-bar">
      <div class="fill" id="progressFill" style="width:0%"></div>
    </div>
    <div class="progress-text" id="progressText">ตอบแล้ว 0 / 0 ข้อ</div>

    <div id="questionsContainer"></div>

    <div class="bar">
      <button class="btn btn-primary" id="btnSubmit">📤 ส่งคำตอบ</button>
    </div>

    <div class="result" id="resultBox">
      <h3 id="resultTitle">ผลการทำแบบฝึกหัด</h3>
      <div class="score" id="resultScore">0/0</div>
      <div class="muted" id="resultPercent">0%</div>
      <div id="resultMsg" style="margin-top:10px;"></div>
    </div>
  </div>
</div>

<button class="sound-toggle" id="soundToggle" onclick="toggleSound()">🔊</button>

<script>
const practiceData = {{ practice_data | tojson | safe }};
const token = "{{ token }}";
const storageKey = "done_" + token;

// --- Auto Fill Logic ---
function autoFillStudent() {
  const select = document.getElementById('studentSelect');
  if (!select) return;
  const option = select.options[select.selectedIndex];
  
  if (option.value) {
    document.getElementById('realStudentId').value = option.value;
    document.getElementById('studentName').value = option.dataset.name;
    document.getElementById('studentNo').value = option.dataset.no;
    document.getElementById('studentId').value = option.dataset.code;
    document.getElementById('classroom').value = option.dataset.class;
    document.getElementById('department').value = option.dataset.dept;
  } else {
    // Clear fields
    ['realStudentId', 'studentName', 'studentNo', 'studentId', 'classroom', 'department'].forEach(id => {
      const el = document.getElementById(id);
      if(el) el.value = '';
    });
  }
}

// --- 1. One-Time Submission Check ---
if (localStorage.getItem(storageKey)) {
  document.getElementById("mainContainer").style.display = "none";
  document.getElementById("completedScreen").style.display = "flex";
  document.getElementById("timerBar").style.display = "none";
}

// --- 2. Timer Logic ---
const urlParams = new URLSearchParams(window.location.search);
const timeLimitMins = parseInt(urlParams.get('limit')) || 0;
let timerInterval;

if (timeLimitMins > 0 && !localStorage.getItem(storageKey)) {
  const timerBar = document.getElementById('timerBar');
  const timerDisplay = document.getElementById('timerDisplay');
  timerBar.style.display = 'block';

  const startTimeKey = "start_" + token;
  let endTime = localStorage.getItem(startTimeKey);
  
  if (!endTime) {
    const now = new Date().getTime();
    endTime = now + (timeLimitMins * 60 * 1000);
    localStorage.setItem(startTimeKey, endTime);
  }

  function updateTimer() {
    const now = new Date().getTime();
    let timeLeft = Math.floor((endTime - now) / 1000); 

    if (timeLeft < 0) timeLeft = 0;

    const m = Math.floor(timeLeft / 60).toString().padStart(2, '0');
    const s = (timeLeft % 60).toString().padStart(2, '0');
    timerDisplay.textContent = `${m}:${s}`;

    if (timeLeft <= 60) { timerBar.classList.remove('safe'); }

    if (timeLeft <= 0) {
      clearInterval(timerInterval);
      if(document.getElementById("mainContainer").style.display !== "none"){
          alert("หมดเวลา! ระบบจะส่งคำตอบโดยอัตโนมัติ");
          handleSubmit(true); // Force submit
      }
    }
  }
  updateTimer();
  timerInterval = setInterval(updateTimer, 1000);
}

// --- Audio System ---
let soundEnabled = true;
let audioContext = null;
function initAudio() {
  if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)();
  return audioContext;
}
function playTone(freq, dur, type = 'sine', vol = 0.3) {
  if (!soundEnabled) return;
  try {
    const ctx = initAudio();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    osc.frequency.value = freq; osc.type = type;
    gain.gain.setValueAtTime(vol, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + dur);
    osc.start(ctx.currentTime); osc.stop(ctx.currentTime + dur);
  } catch (e) {}
}
function playCorrectSound() { playTone(523, 0.15); setTimeout(() => playTone(659, 0.15), 100); setTimeout(() => playTone(784, 0.2), 200); }
function playWrongSound() { playTone(200, 0.3, 'square', 0.15); }
function toggleSound() {
  soundEnabled = !soundEnabled;
  document.getElementById('soundToggle').textContent = soundEnabled ? '🔊' : '🔇';
}

// --- Game Logic ---
let questions = [];
let userAnswers = {};

function init() {
  questions = prepareQuestions();
  if (questions.length === 0) {
    document.getElementById('questionsContainer').innerHTML = '<p style="text-align:center;color:#64748b;padding:2rem;">ไม่มีข้อมูลสำหรับแบบฝึกหัดนี้</p>';
    return;
  }
  renderQuestions();
  updateProgress();
}

function prepareQuestions() {
  const result = [];
  if (practiceData.mcq_questions && practiceData.mcq_questions.length > 0) {
    practiceData.mcq_questions.forEach((q, i) => {
      if (q.prompt && q.choices && q.correct_answer) {
        result.push({ id: i, sentence: q.prompt, answer: q.correct_answer, choices: q.choices });
      }
    });
  }
  if (practiceData.vocabulary && practiceData.vocabulary.length > 0) {
    practiceData.vocabulary.forEach((v, i) => {
      if (v.word && v.example) {
        const blank = v.example.replace(new RegExp('\\b' + v.word + '\\b', 'i'), '_____');
        if (blank !== v.example) {
          result.push({ id: 100 + i, sentence: blank, answer: v.word, choices: null });
        }
      }
    });
  }
  shuffleArray(result);
  return result.slice(0, 15);
}

function shuffleArray(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
}

function generateChoices(q) {
  if (q.choices && q.choices.length >= 4) {
    const c = [...q.choices];
    shuffleArray(c);
    return c;
  }
  const choices = [q.answer];
  const others = questions.map(x => x.answer).filter(a => a !== q.answer);
  shuffleArray(others);
  for (let i = 0; i < 3 && i < others.length; i++) {
    if (!choices.includes(others[i])) choices.push(others[i]);
  }
  const fillers = ['the', 'is', 'are', 'have', 'has', 'do', 'does'];
  while (choices.length < 4) {
    const f = fillers[Math.floor(Math.random() * fillers.length)];
    if (!choices.includes(f)) choices.push(f);
  }
  shuffleArray(choices);
  return choices.slice(0, 4);
}

function renderQuestions() {
  const container = document.getElementById('questionsContainer');
  container.innerHTML = questions.map((q, idx) => {
    const choices = generateChoices(q);
    let displayText = q.sentence;
    if (!displayText.includes('_____')) {
      displayText = displayText + ` <span class="blank-slot" id="blank${q.id}">?</span>`;
    } else {
      displayText = displayText.replace('_____', `<span class="blank-slot" id="blank${q.id}">?</span>`);
    }
    
    return `
      <div class="q" id="q${q.id}" data-qid="${q.id}">
        <strong>${idx + 1}. เติมคำในช่องว่าง</strong>
        <div class="sentence-display">${displayText}</div>
        <div class="choices" id="choices${q.id}">
          ${choices.map(c => `
            <div class="choice" data-answer="${escapeHtml(c)}" onclick="selectChoice(${q.id}, this, '${escapeHtml(c).replace(/'/g, "\\'")}')">${escapeHtml(c)}</div>
          `).join('')}
        </div>
        <div class="feedback" id="fb${q.id}"></div>
      </div>
    `;
  }).join('');
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function selectChoice(qid, el, answer) {
  const q = questions.find(x => x.id === qid);
  if (!q) return;
  if (document.getElementById('btnSubmit').disabled) return;
  
  playTone(400, 0.1, 'sine', 0.2);
  
  const container = document.getElementById('choices' + qid);
  container.querySelectorAll('.choice').forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
  
  userAnswers[qid] = answer;
  const blank = document.getElementById('blank' + qid);
  if (blank) blank.textContent = answer;
  
  document.getElementById('q' + qid).classList.add('answered');
  updateProgress();
}

function updateProgress() {
  const answered = Object.keys(userAnswers).length;
  const total = questions.length;
  const pct = total > 0 ? (answered / total * 100) : 0;
  document.getElementById('progressFill').style.width = pct + '%';
  document.getElementById('progressText').textContent = `ตอบแล้ว ${answered} / ${total} ข้อ`;
}

// --- Submission Logic ---
document.getElementById('btnSubmit').addEventListener('click', () => handleSubmit(false));

async function handleSubmit(force = false) {
  const studentName = (document.getElementById('studentName').value || '').trim();
  const studentNo = (document.getElementById('studentNo').value || '').trim();
  const studentId = (document.getElementById('studentId').value || '').trim();
  const classroom = (document.getElementById('classroom').value || '').trim();
  const department = (document.getElementById('department').value || '').trim();
  
  if (!studentName && !force) {
    alert('กรุณากรอกชื่อ-สกุลก่อนส่ง');
    document.getElementById('studentName').classList.add('error');
    document.getElementById('studentName').focus();
    return;
  }
  document.getElementById('studentName').classList.remove('error');
  
  const unanswered = questions.length - Object.keys(userAnswers).length;
  if (unanswered > 0 && !force) {
    if (!confirm(`ยังมี ${unanswered} ข้อที่ยังไม่ได้ตอบ\nต้องการส่งเลยหรือไม่?`)) {
      return;
    }
  }
  
  if(!force && !confirm("ยืนยันการส่งคำตอบ? คุณสามารถทำได้เพียงครั้งเดียว")) return;

  clearInterval(timerInterval);
  document.getElementById("timerBar").style.display = 'none';

  const btnSubmit = document.getElementById('btnSubmit');
  btnSubmit.disabled = true;
  btnSubmit.innerHTML = '⏳ กำลังส่ง...';
  
  // Calculate score locally for UI feedback
  let score = 0;
  questions.forEach(q => {
    const userAns = userAnswers[q.id] || '';
    const isCorrect = userAns.toLowerCase().trim() === q.answer.toLowerCase().trim();
    
    const blank = document.getElementById('blank' + q.id);
    const fb = document.getElementById('fb' + q.id);
    const container = document.getElementById('choices' + q.id);
    
    container.querySelectorAll('.choice').forEach(c => {
      c.classList.add('disabled');
      if (c.dataset.answer.toLowerCase().trim() === q.answer.toLowerCase().trim()) {
        c.classList.add('correct');
      }
    });
    
    if (isCorrect) {
      score++;
      if (blank) blank.classList.add('correct');
      fb.className = 'feedback show correct';
      fb.innerHTML = '✅ ถูกต้อง!';
    } else {
      playWrongSound();
      if (blank) {
        blank.textContent = q.answer;
        blank.classList.add('wrong');
      }
      const selectedChoice = container.querySelector('.choice.selected');
      if (selectedChoice) selectedChoice.classList.add('wrong');
      fb.className = 'feedback show wrong';
      fb.innerHTML = `❌ ผิด — คำตอบที่ถูกคือ: <strong>${q.answer}</strong>`;
    }
  });
  
  if (score > 0) playCorrectSound();
  
  // Submit to server
  try {
    await fetch(`/api/public/fill/${token}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        // ส่ง student_db_id ถ้าเลือกจาก dropdown
        student_db_id: document.getElementById('realStudentId') ? document.getElementById('realStudentId').value : null,
        student_name: studentName,
        student_no: studentNo,
        student_id: studentId,
        classroom: classroom,
        department: department,
        score: score,
        total: questions.length,
        answers: userAnswers
      })
    });
    
    // Mark as done
    localStorage.setItem(storageKey, "true");
    localStorage.removeItem("start_" + token);

  } catch (e) {
    console.error(e);
  }
  
  // Show result
  const pct = Math.round(score / questions.length * 100);
  const isPass = pct >= 50;
  
  const resultBox = document.getElementById('resultBox');
  resultBox.classList.add('show', isPass ? 'success' : 'fail');
  document.getElementById('resultTitle').textContent = isPass ? '🎉 ทำได้ดีมาก!' : '💪 พยายามต่อไปนะ!';
  document.getElementById('resultScore').textContent = `${score}/${questions.length}`;
  document.getElementById('resultPercent').textContent = `${pct}%`;
  document.getElementById('resultMsg').innerHTML = 'คะแนนถูกบันทึกเรียบร้อยแล้ว ✅<br>(คุณไม่สามารถทำซ้ำได้)';
  
  resultBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
  btnSubmit.innerHTML = '✅ ส่งแล้ว';
}

init();
</script>
{% endblock %}
