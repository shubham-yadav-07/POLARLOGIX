/* POLARLOGIX main app. Every screen below is rendered from live /api/* responses —
 * nothing here is hard-coded demo data (the demo data lives server-side in ./data/*.csv
 * and is seeded into the database; see app/seed.py). */
(function () {
  if (!window.PL.requireAuth()) return;

  const $ = (id) => document.getElementById(id);
  const ICONS = {
    dash:'<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    missions:'<circle cx="12" cy="12" r="9"/><path d="M15 9l-2 6-6 2 2-6z"/>',
    gis:'<path d="M12 21s-7-6-7-11a7 7 0 0114 0c0 5-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    assets:'<path d="M4 6h8M16 6h4M4 12h2M10 12h10M4 18h10M18 18h2"/><circle cx="14" cy="6" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="18" r="2"/>',
    cargo:'<path d="M2 6h11v10H2zM13 9h4l3 3v4h-7z"/><circle cx="6" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
    people:'<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/><path d="M16 5a3.2 3.2 0 010 6M18 14c2 .7 3.5 2.7 3.5 5.5"/>',
    risk:'<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.01"/>',
    cold:'<path d="M12 2v20M4.9 7l14.2 10M4.9 17L19.1 7"/>',
    sar:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/>',
    inv:'<path d="M21 8l-9-5-9 5v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    ai:'<path d="M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2z"/>',
    sync:'<path d="M4 12a8 8 0 0113-6l3 3M20 12a8 8 0 01-13 6l-3-3M20 4v5h-5M4 20v-5h5"/>',
    reports:'<path d="M6 3h9l5 5v13a1 1 0 01-1 1H6a1 1 0 01-1-1V4a1 1 0 011-1z"/><path d="M9 13h6M9 17h6M9 9h2"/>',
  };
  document.querySelectorAll('i[data-i]').forEach(e => { e.outerHTML = '<svg class="ic" viewBox="0 0 24 24">' + ICONS[e.dataset.i] + '</svg>'; });

  const S = { online: navigator.onLine, sel: 0, demoStep: 0, cargoConsign: null, sample: null };

  function toast(msg, red) {
    const box = $('toast'); while (box.children.length >= 2) box.firstChild.remove();
    const t = document.createElement('div'); t.className = 'toast' + (red ? ' r' : ''); t.textContent = msg;
    box.appendChild(t); setTimeout(() => t.remove(), 3200);
  }
  function fmtT(iso) { if (!iso) return '–'; const d = new Date(iso); return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }); }
  function fmtDT(iso) { if (!iso) return '–'; const d = new Date(iso); return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }); }
  function ago(iso) { if (!iso) return ''; const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000); if (m < 1) return 'just now'; if (m < 60) return m + ' min ago'; return Math.round(m / 60) + ' h ago'; }

  /* ---------------------------------------------------------- user + nav */
  const user = window.PL.getUser();
  $('userName').textContent = user.full_name || user.username;
  $('userRole').textContent = user.role;
  $('userAv').textContent = (user.full_name || user.username).slice(0, 1).toUpperCase();
  $('footRole').textContent = user.role;
  $('deviceLabel').textContent = 'device: ' + window.PLSync.deviceId();
  $('deviceLabel2').textContent = window.PLSync.deviceId();

  $('userBox').addEventListener('click', (e) => { if (e.target.id === 'logoutBtn') { window.PL.logout(); return; } $('userMenu').classList.toggle('on'); });
  document.addEventListener('click', (e) => { if (!$('userBox').contains(e.target)) $('userMenu').classList.remove('on'); });
  $('themeBtn').onclick = () => window.PL.toggleTheme();
  $('drawerBtn').onclick = () => $('drawer').classList.toggle('on');
  
  /* ---------------------------------------------------------- notification bell */
  let lastAlerts = [];
  function renderBellPanel() {
    let panel = $('bellPanel');
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'bellPanel';
      panel.className = 'user-menu';
      panel.style.cssText = 'right:44px;min-width:320px;max-height:380px;overflow:auto;padding:8px';
      $('bellBtn').style.position = 'relative';
      $('bellBtn').appendChild(panel);
    }
    panel.innerHTML = lastAlerts.length
      ? lastAlerts.map(a => `<div class="al ${a.level}" style="margin:6px"><div class="t"><span>${esc(a.title)}</span><span>${fmtT(a.at)}</span></div><p>${esc(a.detail)}</p></div>`).join('')
      : '<div class="fine" style="padding:10px">No alerts.</div>';
  }
  $('bellBtn').onclick = (e) => {
    e.stopPropagation();
    const panel = $('bellPanel');
    const willOpen = !(panel && panel.classList.contains('on'));
    document.querySelectorAll('.user-menu').forEach(m => m.classList.remove('on'));
    if (willOpen) { renderBellPanel(); $('bellPanel').classList.add('on'); }
  };
  document.addEventListener('click', (e) => { if (!$('bellBtn').contains(e.target)) { const p = $('bellPanel'); if (p) p.classList.remove('on'); } });
  function updateBell(alerts) {
    lastAlerts = alerts || [];
    $('bellN').style.display = lastAlerts.length ? 'flex' : 'none';
    $('bellN').textContent = lastAlerts.length;
    if ($('bellPanel') && $('bellPanel').classList.contains('on')) renderBellPanel();
  }

  const RENDERERS = { dash: renderDash, missions: renderMissions, gis: renderGIS, assets: renderAssets, cargo: renderCargo,
                      people: renderPeople, risk: renderRisk, cold: renderCold, sar: renderSAR, inv: renderInv, ai: renderAI,
                      sync: renderSync, reports: renderReports };

  function go(v) {
    document.querySelectorAll('.view').forEach(e => e.classList.remove('on'));
    $('v-' + v).classList.add('on');
    document.querySelectorAll('.nav').forEach(n => n.classList.toggle('on', n.dataset.v === v));
    (RENDERERS[v] || (() => Promise.resolve()))().catch(err => handleErr(err));
    $('main').scrollTop = 0;
  }
  document.querySelectorAll('.nav, a[data-v]').forEach(n => n.addEventListener('click', () => go(n.dataset.v)));

  function handleErr(err) {
    if (err && err.offline) { toast('Offline — showing cached data where possible', true); return; }
    if (err && err.status === 403) { toast('Your role cannot do that', true); return; }
    console.error(err); toast((err && err.message) || 'Something went wrong', true);
  }

  /* ---------------------------------------------------------- online/offline */
  function setNetUI(online) {
    S.online = online;
    $('netBtn').className = 'b-sat' + (online ? '' : ' off');
    $('netTxt').textContent = online ? 'Online' : 'Offline';
    if ($('linkLine')) $('linkLine').className = 'link' + (online ? '' : ' off');
    if ($('linkLbl')) $('linkLbl').textContent = online ? 'Backend link' : 'No link';
  }
  window.addEventListener('online', async () => { setNetUI(true); toast('Link restored — syncing queued events'); try { await autoSync(); } catch (e) {} });
  window.addEventListener('offline', () => { setNetUI(false); toast('Offline — changes will be saved on this device', true); });
  setNetUI(navigator.onLine);

  async function autoSync() {
    const res = await window.PLSync.syncNow();
    await refreshSyncBadge();
    if (res.push.pushed) toast(`${res.push.synced} synced${res.push.conflicts ? `, ${res.push.conflicts} conflict(s)` : ''}`, !!res.push.conflicts);
    return res;
  }
  async function refreshSyncBadge() {
    const pend = (await window.PLDB.pending()).length;
    $('syncBadge').style.display = pend ? 'inline-block' : 'none'; $('syncBadge').textContent = pend;
    if ($('syncPend')) $('syncPend').textContent = pend;
  }

  /* ---------------------------------------------------------- health / clock */
  async function pollHealth() {
    try {
      const r = await fetch('/api/health'); const d = await r.json();
      $('dbBadge').innerHTML = d.status === 'ok' ? `&#9679; ${d.db}` : '&#9679; db error';
      $('dbBadge').style.color = d.status === 'ok' ? 'var(--green)' : 'var(--red)';
    } catch { $('dbBadge').innerHTML = '&#9679; unreachable'; $('dbBadge').style.color = 'var(--red)'; }
  }
  setInterval(pollHealth, 15000); pollHealth();
  
  async function pollAlerts() {
    try { const d = await window.PL.authFetch('/api/dashboard'); updateBell(d.alerts); } catch (e) { /* offline or logged out — leave bell as-is */ }
  }
  setInterval(pollAlerts, 20000); pollAlerts();
  setInterval(() => { $('clock').textContent = 'UTC ' + new Date().toISOString().substr(11, 5) + ' | Bharati Base'; }, 1000);

  /* ============================================================ DASHBOARD */
  async function renderDash() {
    const d = await window.PL.authFetch('/api/dashboard');
    $('kActive').textContent = String(d.kpi.active_missions).padStart(2, '0');
    $('kActiveS').textContent = d.kpi.total_missions + ' total registered';
    $('kPersonnel').textContent = d.kpi.personnel;
    $('kPersonnelS').textContent = d.kpi.overdue_teams ? d.kpi.overdue_teams + ' team(s) overdue' : 'All teams on schedule';
    $('kAssets').textContent = d.kpi.assets;
    $('kCargo').textContent = d.kpi.cargo_in_transit;
    $('kAlert').textContent = String(d.kpi.critical_alerts).padStart(2, '0');
    $('kAlertS').textContent = d.kpi.critical_alerts ? 'SAR case active' : 'No SAR case';
    $('kAlertCard').classList.toggle('red', d.kpi.critical_alerts > 0);
    $('kLink').textContent = S.online ? 'Online' : 'Offline';
    $('kLinkS').textContent = d.kpi.open_conflicts ? d.kpi.open_conflicts + ' conflict(s) open' : 'Synchronized';

    $('alertCount').textContent = d.alerts.length + ' open';
    $('alertCount').className = 'chip ' + (d.alerts.some(a => a.level === 'r') ? 'r' : 'a');
        updateBell(d.alerts);
    $('alertList').innerHTML = d.alerts.length ? d.alerts.map(a => `<div class="al ${a.level}"><div class="t"><span>${esc(a.title)}</span><span>${fmtT(a.at)}</span></div><p>${esc(a.detail)}</p><a data-v="${a.go}">${esc(a.cta)} &rarr;</a></div>`).join('') : '<div class="fine">No open alerts.</div>';
    $('alertList').querySelectorAll('a[data-v]').forEach(a => a.onclick = () => go(a.dataset.v));

    const s = d.survival;
    $('survTag').textContent = s.passed ? 'PASSED' : 'FAILED'; $('survTag').className = 'chip ' + (s.passed ? 'g' : 'r');
    $('survBody').innerHTML = s.rows.map(r => `<div class="row"><span class="mute">${esc(r.label)}</span><b>${r.days} days</b></div><div class="bar"><i style="width:${Math.min(100, r.days / s.required_days * 60)}%;background:${r.pass ? 'var(--green)' : 'var(--red)'}"></i></div>`).join('') + `<div class="fine">Required minimum: ${s.required_days} days</div>`;

    if (d.fuel) $('fuelBody').innerHTML = `<div class="row"><span class="mute">Bulk tanks</span><b class="mono">${d.fuel.bulk_l.toLocaleString()} L</b></div><div class="row"><span class="mute">Daily burn rate</span><b class="mono">${d.fuel.burn_l_per_day} L/day</b></div><div class="row"><span class="mute">Days remaining</span><b class="mono" style="color:var(--green)">${d.fuel.days} d</b></div>${d.fuel.traverse_reserve_l != null ? `<div class="row"><span class="mute">Traverse reserve</span><b class="mono">${d.fuel.traverse_reserve_l} L</b></div>` : ''}`;

    if (d.cold) {
      $('coldTag').textContent = d.cold.status.toUpperCase(); $('coldTag').className = 'chip ' + (d.cold.status === 'ok' ? 'g' : d.cold.status === 'warning' ? 'a' : 'r');
      $('coldBody').innerHTML = `<div class="row"><span class="mute">Sample</span><b class="mono">${esc(d.cold.sample_id)}</b></div><div class="row"><span class="mute">Current</span><b class="mono">${d.cold.current} &deg;C</b></div><div class="row"><span class="mute">Safe limit</span><b class="mono">${d.cold.limit_c} &deg;C</b></div><div class="row"><span class="mute">Time to breach</span><b class="mono" style="color:var(--amber)">${d.cold.eta_h != null ? '~' + d.cold.eta_h + ' h' : '—'}</b></div>`;
    }
    if (d.weather) $('wxBody').innerHTML = `<div class="row"><span class="mute">Surface temp</span><b class="mono">${d.weather.temp_c} &deg;C</b></div><div class="row"><span class="mute">Wind</span><b class="mono" style="color:var(--amber)">${d.weather.wind_kt} kt &middot; gust ${d.weather.gust_kt}</b></div><div class="row"><span class="mute">Visibility</span><b class="mono">${d.weather.vis_km} km</b></div><div class="row"><span class="mute">Pressure</span><b class="mono">${d.weather.pressure_hpa} hPa</b></div>`;

    window.PLMap.render($('dashMap'), { vw: 560, vh: 380, labels: true }).catch(() => { $('dashMap').innerHTML = '<div class="fine" style="padding:20px">Map unavailable offline.</div>'; });
    updateSarButton().catch(() => {});
  }

  /* ============================================================ MISSIONS */
  let MISSIONS = [];
  async function renderMissions() {
    MISSIONS = await window.PL.authFetch('/api/missions');
    $('missionCount').textContent = MISSIONS.length + ' total';
    $('missionList').innerHTML = MISSIONS.map((m, i) => `<div class="ms-item ${i === S.sel ? 'sel' : ''}" data-i="${i}"><div class="t"><span class="ms-id">${m.id}</span><h4>${esc(m.name)}</h4><span style="flex:1"></span><span class="chip ${m.status === 'ACTIVE' ? 'g' : 'b'}">${m.status}</span></div><div class="fine">${esc(m.org)}</div>
      <div class="meta"><div><small>Base station</small>${esc(m.base)}</div><div><small>Destination</small>${esc(m.destination)}</div><div><small>Field team</small>${m.team_size} people</div><div><small>Risk rating</small><b style="color:var(--${m.risk_rating === 'HIGH' ? 'red' : m.risk_rating === 'MEDIUM' ? 'amber' : 'green'})">${m.risk_rating}</b></div></div>
      <div class="row fine"><span>Traverse progression</span><b>${m.progress}%</b></div><div class="bar"><i style="width:${m.progress}%"></i></div></div>`).join('');
    $('missionList').querySelectorAll('.ms-item').forEach(el => el.onclick = () => { S.sel = Number(el.dataset.i); renderMissions(); });
    const m = MISSIONS[S.sel] || MISSIONS[0];
    if (!m) { $('dossier').innerHTML = '<div class="fine">No missions yet.</div>'; return; }
    $('dossier').innerHTML = `<div class="fine mono">${m.id} DOSSIER</div><h3 style="font-size:16px;margin:3px 0">${esc(m.name)}</h3><div class="fine">${m.start_date} - ${m.end_date}</div>
      <div class="fine" style="margin:12px 0 4px;font-weight:600;color:var(--text)">Mission objective</div><div class="note">${esc(m.objective || '—')}</div>
      <div class="row" style="margin-top:8px"><span class="mute">Permit</span><span class="chip ${m.permit === 'VALID' ? 'g' : m.permit === 'PENDING' ? 'a' : 'r'}">${m.permit}${m.permit_valid_until ? ' until ' + m.permit_valid_until : ''}</span></div>
      <div class="fine" style="margin:10px 0 4px;font-weight:600;color:var(--text)">Assigned team (${m.team.length})</div>${m.team.map(p => `<div class="row"><span>${esc(p.name)} <span class="fine">(${esc(p.role)})</span></span></div>`).join('') || '<div class="fine">No one assigned yet.</div>'}
      <div class="fine" style="margin:10px 0 4px;font-weight:600;color:var(--text)">Allocated assets</div><div>${m.assets.map(a => `<span class="ms-id" style="margin-right:4px">${a}</span>`).join('') || '<span class="fine">None</span>'}</div>
      <div class="fine" style="margin:12px 0 4px;font-weight:600;color:var(--text)">Status</div>
      <div class="gr g2" style="gap:6px" id="msStatusBtns">${['ACTIVE', 'PAUSED', 'COMPLETED', 'CANCELLED'].map(st => `<button class="btn ${st === m.status ? '' : 'w'} s" data-st="${st}">${st}</button>`).join('')}</div>`;
    $('msStatusBtns').querySelectorAll('button').forEach(b => b.onclick = async () => {
      try { await window.PL.authFetch(`/api/missions/${m.id}/status`, { method: 'PATCH', json: { status: b.dataset.st } }); toast('Mission set to ' + b.dataset.st); renderMissions(); }
      catch (e) { handleErr(e); }
    });
  }
  $('newMissionBtn').onclick = async () => {
    const name = prompt('Expedition name?'); if (!name) return;
    const base = prompt('Base station?', 'Bharati') || 'Bharati';
    try { await window.PL.authFetch('/api/missions', { method: 'POST', json: { name, base } }); toast('Expedition created'); renderMissions(); }
    catch (e) { handleErr(e); }
  };

  /* ============================================================ GIS */
  async function renderGIS() {
    const { feats } = await window.PLMap.render($('gisMap'), { vw: 900, vh: 620, labels: true });
    const rows = feats.features.filter(f => f.properties.layer !== 'sar_cell').map(f => {
      const name = f.properties.name || f.properties.team || f.properties.id || '—';
      return `<tr><td>${esc(name)}</td><td class="fine">${esc(f.properties.layer)}</td></tr>`;
    });
    $('posBody').innerHTML = rows.join('') || '<tr><td colspan="2" class="fine">No features.</td></tr>';
  }

  /* ============================================================ ASSETS */
  async function renderAssets() {
    const d = await window.PL.authFetch('/api/assets?limit=300');
    $('assetBody').innerHTML = d.items.map(a => `<tr><td class="mono">${a.id}</td><td>${esc(a.name)}</td><td>${esc(a.type)}</td><td>${esc(a.station)}</td><td><span class="chip ${a.status === 'Maintenance' ? 'a' : a.status === 'Retired' ? '' : 'g'}">${a.status.toUpperCase()}</span></td><td class="r mono">${a.level_pct}%</td><td class="mono mute">${ago(a.last_seen_at)}</td><td class="r"><button class="btn w s" data-id="${a.id}" data-st="${a.status === 'Retired' ? 'Available' : 'Retired'}">${a.status === 'Retired' ? 'Restore' : 'Retire'}</button></td></tr>`).join('');
    $('assetBody').querySelectorAll('button[data-id]').forEach(b => b.onclick = async () => {
      try { await window.PL.authFetch(`/api/assets/${b.dataset.id}`, { method: 'PATCH', json: { status: b.dataset.st } }); toast('Asset updated'); renderAssets(); } catch (e) { handleErr(e); }
    });
  }
  $('addAssetBtn').onclick = async () => {
    const name = $('aName').value.trim(); if (!name) { toast('Enter an asset name', true); return; }
    try { await window.PL.authFetch('/api/assets', { method: 'POST', json: { name, type: $('aType').value, station: $('aSt').value } }); $('aName').value = ''; toast('Asset added'); renderAssets(); } catch (e) { handleErr(e); }
  };

  /* ============================================================ CARGO */
  async function renderCargo() {
    const d = await window.PL.authFetch('/api/cargo');
    const sel = $('cargoConsignSel');
    if (!S.cargoConsign || !d.consignments.includes(S.cargoConsign)) S.cargoConsign = d.consignments[0];
    sel.innerHTML = d.consignments.map(c => `<option value="${c}" ${c === S.cargoConsign ? 'selected' : ''}>${c}</option>`).join('');
    sel.onchange = () => { S.cargoConsign = sel.value; renderCargo(); };
    if (!S.cargoConsign) { $('cargoChainCard').innerHTML = '<div class="fine">No cargo on file.</div>'; return; }

    const items = d.items.filter(i => i.consignment === S.cargoConsign);
    const chk = await window.PL.authFetch(`/api/cargo/consignments/${S.cargoConsign}/check`);
    const nodes = items[0] ? items[0].route_nodes : [];
    const single = items.find(i => i.next_node);
    $('cargoChainCard').innerHTML = `<div class="card-h"><h3>Consignment ${S.cargoConsign}</h3><span class="chip">${items.length} item(s)</span></div>
      <div class="row"><span class="mute">Air cargo</span><b class="mono">${chk.air_kg} kg</b> <span class="chip ${chk.state === 'ok' ? 'g' : chk.state === 'warn' ? 'a' : 'r'}">limit ${chk.limit_min}-${chk.limit_max} kg</span></div>
      <div class="fine" style="margin-top:6px">Route nodes: ${nodes.join(' &rarr; ')}</div>
      ${single ? `<div style="margin-top:10px"><button class="btn s" id="handoffBtn">Record handoff: ${single.id} &rarr; ${esc(single.next_node)}</button></div>` : ''}`;
    if (single) $('handoffBtn').onclick = async () => { try { await queueOrSend('HANDOFF', single.id, { cargo_id: single.id, to_node: single.next_node }); renderCargo(); } catch (e) { handleErr(e); } };

    $('cargoCheckBody').innerHTML = items.map(i => `<tr><td>${esc(i.name)}</td><td class="r mono">${i.weight_kg} kg</td><td>${i.route === 'air' ? 'Air' : 'Ship'}</td><td><span class="chip ${i.check.level === 'g' ? 'g' : i.check.level === 'a' ? 'a' : 'r'}">${esc(i.check.label)}</span></td></tr>`).join('') || '<tr><td colspan="4" class="fine">No items.</td></tr>';

    const rules = await window.PL.authFetch('/api/cargo/rules');
    $('cargoRulesBody').innerHTML = `<div class="row"><span class="mute">Small flights carry</span><b class="mono">${rules.air_limit_kg.min}-${rules.air_limit_kg.max} kg</b></div><div class="fine" style="margin-bottom:8px">${esc(rules.air_limit_kg.note)}</div>
      <div class="row"><span class="mute">Hazardous cargo</span><b>Not by air</b></div><div class="fine" style="margin-bottom:8px">${esc(rules.hazard_rule.text)}</div>
      <div class="note">Source: ${esc(rules.air_limit_kg.source)}${rules.air_limit_kg.verified ? ' (verified)' : ''}</div>`;
  }

  /* ============================================================ PERSONNEL */
  async function renderPeople() {
    const teams = await window.PL.authFetch('/api/teams');
    const sel = $('teamFilter'); const cur = sel.value;
    sel.innerHTML = '<option value="">All teams</option>' + teams.map(t => `<option value="${t.team}">${t.team}</option>`).join('');
    sel.value = cur; sel.onchange = renderPeople;
    const d = await window.PL.authFetch('/api/personnel' + (sel.value ? '?team=' + encodeURIComponent(sel.value) : ''));
    $('peopleBody').innerHTML = d.items.map(p => { const c = p.status === 'ok' ? ['g', 'ON SCHEDULE'] : p.status === 'due_soon' ? ['a', 'DUE SOON'] : ['r', 'MISSED'];
      return `<tr><td>${esc(p.name)}</td><td class="mute">${esc(p.role)}</td><td>${esc(p.team)}</td><td>${esc(p.station)}</td><td class="mono">${fmtT(p.last_checkin_at)}</td><td class="mono">${fmtT(p.next_due_at)}</td><td><span class="chip ${c[0]}">${c[1]}</span></td><td class="r"><button class="btn w s" data-team="${esc(p.team)}" data-id="${p.id}">Check in</button></td></tr>`; }).join('');
    $('peopleBody').querySelectorAll('button[data-id]').forEach(b => b.onclick = async () => {
      try { await queueOrSend('CHECKIN', b.dataset.id, { person_id: b.dataset.id }); renderPeople(); } catch (e) { handleErr(e); }
    });
  }

  /* ============================================================ RISK */
  let riskDebounce;
  function wireRiskInputs() {
    ['rIce', 'rWind', 'rVis', 'rDist', 'rAge'].forEach(id => $(id).oninput = () => { clearTimeout(riskDebounce); riskDebounce = setTimeout(computeRisk, 120); updateRiskLabels(); });
  }
  function updateRiskLabels() {
    $('rIceV').textContent = $('rIce').value + ' %'; $('rWindV').textContent = $('rWind').value + ' kt'; $('rVisV').textContent = $('rVis').value + ' km';
    $('rDistV').textContent = $('rDist').value + ' km'; $('rAgeV').textContent = $('rAge').value + ' h';
  }
  async function computeRisk() {
    try {
      const body = { ice_pct: +$('rIce').value, wind_kt: +$('rWind').value, visibility_km: +$('rVis').value, distance_km: +$('rDist').value, data_age_h: +$('rAge').value };
      const r = await window.PL.authFetch('/api/risk/score', { method: 'POST', json: body });
      $('rScore').textContent = r.score.toFixed(2); $('rScore').style.color = `var(--${r.band === 'HIGH' ? 'red' : r.band === 'MODERATE' ? 'amber' : 'green'})`;
      $('rBand').textContent = r.band; $('rBand').className = 'chip ' + (r.band === 'HIGH' ? 'r' : r.band === 'MODERATE' ? 'a' : 'g');
      $('rParts').innerHTML = r.parts.map(p => `<div class="rr" style="grid-template-columns:90px 1fr 84px;margin:5px 0"><span>${p.label}</span><div class="bar" style="margin:0"><i style="width:${p.value * 100}%;background:var(--${p.value > .66 ? 'red' : p.value > .33 ? 'amber' : 'green'})"></i></div><b>${p.value.toFixed(2)} x ${p.weight}</b></div>`).join('');
      $('rWhy').innerHTML = `<b style="color:var(--text)">Why:</b> ${esc(r.why)}`;
    } catch (e) { handleErr(e); }
  }
  async function renderRisk() {
    updateRiskLabels(); wireRiskInputs(); computeRisk();
    const routes = await window.PL.authFetch('/api/risk/routes');
    $('routeBody').innerHTML = routes.map(r => `<div class="row"><span>${esc(r.name)} <span class="fine">(${r.distance_km} km)</span></span><span class="chip ${r.band === 'HIGH' ? 'r' : r.band === 'MODERATE' ? 'a' : 'g'}">${r.band} · ${r.score.toFixed(2)}</span></div>`).join('') || '<div class="fine">No routes on file.</div>';
  }

  /* ============================================================ COLD CHAIN */
  function lineChart(series, o = {}) {
    const W = 440, H = 190, p = 30, all = series.flatMap(s => s.d), mn = o.min ?? Math.min(...all) - 1, mx = o.max ?? Math.max(...all) + 1;
    const X = (i, n) => p + i * (W - p * 2) / (n - 1), Y = v => H - p - (v - mn) / (mx - mn) * (H - p * 2);
    let g = `<svg viewBox="0 0 ${W} ${H}" style="width:100%">`;
    for (let i = 0; i < 5; i++) { const y = p + i * (H - p * 2) / 4; g += `<line x1="${p}" x2="${W - p}" y1="${y}" y2="${y}" stroke="var(--line2)"/><text x="3" y="${y + 3}" font-size="9" fill="var(--dim)">${(mx - (mx - mn) * i / 4).toFixed(0)}</text>`; }
    if (o.limit !== undefined) { const y = Y(o.limit); g += `<line x1="${p}" x2="${W - p}" y1="${y}" y2="${y}" stroke="var(--red)" stroke-dasharray="5 4"/><text x="${W - p - 88}" y="${y - 5}" font-size="9.5" fill="var(--red)">safe limit ${o.limit} C</text>`; }
    series.forEach(s => { g += `<polyline points="${s.d.map((v, i) => X(i, s.d.length) + ',' + Y(v)).join(' ')}" fill="none" stroke="${s.c}" stroke-width="${s.w || 2}"/>`; (s.flag || []).forEach(i => g += `<circle cx="${X(i, s.d.length)}" cy="${Y(s.d[i])}" r="4.5" fill="var(--red)" stroke="var(--card)" stroke-width="1.5"/>`); });
    return g + '</svg>';
  }
  async function renderCold() {
    const samples = await window.PL.authFetch('/api/coldchain');
    const sel = $('sampleSel');
    if (!S.sample || !samples.find(s => s.sample_id === S.sample)) S.sample = samples[0] && samples[0].sample_id;
    sel.innerHTML = samples.map(s => `<option value="${s.sample_id}" ${s.sample_id === S.sample ? 'selected' : ''}>${s.sample_id}</option>`).join('');
    sel.onchange = () => { S.sample = sel.value; renderCold(); };
    if (!S.sample) return;
    const full = await window.PL.authFetch(`/api/coldchain/${S.sample}`);
    $('coldTitle').innerHTML = `<h3>${esc(full.sample_id)}</h3><span class="chip">${esc(full.container_id)}</span>`;
    const series = full.series.map(s => s.filtered);
    const raw = full.series.map(s => s.raw);
    const flags = full.series.map((s, i) => s.outlier ? i : -1).filter(i => i >= 0);
    const forecast = full.forecast.map(f => f.temp);
    $('coldChart').innerHTML = lineChart([{ d: raw, c: 'var(--dim)', w: 1.4, flag: flags }, { d: series.concat(forecast.slice(1)), c: 'var(--blue)', w: 2.2 }], { limit: full.limit_c, min: Math.min(...raw, full.limit_c) - 2, max: Math.max(...raw) + 2 });
    $('cNow').textContent = full.current + ' C';
    $('cRate').textContent = (full.rate_c_per_h >= 0 ? '+' : '') + full.rate_c_per_h + ' C/h';
    $('cETA').textContent = full.eta_h != null ? full.eta_h + ' h' : '—';
    $('cETA').style.color = full.eta_h != null && full.eta_h < 4 ? 'var(--red)' : 'var(--amber)';
  }
  $('coldDelayBtn').onclick = async () => { try { await window.PL.authFetch(`/api/coldchain/${S.sample}/simulate-delay`, { method: 'POST', json: { hours: 4 } }); toast('Simulated 4 h delay applied', true); renderCold(); renderDash().catch(() => {}); } catch (e) { handleErr(e); } };
  $('coldResetBtn').onclick = async () => { try { await window.PL.authFetch(`/api/coldchain/${S.sample}/reset-simulation`, { method: 'POST' }); toast('Simulation reset'); renderCold(); } catch (e) { handleErr(e); } };
  $('addReadingBtn').onclick = async () => {
    const t = parseFloat($('readTemp').value); if (Number.isNaN(t)) { toast('Enter a temperature', true); return; }
    const amb = $('readAmbient').value ? parseFloat($('readAmbient').value) : null;
    try { await queueOrSend('READING', S.sample, { sample_id: S.sample, temp_c: t, ambient_c: amb }); $('readTemp').value = ''; $('readAmbient').value = ''; renderCold(); } catch (e) { handleErr(e); }
  };

  /* ============================================================ SAR */
  async function updateSarButton() {
    const st = await window.PL.authFetch('/api/sar/status');
    const has = !!st.incident;
    $('sarBtn').className = 'b-sar' + (has ? '' : ' idle');
    $('sarBtn').textContent = has ? 'SAR ALERT · ' + st.incident.id : 'No active incident';
    $('sarBadge').style.display = has ? 'inline-block' : 'none';
    return st;
  }
  async function renderSAR() {
    const st = await updateSarButton();
    if (!st.incident) {
      $('sarTL').innerHTML = st.overdue.length ? `<div class="fine">${st.overdue.length} team(s) overdue. Click "Run missed check-in scenario" or wait for the automatic alert.</div>` : '<div class="fine">No incident yet. All teams on schedule.</div>';
      $('sarState').textContent = 'STANDBY'; $('sarState').className = 'chip';
      $('sarInfo').textContent = 'Waiting for scenario'; $('sarTeam').textContent = '–'; $('sarWind').textContent = '–'; $('sarBeacon').textContent = '-'; $('sarCells').textContent = '-';
      $('sarMap').innerHTML = '';
      return;
    }
    const inc = st.incident;
    $('sarState').textContent = inc.state; $('sarState').className = 'chip r';
    $('sarInfo').textContent = `${inc.id}, team ${inc.team}`;
    $('sarTeam').textContent = inc.team; $('sarWind').textContent = inc.weather ? `${inc.weather.wind_kt} kt from ${inc.weather.wind_dir}` : '–';
    $('sarBeacon').textContent = inc.last[0].toFixed(3) + ', ' + inc.last[1].toFixed(3);
    $('sarCells').textContent = inc.grid ? inc.grid.cells.length + ' cells' : '-';
    $('sarTL').innerHTML = inc.actions.map(a => `<div class="d"><b>${esc(a.title)}</b>${esc(a.detail)}<br><small>${fmtT(a.at)} UTC</small></div>`).join('');
    window.PLMap.render($('sarMap'), { vw: 900, vh: 620, labels: true }).catch(() => {});
  }
  $('sarScenarioBtn').onclick = async () => {
    try { await window.PL.authFetch('/api/sar/scenario', { method: 'POST' }); toast('Scenario started: Team Bravo missed check-in', true); renderSAR(); renderDash().catch(() => {}); }
    catch (e) { handleErr(e); }
  };
  $('sarResetBtn').onclick = async () => { try { await window.PL.authFetch('/api/sar/reset', { method: 'POST' }); toast('SAR scenario reset'); renderSAR(); renderDash().catch(() => {}); } catch (e) { handleErr(e); } };
  setInterval(() => { if ($('v-sar').classList.contains('on') || $('v-dash').classList.contains('on')) updateSarButton().catch(() => {}); }, 12000);

  /* ============================================================ INVENTORY */
  async function renderInv() {
    const d = await window.PL.authFetch('/api/inventory');
    $('invBody').innerHTML = d.items.map(i => `<tr><td>${esc(i.name)}</td><td class="r mono">${Math.round(i.qty)} ${esc(i.unit)}</td><td class="r mono">${i.daily_use}</td><td class="r mono" style="color:var(--${i.status === 'below_min' ? 'red' : i.status === 'watch' ? 'amber' : 'green'})">${i.days_left > 90 ? '90+' : i.days_left}</td><td><span class="chip ${i.status === 'below_min' ? 'r' : i.status === 'watch' ? 'a' : 'g'}">${i.status.replace('_', ' ').toUpperCase()}</span></td><td class="r"><button class="btn w s" data-id="${i.id}">-10%</button></td></tr>`).join('');
    $('invChart').innerHTML = d.items.map(i => { const dpct = Math.min(i.days_left / 30, 1) * 100; return `<div class="row"><span class="mute">${esc(i.name)}</span><b class="mono">${i.days_left > 30 ? '30+' : i.days_left} d</b></div><div class="bar"><i style="width:${dpct}%;background:var(--${i.status === 'below_min' ? 'red' : i.days_left < 7 ? 'amber' : 'blue'})"></i></div>`; }).join('');
    $('invBody').querySelectorAll('button[data-id]').forEach(b => b.onclick = async () => {
      const item = d.items.find(i => i.id === b.dataset.id);
      try { await queueOrSend('STOCK', item.id, { item_id: item.id, delta: -Math.round(item.qty * 0.1), reason: 'manual adjustment' }); renderInv(); } catch (e) { handleErr(e); }
    });
  }

  /* ============================================================ AI ASSISTANT */
  async function renderAI() {
    if ($('chat').childElementCount === 0) $('chat').innerHTML = '<div class="msg a">I answer only from operational records and list what I used. Pick a question or type your own.</div>';
    const sugg = await window.PL.authFetch('/api/assistant/suggestions');
    $('sugg').innerHTML = sugg.map(q => `<button data-q="${esc(q)}">${esc(q)}</button>`).join('');
    $('sugg').querySelectorAll('button').forEach(b => b.onclick = () => askAI(b.dataset.q));
  }
  async function askAI(q) {
    const c = $('chat'); c.insertAdjacentHTML('beforeend', `<div class="msg u">${esc(q)}</div>`); c.scrollTop = c.scrollHeight;
    try {
      const r = await window.PL.authFetch('/api/assistant/ask', { method: 'POST', json: { question: q } });
      c.insertAdjacentHTML('beforeend', `<div class="msg a">${esc(r.answer)}${r.sources.length ? `<div class="src">sources: ${r.sources.map(esc).join(', ')}</div>` : ''}</div>`);
    } catch (e) { c.insertAdjacentHTML('beforeend', `<div class="msg a">Sorry, I could not reach the backend just now.</div>`); }
    c.scrollTop = c.scrollHeight;
  }
  $('chatSendBtn').onclick = () => { const v = $('chatInput').value.trim(); if (!v) return; $('chatInput').value = ''; askAI(v); };
  $('chatInput').onkeydown = (e) => { if (e.key === 'Enter') $('chatSendBtn').click(); };

  /* ============================================================ SYNC */
  async function renderSync() {
    await refreshSyncBadge();
    setNetUI(navigator.onLine);
    const items = await window.PLDB.all();
    $('qSub').textContent = items.length ? `${items.filter(i => i.status === 'pending').length} pending / ${items.length} total` : '';
    $('queue').innerHTML = items.slice(0, 30).map(e => `<div class="q ${e.status === 'synced' ? 's' : e.status === 'conflict' ? 'c' : 'p'}"><div style="flex:1"><div>${esc(summarizeEvent(e))}</div><div class="m">${e.event_id.slice(0, 8)} &middot; ${e.type} &middot; ${fmtT(e.created_at)}</div></div><span class="chip ${e.status === 'synced' ? 'g' : e.status === 'conflict' ? 'r' : e.status === 'rejected' ? 'r' : 'a'}">${e.status.toUpperCase()}</span></div>`).join('') || '<div class="fine">Queue is empty. Try an action while offline (devtools &rarr; Network &rarr; Offline), then come back here.</div>';

    try {
      const conflicts = await window.PL.authFetch('/api/sync/conflicts?status=open');
      $('conflictBody').innerHTML = conflicts.length ? conflicts.map(c => `<div class="al a"><div class="t"><span>${esc(c.entity)}.${esc(c.field)} on ${esc(c.entity_id)}</span><span>${fmtT(c.created_at)}</span></div><p>Server (${esc(c.server_device)}): <b>${esc(String(c.server_value))}</b> &nbsp;|&nbsp; Device (${esc(c.device_id)}): <b>${esc(String(c.device_value))}</b></p><div style="display:flex;gap:8px;margin-top:6px"><button class="btn s" data-c="${c.id}" data-choice="server">Keep server value</button><button class="btn w s" data-c="${c.id}" data-choice="device">Keep device value</button></div></div>`).join('') : '<div class="fine">No open conflicts.</div>';
      $('conflictBody').querySelectorAll('button[data-c]').forEach(b => b.onclick = async () => { try { await window.PL.authFetch(`/api/sync/conflicts/${b.dataset.c}/resolve`, { method: 'POST', json: { choice: b.dataset.choice } }); toast('Conflict resolved'); renderSync(); } catch (e) { handleErr(e); } });
    } catch { $('conflictBody').innerHTML = '<div class="fine">Could not load conflicts.</div>'; }
  }
  function summarizeEvent(e) {
    if (e.type === 'CHECKIN') return 'Check-in: ' + (e.payload.team || e.payload.person_id);
    if (e.type === 'HANDOFF') return `Cargo ${e.payload.cargo_id} to ${e.payload.to_node}`;
    if (e.type === 'STOCK') return `Stock ${e.payload.item_id} ${e.payload.delta >= 0 ? '+' : ''}${e.payload.delta}`;
    if (e.type === 'READING') return `Reading ${e.payload.sample_id}: ${e.payload.temp_c} C`;
    if (e.type === 'EDIT') return `${e.entity_id}: ${e.payload.field} = ${e.payload.value}`;
    return e.type + ' ' + e.entity_id;
  }
  $('syncNowBtn').onclick = async () => { try { await autoSync(); renderSync(); } catch (e) { handleErr(e); } };
  $('testCheckinBtn').onclick = async () => { try { await window.PLDB.enqueue('CHECKIN', 'Bravo', { team: 'Bravo' }); toast('Queued locally (IndexedDB)'); refreshSyncBadge(); renderSync(); } catch (e) { handleErr(e); } };
  $('testConflictBtn').onclick = async () => { try { await window.PLDB.enqueue('EDIT', 'INV-MED', { entity: 'inventory', field: 'min_qty', value: 6 }); toast('Queued a test edit'); refreshSyncBadge(); renderSync(); } catch (e) { handleErr(e); } };

  /** Every field write goes through here: queue locally first (real IndexedDB), then try an
   *  immediate send if online. If offline, it simply stays queued — this is not a simulation. */
  async function queueOrSend(type, entityId, payload) {
    await window.PLDB.enqueue(type, entityId, payload);
    await refreshSyncBadge();
    if (navigator.onLine) { try { await autoSync(); } catch (e) { /* stays queued */ } }
    else toast('Saved on this device — will sync when back online', true);
  }

  /* ============================================================ REPORTS */
  async function renderReports() {
    const log = await window.PL.authFetch('/api/sync/log?limit=15');
    $('syncLogBody').innerHTML = `<div class="row"><span class="mute">Accepted</span><b style="color:var(--green)">${log.stats.accepted}</b></div><div class="row"><span class="mute">Conflicts</span><b style="color:var(--amber)">${log.stats.conflict}</b></div><div class="row"><span class="mute">Rejected</span><b style="color:var(--red)">${log.stats.rejected}</b></div>` +
      log.events.map(e => `<div class="fine" style="margin-top:4px">${fmtT(e.at)} &middot; ${esc(e.device_id)} &middot; ${esc(e.summary)}</div>`).join('');
        try {
      const audit = await window.PL.authFetch('/api/reports/audit?limit=40');
      $('auditBody').innerHTML = audit.map(a => `<tr><td class="mono">${fmtDT(a.at)}</td><td>${esc(a.user)}</td><td>${esc(a.action)}</td><td class="fine">${esc(a.entity)} ${esc(a.entity_id)}</td></tr>`).join('') || '<tr><td colspan="4" class="fine">No audit rows yet.</td></tr>';
    } catch { $('auditBody').innerHTML = '<tr><td colspan="4" class="fine">Manager/leader role required.</td></tr>'; }
    document.querySelectorAll('.dl').forEach(btn => btn.onclick = async () => {
      const original = btn.textContent; btn.disabled = true; btn.textContent = 'Downloading…';
      try { await window.PL.authDownload(btn.dataset.path, btn.dataset.file); toast('Downloaded ' + btn.dataset.file); }
      catch (e) { handleErr(e); }
      finally { btn.disabled = false; btn.textContent = original; }
    });
  }

  /* ============================================================ demo walkthrough */
  const DEMO = [
    ['Show the dashboard', async () => go('dash')],
    ['Open Offline Sync', async () => go('sync')],
    ['Queue a check-in locally (IndexedDB)', async () => { await window.PLDB.enqueue('CHECKIN', 'Bravo', { team: 'Bravo' }); await refreshSyncBadge(); renderSync(); }],
    ['Sync the queue to the backend', async () => { await autoSync(); renderSync(); }],
    ['Run the missed check-in scenario', async () => { go('sar'); await window.PL.authFetch('/api/sar/scenario', { method: 'POST' }); renderSAR(); }],
    ['Open Route Risk', async () => go('risk')],
    ['Open Cold-Chain and simulate a delay', async () => { go('cold'); await window.PL.authFetch(`/api/coldchain/${S.sample}/simulate-delay`, { method: 'POST', json: { hours: 4 } }); renderCold(); }],
    ['Ask the AI assistant a question', async () => { go('ai'); await askAI('Why is the cold-chain alert open?'); }],
  ];
  function drawDemo() { $('demoSteps').innerHTML = DEMO.map((d, i) => `<div class="ds ${i < S.demoStep ? 'd' : i === S.demoStep ? 'c' : ''}"><i>${i < S.demoStep ? '&#10003;' : i + 1}</i><span>${d[0]}</span></div>`).join(''); }
  $('demoNextBtn').onclick = async () => { if (S.demoStep >= DEMO.length) { toast('Demo finished'); return; } try { await DEMO[S.demoStep][1](); } catch (e) { handleErr(e); } S.demoStep++; drawDemo(); };
  $('demoResetBtn').onclick = async () => { S.demoStep = 0; drawDemo(); try { await window.PL.authFetch('/api/sar/reset', { method: 'POST' }); } catch (e) {} go('dash'); };
  drawDemo();

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

  /* ---------------------------------------------------------- register service worker + boot */
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
  go('dash');
})();
