'use strict';

const $ = (selector) => document.querySelector(selector);
const schemes = ['gbn', 'sr', 'fixed', 'adaptive'];
const names = { gbn: 'Go-Back-N', sr: 'Selective Repeat', fixed: 'Fixed XOR', adaptive: 'Adaptive FEC' };
const colors = { ink: '#25333b', muted: '#59645f', orange: '#b83f16', teal: '#1d7168', data: '#b4c8d2', dataLine: '#466578', rule: '#c4c9bf', panel: '#f7f5ee' };
const state = { response: null, scheme: 'gbn', time: 0, playing: false, frame: 0, previousTick: 0, speed: 1, busy: false, udp: null, controllerIndex: -1, udpBusy: false };
const canvas = $('#packet-canvas');
const ctx = canvas.getContext('2d');
const format = (value, digits = 2) => Number(value).toFixed(digits);
const row = () => state.response?.results.find(result => result.scheme === state.scheme);
const duration = () => Math.max(0.001, row()?.sender_completion_time_s || 0.001);

async function request(path, settings) {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'The operation could not complete. Try again.');
  return result;
}

function settings() {
  return { scenario: $('#scenario').value, loss_percent: Number($('#loss').value), delay_ms: Number($('#delay').value),
    bandwidth_mbps: Number($('#bandwidth').value), file_kib: Number($('#file-size').value),
    window: Number($('#window')?.value || 32), seed: Number($('#seed')?.value || 7), ack_loss_percent: Number($('#ack-loss')?.value || 0) };
}

function socketSettings() {
  const {file_kib, ...config} = settings();
  return {...config, scheme: $('#socket-scheme').value};
}

function recordedSocketSettings(config) {
  const channel = config.channel;
  return {scenario: channel.phases.length ? 'changing' : channel.model === 'gilbert-elliott' ? 'burst' : 'random',
    loss_percent: (channel.phases.length ? channel.phases[0][1] : channel.loss) * 100,
    delay_ms: channel.delay_ms, bandwidth_mbps: channel.bandwidth_mbps, window: config.window,
    seed: config.seed, ack_loss_percent: channel.ack_loss * 100, scheme: config.scheme};
}

function socketSummary(config) {
  const model = {random: 'independent', burst: 'burst', changing: 'changing'}[config.scenario];
  return `32 KiB · ${names[config.scheme]} · ${model} loss ${config.loss_percent}% · ${config.delay_ms} ms · ${config.bandwidth_mbps} Mbps · window ${config.window} · ACK loss ${config.ack_loss_percent}% · seed ${config.seed}`;
}

function rangeLabels() {
  $('#loss-value').textContent = `${$('#loss').value}%`;
  $('#delay-value').textContent = `${$('#delay').value} ms`;
  $('#bandwidth-value').textContent = `${Number($('#bandwidth').value)} Mbps`;
  const nextSocket = socketSettings();
  $('#udp-config').textContent = `Next socket trial: ${socketSummary(nextSocket)}`;
  if (state.udp && !$('#udp-result').hidden) {
    const recorded = recordedSocketSettings(state.udp.config);
    $('#socket-stale').hidden = Object.keys(recorded).every(key => recorded[key] === nextSocket[key]);
  }
}

async function compare(event) {
  event?.preventDefault();
  if (state.busy || !$('#settings').reportValidity()) return;
  state.busy = true;
  pause();
  const button = $('#run');
  button.disabled = true;
  button.querySelector('span').textContent = 'Running four schemes…';
  for (const preset of document.querySelectorAll('[data-preset]')) preset.disabled = true;
  $('#run-status').classList.remove('error');
  $('#run-status').textContent = '';
  $('#settings').setAttribute('aria-busy', 'true');
  const runSettings = settings();
  try {
    state.response = await request('/api/simulate', runSettings);
    state.controllerIndex = -1;
    state.time = Math.min(0.04, duration() / 2);
    renderResults();
    selectScheme(state.scheme, false);
    renderDetails();
    $('#play').disabled = false;
    $('#scrubber').disabled = false;
    if (JSON.stringify(settings()) !== JSON.stringify(runSettings)) $('#run-status').textContent = 'Settings changed during the run. Run comparison to apply them.';
    if (!state.response.all_verified) {
      $('#run-status').classList.add('error');
      $('#run-status').textContent = 'At least one transfer hit the event limit. Try a smaller file or lower loss; incomplete rows are marked.';
    }
  } catch (error) {
    $('#run-status').classList.add('error');
    $('#run-status').textContent = error.message;
  } finally {
    state.busy = false;
    button.disabled = false;
    button.querySelector('span').textContent = 'Run comparison';
    for (const preset of document.querySelectorAll('[data-preset]')) preset.disabled = false;
    $('#settings').removeAttribute('aria-busy');
  }
}

