import {prepareReplay, packetAt, countsAt, nextMoment, summarize, comparisonCSV, adaptiveComparison} from './replay.mjs';

const $ = selector => document.querySelector(selector);
const schemes = ['gbn', 'sr', 'fixed', 'adaptive'];
const names = {gbn: 'Go-Back-N', sr: 'Selective Repeat', fixed: 'Fixed XOR', adaptive: 'Adaptive parity'};
const explanations = {
  gbn: 'Discards out-of-order packets. A timeout retries the outstanding window.',
  sr: 'Buffers out-of-order packets. A timeout retries only the missing packet.',
  fixed: 'Sends one XOR repair per block of up to eight packets. Retries unresolved losses.',
  adaptive: 'Chooses no parity, XOR, or a small grid from its loss estimate. Retries unresolved losses.'
};
const colors = {ink: '#25333b', muted: '#59645f', orange: '#b83f16', teal: '#1d7168', data: '#b4c8d2', dataLine: '#466578', rule: '#d1cfc3', panel: '#f7f5ee'};
const state = {group: null, response: null, replays: {}, scheme: 'adaptive', time: 0, packet: 0, view: 'packets',
  playing: false, frame: 0, previousTick: 0, speed: .25, busy: false, history: [], runID: 0,
  udp: null, udpBusy: false, controllerIndex: -1, inspectorKey: '', chartMax: 1, chartGeometry: null, pendingLink: false};
const canvas = $('#packet-canvas'), ctx = canvas.getContext('2d');
const format = (value, digits = 2) => Number(value).toFixed(digits);
const row = () => state.response?.results.find(result => result.scheme === state.scheme);
const replay = () => state.replays[state.scheme];
const duration = () => Math.max(.001, row()?.sender_completion_time_s || .001);
const setText = (selector, text) => { const element = $(selector); if (element.textContent !== text) element.textContent = text; };
const statusNames = {waiting: 'Not sent yet', flight: 'In flight', retry: 'Retry in flight', lost: 'Lost', discarded: 'Arrived out of order; discarded', received: 'Received', repaired: 'Recovered by parity'};
const fieldIDs = {scenario: 'scenario', loss_percent: 'loss', delay_ms: 'delay', bandwidth_mbps: 'bandwidth', file_kib: 'file-size', window: 'window', seed: 'seed', ack_loss_percent: 'ack-loss', controller_policy: 'controller-policy'};

