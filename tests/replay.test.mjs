import assert from 'node:assert/strict';
import test from 'node:test';
import {prepareReplay, packetAt, countsAt, nextMoment, meanSD, comparisonCSV, adaptiveComparison} from '../web/replay.mjs';

const result = {
  transmissions: [
    {kind: 'data', sequence: 0, attempt: 1, start_s: 0, arrival_s: .1, lost: true},
    {kind: 'data', sequence: 1, attempt: 1, start_s: .01, arrival_s: .11, lost: false},
    {kind: 'parity', start_s: .02, arrival_s: .12, lost: false},
    {kind: 'data', sequence: 0, attempt: 2, start_s: .2, arrival_s: .3, lost: false},
  ],
  receiver_events: [
    {kind: 'receive', sequence: 1, time_s: .11, via: 'data'},
    {kind: 'receive', sequence: 0, time_s: .12, via: 'parity'},
    {kind: 'release', sequence: 0, time_s: .12},
    {kind: 'release', sequence: 1, time_s: .12},
  ]
};

test('a received packet can be blocked from application release', () => {
  const replay = prepareReplay(result, 2);
  assert.deepEqual(packetAt(replay.packets[1], .115).status, 'received');
  assert.equal(packetAt(replay.packets[1], .115).released, false);
  assert.equal(countsAt(replay, .115).received, 1);
  assert.equal(countsAt(replay, .115).released, 0);
  assert.equal(packetAt(replay.packets[1], .12).released, true);
});

test('seeking backward removes later repairs and retries', () => {
  const replay = prepareReplay(result, 2);
  assert.equal(packetAt(replay.packets[0], .1).status, 'lost');
  assert.equal(packetAt(replay.packets[0], .12).status, 'repaired');
  assert.equal(packetAt(replay.packets[0], -.1).status, 'waiting');
  assert.equal(countsAt(replay, .3).retried, 1);
  assert.equal(countsAt(replay, .15).retried, 0);
  assert.equal(countsAt(replay, .12).repaired, 1);
  assert.equal(countsAt(replay, .11).repaired, 0);
});

test('a successful GBN arrival does not imply receiver acceptance', () => {
  const replay = prepareReplay({...result, receiver_events: []}, 2);
  assert.equal(packetAt(replay.packets[1], .2).status, 'discarded');
  assert.equal(countsAt(replay, .2).received, 0);
});

test('event seeking is strict and does not silently wrap', () => {
  const replay = prepareReplay(result, 2);
  assert.equal(nextMoment(replay, 'loss', 0), .1);
  assert.equal(nextMoment(replay, 'loss', .1), null);
  assert.equal(nextMoment(replay, 'retry', .12), .2);
  assert.equal(nextMoment(replay, 'repair', .11), .12);
});

test('sample deviation uses independent trials, and single trials have no spread', () => {
  assert.deepEqual(meanSD([1, 3, 5]), {mean: 3, sd: 2});
  assert.deepEqual(meanSD([7]), {mean: 7, sd: 0});
});

test('event jumps exclude redundant arrivals beyond sender completion', () => {
  const replay = prepareReplay({
    ...result,
    sender_completion_time_s: .25,
    transmissions: [...result.transmissions, {kind: 'ack', start_s: .22, arrival_s: .4, lost: true}],
  }, 2);
  assert.equal(nextMoment(replay, 'loss', .1), null);
  assert.equal(nextMoment(replay, 'retry', .12), .2);
  assert.equal(nextMoment(replay, 'repair', .11), .12);
});

test('CSV preserves every seed and the recorded configuration', () => {
  const trials = [7, 8, 9, 10, 11].map(seed => ({
    config: {scenario: 'burst', loss_percent: 15, file_kib: 64, window: 32},
    results: ['gbn', 'sr', 'fixed', 'adaptive'].map(scheme => ({scheme, seed, integrity_verified: true}))
  }));
  const csv = comparisonCSV(trials).trim().split('\r\n');
  assert.equal(csv.length, 21);
  assert.equal(csv[0].split(',').filter(key => key === 'seed').length, 1);
  assert.equal(csv[1].split(',')[1], '7');
  assert.equal(csv[20].split(',')[1], '11');
  assert.ok(csv.slice(1).every(line => line.includes(',burst,15,')));
});

test('before-after compares seed means and retains negative results', () => {
  const trials = [1, 2].map(value => ({results: [{scheme: 'adaptive', integrity_verified: true,
    goodput_mbps: value, completion_time_s: 4}], legacy_result: {integrity_verified: true,
    goodput_mbps: value * 2, completion_time_s: 2}}));
  const change = adaptiveComparison(trials);
  assert.equal(change.goodputChange, -.5);
  assert.equal(change.completionChange, 1);
  trials[0].legacy_result.integrity_verified = false;
  assert.equal(adaptiveComparison(trials).goodputChange, null);
});

test('CSV includes original-controller comparison and recorded policy', () => {
  const trial = {config: {scenario: 'random', controller_policy: 'cost'},
    results: [{scheme: 'adaptive', seed: 7, controller_policy: 'cost'}],
    legacy_result: {scheme: 'adaptive', seed: 7, controller_policy: 'legacy'}};
  const lines = comparisonCSV([trial]).trim().split('\r\n');
  assert.equal(lines.length, 3);
  assert.ok(lines[0].includes('controller_policy'));
  assert.ok(lines[2].startsWith('adaptive-legacy,7,'));
});