function renderResults() {
  const results = state.response.results;
  const metrics = [
    { label: 'Goodput (Mbps)', value: r => r.goodput_mbps, display: r => format(r.goodput_mbps) },
    { label: 'Completion (s)', value: r => r.completion_time_s, display: r => format(r.completion_time_s) },
    { label: 'Retries', value: r => r.retransmissions, display: r => String(r.retransmissions) },
  ];
  const body = $('#results-body');
  body.replaceChildren();
  function makeRow(label) {
    const tr = document.createElement('tr');
    const th = document.createElement('th');
    th.scope = 'row'; th.textContent = label; tr.append(th); body.append(tr);
    return tr;
  }
  for (const metric of metrics) {
    const tr = makeRow(metric.label);
    const maximum = Math.max(...results.map(metric.value), 0.001);
    for (const result of results) {
      const td = document.createElement('td'); td.dataset.column = result.scheme;
      const measure = document.createElement('div'); measure.className = 'measure';
      const value = document.createElement('span'); value.className = 'value'; value.textContent = metric.display(result);
      const track = document.createElement('div'); track.className = 'bar-track'; track.setAttribute('aria-hidden', 'true');
      const bar = document.createElement('div'); bar.className = 'bar';
      bar.style.setProperty('--bar-width', `${Math.min(100, metric.value(result) / maximum * 100)}%`);
      track.append(bar); measure.append(value, track); td.append(measure); tr.append(td);
    }
  }
  const parity = makeRow('Added parity');
  for (const result of results) {
    const td = document.createElement('td'); td.dataset.column = result.scheme;
    const value = document.createElement('span'); value.className = 'parity-value';
    value.textContent = `${result.parity_packets} KiB (${format(result.parity_overhead_ratio * 100, 0)}%)`;
    td.append(value); parity.append(td);
  }
  const check = makeRow('Byte check');
  for (const result of results) {
    const td = document.createElement('td'); td.dataset.column = result.scheme;
    const status = document.createElement('span'); status.className = `byte-check${result.integrity_verified ? '' : ' incomplete'}`;
    if (result.integrity_verified) {
      status.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4 10-10"/></svg>';
    }
    status.append(document.createTextNode(result.integrity_verified ? 'Verified' : 'Incomplete'));
    td.append(status); check.append(td);
  }
}

function selectScheme(scheme, reset = true) {
  if (reset) pause();
  state.scheme = scheme;
  if (reset) state.time = Math.min(0.04, duration() / 2);
  state.time = Math.min(state.time, duration());
  for (const button of document.querySelectorAll('[data-scheme]')) {
    const selected = button.dataset.scheme === scheme;
    button.setAttribute('aria-selected', String(selected)); button.tabIndex = selected ? 0 : -1;
  }
  for (const cell of document.querySelectorAll('[data-column]')) cell.classList.toggle('selected-column', cell.dataset.column === scheme);
  $('#journey-panel').setAttribute('aria-labelledby', `tab-${scheme}`);
  draw(); renderController(); renderScheme();
}

function pause() {
  state.playing = false; cancelAnimationFrame(state.frame);
  $('#play').setAttribute('aria-label', 'Play packet replay');
  $('#play').innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path class="filled" d="m8 5 11 7-11 7Z"/></svg>';
}

function play() {
  if (!row()) return;
  if (state.playing) { pause(); return; }
  if (state.time >= duration()) state.time = 0;
  state.playing = true; state.previousTick = performance.now();
  $('#play').setAttribute('aria-label', 'Pause packet replay');
  $('#play').innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path class="filled" d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>';
  function tick(now) {
    state.time = Math.min(duration(), state.time + Math.min((now - state.previousTick) / 1000, 0.15) * state.speed);
    state.previousTick = now; draw(); renderController();
    if (state.time >= duration()) pause();
    else state.frame = requestAnimationFrame(tick);
  }
  state.frame = requestAnimationFrame(tick);
}

