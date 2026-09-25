/* POLARLOGIX sync engine. Talks to the real backend sync API (app/routers/misc.py):
 *   POST /api/sync/push  { device_id, events:[{event_id,type,entity_id,payload,clock,base_clock,created_at}] }
 *   GET  /api/sync/pull?since=<cursor>&device_id=<id>
 * The device id is stable per browser (persisted in localStorage) so the server can
 * tell "this device's own edits" apart from others in the pull feed. */
(function () {
  const DEVICE_KEY = 'pl_device_id';
  let cursor = Number(localStorage.getItem('pl_sync_cursor') || 0);

  function deviceId() {
    let id = localStorage.getItem(DEVICE_KEY);
    if (!id) { id = 'WEB-' + (window.PLDB.uuid().slice(0, 8)).toUpperCase(); localStorage.setItem(DEVICE_KEY, id); }
    return id;
  }

  async function pushQueue(opts = {}) {
    const events = await window.PLDB.pending();
    if (!events.length) return { pushed: 0, synced: 0, conflicts: 0, rejected: 0 };
    const body = { device_id: deviceId(), events: events.map(e => ({ event_id: e.event_id, type: e.type, entity_id: e.entity_id, payload: e.payload, clock: e.clock, base_clock: e.base_clock, created_at: e.created_at })) };
    const res = await window.PL.authFetch('/api/sync/push', { method: 'POST', json: body, linkSim: opts.linkSim });
    let synced = 0, conflicts = 0, rejected = 0;
    for (const r of res.results) {
      if (r.status === 'accepted' || r.status === 'duplicate') { await window.PLDB.markStatus(r.event_id, 'synced', r.reason); synced++; }
      else if (r.status === 'conflict') { await window.PLDB.markStatus(r.event_id, 'conflict', r.reason); conflicts++; }
      else { await window.PLDB.markStatus(r.event_id, 'rejected', r.reason); rejected++; }
    }
    return { pushed: events.length, synced, conflicts, rejected, results: res.results };
  }

  async function pull() {
    const res = await window.PL.authFetch(`/api/sync/pull?since=${cursor}&device_id=${encodeURIComponent(deviceId())}`);
    cursor = res.cursor;
    localStorage.setItem('pl_sync_cursor', String(cursor));
    return res;
  }

  /** Full round trip used by the "Sync now" button and the automatic online handler. */
  async function syncNow(opts = {}) {
    const push = await pushQueue(opts);
    const pullRes = await pull().catch(() => ({ changes: [], open_conflicts: 0 }));
    await window.PLDB.clearSynced();
    return { push, pull: pullRes };
  }

  window.PLSync = { deviceId, pushQueue, pull, syncNow, get cursor() { return cursor; } };
})();