async function request(path, config) {
  const abort = new AbortController(), timer = setTimeout(() => abort.abort(), 40000);
  try {
    const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(config), signal: abort.signal});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'The run failed. Try again.');
    if (path === '/api/simulate' && !result.legacy_result) throw new Error('This server is running the previous version. Restart python -m paritylab demo and reload.');
    return result;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('No response after 40 seconds. Check the local server and try a smaller file.');
    if (error instanceof TypeError) throw new Error('Cannot reach the local server. Start it with python -m paritylab demo, then retry.');
    throw error;
  } finally { clearTimeout(timer); }
}
function settings() {
  return Object.fromEntries(Object.entries(fieldIDs).map(([key, id]) => [key, ['scenario', 'controller_policy'].includes(key) ? $(`#${id}`).value : Number($(`#${id}`).value)]));
}
function sameConfig(a, b) { return Object.keys(fieldIDs).every(key => a[key] === b[key]); }
function setControls(config) {
  for (const [key, id] of Object.entries(fieldIDs)) $(`#${id}`).value = String(config[key] ?? (key === 'controller_policy' ? 'cost' : ''));
  rangeLabels();
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
    seed: config.seed, ack_loss_percent: channel.ack_loss * 100, scheme: config.scheme,
    controller_policy: config.controller_policy};
}
function socketSummary(config) {
  const model = {random: 'independent', burst: 'burst', changing: 'changing'}[config.scenario];
  return `32 KiB · ${names[config.scheme]}${config.scheme === 'adaptive' ? config.controller_policy === 'cost' ? ' (updated)' : ' (original)' : ''} · ${model} loss ${format(config.loss_percent, 0)}% · ${config.delay_ms} ms · ${config.bandwidth_mbps} Mbps · window ${config.window} · ACK loss ${config.ack_loss_percent}% · seed ${config.seed}`;
}
function rangeLabels() {
  setText('#loss-value', `${$('#loss').value}%`);
  setText('#delay-value', `${$('#delay').value} ms`);
  setText('#bandwidth-value', `${Number($('#bandwidth').value)} Mbps`);
  const help = {random: 'Each forward transmission has an independent chance of loss.', burst: 'Losses occur in runs. The slider sets the stationary loss probability.',
    changing: `Starts at 0%; changes to ${$('#loss').value}% at 0.25 s, 2% at 0.75 s, and ${$('#loss').value}% at 1.2 s.`};
  setText('#scenario-help', help[$('#scenario').value]); setText('#udp-config', `Next transfer: ${socketSummary(socketSettings())}`);
  if (state.udp) {
    const recorded = recordedSocketSettings(state.udp.config), next = socketSettings();
    $('#socket-stale').hidden = Object.keys(recorded).filter(key => key !== 'controller_policy' || recorded.scheme === 'adaptive').every(key => Math.abs(recorded[key] - next[key]) < 1e-9 || recorded[key] === next[key]);
  }
  for (const button of document.querySelectorAll('[data-preset]')) button.setAttribute('aria-pressed', 'false');
  $('#copy-link').disabled = !state.group;
}
function flagChangedSettings() {
  rangeLabels();
  if (state.group && !state.busy) {
    const changed = !sameConfig(settings(), state.group.trials[0].config) || Number($('#trial-count').value) !== state.group.trials.length;
    $('#run-status').classList.remove('error'); setText('#run-status', changed ? 'Settings changed. Run again to update the results.' : '');
  }
}
function busyControls(busy) {
  for (const element of document.querySelectorAll('#settings input, #settings select, #settings button')) element.disabled = busy;
  $('#run-history').disabled = busy || !state.history.length; $('#settings').setAttribute('aria-busy', String(busy));
}
async function compare(event) {
  event?.preventDefault(); if (state.busy || !$('#settings').reportValidity()) return;
  const config = settings(), count = Number($('#trial-count').value), trials = [];
  state.busy = true; pause(); busyControls(true);
  $('#run-status').classList.remove('error'); $('#run-progress').hidden = count === 1;
  $('#run-progress').value = 0; $('#run-progress').max = count; $('#run').querySelector('span').textContent = 'Running…';
  try {
    for (let index = 0; index < count; index++) {
      setText('#run-status', count === 1 ? 'Running protocols and original-controller comparison…' : `Running seed ${config.seed + index} · ${index} of ${count} finished`);
      trials.push(await request('/api/simulate', {...config, seed: config.seed + index})); $('#run-progress').value = index + 1;
    }
    const group = {id: ++state.runID, trials}; state.history.unshift(group); state.history = state.history.slice(0, 5); useGroup(group);
    const incomplete = trials.flatMap(trial => [...trial.results, ...(config.controller_policy === 'cost' ? [trial.legacy_result] : [])]).filter(result => !result.integrity_verified).length;
    setText('#run-status', incomplete ? `${incomplete} transfers incomplete. Reduce loss or file size and retry.` : `${count * (config.controller_policy === 'cost' ? 5 : 4)} transfers verified.`);
    $('#run-status').classList.toggle('error', incomplete > 0);
  } catch (error) {
    $('#run-status').classList.add('error'); setText('#run-status', `${error.message}${state.group ? ' Previous results are still shown.' : ''}`);
    setText('#replay-state', state.group ? 'Previous recording' : 'No recording');
  } finally {
    state.busy = false; busyControls(false); $('#run-progress').hidden = true; $('#run').querySelector('span').textContent = 'Run comparison';
    if (state.pendingLink) applySharedLink();
  }
}
function groupLabel(group) {
  const config = group.trials[0].config, model = {random: 'Random', burst: 'Burst', changing: 'Changing'}[config.scenario];
  return `Run ${group.id} · ${model} ${format(config.loss_percent, 0)}% · ${group.trials.length} seed${group.trials.length > 1 ? 's' : ''}`;
}
function useGroup(group) {
  pause(); state.group = group; $('#trial-count').value = String(group.trials.length); setControls(group.trials[0].config);
  $('#run-history').replaceChildren(...state.history.map(item => { const option = document.createElement('option'); option.value = String(item.id); option.textContent = groupLabel(item); return option; }));
  $('#run-history').value = String(group.id); $('#run-history').disabled = false;
  $('#replay-seed').replaceChildren(...group.trials.map((trial, index) => { const option = document.createElement('option'); option.value = String(index); option.textContent = `Seed ${trial.config.seed}`; return option; }));
  $('#replay-seed').disabled = group.trials.length === 1; renderResults(); useTrial(0);
  for (const id of ['export-csv', 'export-json', 'copy-link']) $(`#${id}`).disabled = false;
  setText('#expected-digest', group.trials[0].expected_sha256); setText('#export-status', ''); setText('#share-status', ''); $('#share-url').hidden = true;
}
function useTrial(index) {
  pause(); state.response = state.group.trials[index];
  state.replays = Object.fromEntries(state.response.results.map(result => [result.scheme, prepareReplay(result, state.response.config.file_kib)]));
  state.time = Math.min(.035, duration() / 2); state.controllerIndex = -1; renderDetails(); selectScheme(state.scheme, false);
  for (const id of ['play', 'restart', 'scrubber']) $(`#${id}`).disabled = false;
}
function renderResults() {
  const trials = state.group.trials, multiple = trials.length > 1, note = multiple ? `${trials.length} seeds · mean ± sample SD` : 'One seeded run per protocol';
  setText('#sample-note', note); setText('#results-caption', `${note}. Goodput excludes redundant bytes.`);
  const metrics = [
    {label: 'Goodput', unit: 'Mbps · higher is better', key: 'goodput_mbps', digits: 2},
    {label: 'Completion', unit: 's · lower is better', key: 'completion_time_s', digits: 3},
    {label: 'Retries', unit: 'data transmissions', key: 'retransmissions', digits: multiple ? 1 : 0},
    {label: 'Parity packets', unit: '1 KiB each', key: 'parity_packets', digits: multiple ? 1 : 0},
    {label: 'FEC recovery', unit: 'first-attempt losses repaired', key: 'fec_recovered', digits: multiple ? 1 : 0}];
  const body = $('#results-body'); body.replaceChildren();
  for (const metric of metrics) {
    const tr = document.createElement('tr'), th = document.createElement('th'); th.scope = 'row'; th.textContent = metric.label;
    const small = document.createElement('small'); small.textContent = metric.unit; th.append(small); tr.append(th);
    const summaries = schemes.map(scheme => summarize(trials, scheme, metric.key)), maximum = Math.max(.001, ...summaries.map(item => item.mean));
    for (const [index, scheme] of schemes.entries()) {
      const td = document.createElement('td'); td.dataset.column = scheme;
      const measure = document.createElement('div'); measure.className = 'measure'; const value = document.createElement('span'); value.textContent = format(summaries[index].mean, metric.digits);
      if (multiple) { const sd = document.createElement('span'); sd.className = 'sd'; sd.textContent = ` ± ${format(summaries[index].sd, metric.digits)}`; value.append(sd); }
      const track = document.createElement('div'), bar = document.createElement('div'); track.className = 'bar-track'; bar.className = 'bar'; track.setAttribute('aria-hidden', 'true'); bar.style.setProperty('--bar-width', `${summaries[index].mean / maximum * 100}%`);
      track.append(bar); measure.append(value, track); td.append(measure); tr.append(td);
    }
    body.append(tr);
  }
  const tr = document.createElement('tr'), th = document.createElement('th'); th.scope = 'row'; th.textContent = 'File integrity'; tr.append(th);
  for (const scheme of schemes) {
    const verified = trials.filter(trial => trial.results.find(result => result.scheme === scheme).integrity_verified).length, td = document.createElement('td'); td.dataset.column = scheme;
    const check = document.createElement('span'); check.className = `byte-check${verified === trials.length ? '' : ' incomplete'}`;
    if (verified === trials.length) check.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4 10-10"/></svg>';
    check.append(document.createTextNode(multiple ? `${verified}/${trials.length} verified` : verified ? 'Verified' : 'Incomplete')); td.append(check); tr.append(td);
  }
  body.append(tr);
  const complete = trials.every(trial => trial.all_verified), ranked = schemes.map(scheme => ({scheme, ...summarize(trials, scheme, 'goodput_mbps')})).sort((a, b) => b.mean - a.mean);
  setText('#comparison-summary', complete ? `${names[ranked[0].scheme]} had the highest ${multiple ? 'mean ' : ''}goodput here (${format(ranked[0].mean)} Mbps). This ${multiple ? 'sample' : 'run'} does not establish a general ranking.` : 'At least one transfer is incomplete. Completion and goodput for those rows do not describe a finished file.');
  const change = adaptiveComparison(trials), updated = trials[0].config.controller_policy === 'cost';
  const measure = value => `${format(value.mean)}${multiple ? ` ± ${format(value.sd)}` : ''} Mbps`;
  setText('#before-goodput', measure(change.baseline)); setText('#after-goodput', updated ? measure(change.current) : 'Not selected');
  setText('#completion-change', updated && change.completionChange !== null ? `${format(Math.abs(change.completionChange) * 100, 1)}% ${change.completionChange <= 0 ? 'shorter' : 'longer'}` : '—');
  setText('#improvement-result', !updated ? 'Original controller selected. Choose Cost + receiver feedback to compare the update.' : change.goodputChange === null ? 'At least one adaptive transfer is incomplete; no improvement ratio is reported.' : `${format(Math.abs(change.goodputChange) * 100, 1)}% ${change.goodputChange >= 0 ? 'higher' : 'lower'} ${multiple ? 'mean ' : ''}goodput than the original adaptive controller in this ${multiple ? 'seed group' : 'run'}.`);
  setText('#improvement-note', 'Same file, channel, window, timeout rule, and seeds. Loss patterns differ with packet schedules; gains depend on the condition.');
}
function selectScheme(scheme, reset = true) {
  pause(false); state.scheme = scheme;
  if (reset) state.time = Math.min(.035, duration() / 2);
  state.time = Math.min(state.time, duration());
  for (const button of document.querySelectorAll('[data-scheme]')) { const selected = button.dataset.scheme === scheme; button.setAttribute('aria-selected', String(selected)); button.tabIndex = selected ? 0 : -1; }
  for (const cell of document.querySelectorAll('[data-column]')) cell.classList.toggle('selected-column', cell.dataset.column === scheme);
  $('#journey-panel').setAttribute('aria-labelledby', `tab-${scheme}`); setText('#scheme-explanation', scheme === 'adaptive' && state.response?.config.controller_policy === 'cost' ? 'Prices extra parity against retry cost. Receiver block status triggers early retries; the timer remains as fallback.' : explanations[scheme]);
  buildPacketMap(); buildDeliveryChart(); state.inspectorKey = ''; draw(); renderController();
}
function pause(redraw = true) {
  state.playing = false; cancelAnimationFrame(state.frame); $('#play').setAttribute('aria-label', 'Play packet replay');
  $('#play').innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path class="filled" d="m8 5 11 7-11 7Z"/></svg>'; if (redraw) draw();
}
function play() {
  if (!row()) return; if (state.playing) { pause(); return; } if (state.time >= duration()) state.time = 0;
  state.playing = true; state.previousTick = performance.now(); $('#play').setAttribute('aria-label', 'Pause packet replay');
  $('#play').innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path class="filled" d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>';
  function tick(now) {
    state.time = Math.min(duration(), state.time + Math.min((now - state.previousTick) / 1000, .15) * state.speed); state.previousTick = now; draw(); renderController();
    if (state.time >= duration()) pause(); else state.frame = requestAnimationFrame(tick);
  }
  state.frame = requestAnimationFrame(tick);
}
function seek(time) { pause(false); state.time = Math.min(duration(), Math.max(0, time)); draw(); renderController(); }
function seekNext(kind) { const time = replay() && nextMoment(replay(), kind, state.time); if (time !== null && time !== undefined) seek(time + 1e-8); }
function line(x1, y1, x2, y2, color, reverse = false) {
  ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  const x = reverse ? x1 : x2, direction = reverse ? -1 : 1; ctx.beginPath(); ctx.moveTo(x, y1); ctx.lineTo(x - 6 * direction, y1 - 3); ctx.lineTo(x - 6 * direction, y1 + 3); ctx.closePath(); ctx.fill();
}
function drawWire(counts) {
  const width = canvas.clientWidth, height = canvas.clientHeight; if (!width || !height || state.view !== 'packets') return 0;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) { canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio); }
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height);
  const compact = width < 520, nodeWidth = compact ? 62 : 88, left = 2, right = width - nodeWidth - 2, from = left + nodeWidth + 10, to = right - 10;
  const lanes = {data: 40, parity: 92, ack: 143};
  for (const [kind, y] of Object.entries(lanes)) {
    line(from, y, to, y, colors.rule, kind === 'ack'); ctx.fillStyle = colors.muted; ctx.font = '12px Atkinson'; ctx.textAlign = 'center';
    ctx.fillText(kind === 'data' ? 'DATA / RETRIES' : kind === 'parity' ? 'PARITY' : 'ACKS / FEEDBACK', (from + to) / 2, y - 17);
  }
  for (const [x, label, tint] of [[left, 'Sender', '#dae2e5'], [right, 'Receiver', '#d9e8df']]) {
    ctx.fillStyle = tint; ctx.strokeStyle = x === left ? colors.dataLine : colors.teal; ctx.lineWidth = 1; ctx.beginPath(); ctx.roundRect(x, 14, nodeWidth, 147, 8); ctx.fill(); ctx.stroke();
    ctx.fillStyle = colors.ink; ctx.textAlign = 'center'; ctx.font = `700 ${compact ? 12 : 15}px Atkinson`; ctx.fillText(label, x + nodeWidth / 2, 75); ctx.font = '12px Atkinson';
    ctx.fillText(x === left ? `Window ${state.response?.config.window || 32}` : `${counts.received || 0} / ${state.response?.config.file_kib || 64}`, x + nodeWidth / 2, 97);
    if (x === right) { ctx.fillStyle = colors.teal; ctx.fillText(`${counts.released || 0} in order`, x + nodeWidth / 2, 117); }
  }
  let active = 0; const hold = Math.max(.04, Math.min(.12, duration() / 15));
  for (const event of row()?.transmissions || []) {
    if (event.start_s > state.time) continue; const y = lanes[event.kind === 'feedback' ? 'ack' : event.kind]; if (!y) continue;
    if (event.lost && state.time >= event.arrival_s && state.time <= event.arrival_s + hold) {
      const x = (from + to) / 2 + ((event.sequence ?? event.block_start ?? 0) % 5 - 2) * 5;
      ctx.strokeStyle = colors.orange; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x - 5, y - 5); ctx.lineTo(x + 5, y + 5); ctx.moveTo(x + 5, y - 5); ctx.lineTo(x - 5, y + 5); ctx.stroke(); continue;
    }
    if (event.arrival_s < state.time || event.arrival_s === event.start_s) continue; active++;
    const progress = Math.min(1, Math.max(0, (state.time - event.start_s) / (event.arrival_s - event.start_s))), x = ['ack', 'feedback'].includes(event.kind) ? to - (to - from) * progress : from + (to - from) * progress;
    const selected = event.kind === 'data' && event.sequence === state.packet;
    ctx.lineWidth = selected ? 2 : 1.2; ctx.strokeStyle = selected ? colors.ink : event.kind === 'data' ? event.attempt > 1 ? colors.orange : colors.dataLine : colors.teal;
    ctx.fillStyle = event.kind === 'data' ? colors.data : event.kind === 'parity' ? colors.teal : colors.panel; ctx.beginPath();
    if (event.kind === 'parity') { ctx.moveTo(x, y - 6); ctx.lineTo(x + 6, y); ctx.lineTo(x, y + 6); ctx.lineTo(x - 6, y); ctx.closePath(); }
    else ctx.arc(x, y, selected ? 7 : event.kind === 'ack' ? 4 : 5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    if (selected) { ctx.fillStyle = colors.ink; ctx.textAlign = 'center'; ctx.font = '700 12px Atkinson'; ctx.fillText(`${event.sequence + 1}`, x, y + 19); }
  }
  return active;
}
function draw() {
  const result = row(), prepared = replay(), counts = prepared ? countsAt(prepared, state.time) : {}, active = drawWire(counts);
  setText('#time-readout', `${format(state.time, 3)} s`); setText('#end-time', result ? `${format(duration(), 3)} s` : '—'); $('#scrubber').value = String(Math.round(state.time / duration() * 10000));
  $('#scrubber').setAttribute('aria-valuetext', `${format(state.time, 3)} of ${format(duration(), 3)} seconds`);
  if (!result) { setText('#replay-state', state.busy ? 'Loading recording' : 'Waiting for recording'); return; }
  setText('#count-sent', String(counts.started)); setText('#count-lost', String(counts.dropped)); setText('#count-retry', String(counts.retried)); setText('#count-repair', String(counts.repaired));
  setText('#count-delivered', `${counts.received} / ${prepared.packets.length}`); setText('#release-status', `${counts.released} KiB available in order`);
  const completion = state.time >= duration() ? 'Replay complete' : counts.received === prepared.packets.length ? 'File received · awaiting ACKs' : `${state.playing ? 'Playing' : 'Paused'}${state.view === 'packets' ? ` · ${active} in flight` : ''}`; setText('#replay-state', completion);
  for (const kind of ['loss', 'retry', 'repair']) $(`#next-${kind}`).disabled = nextMoment(prepared, kind, state.time) === null;
  for (const button of $('#packet-map').children) {
    const packet = prepared.packets[Number(button.dataset.sequence)], current = packetAt(packet, state.time);
    if (button.dataset.status !== current.status) { button.className = `packet ${current.status}`; button.dataset.status = current.status; }
    button.setAttribute('aria-pressed', String(packet.sequence === state.packet));
    button.tabIndex = packet.sequence === state.packet ? 0 : -1;
    const label = `Packet ${packet.sequence + 1}: ${statusNames[current.status]}${current.receive ? current.released ? ', released to application' : ', waiting for earlier packets' : ''}`;
    if (button.getAttribute('aria-label') !== label) { button.setAttribute('aria-label', label); button.title = label; }
  }
  canvas.setAttribute('aria-label', `${names[state.scheme]} at ${format(state.time, 3)} seconds. ${counts.started} data transmissions, ${counts.dropped} losses, ${counts.repaired} parity recoveries. Receiver has ${counts.received} packets; ${counts.released} released in order. Positions are illustrative.`); renderInspector(); updateChartCursor();
}
function buildPacketMap() {
  $('#packet-map').replaceChildren();
  if (state.packet >= (replay()?.packets.length || 0)) state.packet = 0;
  for (const packet of replay()?.packets || []) {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'packet'; button.dataset.sequence = String(packet.sequence); button.textContent = String(packet.sequence + 1);
    button.tabIndex = packet.sequence === state.packet ? 0 : -1;
    button.addEventListener('click', () => selectPacket(packet.sequence)); $('#packet-map').append(button);
  }
}
function selectPacket(sequence, focus = false) {
  pause(false); state.packet = sequence; state.inspectorKey = ''; draw();
  if (focus) $('#packet-map').children[sequence]?.focus();
}
function renderInspector() {
  const packet = replay()?.packets[state.packet]; if (!packet) return; const current = packetAt(packet, state.time);
  setText('#packet-title', `Packet ${state.packet + 1}`); setText('#packet-status', `${statusNames[current.status]}${current.receive ? current.released ? ' · released to application' : ' · waiting for earlier packets' : ''}`);
  const key = `${state.response.config.seed}-${state.scheme}-${state.packet}`; if (key === state.inspectorKey) return; state.inspectorKey = key; const list = $('#packet-attempts'); list.replaceChildren();
  function add(label, time, className = '') { const button = document.createElement('button'); button.className = `attempt-button ${className}`; button.type = 'button'; button.textContent = label; button.addEventListener('click', () => seek(time + 1e-8)); list.append(button); }
  for (const event of packet.attempts) add(`Attempt ${event.attempt} · ${event.lost ? 'lost' : 'arrived'} ${format(event.arrival_s, 3)} s`, event.arrival_s, event.lost ? 'loss' : '');
  if (packet.receive) add(`${packet.receive.via === 'parity' ? 'Parity recovery' : 'Receiver accepted'} · ${format(packet.receive.time_s, 3)} s`, packet.receive.time_s, packet.receive.via === 'parity' ? 'repair' : '');
  if (packet.release) add(`App release · ${format(packet.release.time_s, 3)} s`, packet.release.time_s);
  if (!packet.attempts.length) list.textContent = 'This packet was not transmitted before the run ended.';
}
const svgNS = 'http://www.w3.org/2000/svg';
function svgNode(tag, attributes, text) { const element = document.createElementNS(svgNS, tag); for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value)); if (text !== undefined) element.textContent = text; return element; }
function buildDeliveryChart() {
  const chart = $('#delivery-chart'); chart.replaceChildren(); if (!state.response) return;
  const width = Math.max(280, chart.clientWidth || canvas.clientWidth);
  chart.setAttribute('viewBox', `0 0 ${width} 142`);
  state.chartGeometry = {width, left: 38, right: width - 10, bottom: 114, top: 12};
  const g = state.chartGeometry;
  state.chartMax = Math.max(...state.response.results.map(result => result.sender_completion_time_s), .001);
  const total = state.response.config.file_kib, x = time => g.left + time / state.chartMax * (g.right - g.left), y = count => g.bottom - count / total * (g.bottom - g.top);
  for (let index = 0; index <= 4; index++) {
    const count = total * index / 4, time = state.chartMax * index / 4;
    chart.append(svgNode('line', {x1: g.left, x2: g.right, y1: y(count), y2: y(count), stroke: colors.rule, 'stroke-width': 1}), svgNode('text', {x: 30, y: y(count) + 4, fill: colors.muted, stroke: 'none', 'font-size': 12, 'text-anchor': 'end'}, `${format(count, 0)}`), svgNode('text', {x: x(time), y: 134, fill: colors.muted, stroke: 'none', 'font-size': 12, 'text-anchor': index === 0 ? 'start' : index === 4 ? 'end' : 'middle'}, `${format(time, 2)} s`));
  }
  chart.append(svgNode('text', {x: 2, y: 10, fill: colors.muted, stroke: 'none', 'font-size': 12}, 'KiB'));
  $('#chart-legend').replaceChildren();
  for (const [index, scheme] of schemes.entries()) {
    const prepared = state.replays[scheme], selected = scheme === state.scheme, color = selected ? colors.orange : colors.teal; let path = `M ${x(0)} ${y(0)}`;
    for (const packet of prepared.packets) if (packet.release) path += ` H ${x(packet.release.time_s)} V ${y(packet.sequence + 1)}`;
    path += ` H ${x(state.chartMax)}`;
    chart.append(svgNode('path', {d: path, stroke: color, fill: 'none', 'stroke-width': selected ? 2.5 : 1.5, 'stroke-dasharray': selected ? '' : ['', '5 4', '2 4', '10 4'][index], opacity: selected ? 1 : .8}));
    const label = document.createElement('li'), swatch = document.createElement('i');
    swatch.setAttribute('aria-hidden', 'true'); swatch.style.borderTopStyle = selected || index === 0 ? 'solid' : index === 2 ? 'dotted' : 'dashed';
    label.classList.toggle('chart-selected', selected); label.append(swatch, document.createTextNode(names[scheme])); $('#chart-legend').append(label);
  }
  chart.append(svgNode('line', {id: 'chart-cursor', x1: g.left, x2: g.left, y1: g.top, y2: g.bottom, stroke: colors.ink, 'stroke-dasharray': '3 3', 'stroke-width': 1}), svgNode('circle', {id: 'chart-point', cx: g.left, cy: g.bottom, r: 4, fill: colors.orange, stroke: colors.panel, 'stroke-width': 1.5}));
}
function updateChartCursor() {
  if (!$('#chart-cursor') || !replay()) return;
  const g = state.chartGeometry, x = g.left + state.time / state.chartMax * (g.right - g.left), count = countsAt(replay(), state.time).released;
  $('#chart-cursor').setAttribute('x1', String(x)); $('#chart-cursor').setAttribute('x2', String(x)); $('#chart-point').setAttribute('cx', String(x)); $('#chart-point').setAttribute('cy', String(g.bottom - count / state.response.config.file_kib * (g.bottom - g.top)));
  $('#delivery-chart').setAttribute('aria-label', `In-order application delivery for seed ${state.response.config.seed}. Selected protocol ${names[state.scheme]} has released ${count} KiB at ${format(state.time, 3)} seconds. All four curves use this recorded seed.`);
}
function setView(view) {
  state.view = view; $('#packet-view').hidden = view !== 'packets'; $('#delivery-view').hidden = view !== 'delivery'; $('#view-packets').setAttribute('aria-pressed', String(view === 'packets')); $('#view-delivery').setAttribute('aria-pressed', String(view === 'delivery')); buildDeliveryChart(); draw();
}
function modeName(mode) { return mode.startsWith('none-') ? `No parity · up to ${mode.slice(5)} data` : mode.replace('xor-', 'XOR · ').replace('grid-', 'Grid · '); }
function renderController(forcedIndex = null) {
  const trace = state.response?.results.find(result => result.scheme === 'adaptive')?.controller_trace || []; if (!trace.length) return;
  let index = Number($('#controller-block').value) || 0;
  if (forcedIndex !== null) index = forcedIndex; else if (state.scheme === 'adaptive') { index = 0; for (let i = 0; i < trace.length; i++) if (trace[i].time_s <= state.time) index = i; }
  if (index === state.controllerIndex) return; state.controllerIndex = index; const decision = trace[index]; $('#controller-block').value = String(index);
  const cost = state.response.config.controller_policy === 'cost';
  setText('#protection-mode', modeName(decision.mode)); setText('#estimated-loss', `${format(decision.estimated_loss * 100, 1)}%`); setText('#predicted-risk', `${format(decision.predicted_failure * 100)}%`);
  setText('#decision-objective', cost ? 'Cost per data packet' : '1% model target');
  setText('#target-met', cost ? `${format(decision.estimated_cost_per_packet_s * 1000)} ms` : decision.target_met ? 'Feasible in model' : 'No feasible layout'); $('#target-met').classList.toggle('unmet', !cost && !decision.target_met);
  setText('#cost-detail', cost ? `Selected cost: ${format(decision.estimated_cost_per_packet_s * 1000)} ms per packet; without parity: ${format(decision.unprotected_cost_per_packet_s * 1000)} ms. Scores include serialization and one modeled timeout per unresolved block.` : 'Select the least parity meeting the modeled target, or the lowest predicted risk when infeasible.');
  for (const tr of $('#trace-body').children) tr.classList.toggle('current-decision', Number(tr.dataset.index) === index);
}
function seekDecision(index) {
  const decision = state.response.results.find(result => result.scheme === 'adaptive').controller_trace[index]; selectScheme('adaptive', false); state.packet = decision.start_packet; state.inspectorKey = ''; seek(decision.time_s); renderController(index);
}
function renderDetails() {
  const config = state.response.config, scenario = {random: `${format(config.loss_percent, 0)}% independent loss`, burst: `${format(config.loss_percent, 0)}% stationary burst loss`, changing: `changing loss (0 → ${format(config.loss_percent, 0)} → 2 → ${format(config.loss_percent, 0)}%)`}[config.scenario];
  setText('#trial-config', `${config.file_kib} KiB · 1 KiB packets · ${scenario} · ${config.delay_ms} ms one-way · ${config.bandwidth_mbps} Mbps · window ${config.window} · ACK loss ${config.ack_loss_percent}% · replay seed ${config.seed}`);
  const trace = state.response.results.find(result => result.scheme === 'adaptive').controller_trace; $('#controller-block').replaceChildren(); $('#trace-body').replaceChildren();
  for (const [index, decision] of trace.entries()) {
    const option = document.createElement('option'); option.value = String(index); option.textContent = `Packets ${decision.start_packet + 1}–${decision.start_packet + decision.data_packets} · ${format(decision.time_s, 3)} s · ${modeName(decision.mode)}`; $('#controller-block').append(option);
    const tr = document.createElement('tr'); tr.dataset.index = String(index); const time = document.createElement('td'), button = document.createElement('button'); button.type = 'button'; button.textContent = format(decision.time_s, 3); button.setAttribute('aria-label', `Replay decision for packet ${decision.start_packet + 1} at ${format(decision.time_s, 3)} seconds`); button.addEventListener('click', () => seekDecision(index)); time.append(button); tr.append(time);
    for (const value of [modeName(decision.mode), `${format(decision.estimated_loss * 100, 1)}%`, `${format(decision.predicted_failure * 100)}%${config.controller_policy === 'legacy' && !decision.target_met ? ' (infeasible)' : ''}`]) { const td = document.createElement('td'); td.textContent = value; tr.append(td); } $('#trace-body').append(tr);
  }
  $('#controller-block').disabled = !trace.length; setText('#trace-summary', `All decisions (${trace.length})`); state.controllerIndex = -1; renderController();
}
async function runUDP() {
  if (state.udpBusy || !$('#settings').reportValidity()) return; state.udpBusy = true;
  const button = $('#udp-run'), status = $('#udp-status'), config = socketSettings(); button.disabled = true; button.textContent = 'Transferring…'; $('#socket-scheme').disabled = true;
  status.classList.remove('error'); status.textContent = 'Sending 32 KiB. The transfer may take up to 30 seconds.'; $('.udp-check').setAttribute('aria-busy', 'true');
  try {
    const result = await request('/api/socket', config); state.udp = result; const list = $('#udp-result'); list.replaceChildren();
    const values = [['File integrity', result.verified ? 'Verified · 32,768 bytes' : 'Mismatch'], ['Sender wall time', `${format(result.sender.elapsed_s, 3)} s`], ['Data retries / parity', `${result.sender.retransmissions} / ${result.sender.parity_packets}`], ['Sender / proxy / receiver PIDs', result.processes.map(process => process.pid).reverse().join(' / ')], ['In-order releases', `${result.receiver.application_release_count} packets`], ['Received SHA-256', result.receiver.sha256]];
    for (const [label, value] of values) {
      const div = document.createElement('div'), dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = label;
      if (label === 'Received SHA-256') { div.className = 'hash-row'; const code = document.createElement('code'); code.textContent = value; dd.append(code); } else dd.textContent = value;
      if (label === 'File integrity' && result.verified) dd.className = 'verified'; div.append(dt, dd); list.append(div);
    }
    list.hidden = false; $('#socket-export').hidden = false; setText('#socket-recorded', `Completed transfer: ${socketSummary(recordedSocketSettings(result.config))}`); $('#socket-recorded').hidden = false;
    status.textContent = result.verified ? 'Received file matches the original.' : 'Received file differs. Retry the transfer.'; status.classList.toggle('error', !result.verified);
  } catch (error) { status.classList.add('error'); status.textContent = `${error.message}${state.udp ? ' The previous receipt is still shown.' : ''}`; }
  finally { state.udpBusy = false; button.disabled = false; button.textContent = 'Run UDP transfer'; $('#socket-scheme').disabled = false; $('.udp-check').removeAttribute('aria-busy'); rangeLabels(); }
}
function saveFile(content, mime, filename) {
  const url = URL.createObjectURL(new Blob([content], {type: mime})), link = document.createElement('a'); link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function download(kind) {
  if (!state.group) return; const config = state.group.trials[0].config;
  if (kind === 'json') {
    const content = state.group.trials.length === 1 ? state.group.trials[0] : {seed_count: state.group.trials.length, trials: state.group.trials, summary_note: 'Mean and sample SD; seeds are independent runs, not paired transmission masks.'}; saveFile(JSON.stringify(content, null, 2), 'application/json', `paritylab-${config.scenario}-${state.group.trials.length}-seeds.json`);
  } else {
    saveFile(comparisonCSV(state.group.trials), 'text/csv;charset=utf-8', `paritylab-${config.scenario}-${state.group.trials.length}-seeds.csv`);
  }
  setText('#export-status', `${kind.toUpperCase()} download started · ${state.group.trials.length * (config.controller_policy === 'cost' ? 5 : 4)} measured transfers`);
}
async function copyLink() {
  if (!state.group) return; const params = new URLSearchParams(); for (const key of Object.keys(fieldIDs)) params.set(key, state.group.trials[0].config[key]); params.set('seeds', state.group.trials.length); params.set('protocol', state.scheme);
  const url = `${window.location.origin}/#${params}`;
  try { await navigator.clipboard.writeText(url); setText('#share-status', 'Recorded settings copied. The link reruns them on this server.'); }
  catch { $('#share-url').value = url; $('#share-url').hidden = false; $('#share-url').select(); setText('#share-status', 'Copy this link. It reruns the recorded settings on this server.'); }
}
function loadLink() {
  if (!window.location.hash) return; const params = new URLSearchParams(window.location.hash.slice(1));
  for (const [key, id] of Object.entries(fieldIDs)) {
    if (!params.has(key)) continue; const element = $(`#${id}`), value = params.get(key);
    if (element.tagName === 'SELECT') { if ([...element.options].some(option => option.value === value)) element.value = value; }
    else { const number = Number(value), min = Number(element.min), max = Number(element.max), step = Number(element.step || 1); if (Number.isFinite(number) && number >= min && number <= max && Math.abs((number - min) / step - Math.round((number - min) / step)) < 1e-6) element.value = value; }
  }
  if (['1', '5'].includes(params.get('seeds'))) $('#trial-count').value = params.get('seeds'); if (schemes.includes(params.get('protocol'))) state.scheme = params.get('protocol');
}
function applySharedLink() {
  if (!new URLSearchParams(window.location.hash.slice(1)).has('scenario')) { state.pendingLink = false; return; }
  if (state.busy) { state.pendingLink = true; return; }
  state.pendingLink = false; loadLink(); rangeLabels(); compare();
}
window.addEventListener('hashchange', applySharedLink);
async function loadStudy() {
  try {
    const response = await fetch('/assets/controller-study.json');
    if (!response.ok) throw new Error('Missing saved evaluation');
    const study = await response.json(), manifest = study.manifest;
    const labels = {'clean': 'Clean', 'random-2': 'Random 2%', 'random-5': 'Random 5%', 'random-10': 'Random 10%', 'random-20': 'Random 20%', 'slow-link': 'Slow link · 1 Mbps', 'fast-link': 'Fast link · 20 Mbps', 'short-delay': 'Short delay · 5 ms', 'long-delay': 'Long delay · 150 ms', burst: 'Burst · 10%', changing: 'Changing · short file', 'ack-loss': 'ACK loss · 5%'};
    for (const comparison of manifest.comparisons) {
      const condition = comparison.condition, rows = Object.fromEntries(study.summary.filter(item => item.condition === condition).map(item => [item.method, item]));
      const tr = document.createElement('tr'), th = document.createElement('th'), button = document.createElement('button'); th.scope = 'row'; button.type = 'button'; button.textContent = labels[condition]; button.title = 'Run this condition with five seeds';
      button.addEventListener('click', () => {
        if (state.busy) return;
        const config = {scenario: condition === 'burst' ? 'burst' : condition === 'changing' ? 'changing' : 'random', loss_percent: condition === 'clean' ? 0 : condition.startsWith('random-') ? Number(condition.split('-')[1]) : 10, delay_ms: condition === 'short-delay' ? 5 : condition === 'long-delay' ? 150 : 50, bandwidth_mbps: condition === 'slow-link' ? 1 : condition === 'fast-link' ? 20 : 5, file_kib: 64, window: 32, seed: 100, ack_loss_percent: condition === 'ack-loss' ? 5 : 0, controller_policy: 'cost'};
        setControls(config); $('#trial-count').value = '5'; compare(); $('#experiment').scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
      });
      th.append(button); tr.append(th);
      const change = (comparison.goodput_ratio_to_legacy - 1) * 100;
      for (const [index, value] of [rows.legacy, rows.cost, change, rows.fixed, rows.sr].entries()) {
        const td = document.createElement('td');
        td.textContent = index === 2 ? `${value >= 0 ? '+' : ''}${format(value, 1)}%` : `${format(value.goodput_mbps_mean)} ± ${format(value.goodput_mbps_std)}`;
        if (index === 2) td.className = change >= 0 ? 'positive' : 'negative';
        tr.append(td);
      }
      $('#study-body').append(tr);
    }
    setText('#study-status', `${manifest.runs.toLocaleString()} transfers · 20 unused seeds per condition · ${manifest.all_verified ? 'all files verified' : 'some failures'}. Across the 11 nonclean conditions, geometric mean goodput was ${format((manifest.geometric_goodput_ratio_to_legacy_nonclean - 1) * 100, 1)}% higher than the original controller.`);
  } catch { setText('#study-status', 'Saved evaluation unavailable. Live comparisons still work.'); }
}
$('#settings').addEventListener('submit', compare); $('#settings').addEventListener('input', flagChangedSettings);
$('#play').addEventListener('click', play); $('#restart').addEventListener('click', () => seek(0)); $('#scrubber').addEventListener('input', () => seek(Number($('#scrubber').value) / 10000 * duration())); $('#speed').addEventListener('change', () => { state.speed = Number($('#speed').value); });
for (const kind of ['loss', 'retry', 'repair']) $(`#next-${kind}`).addEventListener('click', () => seekNext(kind));
$('#packet-map').addEventListener('keydown', event => {
  if (!event.target.matches('.packet') || event.ctrlKey || event.metaKey || event.altKey) return;
  const columns = getComputedStyle($('#packet-map')).gridTemplateColumns.split(' ').length;
  const current = Number(event.target.dataset.sequence), last = replay().packets.length - 1;
  const next = {ArrowLeft: current - 1, ArrowRight: current + 1, ArrowUp: current - columns, ArrowDown: current + columns, Home: 0, End: last}[event.key];
  if (next === undefined) return;
  event.preventDefault(); selectPacket(Math.max(0, Math.min(last, next)), true);
});
$('#controller-block').addEventListener('change', () => seekDecision(Number($('#controller-block').value)));
$('#view-packets').addEventListener('click', () => setView('packets')); $('#view-delivery').addEventListener('click', () => setView('delivery'));
$('#delivery-chart').addEventListener('click', event => { if (!state.response) return; const rect = $('#delivery-chart').getBoundingClientRect(), g = state.chartGeometry; seek(Math.max(0, Math.min(1, ((event.clientX - rect.left) / rect.width * g.width - g.left) / (g.right - g.left))) * state.chartMax); });
$('#replay-seed').addEventListener('change', () => useTrial(Number($('#replay-seed').value)));
$('#run-history').addEventListener('change', () => { useGroup(state.history.find(group => group.id === Number($('#run-history').value))); setText('#run-status', 'Previous run restored.'); });
$('#present').addEventListener('click', () => { const presenting = document.body.classList.toggle('presenting'); $('#present').setAttribute('aria-pressed', String(presenting)); $('#present').querySelector('span').textContent = presenting ? 'Exit presentation' : 'Present'; draw(); });
$('#udp-run').addEventListener('click', runUDP); $('#socket-scheme').addEventListener('change', rangeLabels);
$('#socket-export').addEventListener('click', () => { if (!state.udp) return; saveFile(JSON.stringify(state.udp, null, 2), 'application/json', `paritylab-udp-${state.udp.config.scheme}-seed-${state.udp.config.seed}.json`); setText('#udp-status', 'Transfer JSON download started.'); });
$('#export-csv').addEventListener('click', () => download('csv')); $('#export-json').addEventListener('click', () => download('json')); $('#copy-link').addEventListener('click', copyLink);
for (const button of document.querySelectorAll('[data-preset]')) button.addEventListener('click', () => {
  const preset = button.dataset.preset; setControls({scenario: preset === 'clean' ? 'random' : preset, loss_percent: preset === 'clean' ? 0 : preset === 'random' ? 10 : 15, delay_ms: 50, bandwidth_mbps: 5, file_kib: preset === 'changing' ? 256 : 64, window: 32, seed: preset === 'burst' ? 19 : 7, ack_loss_percent: 0}); button.setAttribute('aria-pressed', 'true'); compare();
});
for (const button of document.querySelectorAll('[data-scheme]')) {
  button.addEventListener('click', () => selectScheme(button.dataset.scheme));
  button.addEventListener('keydown', event => { const index = schemes.indexOf(button.dataset.scheme), next = event.key === 'ArrowRight' ? (index + 1) % 4 : event.key === 'ArrowLeft' ? (index + 3) % 4 : event.key === 'Home' ? 0 : event.key === 'End' ? 3 : null; if (next === null) return; event.preventDefault(); selectScheme(schemes[next]); $(`#tab-${schemes[next]}`).focus(); });
}
document.addEventListener('keydown', event => {
  if (event.ctrlKey || event.metaKey || event.altKey || event.target.closest('input, select, button, a, summary') || !row()) return;
  if (event.code === 'Space') { event.preventDefault(); play(); } else if (event.key.toLowerCase() === 'r') seek(0); else if (event.key.toLowerCase() === 'l') seekNext('loss');
});
new ResizeObserver(() => { buildDeliveryChart(); draw(); }).observe($('.journey')); document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); }); document.fonts.ready.then(draw);
loadLink(); rangeLabels(); draw(); compare(); loadStudy();