function arrow(x1, y1, x2, y2, color = colors.ink) {
  ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  const direction = x2 > x1 ? 1 : -1;
  ctx.beginPath(); ctx.moveTo(x2, y2); ctx.lineTo(x2 - 9 * direction, y2 - 5); ctx.lineTo(x2 - 9 * direction, y2 + 5); ctx.closePath(); ctx.fill();
}

function endpoint(x, y, width, height, label, receiver = false) {
  ctx.fillStyle = receiver ? '#d9e8df' : '#dae2e5'; ctx.strokeStyle = receiver ? colors.teal : colors.dataLine;
  ctx.lineWidth = 1.2; ctx.beginPath(); ctx.roundRect(x, y, width, height, 7); ctx.fill(); ctx.stroke();
  ctx.fillStyle = colors.ink; ctx.font = '700 17px Atkinson'; ctx.textAlign = 'center'; ctx.fillText(label, x + width / 2, y + height / 2 + 5);
}

function draw() {
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (!width || !height) return;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
  }
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height);
  const compact = width < 550;
  const labelWidth = compact ? 0 : 115, nodeWidth = compact ? 70 : 103;
  const left = labelWidth, right = width - nodeWidth - 2;
  const from = left + nodeWidth + 4, to = right - 10;
  const dataY = compact ? 88 : Math.min(69, height - 100);
  const ackY = compact ? 161 : Math.min(145, height - 28);
  endpoint(left, dataY - 28, nodeWidth, 72, 'Sender');
  endpoint(right, dataY - 28, nodeWidth, 72, 'Receiver', true);
  arrow(from - 4, dataY, to, dataY);
  ctx.strokeStyle = colors.ink; ctx.beginPath(); ctx.moveTo(right + nodeWidth / 2, dataY + 44); ctx.lineTo(right + nodeWidth / 2, ackY); ctx.lineTo(left + nodeWidth / 2, ackY); ctx.lineTo(left + nodeWidth / 2, dataY + 45); ctx.stroke();
  arrow(from + 15, ackY, left + nodeWidth / 2, ackY);
  ctx.fillStyle = colors.ink; ctx.font = '16px Atkinson'; ctx.textAlign = 'left';
  if (compact) { ctx.fillText('Data / parity', 2, 25); ctx.fillText('ACKs return', 2, height - 8); }
  else { ctx.fillText('Data / parity', 2, dataY - 14); ctx.fillText('(to receiver)', 2, dataY + 7); ctx.fillText('ACKs', 2, ackY - 4); ctx.fillText('(to sender)', 2, ackY + 17); }
  const result = row();
  let active = 0, sent = 0, losses = 0, lastLabelX = -100;
  const lossHold = Math.max(0.09, Math.min(0.35, duration() / 8));
  for (const event of result?.transmissions || []) {
    if (event.start_s > state.time) continue;
    sent += Number(event.kind === 'data');
    losses += Number(event.kind === 'data' && event.lost && event.arrival_s <= state.time);
    if (event.lost && state.time >= event.arrival_s && state.time <= event.arrival_s + lossHold) {
      const x = (from + to) / 2 + ((event.sequence ?? event.block_start ?? 0) % 5 - 2) * 12;
      const y = event.kind === 'ack' ? ackY : dataY - 18;
      ctx.strokeStyle = colors.orange; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.moveTo(x - 6, y - 6); ctx.lineTo(x + 6, y + 6); ctx.moveTo(x + 6, y - 6); ctx.lineTo(x - 6, y + 6); ctx.stroke();
      continue;
    }
    if (event.arrival_s < state.time || event.arrival_s === event.start_s) continue;
    active++;
    const progress = Math.min(1, Math.max(0, (state.time - event.start_s) / (event.arrival_s - event.start_s)));
    const x = event.kind === 'ack' ? to - (to - from) * progress : from + (to - from) * progress;
    const y = event.kind === 'ack' ? ackY : dataY - 18;
    ctx.lineWidth = 1.5; ctx.strokeStyle = event.kind === 'data' ? colors.dataLine : colors.teal;
    ctx.fillStyle = event.kind === 'data' ? colors.data : event.kind === 'parity' ? colors.teal : colors.panel;
    ctx.beginPath();
    if (event.kind === 'parity') { ctx.moveTo(x, y - 9); ctx.lineTo(x + 9, y); ctx.lineTo(x, y + 9); ctx.lineTo(x - 9, y); ctx.closePath(); }
    else ctx.arc(x, y, event.kind === 'data' ? 8 : 7, 0, Math.PI * 2);
    ctx.fill(); ctx.stroke();
    if (event.kind !== 'ack') {
      ctx.strokeStyle = colors.rule; ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(x, y + 12); ctx.lineTo(x, ackY - 10); ctx.stroke(); ctx.setLineDash([]);
      if (!compact && Math.abs(x - lastLabelX) > 30) {
        ctx.fillStyle = colors.ink; ctx.font = '14px Atkinson'; ctx.textAlign = 'center';
        ctx.fillText(event.kind === 'data' ? String(event.sequence + 1) : 'P', x, y - 16); lastLabelX = x;
      }
    }
  }
  if (!result) { ctx.fillStyle = colors.muted; ctx.textAlign = 'center'; ctx.font = '17px Atkinson'; ctx.fillText('Waiting for measured transmissions…', width / 2, 39); }
  $('#time-readout').textContent = `${format(state.time)} s / ${result ? format(duration()) + ' s' : '—'}`;
  $('#end-time').textContent = result ? `${format(duration())} s` : '—';
  $('#scrubber').value = String(Math.round(state.time / duration() * 1000));
  canvas.setAttribute('aria-label', `${names[state.scheme]} recorded replay at ${format(state.time)} seconds: ${sent} data transmissions started, ${losses} data losses recorded, ${active} transmissions in flight. Positions are illustrative.`);
  if ($('#replay-stats')) $('#replay-stats').textContent = `${sent} data sent · ${losses} data dropped · ${active} in flight`;
}

