/* POLARLOGIX offline queue. Real IndexedDB storage: events survive page reload.
 * This is the actual offline-first path — the field app always writes here first,
 * then a background sync pushes queued events to /api/sync/push once online. */
(function () {
  const DB_NAME = 'polarlogix';
  const DB_VER = 1;
  const STORE = 'outbox';
  let dbp = null;

  function openDb() {
    if (dbp) return dbp;
    dbp = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VER);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          const os = db.createObjectStore(STORE, { keyPath: 'event_id' });
          os.createIndex('status', 'status');
          os.createIndex('created_at', 'created_at');
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return dbp;
  }

  async function tx(mode) {
    const db = await openDb();
    return db.transaction(STORE, mode).objectStore(STORE);
  }

  function uuid() {
    if (crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8); return v.toString(16);
    });
  }

  /** Queue a new event. Returns the stored record (status='pending'). */
  async function enqueue(type, entityId, payload, clock) {
    const rec = { event_id: uuid(), type, entity_id: entityId || '', payload: payload || {}, clock: clock || 0,
                  base_clock: clock || 0, created_at: new Date().toISOString(), status: 'pending', reason: '' };
    const store = await tx('readwrite');
    await new Promise((res, rej) => { const r = store.add(rec); r.onsuccess = res; r.onerror = () => rej(r.error); });
    return rec;
  }

  async function all() {
    const store = await tx('readonly');
    return new Promise((resolve, reject) => {
      const items = []; const req = store.openCursor(null, 'prev');
      req.onsuccess = () => { const c = req.result; if (c) { items.push(c.value); c.continue(); } else resolve(items); };
      req.onerror = () => reject(req.error);
    });
  }

  async function pending() { return (await all()).filter(e => e.status === 'pending'); }

  async function markStatus(eventId, status, reason) {
    const store = await tx('readwrite');
    return new Promise((resolve, reject) => {
      const g = store.get(eventId);
      g.onsuccess = () => {
        const rec = g.result; if (!rec) return resolve(null);
        rec.status = status; if (reason !== undefined) rec.reason = reason;
        const p = store.put(rec); p.onsuccess = () => resolve(rec); p.onerror = () => reject(p.error);
      };
      g.onerror = () => reject(g.error);
    });
  }

  async function clearSynced() {
    const items = await all();
    const store = await tx('readwrite');
    items.filter(i => i.status === 'synced').forEach(i => store.delete(i.event_id));
  }

  window.PLDB = { enqueue, all, pending, markStatus, clearSynced, uuid };
})();
