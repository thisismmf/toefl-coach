/* TOEFL Coach – front end */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const api = async (url, opt) => {
  const r = await fetch(url, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || j.detail || `HTTP ${r.status}`);
  return j;
};
const LS = 'toeflcoach.cfg';

const state = {
  task: 'email', view: 'new',
  ids: { grade: null, model: null, lesson: null },
  polls: {},
};

/* ───────────────── settings ───────────────── */
function cfg() {
  return {
    provider: $('#provider').value,
    model: $('#model').value.trim(),
    temperature: parseFloat($('#temp').value) || 0.2,
    num_ctx: parseInt($('#ctx').value) || 8192,
    base_url: $('#baseUrl').value.trim() || null,
    api_key: $('#apiKey').value.trim() || null,
  };
}
function saveCfg() {
  const c = cfg(); delete c.api_key;
  localStorage.setItem(LS, JSON.stringify(c));
}
function loadCfg() {
  try {
    const c = JSON.parse(localStorage.getItem(LS) || '{}');
    if (c.provider) $('#provider').value = c.provider;
    if (c.model) $('#model').value = c.model;
    if (c.temperature != null) $('#temp').value = c.temperature;
    if (c.num_ctx) $('#ctx').value = c.num_ctx;
    if (c.base_url) $('#baseUrl').value = c.base_url;
  } catch { /* ignore */ }
}
let PROVIDERS = [];
function providerInfo(id) { return PROVIDERS.find(p => p.id === id) || {}; }
function renderProviders(sel) {
  $('#provider').innerHTML = PROVIDERS.map(p =>
    `<option value="${esc(p.id)}">${esc(p.label)}${p.has_key ? '' : ' — no key'}</option>`).join('');
  if (sel && PROVIDERS.some(p => p.id === sel)) $('#provider').value = sel;
}
function syncProviderFields() {
  const p = $('#provider').value;
  $('#wrapBase').hidden = p === 'ollama' || p === 'ollama_cloud';
  // A key already in .env means the field is optional, so only show it when missing.
  $('#wrapKey').hidden = p === 'ollama' || providerInfo(p).has_key === true;
  setModelStatus('');
}
let SERVER_DEFAULTS = {};
// Sensible first pick per provider; the free Ollama Cloud tier does not cover
// every model it lists, so do not land on one that will simply refuse.
const PREFERRED = {
  ollama_cloud: ['gpt-oss:120b', 'gpt-oss:20b', 'gemma4:31b', 'nemotron-3-nano:30b'],
  ollama: ['qwen3-vl:8b', 'llama3.1:8b'],
  openai: ['gpt-4o-mini', 'gpt-4o'],
  anthropic: ['claude-sonnet-4-5', 'claude-3-5-sonnet-latest'],
};
function setModelStatus(kind, text) {
  const el = $('#modelStatus');
  el.className = 'mstat' + (kind ? ' ' + kind : '');
  el.textContent = text || '';
}
async function testModel(quiet) {
  const c = cfg();
  if (!c.model) { if (!quiet) alert('Choose a model first.'); return null; }
  setModelStatus('testing', 'testing…');
  try {
    const res = await api('/api/check', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: c.provider, model: c.model,
                             base_url: c.base_url, api_key: c.api_key }),
    });
    setModelStatus(res.ok ? 'ok' : 'no', res.ok ? 'reachable' : 'unreachable');
    if (!res.ok && !quiet) showConnProblem($('#view-new'), res, null);
    return res;
  } catch (e) { setModelStatus('no', 'unreachable'); return null; }
}
async function refreshModels() {
  const p = $('#provider').value;
  const q = new URLSearchParams({ provider: p, base_url: $('#baseUrl').value.trim(), api_key: $('#apiKey').value.trim() });
  try {
    const { models } = await api('/api/models?' + q);
    $('#modellist').innerHTML = models.map(m => `<option value="${esc(m)}">`).join('');
    if (!$('#model').value && models.length) {
      // Prefer the configured default, then a known-good model for this
      // provider, then whatever is first.
      const wanted = [SERVER_DEFAULTS.provider === p ? SERVER_DEFAULTS.model : null,
                      ...(PREFERRED[p] || [])].filter(Boolean);
      $('#model').value = wanted.find(m => models.includes(m)) || models[0];
    }
  } catch { /* offline is fine */ }
}