function modeName(mode) {
  return mode.startsWith('none-') ? `No parity / ${mode.slice(5)}` : mode.replace('xor-', 'XOR / ').replace('grid-', 'Grid / ');
}

function renderController(forcedIndex = null) {
  const trace = state.response?.results.find(result => result.scheme === 'adaptive')?.controller_trace || [];
  if (!trace.length) return;
  let index = Number($('#controller-block').value) || 0;
  if (forcedIndex !== null) index = forcedIndex;
  else if (state.scheme === 'adaptive') {
    index = 0;
    for (let i = 0; i < trace.length; i++) if (trace[i].time_s <= state.time) index = i;
  }
  if (index === state.controllerIndex) return;
  state.controllerIndex = index;
  const decision = trace[index];
  $('#controller-block').value = String(index);
  $('#protection-mode').textContent = modeName(decision.mode);
  $('#estimated-loss').textContent = `${format(decision.estimated_loss * 100, 1)}%`;
  $('#predicted-risk').textContent = `${format(decision.predicted_failure * 100, 2)}%`;
  $('#target-met').textContent = decision.target_met ? 'Met in model' : 'No feasible mode';
  $('#target-met').classList.toggle('unmet', !decision.target_met);
  for (const tr of $('#trace-body').children) tr.classList.toggle('current-decision', Number(tr.dataset.index) === index);
}

function renderScheme() {
  const result = row();
  if (!result) return;
  const explanations = {
    gbn: 'Go-Back-N resends the outstanding window after the oldest unacknowledged packet times out. Out-of-order data is discarded.',
    sr: 'Selective Repeat buffers out-of-order data and retries individual missing packets. It sends no parity.',
    fixed: 'Fixed XOR sends one repair packet per block of up to eight data packets. A single erasure can be repaired; unresolved data is retried.',
    adaptive: 'Adaptive FEC estimates original losses from block feedback, then selects no parity, XOR, or row-and-column XOR. Unresolved data is retried.'
  };
  $('#scheme-explanation').textContent = `${explanations[state.scheme]} This trial recovered ${result.fec_recovered} data packets through FEC and retried ${result.retransmissions} data transmissions.`;
}

