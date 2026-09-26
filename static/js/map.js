/* POLARLOGIX map renderer. Draws polar-stereographic SVG maps from the GeoJSON the
 * backend serves (real Natural Earth coastline/ice-shelf polygons + live feature points
 * from the database — see app/routers/misc.py: /api/geo/coastline, /iceshelves, /features). */
(function () {
  const S = 1000;
  function proj(lat, lon) {
    const r = 2 * S * Math.tan(Math.PI / 4 + (lat * Math.PI / 180) / 2);
    const l = lon * Math.PI / 180;
    return [r * Math.sin(l), -r * Math.cos(l)];
  }
  function ringToPath(ring) { return 'M' + ring.map(([lon, lat]) => proj(lat, lon).map(n => n.toFixed(1)).join(' ')).join('L') + 'Z'; }
  function geomToPath(geom) {
    if (geom.type === 'Polygon') return geom.coordinates.map(ringToPath).join('');
    if (geom.type === 'MultiPolygon') return geom.coordinates.map(poly => poly.map(ringToPath).join('')).join('');
    if (geom.type === 'LineString') return 'M' + geom.coordinates.map(([lon, lat]) => proj(lat, lon).map(n => n.toFixed(1)).join(' ')).join('L');
    return '';
  }
  function fcToPath(fc) { return (fc.features || []).map(f => geomToPath(f.geometry)).join(''); }

  const LAYER_STYLE = {
    station: { fill: '#0e3a58', shape: 'square', r: 3.5 },
    summer_base: { fill: '#fff', stroke: '#0e3a58', shape: 'square', r: 3.5 },
    team: { fill: '#12805c', shape: 'circle', r: 3.4 },
    asset: { fill: '#1673a6', shape: 'circle', r: 2.6 },
    incident: { fill: '#d92d20', shape: 'circle', r: 4 },
  };

    /* -------------------------------------------------------- offline cache
   * Coastline and ice-shelf polygons never change and are a few hundred KB at
   * most, so we keep the last good copy in localStorage. Live feature points
   * (stations, teams, incident, SAR grid) are only cached as a fallback for
   * when the device is fully offline — they will be stale until reconnected,
   * and we say so on the map when that happens. */
  const CACHE_KEY = 'pl_map_cache_v1';
  function loadCache() { try { return JSON.parse(localStorage.getItem(CACHE_KEY) || 'null'); } catch { return null; } }
  function saveCache(data) { try { localStorage.setItem(CACHE_KEY, JSON.stringify({ ...data, cachedAt: new Date().toISOString() })); } catch { /* storage full/unavailable: skip caching silently */ } }

  async function fetchWithCache() {
    try {
      const [coast, shelf, feats] = await Promise.all([
        window.PL.authFetch('/api/geo/coastline'),
        window.PL.authFetch('/api/geo/iceshelves'),
        window.PL.authFetch('/api/geo/features'),
      ]);
      saveCache({ coast, shelf, feats });
      return { coast, shelf, feats, stale: false };
    } catch (err) {
      const cached = loadCache();
      if (cached) return { ...cached, stale: true };
      throw err;
    }
  }

  /** Renders a full map: coastline + ice shelves + live feature points.
   *  Falls back to the last cached copy (localStorage) when offline, and
   *  shows a "showing cached map" banner in that case — this is why the map
   *  keeps working with no network, not just the sync queue. */
  async function render(container, opts = {}) {
    const { coast, shelf, feats, stale } = await fetchWithCache();
    const vx = opts.vx ?? -20, vy = opts.vy ?? -560, vw = opts.vw ?? 560, vh = opts.vh ?? 380;
    let svg = `<svg viewBox="${vx} ${vy} ${vw} ${vh}" xmlns="http://www.w3.org/2000/svg">`;
    svg += `<path d="${fcToPath(coast)}" fill="#fbfcfd" stroke="#8ea3b8" stroke-width=".55"/>`;
    svg += `<path d="${fcToPath(shelf)}" fill="#dde9f3" stroke="#7d93aa" stroke-width=".4"/>`;
    const routes = feats.features.filter(f => f.properties.layer === 'route');
    routes.forEach(r => { svg += `<path d="${geomToPath(r.geometry)}" fill="none" stroke="#c86a05" stroke-width=".9" stroke-dasharray="3 2.5"/>`; });

    const sarCells = feats.features.filter(f => f.properties.layer === 'sar_cell');
    sarCells.forEach(c => { const op = Math.max(.06, Math.min(.55, c.properties.p * 6)); svg += `<path d="${geomToPath(c.geometry)}" fill="#d92d20" fill-opacity="${op.toFixed(2)}" stroke="#d92d20" stroke-opacity=".3" stroke-width=".3"/>`; });

    // Sort points so stations/incidents (drawn+labelled last) win any overlap, and
    // track label boxes already placed so nearby points don't print on top of each other.
    const order = { asset: 0, team: 1, summer_base: 2, station: 3, incident: 4 };
    const points = feats.features.filter(f => f.geometry.type === 'Point')
      .sort((a, b) => (order[a.properties.layer] ?? 0) - (order[b.properties.layer] ?? 0));
    const placedLabels = []; // [x0,y0,x1,y1] in svg units, used to skip a colliding label
    const labelW = (s) => 3.6 * s.length + 4;
    points.forEach(f => {
      const st = LAYER_STYLE[f.properties.layer] || LAYER_STYLE.asset;
      const [lon, lat] = f.geometry.coordinates;
      const [x, y] = proj(lat, lon);
      if (st.shape === 'square') svg += `<rect x="${(x - st.r).toFixed(1)}" y="${(y - st.r).toFixed(1)}" width="${st.r * 2}" height="${st.r * 2}" fill="${st.fill}" stroke="${st.stroke || '#fff'}" stroke-width="1"/>`;
      else svg += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${st.r}" fill="${st.fill}" stroke="#fff" stroke-width="1"/>`;
      if (opts.labels !== false) {
        const label = f.properties.name || f.properties.team || '';
        if (!label) return;
        const w = labelW(label), h = 8;
        const lx = x + st.r + 3, ly = y + 3;
        const box = [lx, ly - h, lx + w, ly + 2];
        const overlaps = placedLabels.some(b => !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]));
        if (overlaps) return; // drop this label rather than render an unreadable clash
        placedLabels.push(box);
        svg += `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" font-size="7.5" font-weight="600" fill="#1b2a3a" style="paint-order:stroke;stroke:#fff;stroke-width:2.2px">${escapeXml(label)}</text>`;
      }
    });
    svg += '</svg>';
        container.innerHTML = (stale ? '<div class="note" style="margin-bottom:6px">Offline — showing the last cached map. Positions may be out of date.</div>' : '') + svg;
    return { coast, shelf, feats, stale };
  }

  function escapeXml(s) { return String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }

  window.PLMap = { render, proj };
})();
