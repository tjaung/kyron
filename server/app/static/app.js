const runButton = document.querySelector('#run');
const selection = document.querySelector('#scenario');
const statusLine = document.querySelector('#status');
const calls = new Map();
let connected = false;
let running = false;
let submitting = false;
let simulatorAvailable = false;
let previousStatus = '';

function updateButton() {
  runButton.disabled = !connected || !simulatorAvailable || running || submitting;
  runButton.textContent = running ? 'Simulation in progress…' : selection.value ? 'Run selected scenario →' : 'Simulate random conversation →';
}

function pair(list, label, value) {
  const group = document.createElement('div');
  const term = document.createElement('dt');
  const definition = document.createElement('dd');
  term.textContent = label;
  definition.textContent = value || '—';
  group.append(term, definition);
  list.append(group);
}

function createCall(metadata) {
  if (calls.has(metadata.id)) return;
  const card = document.querySelector('#call-template').content.firstElementChild.cloneNode(true);
  card.dataset.conversationId = metadata.id;
  card.querySelector('.scenario-name').textContent = metadata.scenario_name;
  card.querySelector('h3').textContent = metadata.name.split(' · ').slice(1).join(' · ') || metadata.name;
  const details = card.querySelector('.metadata');
  pair(details, 'Patient', metadata.patient_name);
  pair(details, 'Practice', metadata.practice_name);
  pair(details, 'Prescription', metadata.medication_name);
  pair(details, 'Started', new Date(metadata.start_time).toLocaleTimeString());
  const ids = card.querySelector('.ids dl');
  for (const key of ['id', 'practice_id', 'patient_practice_id', 'prescription_id', 'source_conversation_id', 'next_conversation']) {
    pair(ids, key.replaceAll('_', ' '), metadata[key]);
  }
  document.querySelector('#conversations').prepend(card);
  document.querySelector('#empty').hidden = true;
  calls.set(metadata.id, {card, turns: new Map()});
  document.querySelector('#count').textContent = `${calls.size} call${calls.size === 1 ? '' : 's'}`;
}

function accept(event) {
  if (event.type === 'conversation.created') { createCall(event.metadata); return; }
  const call = calls.get(event.conversation_id);
  if (!call) return;
  const feed = call.card.querySelector('.transcript');
  const atBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
  if (event.type === 'transcript.started') {
    const turn = document.createElement('div');
    turn.className = `turn speaking ${event.speaker === 'ai_agent' ? 'ai' : ''}`;
    const speaker = document.createElement('span');
    speaker.className = 'speaker';
    speaker.textContent = event.speaker.replaceAll('_', ' ');
    const speech = document.createElement('p');
    speech.className = 'speech';
    turn.append(speaker, speech);
    feed.append(turn);
    call.turns.set(event.transcript_id, turn);
  } else if (event.type === 'transcript.word') {
    const speech = call.turns.get(event.transcript_id)?.querySelector('.speech');
    if (speech) speech.append(document.createTextNode(event.delta));
  } else if (event.type === 'transcript.completed') {
    call.turns.get(event.transcript_id)?.classList.remove('speaking');
  } else if (event.type === 'action.simulated') {
    const action = document.createElement('aside');
    action.className = 'action';
    const title = document.createElement('strong');
    title.textContent = `${event.transcript_id ? 'During call' : 'After call'} · ${event.action.replaceAll('_', ' ')}`;
    const reason = document.createElement('p');
    reason.textContent = event.reason;
    action.append(title, reason);
    feed.append(action);
  } else if (event.type === 'conversation.ended' || event.type === 'replay.completed') {
    const badge = call.card.querySelector('.call-status');
    badge.textContent = event.type === 'replay.completed' ? 'Completed' : 'Call ended';
    badge.classList.remove('live');
  }
  if (atBottom) feed.scrollTop = feed.scrollHeight;
}

const stream = new EventSource('/api/events');
stream.onopen = () => {
  connected = true;
  document.querySelector('#connection').textContent = 'Live connection';
  document.querySelector('#connection').classList.add('live');
  updateButton();
};
stream.onerror = () => {
  connected = false;
  document.querySelector('#connection').textContent = 'Reconnecting…';
  document.querySelector('#connection').classList.remove('live');
  updateButton();
};
stream.onmessage = event => accept(JSON.parse(event.data));

async function loadScenarios() {
  const response = await fetch('/api/simulations');
  if (!response.ok) throw new Error('Could not load scenarios');
  const scenarios = await response.json();
  const selected = selection.value;
  selection.replaceChildren(new Option('Random unused scenario', ''));
  for (const scenario of scenarios) {
    const option = new Option(scenario.name.split(' · ')[0] + (scenario.is_used ? ' (used)' : ''), scenario.conversation_id);
    option.disabled = scenario.is_used;
    selection.append(option);
  }
  if (scenarios.some(item => item.conversation_id === selected && !item.is_used)) selection.value = selected;
  updateButton();
}

async function refreshStatus() {
  try {
    const response = await fetch('/api/simulations/status');
    if (!response.ok) throw new Error('Simulator is unavailable. Waiting to reconnect…');
    const state = await response.json();
    simulatorAvailable = true;
    running = state.status === 'running';
    statusLine.classList.toggle('error', state.status === 'failed');
    const completed = state.completed_conversations?.length || 0;
    const messages = {
      idle: 'Ready · Five scenarios, each with linked follow-up calls.',
      running: `${completed} calls completed · ${state.name || 'Starting conversation…'}`,
      completed: `Scenario complete · ${completed} calls replayed. Choose another scenario to continue.`,
      empty: 'No unused starting conversations are available.',
      failed: `Replay stopped (${state.error}). Completed calls were saved; the failed call remains unused.`,
    };
    if (!submitting) statusLine.textContent = messages[state.status] || state.status;
    if (state.status !== previousStatus && !running) await loadScenarios();
    previousStatus = state.status;
  } catch (error) {
    simulatorAvailable = false;
    statusLine.textContent = error.message;
    statusLine.classList.add('error');
  } finally {
    updateButton();
    setTimeout(refreshStatus, 1000);
  }
}

selection.addEventListener('change', updateButton);
runButton.addEventListener('click', async () => {
  submitting = true;
  updateButton();
  statusLine.classList.remove('error');
  statusLine.textContent = 'Starting simulation…';
  const path = selection.value ? `/api/simulations/${selection.value}/run` : '/api/simulations/random';
  try {
    const response = await fetch(path, {method: 'POST'});
    if (!response.ok) {
      const body = await response.json();
      throw new Error(body.detail || 'Could not start the simulation');
    }
    running = true;
  } catch (error) {
    statusLine.textContent = error.message;
    statusLine.classList.add('error');
  } finally {
    submitting = false;
    updateButton();
  }
});
refreshStatus();