function renderDetails() {
  const response = state.response, config = response.config;
  const scenarioNames = {random: 'independent loss', burst: 'burst loss', changing: 'changing loss'};
  let scenario = `${config.loss_percent}% ${scenarioNames[config.scenario]}`;
  if (config.scenario === 'changing') scenario = `changing loss: 0% initially, ${config.loss_percent}% at 0.25 s, 2% at 0.75 s, ${config.loss_percent}% at 1.2 s`;
  $('#trial-config').textContent = `Recorded trial: ${config.file_kib} KiB file · 1 KiB packets · ${scenario} · ${config.delay_ms} ms one-way · ${config.bandwidth_mbps} Mbps · window ${config.window} · ACK loss ${config.ack_loss_percent}% · seed ${config.seed}. Each scheme uses the same channel settings and seed; its transmissions consume random draws differently.`;
  $('#expected-digest').textContent = response.expected_sha256;
  $('#export-csv').disabled = false; $('#export-json').disabled = false;
  $('#export-status').textContent = '';
  const trace = response.results.find(result => result.scheme === 'adaptive').controller_trace;
  $('#controller-block').replaceChildren(); $('#trace-body').replaceChildren();
  for (const [index, decision] of trace.entries()) {
    const option = document.createElement('option'); option.value = String(index);
    option.textContent = `Packet ${decision.start_packet + 1} · ${format(decision.time_s, 3)} s · ${modeName(decision.mode)}`;
    $('#controller-block').append(option);
    const tr = document.createElement('tr'); tr.dataset.index = String(index);
    for (const value of [format(decision.time_s, 3), modeName(decision.mode), `${format(decision.estimated_loss * 100, 1)}%`, `${format(decision.predicted_failure * 100, 2)}%${decision.target_met ? '' : ' (unmet)'}`]) {
      const td = document.createElement('td'); td.textContent = value; tr.append(td);
    }
    $('#trace-body').append(tr);
  }
  $('#controller-block').disabled = !trace.length;
  $('#trace-summary').textContent = `Full controller trace (${trace.length} decisions)`;
  $('#restart').disabled = false;
  state.controllerIndex = -1; renderController(); renderScheme();
}

async function runUDP() {
  if (state.udpBusy || !$('#settings').reportValidity()) return;
  state.udpBusy = true;
  const button = $('#udp-run'), status = $('#udp-status'), config = settings();
  button.disabled = true; button.textContent = 'Transferring actual UDP bytes…';
  status.classList.remove('error'); status.textContent = 'Sending 32 KiB through three processes. This may take up to 30 seconds.';
  $('#udp-result').hidden = true;
  $('#socket-export').hidden = true;
  $('#socket-recorded').hidden = true;
  $('#socket-stale').hidden = true;
  const protocol = $('#socket-scheme').value;
  $('#socket-scheme').disabled = true;
  try {
    state.udp = await request('/api/socket', {...config, scheme: protocol});
    const result = state.udp, list = $('#udp-result'); list.replaceChildren();
    const values = [['Byte check', result.verified ? 'Verified · 32,768 bytes' : 'Mismatch'], ['Protocol / loss', `${names[protocol]} / ${config.scenario} ${config.loss_percent}%`], ['Sender wall time', `${format(result.sender.elapsed_s, 3)} s`], ['Data retries / parity', `${result.sender.retransmissions} / ${result.sender.parity_packets}`], ['Sender / proxy / receiver PIDs', result.processes.map(p => p.pid).reverse().join(' / ')], ['In-order releases', `${result.receiver.application_release_count} packets`], ['Received SHA-256', result.receiver.sha256]];
    for (const [label, value] of values) {
      const div = document.createElement('div'), dt = document.createElement('dt'), dd = document.createElement('dd');
      dt.textContent = label;
      if (label === 'Received SHA-256') { div.className = 'hash-row'; const code = document.createElement('code'); code.textContent = value; dd.append(code); }
      else dd.textContent = value;
      if (label === 'Byte check' && result.verified) dd.className = 'verified';
      div.append(dt, dd); list.append(div);
    }
    list.hidden = false;
    $('#socket-export').hidden = false;
    $('#socket-recorded').textContent = `Last completed socket trial: ${socketSummary(recordedSocketSettings(result.config))}`;
    $('#socket-recorded').hidden = false;
    status.textContent = result.verified ? 'The received bytes match the original.' : 'The received bytes differ. Restart the local server and retry.';
    status.classList.toggle('error', !result.verified);
  } catch (error) { status.classList.add('error'); status.textContent = error.message; }
  finally { state.udpBusy = false; button.disabled = false; button.textContent = 'Run socket transfer'; $('#socket-scheme').disabled = false; rangeLabels(); }
}

