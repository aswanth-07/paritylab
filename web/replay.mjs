// These helpers only read recorded events. They do not simulate a protocol.
export function countThrough(sorted, time) {
  let low = 0, high = sorted.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (sorted[middle] <= time) low = middle + 1;
    else high = middle;
  }
  return low;
}

export function prepareReplay(result, packetCount) {
  const packets = Array.from({length: packetCount}, (_, sequence) => ({sequence, attempts: [], receive: null, release: null}));
  const moments = {loss: [], retry: [], repair: []};
  const duration = result.sender_completion_time_s ?? Infinity;
  const started = [], dropped = [], retried = [], repaired = [], received = [], released = [];
  for (const event of result.transmissions) {
    if (event.lost && event.arrival_s <= duration) moments.loss.push(event.arrival_s);
    if (event.kind !== 'data') continue;
    packets[event.sequence]?.attempts.push(event);
    started.push(event.start_s);
    if (event.lost) dropped.push(event.arrival_s);
    if (event.attempt > 1) {
      retried.push(event.start_s);
      if (event.start_s <= duration) moments.retry.push(event.start_s);
    }
  }
  for (const event of result.receiver_events || []) {
    const packet = packets[event.sequence];
    if (!packet) continue;
    if (event.kind === 'receive') {
      packet.receive = event;
      received.push(event.time_s);
      if (event.via === 'parity') {
        repaired.push(event.time_s);
        if (event.time_s <= duration) moments.repair.push(event.time_s);
      }
    } else if (event.kind === 'release') {
      packet.release = event;
      released.push(event.time_s);
    }
  }
  for (const packet of packets) packet.attempts.sort((a, b) => a.start_s - b.start_s);
  const counts = {started, dropped, retried, repaired, received, released};
  for (const values of [...Object.values(moments), ...Object.values(counts)]) values.sort((a, b) => a - b);
  return {packets, moments, counts, result};
}

export function packetAt(packet, time) {
  const receive = packet.receive?.time_s <= time ? packet.receive : null;
  const released = packet.release?.time_s <= time;
  let attempt = null;
  for (const event of packet.attempts) {
    if (event.start_s > time) break;
    attempt = event;
  }
  const status = receive ? receive.via === 'parity' ? 'repaired' : 'received'
    : !attempt ? 'waiting'
    : attempt.arrival_s <= time && attempt.lost ? 'lost'
    : attempt.arrival_s <= time ? 'discarded'
    : attempt.attempt > 1 ? 'retry' : 'flight';
  return {status, released, receive, attempt};
}

export function countsAt(replay, time) {
  return Object.fromEntries(Object.entries(replay.counts).map(([key, values]) => [key, countThrough(values, time)]));
}

export function nextMoment(replay, kind, time) {
  const values = replay.moments[kind];
  return values[countThrough(values, time + 1e-7)] ?? null;
}

export function meanSD(values) {
  const mean = values.reduce((total, value) => total + value, 0) / values.length;
  const sd = values.length > 1 ? Math.sqrt(values.reduce((total, value) => total + (value - mean) ** 2, 0) / (values.length - 1)) : 0;
  return {mean, sd};
}

export function summarize(trials, scheme, metric) {
  return meanSD(trials.map(trial => trial.results.find(result => result.scheme === scheme)[metric]));
}

export function comparisonCSV(trials) {
  const keys = ['scheme', 'seed', 'completed', 'integrity_verified', 'goodput_mbps', 'completion_time_s', 'sender_completion_time_s', 'retransmissions', 'parity_packets', 'fec_recovered', 'parity_overhead_ratio', 'sha256'];
  const configKeys = ['scenario', 'loss_percent', 'delay_ms', 'bandwidth_mbps', 'file_kib', 'window', 'ack_loss_percent'];
  return [...keys, ...configKeys].join(',') + '\r\n' + trials.flatMap(trial => trial.results.map(result => [...keys.map(key => result[key]), ...configKeys.map(key => trial.config[key])].join(','))).join('\r\n') + '\r\n';
}