/* ───────────────── views ───────────────── */
function setView(v) {
  state.view = v;
  $$('#tabs .tab').forEach(t => t.classList.toggle('on', t.dataset.view === v));
  ['new', 'grade', 'model', 'lesson'].forEach(k => { $('#view-' + k).hidden = k !== v; });
}
function setTask(t) {
  state.task = t;
  $$('#taskTabs .tab').forEach(b => b.classList.toggle('on', b.dataset.task === t));
  const L = {
    email: ['Write an Email', 'Paste the task prompt and your answer',
      'Task prompt (including all bullet points)', 'Your email'],
    discussion: ['Academic Discussion', 'Paste the professor’s question, both classmates, and your post',
      'Professor’s question', 'Your post'],
    speaking: ['Take an Interview', 'Paste the interview question and your transcript',
      'Interview question', 'Your spoken answer (transcript)'],
  }[t];
  $('#formTitle').textContent = L[0];
  $('#formHint').textContent = L[1];
  $('#qLabel').textContent = L[2];
  $('#rLabel').textContent = L[3];
  $('#classmates').hidden = t !== 'discussion';
  $('#durWrap').hidden = t !== 'speaking';
  updateCounter();
}
function updateCounter() {
  const txt = $('#response').value;
  const w = (txt.match(/[A-Za-z][A-Za-z'-]*/g) || []).length;
  const s = txt.trim() ? (txt.trim().split(/(?<=[.!?])\s+(?=[A-Z"'(])|\n{2,}/).filter(Boolean)).length : 0;
  const tgt = { email: [100, 130, 11], discussion: [120, 160, 12], speaking: [110, 145, 12] }[state.task];
  const wOK = w >= tgt[0], sOK = s <= tgt[2];
  $('#counter').innerHTML =
    `<span style="color:${wOK ? 'var(--brand)' : 'var(--bad)'}">${w} words</span>` +
    ` <span style="color:var(--mute)">(target ${tgt[0]}–${tgt[1]})</span> · ` +
    `<span style="color:${sOK ? 'var(--brand)' : 'var(--bad)'}">${s} sentences</span>` +
    ` <span style="color:var(--mute)">(max ${tgt[2]})</span>`;
}

/* ───────────────── polling ───────────────── */
function poll(kind, id, render) {
  clearInterval(state.polls[kind]);
  const tick = async () => {
    let run;
    try { run = await api('/api/runs/' + id); }
    catch (e) { clearInterval(state.polls[kind]); render({ status: 'error', error: e.message }); return; }
    render(run);
    if (run.status !== 'running') { clearInterval(state.polls[kind]); loadHistory(); }
  };
  tick();
  state.polls[kind] = setInterval(tick, 1200);
}
const progressHTML = r => `
  <div class="card"><div class="prog">
    <div class="spin"></div>
    <div style="min-width:190px">${esc(r.stage || 'Starting…')}</div>
    <div class="bar"><span style="width:${Math.round((r.progress || 0) * 100)}%"></span></div>
    <div class="mono" style="font-size:12px">${Math.round((r.progress || 0) * 100)}%</div>
  </div></div>`;
const errorHTML = r => `<div class="card"><div class="err"><b>Run failed.</b><br>${esc(r.error || 'Unknown error')}</div></div>`;

const KIND_TITLE = {
  no_key: 'No API key for this provider',
  auth: 'The API key was rejected',
  missing_model: 'That model is not available here',
  needs_plan: 'That model is not in your plan',
  rate_limited: 'Rate limited',
  unreachable: 'Could not reach the model',
};

function connHTML(info, alts) {
  const opts = (alts || []).map(a => {
    // Put the models most likely to work for this provider at the top.
    const pref = PREFERRED[a.provider] || [];
    const models = [...a.models].sort((x, y) => {
      const ix = pref.indexOf(x), iy = pref.indexOf(y);
      if (ix !== -1 || iy !== -1) return (ix === -1 ? 99 : ix) - (iy === -1 ? 99 : iy);
      return x.localeCompare(y);
    });
    return `<optgroup label="${esc(a.label)}">` +
      models.map(m => `<option value="${esc(a.provider)}|${esc(m)}">${esc(m)}</option>`).join('') +
      `</optgroup>`;
  }).join('');
  return `<div class="card conn">
    <h3>${esc(KIND_TITLE[info.kind] || 'Could not reach the model')}</h3>
    <p>${esc(info.message || info.error || '')}</p>
    ${info.hint ? `<p class="hint">${esc(info.hint)}</p>` : ''}
    ${opts ? `<div class="swap">
      <div><label for="swapModel">Switch to a model that is reachable now</label>
        <select id="swapModel">${opts}</select></div>
      <div></div>
      <button class="btn btn-primary" id="swapRetry">Use it &amp; retry</button>
    </div>` : `<p class="hint">No other provider is configured. Add a key in the sidebar or start Ollama.</p>`}
  </div>`;
}

async function showConnProblem(container, res, retry) {
  const alts = res.alternatives || (await api('/api/check', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg()),
  }).then(r => r.alternatives).catch(() => []));
  container.innerHTML = connHTML(res, alts) + (container === $('#view-new') ? '' : '');
  $('#swapRetry')?.addEventListener('click', () => {
    const [prov, model] = $('#swapModel').value.split('|');
    $('#provider').value = prov;
    syncProviderFields();
    $('#model').value = model;
    saveCfg();
    setModelStatus('', '');
    if (retry) retry(); else testModel(false);
  });
}

/* ───────────────── renderers ───────────────── */
const ringColour = v => v >= 4.5 ? 'var(--brand-d)' : v >= 3.5 ? 'var(--brand)' : v >= 3 ? 'var(--amber)' : 'var(--bad)';

function errorTable(list, title) {
  if (!list || !list.length) return '';
  return `<div class="card">
    <div class="card-h"><h3>${esc(title)}</h3><span class="sub">${list.length} found</span></div>
    <table><thead><tr><th style="width:29%">You wrote</th><th style="width:16%">Problem</th>
      <th style="width:29%">Correct</th><th>Rule</th><th style="width:60px"></th></tr></thead><tbody>
      ${list.map(e => `<tr>
        <td class="wrong">${esc(e.original)}</td>
        <td>${esc(e.problem)}</td>
        <td class="right">${esc(e.correction)}</td>
        <td class="why">${esc(e.rule)}</td>
        <td><span class="sev ${esc(e.severity)}">${esc(e.severity)}</span></td>
      </tr>`).join('')}
    </tbody></table></div>`;
}

function renderGrade(r) {
  const el = $('#gradeOut');
  if (r.status === 'running') { el.innerHTML = progressHTML(r); return; }
  if (r.status === 'error') {
    const cp = r.result && r.result.connection_problem;
    if (cp) { showConnProblem(el, { ...cp, alternatives: null }, () => retryRun(r)); }
    else el.innerHTML = errorHTML(r);
    return;
  }
  const R = r.result || {}, v = R.verdict || {}, st = R.stats || {};
  const score = Number(v.score ?? 0), pct = (score / 5) * 100;

  const charts = R.charts || {};
  const chartImgs = ['subscores', 'errors', 'length', 'pace', 'checklist']
    .filter(k => charts[k]).map(k => `<img src="${charts[k]}?t=${r.updated_at}" alt="${k}">`).join('');

  el.innerHTML = `
  <div class="card">
    <div class="verdict">
      <div class="score-ring" style="--pct:${pct};--ring-c:${ringColour(score)}">
        <div><b>${score}</b><i>OUT OF 5</i></div>
      </div>
      <div class="verdict-body">
        <h2>${esc(r.title || '')}</h2>
        <p>${esc(v.justification || '')}</p>
        ${v.main_limiter ? `<div class="limiter">▸ Main limiter: ${esc(v.main_limiter)}</div>` : ''}
        <div class="pills" style="margin-top:11px">
          <span class="pill mute">${st.words || 0} words</span>
          <span class="pill mute">${st.sentences || 0} sentences</span>
          ${st.wpm ? `<span class="pill ${st.wpm >= 110 ? '' : 'bad'}">${st.wpm} wpm</span>` : ''}
          <span class="pill mute">${r.model || ''}</span>
        </div>
      </div>
    </div>
    <div class="actions" style="margin-top:16px">
      <button class="btn btn-primary" id="goModel">Generate my 5/5 answer →</button>
      <button class="btn btn-ghost" id="goLesson">Build lesson &amp; drills →</button>
      <a class="btn btn-ghost" href="/api/runs/${r.id}/export" download>Export .md</a>
    </div>
  </div>

  ${(v.strengths?.length || v.upgrade_plan?.length) ? `<div class="grid2">
    ${v.strengths?.length ? `<div class="card"><div class="card-h"><h3>What already works</h3></div>
      <ul class="clean">${v.strengths.map(s => `<li>${esc(s)}</li>`).join('')}</ul></div>` : ''}
    ${v.upgrade_plan?.length ? `<div class="card"><div class="card-h"><h3>3-step upgrade plan</h3></div>
      <ol class="steps">${v.upgrade_plan.map(s => `<li>${esc(s)}</li>`).join('')}</ol></div>` : ''}
  </div>` : ''}

  ${chartImgs ? `<div class="card"><div class="card-h"><h3>Diagnostics</h3>
      <span class="sub">generated with matplotlib</span></div>
      <div class="charts">${chartImgs}</div></div>` : ''}

  ${(R.subscores || []).length ? `<div class="card">
    <div class="card-h"><h3>Rubric sub-scores</h3><span class="sub">ETS 2026 criteria</span></div>
    <table><thead><tr><th style="width:34%">Dimension</th><th style="width:70px">Score</th><th>Evidence</th></tr></thead><tbody>
    ${R.subscores.map(s => `<tr><td><b>${esc(s.dimension)}</b></td>
      <td><span class="pill ${s.score >= 4 ? '' : s.score >= 3 ? 'amber' : 'bad'}">${s.score}</span></td>
      <td class="why">${esc(s.comment)}</td></tr>`).join('')}
    </tbody></table></div>` : ''}

  ${errorTable(R.errors?.grammar, 'Grammar errors')}
  ${errorTable(R.errors?.vocabulary, 'Vocabulary & collocation errors')}
  ${errorTable(R.errors?.mechanics, 'Mechanics errors')}
  ${errorTable(R.errors?.delivery, 'Delivery problems')}

  ${(R.checklist || []).length ? `<div class="card">
    <div class="card-h"><h3>ETS 2026 self-grading checklist</h3></div>
    <div class="checks">${R.checklist.map(c => {
      const k = c.pass === true ? 'ok' : c.pass === false ? 'no' : 'na';
      const m = c.pass === true ? '✓' : c.pass === false ? '✕' : '–';
      return `<div class="chk ${k}"><div class="mk">${m}</div>
        <div>${esc(c.label)}</div><div class="dt">${esc(c.detail)}</div></div>`;
    }).join('')}</div></div>` : ''}

  ${renderTaskCheck(r.task, R.task_check)}`;

  $('#goModel')?.addEventListener('click', () => startDerived('model'));
  $('#goLesson')?.addEventListener('click', () => startDerived('lesson'));
}

function renderTaskCheck(task, tc) {
  if (!tc) return '';
  let rows = '';
  if (task === 'email' && Array.isArray(tc.bullets)) {
    rows = tc.bullets.map(b => `<div class="chk ${b.addressed ? 'ok' : 'no'}">
      <div class="mk">${b.addressed ? '✓' : '✕'}</div>
      <div>${esc(b.bullet)}</div>
      <div class="dt">${esc((b.evidence || '').slice(0, 60))}</div></div>`).join('');
  } else {
    const map = task === 'discussion'
      ? [['position_stated', 'Position clearly stated', 'position'],
         ['contribution_ok', 'Adds a new idea', 'contribution_detail'],
         ['has_example', 'Uses a concrete example', 'example_detail'],
         ['has_mechanism', 'Explains how the example proves the claim', 'mechanism_detail'],
         ['on_topic', 'Stays on topic', 'on_topic_detail']]
      : [['forced_choice_answered', 'Forced choice answered in sentence 1', 'forced_choice_detail'],
         ['elaboration_ok', 'Concrete, developed example', 'elaboration_detail'],
         ['complete_ending', 'Finishes the final sentence', 'ending_detail'],
         ['strong_phrase_ok', 'Uses a strong phrase or expression', 'strong_phrase_detail'],
         ['on_topic', 'Stays on topic', 'on_topic_detail']];
    rows = map.map(([k, label, d]) => {
      const val = tc[k];
      const cls = val === true ? 'ok' : val === false ? 'no' : 'na';
      const m = val === true ? '✓' : val === false ? '✕' : '–';
      return `<div class="chk ${cls}"><div class="mk">${m}</div><div>${esc(label)}</div>
        <div class="dt">${esc(String(tc[d] ?? '').slice(0, 70))}</div></div>`;
    }).join('');
  }
  return `<div class="card"><div class="card-h"><h3>Task completion</h3>
    <span class="sub">${esc(tc.summary || '')}</span></div>
    <div class="checks">${rows}</div></div>`;
}

function renderModel(r) {
  const el = $('#modelOut');
  if (r.status === 'running') { el.innerHTML = progressHTML(r); return; }
  if (r.status === 'error') {
    const cp = r.result && r.result.connection_problem;
    if (cp) { showConnProblem(el, { ...cp, alternatives: null }, () => retryRun(r)); }
    else el.innerHTML = errorHTML(r);
    return;
  }
  const R = r.result || {}, ideas = R.ideas || {}, ms = R.model_stats || {};
  const d = R.delivery || {};

  el.innerHTML = `
  ${ideas.main_ideas?.length ? `<div class="card">
    <div class="card-h"><h3>Your own ideas, extracted</h3>
      <span class="sub">the 5/5 answer is built from these, not from new content</span></div>
    ${ideas.position ? `<p style="margin:0 0 10px"><b>Position:</b> ${esc(ideas.position)}</p>` : ''}
    <ul class="clean">${ideas.main_ideas.map(i => `<li>${esc(i)}</li>`).join('')}</ul>
    ${ideas.examples?.length ? `<div style="margin-top:10px"><b style="font-size:13px">Your examples</b>
      <ul class="clean">${ideas.examples.map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>` : ''}
  </div>` : ''}

  ${R.corrected ? `<div class="card">
    <div class="card-h"><h3>Corrected version</h3>
      <span class="sub">your text, errors fixed, nothing added · ${R.corrected_stats?.words || 0} words</span></div>
    <div class="answer alt">${esc(R.corrected)}</div></div>` : ''}

  <div class="card">
    <div class="card-h"><h3>Full-score model answer</h3>
      <span class="sub">${ms.words || 0} words · ${ms.sentences || 0} sentences${R.length_ok === false ? ' · below ETS minimum' : ''}</span></div>
    <div class="answer">${esc(R.model_answer || '')}</div>
    <div class="actions" style="margin-top:12px">
      <button class="btn btn-ghost btn-sm" id="copyModel">Copy</button>
      <a class="btn btn-ghost btn-sm" href="/api/runs/${r.id}/export" download>Export .md</a>
      ${state.ids.grade ? '<button class="btn btn-ghost btn-sm" id="goLesson2">Build lesson &amp; drills →</button>' : ''}
    </div>
    ${R.verify_issues?.length ? `<div class="hint" style="margin-top:10px">
      Self-check fixed: ${R.verify_issues.map(esc).join('; ')}</div>` : ''}
  </div>

  ${d.chunked ? `<div class="card">
    <div class="card-h"><h3>Delivery script</h3><span class="sub">thought groups &amp; stress</span></div>
    <div class="answer mono">${esc(d.chunked)}</div>
    ${d.stress_words?.length ? `<div class="pills" style="margin-top:11px">
      ${d.stress_words.map(w => `<span class="pill">${esc(w)}</span>`).join('')}</div>` : ''}
    ${d.delivery_notes?.length ? `<ul class="clean" style="margin-top:11px">
      ${d.delivery_notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>` : ''}
  </div>` : ''}

  ${R.outline?.plan?.length ? `<div class="card">
    <div class="card-h"><h3>How it was built</h3><span class="sub">sentence plan</span></div>
    <table><thead><tr><th style="width:150px">Slot</th><th>Content</th></tr></thead><tbody>
    ${R.outline.plan.map(p => `<tr><td><b>${esc(p.slot)}</b></td><td>${esc(p.content)}</td></tr>`).join('')}
    </tbody></table></div>` : ''}`;

  $('#copyModel')?.addEventListener('click', e => {
    navigator.clipboard.writeText(R.model_answer || '');
    e.target.textContent = 'Copied';
    setTimeout(() => (e.target.textContent = 'Copy'), 1400);
  });
  $('#goLesson2')?.addEventListener('click', () => startDerived('lesson'));
}

function renderLesson(r) {
  const el = $('#lessonOut');
  if (r.status === 'running') { el.innerHTML = progressHTML(r); return; }
  if (r.status === 'error') {
    const cp = r.result && r.result.connection_problem;
    if (cp) { showConnProblem(el, { ...cp, alternatives: null }, () => retryRun(r)); }
    else el.innerHTML = errorHTML(r);
    return;
  }
  const R = r.result || {}, L = R.lessons || {}, D = R.drills || {}, P = R.study_plan || {};
  const TITLES = { grammar: 'Grammar', vocabulary: 'Vocabulary & collocation', mechanics: 'Mechanics', delivery: 'Delivery', structure: 'Task & structure' };

  const blocks = (R.categories || []).map(cat => {
    const l = L[cat] || {}, d = D[cat] || {};
    const pats = (l.patterns || []).map(p => `
      <div class="pattern">
        <h4>${esc(p.name)}</h4>
        <div>${esc(p.rule)}</div>
        ${p.root_cause ? `<div class="rootc"><b>Why you do this:</b> ${esc(p.root_cause)}</div>` : ''}
        ${(p.your_examples || []).length ? `<table style="margin-top:6px"><tbody>
          ${p.your_examples.map(x => `<tr><td class="wrong" style="width:46%">${esc(x.wrong)}</td>
            <td class="right">${esc(x.right)}</td></tr>`).join('')}</tbody></table>` : ''}
        ${p.quick_test ? `<div class="qt">Self-check: ${esc(p.quick_test)}</div>` : ''}
      </div>`).join('');

    const items = (d.items || []).map(i => `
      <div class="drill-item"><div class="n">${i.n}</div><div>
        <div>${esc(i.prompt)}</div>
        <div class="drill-a hidden" title="click to reveal">${esc(i.answer)}${i.why ? ` <span class="why">— ${esc(i.why)}</span>` : ''}</div>
      </div></div>`).join('');

    return `<div class="card">
      <div class="card-h"><h3>${esc(TITLES[cat] || cat)}</h3>
        <span class="sub">${esc(l.headline || '')}</span></div>
      ${pats}
      ${(l.memorise || []).length ? `<div style="margin:12px 0 4px"><b style="font-size:13px">Memorise these</b>
        <div class="pills" style="margin-top:7px">${l.memorise.map(m => `<span class="pill">${esc(m)}</span>`).join('')}</div></div>` : ''}
      ${items ? `<div style="margin-top:16px;padding-top:14px;border-top:1px solid var(--line)">
        <div class="card-h"><h3 style="font-size:14px">Drills</h3>
          <span class="sub">${esc(d.instructions || '')} · click a blurred answer to reveal</span></div>
        ${items}
        ${d.spoken_drill ? `<div class="rootc" style="margin-top:12px"><b>Say it aloud:</b> ${esc(d.spoken_drill)}</div>` : ''}
      </div>` : ''}
    </div>`;
  }).join('');

  el.innerHTML = `<div class="card" style="padding:12px 20px"><div class="actions" style="margin:0">
      <a class="btn btn-ghost btn-sm" href="/api/runs/${r.id}/export" download>Export .md</a>
      <button class="btn btn-ghost btn-sm" id="revealAll">Reveal all answers</button>
    </div></div>` +
    (blocks || `<div class="empty"><h3>No errors to teach</h3>
    <p>The grading run found nothing to build a lesson from.</p></div>`) +
    ((P.days || []).length ? `<div class="card">
      <div class="card-h"><h3>7-day plan</h3>
        <span class="sub">${esc(P.single_highest_value_habit || '')}</span></div>
      <table><thead><tr><th style="width:56px">Day</th><th style="width:190px">Focus</th><th>Tasks</th></tr></thead><tbody>
      ${P.days.map(d => `<tr><td><b>${esc(d.day)}</b></td><td>${esc(d.focus)}</td>
        <td><ul class="clean">${(d.tasks || []).map(t => `<li>${esc(t)}</li>`).join('')}</ul></td></tr>`).join('')}
      </tbody></table></div>` : '');

  $$('.drill-a', el).forEach(a => a.addEventListener('click', () => a.classList.toggle('hidden')));
  $('#revealAll')?.addEventListener('click', e => {
    const hide = !$$('.drill-a.hidden', el).length;
    $$('.drill-a', el).forEach(a => a.classList.toggle('hidden', hide));
    e.target.textContent = hide ? 'Reveal all answers' : 'Hide all answers';
  });
}

async function retryRun(run) {
  if (run.kind === 'grade') {
    const p = run.payload || {};
    fillForm(run);
    await startGrade();
  } else {
    state.ids.grade = run.parent_id || state.ids.grade;
    await startDerived(run.kind);
  }
}

/* ───────────────── actions ───────────────── */
async function startGrade() {
  const q = $('#question').value.trim(), a = $('#response').value.trim();
  if (!q || !a) { alert('Please fill in both the task prompt and your answer.'); return; }
  if (!$('#model').value.trim()) { alert('Please choose a model in the sidebar.'); return; }
  saveCfg();
  const body = {
    task: state.task, question: q, response: a,
    classmate_a: $('#classA').value.trim(), classmate_b: $('#classB').value.trim(),
    duration_sec: state.task === 'speaking' && $('#duration').value
      ? parseFloat($('#duration').value) : null,
    llm: cfg(),
  };
  const btn = $('#btnGrade'); btn.disabled = true; btn.textContent = 'Starting…';
  try {
    const { id } = await api('/api/grade', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    state.ids = { grade: id, model: null, lesson: null };
    $('#modelOut').innerHTML = emptyDerived('5/5 answer');
    $('#lessonOut').innerHTML = emptyDerived('lesson & drills');
    setView('grade');
    poll('grade', id, renderGrade);
    loadHistory();
  } catch (e) { alert('Could not start: ' + e.message); }
  finally { btn.disabled = false; btn.textContent = 'Score & find errors'; }
}
const emptyDerived = what => `<div class="empty"><h3>Nothing here yet</h3>
  <p>Run a correction first, then generate the ${esc(what)} from the score page.</p></div>`;

async function startDerived(kind) {
  if (!state.ids.grade) { alert('Run a correction first.'); return; }
  saveCfg();
  const url = kind === 'model' ? '/api/model-answer' : '/api/lesson';
  setView(kind);
  const el = kind === 'model' ? $('#modelOut') : $('#lessonOut');
  el.innerHTML = progressHTML({ stage: 'Starting…', progress: 0.02 });
  try {
    const { id } = await api(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ grade_id: state.ids.grade, llm: cfg() }),
    });
    state.ids[kind] = id;
    poll(kind, id, kind === 'model' ? renderModel : renderLesson);
    loadHistory();
  } catch (e) { el.innerHTML = errorHTML({ error: e.message }); }
}

/* ───────────────── history ───────────────── */
async function loadHistory() {
  try {
    const { runs } = await api('/api/runs?limit=60');
    const KIND = { grade: 'Score', model: '5/5', lesson: 'Lesson' };
    $('#history').innerHTML = runs.map(r => `
      <button class="hist-item ${Object.values(state.ids).includes(r.id) ? 'on' : ''}" data-id="${r.id}" data-kind="${r.kind}">
        <b>${esc(r.title || r.task)}</b>
        <span><span class="dot ${r.status}"></span>${KIND[r.kind] || r.kind} · ${esc(r.model || '')}</span>
      </button>`).join('') || '<div class="hint">No runs yet.</div>';
    $$('.hist-item').forEach(b => b.addEventListener('click', () => openRun(b.dataset.id, b.dataset.kind)));
  } catch { /* ignore */ }
}
async function openRun(id, kind) {
  const run = await api('/api/runs/' + id);
  if (kind === 'grade') {
    state.ids = { grade: id, model: null, lesson: null };
    const { runs } = await api(`/api/runs/${id}/children`);
    for (const c of runs) if (!state.ids[c.kind]) state.ids[c.kind] = c.id;
    $('#modelOut').innerHTML = emptyDerived('5/5 answer');
    $('#lessonOut').innerHTML = emptyDerived('lesson & drills');
    if (state.ids.model) poll('model', state.ids.model, renderModel);
    if (state.ids.lesson) poll('lesson', state.ids.lesson, renderLesson);
    setView('grade'); poll('grade', id, renderGrade);
    if (run.payload) fillForm(run);
  } else {
    state.ids[kind] = id;
    if (run.parent_id) {
      state.ids.grade = run.parent_id;
      poll('grade', run.parent_id, renderGrade);
    }
    setView(kind);
    poll(kind, id, kind === 'model' ? renderModel : renderLesson);
  }
  loadHistory();
}
function fillForm(run) {
  const p = run.payload || {};
  setTask(run.task);
  $('#question').value = p.question || '';
  $('#response').value = p.response || '';
  $('#classA').value = p.classmate_a || '';
  $('#classB').value = p.classmate_b || '';
  $('#duration').value = p.duration_sec || '';
  updateCounter();
}

/* ───────────────── samples ───────────────── */
const SAMPLES = {
  email: {
    q: `You recently stayed at a hotel during a campus visit. While you generally liked the room, there were some issues with the room during your stay. You need to provide feedback to the hotel manager, Ms. Thompson.

Write an email to Ms. Thompson. In your email, do the following:
• Describe what you liked about your stay.
• Explain the problems you experienced.
• Suggest what the hotel could do to improve.`,
    a: `Dear Ms. Thompson,
I hope this email finds you well. I'm writing to give you a feedback about my previous experience in your hotel. Firstly the room was clean and the staff was so kind, and the breakfast was delicious. However there were some problems, the air conditioning didn't work well and there were still a bad smell in the room. Also I recieved my room service too much later than what we've expected. I suggest you to check the air conditioning system regulary and hire more staff for room service. Althogh these problems, I enjoyed my stay.
Best refards,
Farhadi`,
  },
  discussion: {
    q: `Dr. Diaz: We've been discussing strategic growth in corporations. Businesses may often choose to expand globally or prefer instead to deepen local roots. Global growth offers access to new markets and new resources, but can dilute brand identity and strain resources. A local focus builds community trust, adapts to regional needs, and strengthens customer loyalty. Do you think corporations should concentrate more on expansion or local business? Why?`,
    a: `I concur with Claire's perspective that global expansion leads to better oppotunities and more profit. While her argument is valid, I would add that cost of products or services is ususally the most pivotal factor in customer's deciscion making process. Hence some global companies which can reduce their prices to the lowest price, may outweight some local buisnesses which are not capable to lower their prices to that level. For instance, consider cosco supermarkets that selling their products at lowest possible price and people usually prefer to buy from these franchized stroes. This clearly demonstrates that expansion to global markets give buisnesses some undeniable advantages. Paul raises a relevant point about loyalty and trust; however he overlooked the fact that some factors like lower prices plays more significant roles. Therefore, althogh local buisnesses have some important advantages, but global expansion have more merits.`,
    ca: `Claire: Global expansion is vital because it can broaden talent pools, increase innovation, and improve competitiveness and resilience across markets.`,
    cb: `Paul: A local focus supports regional economies, allows companies to tailor offerings, and can build trust, loyalty, authenticity, and lasting community impact.`,
  },
  speaking: {
    q: `Imagine that you could choose to commute by car, which is faster but more expensive, or by public transportation, which is slower but less expensive. Which would you choose, and why?`,
    a: `Well, I choose the public transportation because I'm an student and I don't have a lot of income. So I cannot afford other transportation options. Moreover, I want to contribute to some environmental concerns and this will help me through that. Besides, I can do my own works, for example, reading books on my commuting time with public transportation. So overall, yes, I will choose public transportation.`,
    dur: 45,
  },
};
function loadSample() {
  const s = SAMPLES[state.task];
  $('#question').value = s.q;
  $('#response').value = s.a;
  $('#classA').value = s.ca || '';
  $('#classB').value = s.cb || '';
  $('#duration').value = s.dur || '';
  updateCounter();
}

/* ───────────────── boot ───────────────── */
loadCfg();
syncProviderFields();
api('/api/health')
  .then(h => {
    SERVER_DEFAULTS = h.defaults || {};
    PROVIDERS = h.providers || [];
    const saved = (() => { try { return JSON.parse(localStorage.getItem(LS) || '{}').provider; } catch { return null; } })();
    renderProviders(saved || SERVER_DEFAULTS.provider);
    syncProviderFields();
  })
  .catch(() => {})
  .finally(() => refreshModels().then(() => testModel(true)));
setTask('email');
loadHistory();

$$('#tabs .tab').forEach(t => t.addEventListener('click', () => setView(t.dataset.view)));
$$('#taskTabs .tab').forEach(t => t.addEventListener('click', () => setTask(t.dataset.task)));
$('#provider').addEventListener('change', () => {
  syncProviderFields();
  $('#model').value = '';
  saveCfg();
  refreshModels().then(() => testModel(true));
});
$('#refreshModels').addEventListener('click', () => refreshModels().then(() => testModel(true)));
$('#testModel').addEventListener('click', () => testModel(false));
$('#model').addEventListener('input', () => setModelStatus(''));
$('#model').addEventListener('change', () => { saveCfg(); testModel(true); });
$('#response').addEventListener('input', updateCounter);
$('#btnGrade').addEventListener('click', startGrade);
$('#btnSample').addEventListener('click', loadSample);
$('#btnClear').addEventListener('click', () => {
  ['#question', '#response', '#classA', '#classB', '#duration'].forEach(s => ($(s).value = ''));
  updateCounter();
});
$('#modelOut').innerHTML = emptyDerived('5/5 answer');
$('#lessonOut').innerHTML = emptyDerived('lesson & drills');
setInterval(loadHistory, 8000);