$('#socket-scheme').addEventListener('change', rangeLabels);
$('#socket-export').addEventListener('click', () => {
  if (!state.udp) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(state.udp, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a');
  link.href = url; link.download = `paritylab-socket-${state.udp.config.scheme}-seed-${state.udp.config.seed}.json`;
  document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  $('#udp-status').textContent = `Transfer JSON download requested for the ${state.udp.verified ? 'verified transfer' : 'completed socket trial'}.`;
});

function download(kind) {
  if (!state.response) return;
  let content, mime;
  if (kind === 'json') { content = JSON.stringify(state.response, null, 2); mime = 'application/json'; }
  else {
    const config = state.response.config;
    const keys = ['scheme','completed','integrity_verified','goodput_mbps','completion_time_s','sender_completion_time_s','retransmissions','parity_packets','fec_recovered','parity_overhead_ratio','sha256'];
    const configKeys = ['scenario','loss_percent','delay_ms','bandwidth_mbps','file_kib','window','ack_loss_percent','seed'];
    content = [...keys,...configKeys].join(',') + '\r\n' + state.response.results.map(result => [...keys.map(key => result[key]),...configKeys.map(key => config[key])].join(',')).join('\r\n') + '\r\n';
    mime = 'text/csv;charset=utf-8';
  }
  const url = URL.createObjectURL(new Blob([content], {type:mime})), link = document.createElement('a');
  link.href = url; link.download = `paritylab-${state.response.config.scenario}-seed-${state.response.config.seed}.${kind}`;
  document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  $('#export-status').textContent = `${kind.toUpperCase()} download requested for the recorded trial.`;
}

$('#settings').addEventListener('submit', compare);
$('#settings').addEventListener('input', () => {
  rangeLabels();
  if (state.response) { $('#run-status').classList.remove('error'); $('#run-status').textContent = 'Settings changed. Run comparison to apply them; the displayed results are the recorded trial.'; }
});
$('#play').addEventListener('click', play);
$('#scrubber').addEventListener('input', () => { pause(); state.time = Number($('#scrubber').value) / 1000 * duration(); draw(); renderController(); });
$('#speed').addEventListener('change', () => { state.speed = Number($('#speed').value); });
$('#restart').addEventListener('click', () => { pause(); state.time = 0; draw(); renderController(); });
$('#controller-block').addEventListener('change', () => {
  const index = Number($('#controller-block').value), trace = state.response.results.find(result => result.scheme === 'adaptive').controller_trace;
  selectScheme('adaptive', false); pause(); state.time = trace[index].time_s; state.controllerIndex = -1; draw(); renderController(index);
});
$('#udp-run').addEventListener('click', runUDP);
$('#export-csv').addEventListener('click', () => download('csv'));
$('#export-json').addEventListener('click', () => download('json'));
for (const button of document.querySelectorAll('[data-preset]')) button.addEventListener('click', () => {
  const preset = button.dataset.preset;
  $('#scenario').value = preset === 'clean' ? 'random' : preset;
  $('#loss').value = preset === 'clean' ? '0' : '15';
  $('#file-size').value = preset === 'changing' ? '256' : '64';
  $('#delay').value = '50'; $('#bandwidth').value = '5'; $('#window').value = '32'; $('#seed').value = preset === 'burst' ? '19' : '7'; $('#ack-loss').value = '0';
  rangeLabels(); compare();
});
for (const button of document.querySelectorAll('[data-scheme]')) {
  button.addEventListener('click', () => selectScheme(button.dataset.scheme));
  button.addEventListener('keydown', event => {
    const index = schemes.indexOf(button.dataset.scheme);
    const next = event.key === 'ArrowRight' ? (index + 1) % 4 : event.key === 'ArrowLeft' ? (index + 3) % 4 : event.key === 'Home' ? 0 : event.key === 'End' ? 3 : null;
    if (next === null) return;
    event.preventDefault(); selectScheme(schemes[next]); $(`#tab-${schemes[next]}`).focus();
  });
}
new ResizeObserver(draw).observe(canvas);
document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });
document.fonts.ready.then(draw);
rangeLabels(); draw(); compare();
