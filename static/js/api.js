/* POLARLOGIX API client. Loaded by both login.html and index.html. */
(function () {
  const TOK_KEY = 'pl_tokens';
  const USER_KEY = 'pl_user';
  const THEME_KEY = 'pl_theme';

  function getTokens() { try { return JSON.parse(localStorage.getItem(TOK_KEY) || 'null'); } catch { return null; } }
  function setTokens(t) { localStorage.setItem(TOK_KEY, JSON.stringify(t)); }
  function clearTokens() { localStorage.removeItem(TOK_KEY); localStorage.removeItem(USER_KEY); }
  function getUser() { try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch { return null; } }

  async function login(username, password) {
    const r = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) });
    if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || 'Wrong username or password'); }
    const d = await r.json();
    setTokens({ access: d.access_token, refresh: d.refresh_token });
    localStorage.setItem(USER_KEY, JSON.stringify(d.user));
    return d.user;
  }

  function logout() { clearTokens(); location.href = '/login.html'; }

  async function refresh() {
    const t = getTokens();
    if (!t || !t.refresh) throw new Error('No refresh token');
    const r = await fetch('/api/auth/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: t.refresh }) });
    if (!r.ok) throw new Error('Refresh failed');
    const d = await r.json();
    setTokens({ access: d.access_token, refresh: d.refresh_token });
    localStorage.setItem(USER_KEY, JSON.stringify(d.user));
    return d.access_token;
  }

  /** Authenticated fetch. Retries once after a token refresh on 401. Set opts.linkSim=true to
   *  tag the request with X-Link-Sim so the backend demo middleware can simulate a slow link. */
  async function authFetch(path, opts = {}) {
    const t = getTokens();
    if (!t) { location.href = '/login.html'; throw new Error('Not signed in'); }
    const headers = Object.assign({}, opts.headers || {}, { Authorization: 'Bearer ' + t.access });
    if (opts.json !== undefined) { headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(opts.json); }
    if (opts.linkSim) headers['X-Link-Sim'] = 'sat';
    let r;
    try {
      r = await fetch(path, Object.assign({}, opts, { headers }));
    } catch (netErr) {
      const e = new Error('Network unreachable'); e.offline = true; throw e;
    }
    if (r.status === 401) {
      try {
        await refresh();
        const t2 = getTokens();
        headers.Authorization = 'Bearer ' + t2.access;
        r = await fetch(path, Object.assign({}, opts, { headers }));
      } catch { logout(); throw new Error('Session expired'); }
    }
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      const e = new Error(d.detail || ('Request failed: ' + r.status)); e.status = r.status; throw e;
    }
    const ct = r.headers.get('content-type') || '';
    return ct.includes('application/json') ? r.json() : r.text();
  }

  function requireAuth() {
    if (!getTokens()) { location.href = '/login.html'; return false; }
    return true;
  }

  function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem(THEME_KEY, t);
  }
  function toggleTheme() {
    const cur = localStorage.getItem(THEME_KEY) || 'light';
    applyTheme(cur === 'light' ? 'dark' : 'light');
  }
  (function initTheme() { applyTheme(localStorage.getItem(THEME_KEY) || 'light'); })();

  /** Downloads a file (CSV export, etc.) with the auth header a plain <a href> can't send,
   *  then triggers a normal browser save via a temporary blob link. */
  async function authDownload(path, filename) {
    const t = getTokens();
    if (!t) { location.href = '/login.html'; throw new Error('Not signed in'); }
    let r = await fetch(path, { headers: { Authorization: 'Bearer ' + t.access } });
    if (r.status === 401) {
      await refresh();
      const t2 = getTokens();
      r = await fetch(path, { headers: { Authorization: 'Bearer ' + t2.access } });
    }
    if (!r.ok) { const e = new Error('Download failed: ' + r.status); e.status = r.status; throw e; }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename || path.split('/').pop();
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  window.PL = { login, logout, refresh, authFetch, authDownload, requireAuth, getUser, getTokens, applyTheme, toggleTheme };
})();
