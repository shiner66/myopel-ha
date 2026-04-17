import { LitElement, html, css, nothing } from "https://unpkg.com/lit?module";

class MyOpelCard extends LitElement {
  static properties = {
    _hass:         { state: true },
    _config:       { state: true },
    _tab:          { state: true },
    _refuelView:   { state: true },
    _view360Idx:   { state: true },
    _use360:       { state: true },
    _showAcked:    { state: true },
    _periodView:   { state: true },
  };

  static styles = css`
    @import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700;800;900&family=Barlow+Condensed:wght@500;600;700;800&display=swap');

    :host {
      --op-red:      #e3001b;
      --op-red-glow: rgba(227,0,27,0.25);
      --op-dark:     #111113;
      --op-surface:  #191a1c;
      --op-card:     #1f2022;
      --op-border:   rgba(255,255,255,0.06);
      --op-text:     #eeeef0;
      --op-muted:    #666870;
      --op-green:    #22c55e;
      --op-yellow:   #f59e0b;
      font-family: 'Barlow', 'Helvetica Neue', Arial, sans-serif;
    }
    ha-card {
      background: var(--op-dark);
      color: var(--op-text);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 12px 48px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.04);
    }

    /* ── Hero ── */
    .op-hero {
      position: relative;
      background: radial-gradient(ellipse at 60% 0%, #1c1012 0%, #111113 60%);
      overflow: hidden;
      padding-bottom: 16px;
    }
    .op-hero::before {
      content: '';
      position: absolute;
      top: -40px; right: -40px;
      width: 180px; height: 180px;
      background: radial-gradient(circle, rgba(227,0,27,0.08) 0%, transparent 70%);
      pointer-events: none;
    }
    .op-hero-topbar {
      display: flex; align-items: center; justify-content: space-between;
      padding: 18px 18px 0;
    }
    .op-hero-title {
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 20px; font-weight: 800;
      letter-spacing: 0.5px; text-transform: uppercase;
    }
    .op-vin-badge {
      font-size: 10px; color: var(--op-muted);
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--op-border);
      border-radius: 5px; padding: 3px 8px;
      letter-spacing: 1px; font-weight: 600;
      font-family: 'Barlow Condensed', sans-serif;
    }
    .op-hero-topbar-right {
      display: flex; align-items: center; gap: 6px;
    }
    .op-360-toggle {
      font-size: 10px; font-weight: 700;
      font-family: 'Barlow Condensed', sans-serif;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--op-border);
      border-radius: 5px; padding: 3px 8px;
      cursor: pointer; letter-spacing: 1px;
      color: var(--op-muted);
      transition: background 0.2s, border-color 0.2s, color 0.2s;
      user-select: none;
    }
    .op-360-toggle:hover { border-color: rgba(255,255,255,0.18); }
    .op-360-toggle.active {
      background: rgba(227,0,27,0.15);
      border-color: rgba(227,0,27,0.5);
      color: var(--op-red);
    }

    /* car image */
    .op-car-wrap {
      position: relative; padding: 8px 0 0;
      min-height: 155px;
      display: flex; align-items: center; justify-content: center;
    }
    /* visual3D images have a white background — radial glow blends it with the dark card */
    .op-car-wrap.has-v3d {
      background: radial-gradient(ellipse at 50% 42%,
        rgba(255,255,255,0.11) 0%,
        rgba(255,255,255,0.04) 45%,
        transparent 68%);
      border-radius: 10px;
      margin: 4px 8px 0;
    }
    .op-car-img {
      max-width: 92%; max-height: 165px;
      object-fit: contain;
      filter: drop-shadow(0 10px 30px rgba(0,0,0,0.6));
      transition: opacity 0.3s;
    }
    .op-car-mileage {
      position: absolute; bottom: 2px; left: 18px;
      font-size: 12px; color: var(--op-muted);
      font-weight: 500;
    }
    .op-car-mileage strong {
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 20px; font-weight: 800; color: var(--op-text);
      letter-spacing: -0.5px;
    }
    .op-car-updated {
      position: absolute; bottom: 2px; right: 18px;
      font-size: 10px; color: var(--op-muted); text-align: right;
      font-weight: 500;
    }

    /* ── 360° drag viewer ── */
    .op-car-wrap.is-360 {
      cursor: grab;
      touch-action: pan-y;
    }
    .op-car-wrap.is-360:active { cursor: grabbing; }
    .op-car-wrap.is-360 .op-car-img {
      pointer-events: none;
      user-select: none;
    }
    .op-360-hint {
      position: absolute; bottom: 22px; left: 50%; transform: translateX(-50%);
      font-size: 10px; color: var(--op-muted);
      pointer-events: none; white-space: nowrap;
      letter-spacing: 0.5px; opacity: 0.8;
    }

    /* ── Fuel bar — premium ── */
    .op-hero-fuel {
      margin: 12px 16px 0;
      padding: 14px 16px;
      background: linear-gradient(135deg, rgba(255,255,255,0.035) 0%, rgba(255,255,255,0.015) 100%);
      border-radius: 14px;
      border: 1px solid var(--op-border);
      cursor: pointer;
      transition: border-color 0.2s;
    }
    .op-hero-fuel:hover { border-color: rgba(255,255,255,0.12); }

    .op-fuel-top-row {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 10px;
    }
    .op-fuel-label-left {
      font-size: 12px; font-weight: 600;
      letter-spacing: 1px; text-transform: uppercase;
      color: var(--op-muted);
    }
    .op-fuel-pct {
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 32px; font-weight: 800; line-height: 1; letter-spacing: -1px;
    }
    .op-fuel-pct.low  { color: var(--op-red);    text-shadow: 0 0 20px rgba(227,0,27,0.4); }
    .op-fuel-pct.mid  { color: var(--op-yellow);  text-shadow: 0 0 20px rgba(245,158,11,0.3); }
    .op-fuel-pct.ok   { color: var(--op-green);   text-shadow: 0 0 20px rgba(34,197,94,0.25); }
    .op-fuel-pct-unit { font-size: 14px; font-weight: 500; color: var(--op-muted); margin-left: -4px; }

    /* segmented bar */
    .op-fuel-segments {
      display: flex; gap: 3px; margin-bottom: 6px;
    }
    .op-fuel-seg {
      flex: 1; height: 6px; border-radius: 3px;
      background: rgba(255,255,255,0.07);
      transition: background 0.4s, box-shadow 0.4s;
    }
    .op-fuel-seg.lit.low  { background: var(--op-red);    box-shadow: 0 0 6px rgba(227,0,27,0.5); }
    .op-fuel-seg.lit.mid  { background: var(--op-yellow);  box-shadow: 0 0 6px rgba(245,158,11,0.4); }
    .op-fuel-seg.lit.ok   { background: var(--op-green);   box-shadow: 0 0 6px rgba(34,197,94,0.3); }
    .op-fuel-footer {
      display: flex; justify-content: space-between; align-items: center;
      margin-top: 7px;
    }
    .op-fuel-ef {
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 12px; font-weight: 800; color: var(--op-muted);
      letter-spacing: 1px;
    }
    .op-fuel-info {
      font-size: 11px; color: var(--op-muted); font-weight: 500;
      text-align: center; flex: 1; padding: 0 8px;
    }

    /* alert banner */
    .op-alert {
      margin: 10px 16px 0;
      background: rgba(227,0,27,0.08);
      border: 1px solid rgba(227,0,27,0.3);
      border-radius: 10px;
      padding: 9px 13px;
      display: flex; align-items: center; gap: 8px;
      font-size: 12px; color: #ff7070; cursor: pointer;
      font-weight: 500;
    }

    /* ── Tabs ── */
    .op-tabs {
      display: flex; background: var(--op-surface);
      border-bottom: 1px solid var(--op-border);
      margin-top: 14px;
    }
    .op-tab {
      flex: 1; padding: 12px 4px; text-align: center;
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 12px; font-weight: 700;
      letter-spacing: 1px; text-transform: uppercase;
      color: var(--op-muted); cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: color 0.2s, border-color 0.2s;
      user-select: none;
    }
    .op-tab.active { color: var(--op-text); border-bottom-color: var(--op-red); }
    .op-tab:hover:not(.active) { color: var(--op-text); }

    /* ── Body ── */
    .op-body { padding: 14px 16px 18px; }

    .op-section-label {
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 11px; font-weight: 700;
      letter-spacing: 2px; text-transform: uppercase;
      color: var(--op-red); margin-bottom: 10px;
      padding-bottom: 6px; border-bottom: 1px solid var(--op-border);
    }

    /* 2-col grid */
    .op-grid {
      display: grid; grid-template-columns: 1fr 1fr;
      gap: 8px; margin-bottom: 12px;
    }
    .op-tile {
      background: var(--op-card); border-radius: 12px;
      padding: 12px 13px;
      border: 1px solid var(--op-border);
      cursor: pointer; transition: border-color 0.2s, background 0.2s;
    }
    .op-tile:hover { border-color: rgba(227,0,27,0.25); background: #222426; }
    .op-tile-header {
      display: flex; align-items: center; gap: 5px;
      margin-bottom: 8px;
    }
    .op-tile-icon  { font-size: 14px; flex-shrink: 0; }
    .op-tile-lbl   { font-size: 11px; color: var(--op-muted); font-weight: 600; letter-spacing: 0.3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .op-tile-val   {
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 26px; font-weight: 800; line-height: 1; letter-spacing: -0.5px;
    }
    .op-tile-unit  { font-size: 11px; color: var(--op-muted); margin-left: 2px; font-weight: 500; }

    /* row list */
    .op-row {
      display: flex; align-items: center; justify-content: space-between;
      padding: 8px 6px; border-bottom: 1px solid var(--op-border);
      cursor: pointer; border-radius: 6px; transition: background 0.1s;
    }
    .op-row:last-child { border-bottom: none; }
    .op-row:hover { background: rgba(255,255,255,0.025); }
    .op-row-left { display: flex; align-items: center; gap: 9px; min-width: 0; }
    .op-row-ico {
      width: 28px; height: 28px; background: var(--op-card);
      border-radius: 7px; display: flex; align-items: center;
      justify-content: center; font-size: 13px; flex-shrink: 0;
      border: 1px solid var(--op-border);
    }
    .op-row-lbl { font-size: 13px; color: var(--op-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 500; }
    .op-row-val { font-size: 14px; font-weight: 700; white-space: nowrap; flex-shrink: 0; }
    .op-row-val .u { font-size: 11px; font-weight: 500; color: var(--op-muted); margin-left: 2px; }
    /* full-width alert codes block */
    .op-alert-block {
      margin: 4px 0 2px; padding: 9px 12px;
      background: rgba(227,0,27,0.07); border: 1px solid rgba(227,0,27,0.22);
      border-radius: 10px;
    }
    .op-alert-block-header {
      display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;
    }
    .op-alert-block-label {
      font-size: 11px; font-weight: 700; letter-spacing: 0.5px;
      text-transform: uppercase; color: var(--op-red);
    }
    .op-alert-block-count {
      font-size: 11px; font-weight: 700;
      background: rgba(227,0,27,0.15); color: var(--op-red);
      border: 1px solid rgba(227,0,27,0.3); border-radius: 20px; padding: 1px 7px;
    }
    .op-alert-block-text { font-size: 12px; color: var(--op-text); line-height: 1.5; word-break: break-word; }

    /* alert list with per-item ack button */
    .op-alert-list { display: flex; flex-direction: column; gap: 6px; margin-top: 6px; }
    .op-alert-item {
      display: flex; align-items: center; gap: 8px;
      background: rgba(227,0,27,0.08);
      border: 1px solid rgba(227,0,27,0.22);
      border-radius: 8px; padding: 7px 9px;
      font-size: 12px;
    }
    .op-alert-item.acked {
      background: rgba(255,255,255,0.025);
      border-color: var(--op-border);
      color: var(--op-muted);
      text-decoration: line-through;
      text-decoration-color: rgba(255,255,255,0.35);
    }
    .op-alert-item-label { flex: 1; line-height: 1.3; word-break: break-word; }
    .op-alert-ack-btn {
      font-size: 10px; font-weight: 700; letter-spacing: 0.5px;
      text-transform: uppercase; padding: 3px 8px; border-radius: 6px;
      border: 1px solid rgba(227,0,27,0.4);
      background: rgba(227,0,27,0.15); color: var(--op-red);
      cursor: pointer; user-select: none; white-space: nowrap;
      transition: background 0.15s, border-color 0.15s;
    }
    .op-alert-ack-btn:hover { background: rgba(227,0,27,0.28); border-color: rgba(227,0,27,0.7); }
    .op-alert-ack-btn.restore {
      background: rgba(255,255,255,0.04); color: var(--op-muted);
      border-color: var(--op-border);
    }
    .op-alert-ack-btn.restore:hover { color: var(--op-text); border-color: rgba(255,255,255,0.25); }
    .op-alert-ack-all {
      margin-top: 8px; text-align: right;
    }
    .op-acked-toggle {
      margin-top: 8px; font-size: 11px; color: var(--op-muted);
      cursor: pointer; user-select: none; text-align: center;
      padding: 4px; border-top: 1px dashed var(--op-border);
    }
    .op-acked-toggle:hover { color: var(--op-text); }

    /* maintenance bars */
    .op-mbar {
      background: var(--op-card); border-radius: 12px;
      padding: 14px 15px; border: 1px solid var(--op-border);
      margin-bottom: 10px;
    }
    .op-mbar-head {
      display: flex; justify-content: space-between; align-items: baseline;
      margin-bottom: 10px;
    }
    .op-mbar-label { font-size: 12px; color: var(--op-muted); font-weight: 500; }
    .op-mbar-val   {
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 18px; font-weight: 800; letter-spacing: -0.3px;
    }
    .op-mbar-val.warn { color: var(--op-yellow); }
    .op-mbar-val.crit { color: var(--op-red); text-shadow: 0 0 12px rgba(227,0,27,0.4); }
    .op-bar-track  {
      height: 5px; background: rgba(255,255,255,0.06);
      border-radius: 3px; overflow: hidden;
    }
    .op-bar-fill   { height: 100%; border-radius: 3px; transition: width 0.5s ease; }
    .op-bar-fill.ok   { background: linear-gradient(90deg, #16a34a, #22c55e); box-shadow: 0 0 8px rgba(34,197,94,0.3); }
    .op-bar-fill.warn { background: var(--op-yellow); }
    .op-bar-fill.crit { background: var(--op-red); box-shadow: 0 0 8px rgba(227,0,27,0.4); }

    /* ── Mini map (Leaflet via iframe) ── */
    .op-map-wrap {
      margin: 12px 16px 0;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--op-border);
      background: #111;
    }
    .op-map-footer {
      padding: 8px 12px;
      border-top: 1px solid var(--op-border);
      display: flex; align-items: flex-start; justify-content: space-between; gap: 8px;
    }
    .op-map-address {
      font-size: 11px; color: var(--op-text); font-weight: 500;
      flex: 1; cursor: pointer; line-height: 1.4;
    }
    .op-map-date {
      font-size: 10px; color: var(--op-muted); white-space: nowrap; flex-shrink: 0;
      text-align: right; line-height: 1.4;
    }
    .op-map-unavail {
      height: 150px; display: flex; align-items: center; justify-content: center;
      font-size: 12px; color: var(--op-muted);
    }

    /* ── Refuel sub-section toggle ── */
    .op-refuel-toggle {
      display: flex; align-items: center; justify-content: space-between;
      padding: 9px 10px; margin-bottom: 10px;
      background: var(--op-card); border-radius: 10px;
      border: 1px solid var(--op-border); cursor: pointer;
      user-select: none; transition: border-color 0.2s;
    }
    .op-refuel-toggle:hover { border-color: rgba(227,0,27,0.3); }
    .op-refuel-toggle-label {
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 12px; font-weight: 700; letter-spacing: 1px;
      text-transform: uppercase; color: var(--op-muted);
    }
    .op-refuel-toggle-label.active { color: var(--op-text); }
    .op-refuel-since {
      font-size: 10px; color: var(--op-muted); margin-top: 1px;
    }
    .op-refuel-pill {
      font-size: 10px; font-weight: 700; letter-spacing: 0.5px;
      padding: 2px 8px; border-radius: 20px;
      background: rgba(227,0,27,0.15); color: var(--op-red);
      border: 1px solid rgba(227,0,27,0.3);
    }
  `;

  // ── Config ────────────────────────────────────────────────────────────────
  setConfig(config) {
    this._config = config;
    this._tab    = "trip";
    this._refuelView = false;
    this._showAcked  = {};
    this._periodView = "month";
    this._leafletMap = null;
    this._leafletMarker = null;
    this._view360Idx = 0;
    this._use360     = !!(config.car_view_360);
    this._v360Start  = null;
    this._v360Base   = 0;
    this._v360IdxF   = 0;
    this._v360Vel    = 0;
    this._v360RafId  = null;
    this._v360LastX  = 0;
    this._v360LastT  = 0;
    // px per frame — più alto = giri più lenti ma frame più spazi tra loro
    this._v360Sens   = 12;
  }
  set hass(h) {
    const prev = this._hass;
    this._hass = h;
    // If lat/lon changed, update marker without full re-render
    if (this._leafletMap && prev) {
      const plate = this._uniprefix();
      if (plate) {
        const tracker = this._hass.states[`device_tracker.auto_${plate}`];
        const lat = tracker?.attributes?.latitude;
        const lon = tracker?.attributes?.longitude;
        if (lat && lon) {
          this._leafletMarker?.setLatLng([lat, lon]);
          this._leafletMap.setView([lat, lon]);
        }
      }
    }
  }
  getCardSize() { return 7; }

  // ── UnipolSai entity helpers ──────────────────────────────────────────────
  _uniprefix() {
    const p = (this._config.plate || "").toString().trim().toUpperCase();
    return p ? p.toLowerCase() : null;
  }
  _uni(suffix, domain = "sensor") {
    const p = this._uniprefix();
    if (!p || !this._hass) return null;
    const id = `${domain}.${suffix}_${p}`;
    const s = this._hass.states[id];
    return (s && s.state !== "unavailable" && s.state !== "unknown") ? s : null;
  }
  _uniVal(suffix, domain = "sensor") {
    const e = this._uni(suffix, domain);
    return e ? e.state : null;
  }
  _uniOpen(suffix, domain = "sensor") {
    const p = this._uniprefix();
    if (!p || !this._hass) return;
    const id = `${domain}.${suffix}_${p}`;
    if (!this._hass.states[id]) return;
    const ev = new Event("hass-more-info", { bubbles: true, composed: true });
    ev.detail = { entityId: id };
    this.dispatchEvent(ev);
  }

  // ── Entity helpers ────────────────────────────────────────────────────────
  _prefix() {
    const v = (this._config.vin || "").toString().trim().slice(-6).toLowerCase();
    return v ? `opel_${v}` : "opel";
  }
  _eid(suffix, domain = "sensor") {
    return `${domain}.${this._prefix()}_${suffix}`;
  }
  _state(suffix, domain = "sensor") {
    if (!this._hass) return null;
    const s = this._hass.states[this._eid(suffix, domain)];
    if (!s || s.state === "unavailable" || s.state === "unknown") return null;
    return s.state;
  }
  _num(suffix, domain = "sensor") {
    const v = this._state(suffix, domain);
    return v !== null ? parseFloat(v) : null;
  }
  _fmt(suffix, domain = "sensor", dec = 1) {
    const v = this._num(suffix, domain);
    if (v === null) return "—";
    return Number.isInteger(v) || dec === 0
      ? Math.round(v).toString()
      : v.toFixed(dec);
  }
  _open(suffix, domain = "sensor") {
    const id = this._eid(suffix, domain);
    if (!this._hass?.states[id]) return;
    const e = new Event("hass-more-info", { bubbles: true, composed: true });
    e.detail = { entityId: id };
    this.dispatchEvent(e);
  }
  _fuelCls(pct) {
    if (pct === null) return "ok";
    if (pct < 20)     return "low";
    if (pct < 40)     return "mid";
    return "ok";
  }
  _fmtDate(suffix) {
    const v = this._state(suffix);
    if (!v) return "—";
    try {
      const tz = this._hass?.config?.time_zone;
      return new Date(v).toLocaleString("it-IT", {
        day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit",
        ...(tz ? { timeZone: tz } : {}),
      });
    } catch { return v; }
  }

  // ── VIN completo (dall'attributo sensore, non dal config troncato) ─────────
  _fullVin() {
    // sensor.py espone vin come extra_state_attributes su ogni sensore.
    // Usiamo il chilometraggio come âancora (è sempre present quando ci sono dati).
    const prefix = this._prefix();
    const s = this._hass?.states[`sensor.${prefix}_chilometraggio`];
    const attrVin = s?.attributes?.vin;
    if (attrVin && attrVin.length >= 10) return attrVin;
    // Fallback: usa il valore config (potrebbe essere il VIN intero se l'utente lo ha inserito)
    return (this._config.vin || "").toString().trim();
  }

  // ── 360° viewer ──────────────────────────────────────────────────────────
  // Frames 030–053: 24 angolazioni × 15° = rotazione completa
  _v360Url(idx) {
    const vin  = this._fullVin();
    const view = String(30 + (((idx % 24) + 24) % 24)).padStart(3, "0");
    return `https://visual3d-secure.opel-vauxhall.com/V3DImage.ashx?client=MyMarque&vin=${encodeURIComponent(vin)}&format=png&width=&view=${view}`;
  }

  _on360Down(e) {
    cancelAnimationFrame(this._v360RafId);
    this._v360Vel   = 0;
    this._v360Start = e.clientX;
    this._v360Base  = this._v360IdxF;
    this._v360LastX = e.clientX;
    this._v360LastT = performance.now();
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  _on360Move(e) {
    if (this._v360Start === null) return;
    const now = performance.now();
    const dt  = Math.max(now - this._v360LastT, 1);
    const dx  = e.clientX - this._v360LastX;
    const rawVel = (dx / dt) / this._v360Sens;
    this._v360Vel = this._v360Vel * 0.7 + rawVel * 0.3;
    this._v360LastX = e.clientX;
    this._v360LastT = now;
    this._v360IdxF = this._v360Base + (e.clientX - this._v360Start) / this._v360Sens;
    this._view360Idx = ((Math.round(this._v360IdxF) % 24) + 24) % 24;
  }

  _on360Up() {
    this._v360Start = null;
    this._v360Inertia();
  }

  _v360Inertia() {
    let lastT = performance.now();
    const step = (now) => {
      const dt = Math.max(now - lastT, 1);
      lastT = now;
      this._v360Vel *= Math.pow(0.92, dt / 16);
      if (Math.abs(this._v360Vel) < 0.0006) return;
      this._v360IdxF += this._v360Vel * dt;
      this._view360Idx = ((Math.round(this._v360IdxF) % 24) + 24) % 24;
      this._v360RafId = requestAnimationFrame(step);
    };
    this._v360RafId = requestAnimationFrame(step);
  }

  _v360Preload() {
    const vin = this._fullVin();
    if (!vin) return;
    for (let i = 0; i < 24; i++) {
      const img = new Image();
      img.src = this._v360Url(i);
    }
  }

  // ── Opel visual3D car image (from VIN) ───────────────────────────────────
  _carImageUrl() {
    const vin = this._fullVin();
    if (vin && vin.length >= 10) {
      const view = this._config.car_view || "001";
      return `https://visual3d-secure.opel-vauxhall.com/V3DImage.ashx?client=MyMarque&vin=${encodeURIComponent(vin)}&format=png&width=&view=${encodeURIComponent(view)}`;
    }
    return this._imaginstudioUrl();
  }

  _imaginstudioUrl() {
    const make  = encodeURIComponent(this._config.car_make  || "opel");
    const model = encodeURIComponent(this._config.car_model || "corsa");
    const year  = encodeURIComponent(this._config.car_year  || "2021");
    const color = encodeURIComponent(this._config.car_color || "");
    const base  = `https://cdn.imagin.studio/getImage?customer=img&make=${make}&modelFamily=${model}&modelYear=${year}&zoomType=fullscreen&angle=29`;
    return color ? `${base}&paintId=${color}` : base;
  }

  // Fallback chain: visual3D → imagin.studio → hidden
  _onCarImgError(e) {
    const fallback = this._imaginstudioUrl();
    if (e.target.src !== fallback) {
      e.target.src = fallback;
    } else {
      e.target.style.opacity = "0.15";
    }
  }

  // ── Alert block (full-width, wrappable) ──────────────────────────────────
  _alertBlock(countSuffix, codesSuffix) {
    const count = this._state(countSuffix);
    const codes = this._state(codesSuffix);
    if (!codes || codes === "Nessuno") {
      return html`<div class="op-row" style="padding:8px 6px;border-bottom:none;">
        <div class="op-row-left">
          <div class="op-row-ico">✅</div>
          <div class="op-row-lbl">Alert</div>
        </div>
        <div class="op-row-val">Nessuno</div>
      </div>`;
    }
    return html`
      <div class="op-alert-block" @click=${() => this._open(codesSuffix)} style="cursor:pointer;">
        <div class="op-alert-block-header">
          <span class="op-alert-block-label">⚠️ Alert attivi</span>
          ${count !== null ? html`<span class="op-alert-block-count">${count}</span>` : nothing}
        </div>
        <div class="op-alert-block-text">${codes}</div>
      </div>`;
  }

  // ── Alert acknowledgment helpers ─────────────────────────────────────────
  // Each scope maps to the sensor whose attributes carry the full ack data
  // (all_codes, unacknowledged_codes, acknowledged_codes, code_labels, entry_id).
  _scopeSensorSuffix(scope) {
    switch (scope) {
      case "today":     return "oggi_codici_alert";
      case "month":     return "mese_corrente_codici_alert";
      case "total":     return "totale_riepilogo_codici_alert";
      case "last_trip":
      default:          return "ultimo_viaggio_alert_non_letti_codici";
    }
  }

  _alertInfo(scope = "last_trip") {
    const prefix = this._prefix();
    const suffix = this._scopeSensorSuffix(scope);
    let src = this._hass?.states[`sensor.${prefix}_${suffix}`];
    if (!src && scope === "last_trip") {
      // Legacy fallback to the binary sensor
      src = this._hass?.states[`binary_sensor.${prefix}_ultimo_viaggio_alert_presenti`];
    }
    if (!src) return null;
    const a = src.attributes || {};
    return {
      scope,
      tripId:   a.trip_id ?? null,
      entryId:  a.entry_id ?? null,
      all:      Array.isArray(a.all_codes) ? a.all_codes : [],
      unack:    Array.isArray(a.unacknowledged_codes) ? a.unacknowledged_codes : [],
      acked:    Array.isArray(a.acknowledged_codes) ? a.acknowledged_codes : [],
      labels:   a.code_labels && typeof a.code_labels === "object" ? a.code_labels : {},
    };
  }

  _alertLabel(info, code) {
    return info.labels?.[String(code)] ?? `Codice ${code}`;
  }

  async _ackAlert(scope, code) {
    const info = this._alertInfo(scope);
    if (!info) return;
    await this._hass.callService("myopel", "acknowledge_alert", {
      alert_code: Number(code),
      scope,
      ...(scope === "last_trip" && info.tripId != null ? { trip_id: Number(info.tripId) } : {}),
      ...(info.entryId ? { entry_id: info.entryId } : {}),
    });
  }

  async _ackAllAlerts(scope) {
    const info = this._alertInfo(scope);
    if (!info || info.unack.length === 0) return;
    await this._hass.callService("myopel", "acknowledge_all_alerts", {
      scope,
      ...(scope === "last_trip" && info.tripId != null ? { trip_id: Number(info.tripId) } : {}),
      ...(info.entryId ? { entry_id: info.entryId } : {}),
    });
  }

  async _unackAlert(scope, code) {
    const info = this._alertInfo(scope);
    if (!info) return;
    await this._hass.callService("myopel", "unacknowledge_alert", {
      alert_code: Number(code),
      scope,
      ...(scope === "last_trip" && info.tripId != null ? { trip_id: Number(info.tripId) } : {}),
      ...(info.entryId ? { entry_id: info.entryId } : {}),
    });
  }

  async _resetAcks() {
    const info = this._alertInfo("last_trip");
    await this._hass.callService("myopel", "reset_alert_acknowledgments", {
      ...(info?.entryId ? { entry_id: info.entryId } : {}),
    });
  }

  _renderAlertList(scope = "last_trip") {
    const info = this._alertInfo(scope);
    if (!info || info.all.length === 0) {
      return html`<div class="op-row" style="padding:8px 6px;border-bottom:none;">
        <div class="op-row-left">
          <div class="op-row-ico">✅</div>
          <div class="op-row-lbl">Alert</div>
        </div>
        <div class="op-row-val">Nessuno</div>
      </div>`;
    }

    const showAcked = !!this._showAcked?.[scope];
    const unackItems = info.unack.map(code => html`
      <div class="op-alert-item">
        <span class="op-alert-item-label">⚠️ ${this._alertLabel(info, code)}</span>
        <span class="op-alert-ack-btn"
              title="Conferma — resta visibile ma non farà più scattare l'allarme"
              @click=${(e) => { e.stopPropagation(); this._ackAlert(scope, code); }}>
          ✓ Conferma
        </span>
      </div>
    `);

    const ackedItems = (showAcked ? info.acked : []).map(code => html`
      <div class="op-alert-item acked">
        <span class="op-alert-item-label">${this._alertLabel(info, code)}</span>
        <span class="op-alert-ack-btn restore"
              title="Ripristina — torna a segnalarlo come attivo"
              @click=${(e) => { e.stopPropagation(); this._unackAlert(scope, code); }}>
          ↺ Ripristina
        </span>
      </div>
    `);

    const headerCount = info.unack.length;
    const hasAcked = info.acked.length > 0;

    return html`
      <div class="op-alert-block">
        <div class="op-alert-block-header">
          <span class="op-alert-block-label">
            ${headerCount > 0 ? "⚠️ Alert attivi" : "✅ Tutti confermati"}
          </span>
          ${headerCount > 0
            ? html`<span class="op-alert-block-count">${headerCount}</span>`
            : nothing}
        </div>
        ${unackItems.length > 0 ? html`<div class="op-alert-list">${unackItems}</div>` : nothing}
        ${unackItems.length > 1 ? html`
          <div class="op-alert-ack-all">
            <span class="op-alert-ack-btn"
                  @click=${(e) => { e.stopPropagation(); this._ackAllAlerts(scope); }}>
              ✓✓ Conferma tutti
            </span>
          </div>` : nothing}
        ${hasAcked ? html`
          <div class="op-acked-toggle"
               @click=${(e) => {
                 e.stopPropagation();
                 this._showAcked = { ...this._showAcked, [scope]: !showAcked };
               }}>
            ${showAcked
              ? `▲ Nascondi ${info.acked.length} confermati`
              : `▼ Mostra ${info.acked.length} alert confermati`}
          </div>
          ${showAcked
            ? html`<div class="op-alert-list">${ackedItems}</div>`
            : nothing}
        ` : nothing}
      </div>
    `;
  }

  // ── Render: Hero ──────────────────────────────────────────────────────────
  _renderHero() {
    const fuelPct   = this._num("livello_carburante");
    const autonomy  = this._fmt("autonomia_carburante", "sensor", 0);
    const mileage   = this._fmt("chilometraggio");
    const hasAlert  = this._state("ultimo_viaggio_alert_presenti", "binary_sensor") === "on";
    const fc        = this._fuelCls(fuelPct);
    const tripEnd   = this._fmtDate("ultimo_viaggio_fine");
    const vinShort  = (this._config.vin || "").toString().trim().slice(-6).toUpperCase();
    const tankCap   = parseFloat(this._config.tank_capacity) || null;
    const remaining = (tankCap && fuelPct !== null)
      ? (tankCap * fuelPct / 100).toFixed(1)
      : null;

    const footerLine = autonomy !== "—"
      ? (remaining !== null
          ? `Autonomia: ${autonomy} km  ·  ~${remaining} L rimanenti`
          : `Autonomia: ${autonomy} km`)
      : (remaining !== null ? `~${remaining} L rimanenti` : null);

    return html`
      <div class="op-hero">
        <div class="op-hero-topbar">
          <div>
            <div class="op-hero-title">${this._config.name ?? "La mia Opel"}</div>
          </div>
          <div class="op-hero-topbar-right">
            ${vinShort ? html`
              <div class="op-360-toggle ${this._use360 ? 'active' : ''}"
                   title="${this._use360 ? 'Vista 360° — clicca per disattivare' : 'Clicca per attivare vista 360°'}"
                   @click=${() => {
                     this._use360 = !this._use360;
                     this._view360Idx = 0;
                     this._v360IdxF   = 0;
                     this._v360Vel    = 0;
                     cancelAnimationFrame(this._v360RafId);
                     if (this._use360) this._v360Preload();
                   }}>
                360°
              </div>
              <div class="op-vin-badge">VIN …${vinShort}</div>
            ` : nothing}
          </div>
        </div>

        ${(this._use360 && (this._config.vin || "").toString().trim())
          ? html`
            <div class="op-car-wrap is-360 has-v3d"
                 @pointerdown=${this._on360Down.bind(this)}
                 @pointermove=${this._on360Move.bind(this)}
                 @pointerup=${this._on360Up.bind(this)}
                 @pointercancel=${this._on360Up.bind(this)}>
              <img class="op-car-img" src="${this._v360Url(this._view360Idx)}"
                   draggable="false" alt="360° Opel"
                   @error=${this._onCarImgError.bind(this)} />
              <div class="op-car-mileage"><strong>${mileage}</strong> km</div>
              <div class="op-car-updated">
                ${tripEnd !== "—" ? html`Agg. ${tripEnd}` : nothing}
              </div>
              <div class="op-360-hint">⟵ trascina per ruotare ⟶</div>
            </div>`
          : html`
            <div class="op-car-wrap has-v3d">
              <img class="op-car-img" src="${this._carImageUrl()}"
                   alt="Opel ${this._config.car_model ?? 'Corsa'}"
                   @error=${this._onCarImgError.bind(this)} />
              <div class="op-car-mileage"><strong>${mileage}</strong> km</div>
              <div class="op-car-updated">
                ${tripEnd !== "—" ? html`Agg. ${tripEnd}` : nothing}
              </div>
            </div>`
        }

        <div class="op-hero-fuel" @click=${() => this._open("livello_carburante")}>
          <div class="op-fuel-top-row">
            <div class="op-fuel-label-left">⛽ Carburante</div>
            <span class="op-fuel-pct ${fc}">
              ${fuelPct !== null ? fuelPct : "—"}<span class="op-fuel-pct-unit">%</span>
            </span>
          </div>
          <div class="op-fuel-segments">
            ${Array.from({length: 20}, (_, i) => {
              const threshold = (i + 1) * 5;
              const lit = fuelPct !== null && fuelPct >= threshold;
              return html`<div class="op-fuel-seg ${lit ? `lit ${fc}` : ""}"></div>`;
            })}
          </div>
          <div class="op-fuel-footer">
            <span class="op-fuel-ef">E</span>
            ${footerLine ? html`<span class="op-fuel-info">${footerLine}</span>` : nothing}
            <span class="op-fuel-ef">F</span>
          </div>
        </div>

        ${(() => {
          const info = this._alertInfo("last_trip");
          if (!info || info.unack.length === 0) return nothing;
          const first = this._alertLabel(info, info.unack[0]);
          const extra = info.unack.length > 1 ? ` +${info.unack.length - 1}` : "";
          return html`
            <div class="op-alert" @click=${() => { this._tab = "trip"; }}>
              ⚠️ Alert attivo — <strong>${first}${extra}</strong>
            </div>`;
        })()}
      </div>
    `;
  }

  // ── Leaflet map via iframe (bypass shadow DOM limitations) ───────────────
  _getMapHtml(lat, lon) {
    return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html, body, #map { width:100%; height:100%; background:#111; }
  .leaflet-container { background:#111 !important; }
  /* hide Leaflet default attribution */
  .leaflet-control-attribution { display:none !important; }
</style>
<link rel="stylesheet"
  href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
</head>
<body>
<div id="map"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"><\/script>
<script>
  var map = L.map('map', {
    zoomControl: false, attributionControl: false,
    dragging: false, scrollWheelZoom: false,
    doubleClickZoom: false, touchZoom: false, keyboard: false
  });

  L.tileLayer(
    'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    { maxZoom: 19, subdomains: 'abcd' }
  ).addTo(map);

  var pinSvg = '<svg width="34" height="44" viewBox="0 0 34 44" xmlns="http://www.w3.org/2000/svg">'
    + '<defs><filter id="g"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="rgba(0,0,0,.6)"/>'
    + '<feDropShadow dx="0" dy="0" stdDeviation="5" flood-color="rgba(227,0,27,.45)"/></filter></defs>'
    + '<path d="M17 2C9.82 2 4 7.82 4 15c0 9.5 13 27 13 27S30 24.5 30 15C30 7.82 24.18 2 17 2z"'
    + ' fill="#e3001b" filter="url(#g)"/>'
    + '<circle cx="17" cy="15" r="6" fill="white"/>'
    + '<circle cx="17" cy="15" r="3" fill="#e3001b"/></svg>';

  var icon = L.divIcon({
    className: '', html: pinSvg,
    iconSize: [34, 44], iconAnchor: [17, 44]
  });

  var lat = ${lat}, lon = ${lon};
  var marker = L.marker([lat, lon], { icon: icon }).addTo(map);
  map.setView([lat, lon], 15);

  // Listen for position updates from parent card
  window.addEventListener('message', function(e) {
    if (e.data && e.data.type === 'myopel-update') {
      var newLat = e.data.lat, newLon = e.data.lon;
      marker.setLatLng([newLat, newLon]);
      map.setView([newLat, newLon], 15);
    }
  });
<\/script>
</body>
</html>`;
  }

  updated(changed) {
    super.updated && super.updated(changed);
    if (!this._config?.plate) return;

    const plate = this._uniprefix();
    if (!plate) return;
    const tracker = this._hass?.states[`device_tracker.auto_${plate}`];
    const lat = tracker?.attributes?.latitude;
    const lon = tracker?.attributes?.longitude;
    if (!lat || !lon) return;

    const iframe = this.shadowRoot?.querySelector('.op-map-iframe');
    if (!iframe) return;

    if (!iframe.dataset.initialized) {
      // First load: inject full HTML via srcdoc
      iframe.srcdoc = this._getMapHtml(lat, lon);
      iframe.dataset.initialized = '1';
      this._lastLat = lat;
      this._lastLon = lon;
    } else if (lat !== this._lastLat || lon !== this._lastLon) {
      // Position changed: update via postMessage
      iframe.contentWindow?.postMessage({ type: 'myopel-update', lat, lon }, '*');
      this._lastLat = lat;
      this._lastLon = lon;
    }
  }

  // ── Render: Mini Map ──────────────────────────────────────────────────────
  _renderMap() {
    if (!this._config?.plate) return nothing;

    const plate = this._uniprefix();
    if (!plate) return nothing;

    const tracker = this._hass?.states[`device_tracker.auto_${plate}`];
    const lat = tracker?.attributes?.latitude;
    const lon = tracker?.attributes?.longitude;
    const address = this._uniVal("indirizzo");
    const lastUpdate = this._uniVal("ultimo_aggiornamento_gps");

    let fmtDate = null;
    if (lastUpdate) {
      try {
        fmtDate = new Date(lastUpdate).toLocaleString("it-IT",
          { day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit" });
      } catch { fmtDate = lastUpdate; }
    }

    const mapContent = (lat && lon)
      ? html`<iframe class="op-map-iframe"
                 frameborder="0" scrolling="no"
                 style="width:100%;height:150px;display:block;border:none;">
             </iframe>`
      : html`<div class="op-map-unavail">📍 Posizione GPS non disponibile</div>`;

    return html`
      <div class="op-map-wrap">
        ${mapContent}
        <div class="op-map-footer">
          <div class="op-map-address" @click=${() => this._uniOpen("indirizzo")}>
            ${address ?? "Indirizzo non disponibile"}
          </div>
          ${fmtDate ? html`<div class="op-map-date">🕐 ${fmtDate}</div>` : nothing}
        </div>
      </div>
    `;
  }

  // ── Render: Tabs ──────────────────────────────────────────────────────────
  _renderTabs() {
    return html`
      <div class="op-tabs">
        ${[["trip","Viaggio"],["month","Mese"],["total","Totali"],["maint","Manutenzione"]]
          .map(([k,l]) => html`
            <div class="op-tab ${this._tab===k?"active":""}" @click=${()=>{this._tab=k;}}>${l}</div>
          `)}
      </div>`;
  }

  // ── Render helpers ────────────────────────────────────────────────────────
  _tile(icon, label, suffix, unit, dec=1, domain="sensor") {
    return html`
      <div class="op-tile" @click=${()=>this._open(suffix,domain)}>
        <div class="op-tile-header">
          <span class="op-tile-icon">${icon}</span>
          <span class="op-tile-lbl">${label}</span>
        </div>
        <div><span class="op-tile-val">${this._fmt(suffix,domain,dec)}</span><span class="op-tile-unit">${unit}</span></div>
      </div>`;
  }
  _row(icon, label, value, unit, suffix, domain="sensor") {
    return html`
      <div class="op-row" @click=${()=>this._open(suffix,domain)}>
        <div class="op-row-left">
          <div class="op-row-ico">${icon}</div>
          <div class="op-row-lbl">${label}</div>
        </div>
        <div class="op-row-val">${value}<span class="u">${unit}</span></div>
      </div>`;
  }

  // ── Tab: Viaggio ──────────────────────────────────────────────────────────
  _renderTrip() {
    return html`<div class="op-body">
      <div class="op-section-label">Ultimo viaggio</div>
      <div class="op-grid">
        ${this._tile("📍","Distanza","ultimo_viaggio_distanza","km",1)}
        ${this._tile("⏱","Durata","ultimo_viaggio_durata","min",0)}
        ${this._tile("🏎","Vel. media","ultimo_viaggio_velocita_media","km/h",1)}
        ${this._tile("📈","Consumo","ultimo_viaggio_consumo_medio","km/L",1)}
      </div>
      ${this._row("🔥","Carburante usato",  this._fmt("ultimo_viaggio_carburante_consumato")," L","ultimo_viaggio_carburante_consumato")}
      ${this._row("💶","Costo stimato",      this._fmt("ultimo_viaggio_costo_stimato")," €","ultimo_viaggio_costo_stimato")}
      ${this._row("⛽","Prezzo al litro",     this._fmt("prezzo_carburante")," €/L","prezzo_carburante")}
      ${this._row("🕐","Partenza",            this._fmtDate("ultimo_viaggio_inizio"),"","ultimo_viaggio_inizio")}
      ${this._row("🏁","Arrivo",              this._fmtDate("ultimo_viaggio_fine"),"","ultimo_viaggio_fine")}
      ${this._renderAlertList("last_trip")}
    </div>`;
  }

  // ── Tab: Oggi | Mese ─────────────────────────────────────────────────────
  _renderPeriodSwitch() {
    const isToday = this._periodView === "today";
    return html`
      <div class="op-refuel-toggle" @click=${() => { this._periodView = isToday ? "month" : "today"; }}>
        <div class="op-refuel-toggle-label ${isToday ? 'active' : ''}">
          ${isToday ? "📅 Oggi" : "🗓 Mese corrente"}
        </div>
        <span class="op-refuel-pill">${isToday ? "🗓 Mese" : "📅 Oggi"}</span>
      </div>
    `;
  }

  _renderToday() {
    return html`<div class="op-body">
      ${this._renderPeriodSwitch()}
      <div class="op-grid">
        ${this._tile("🗓","Viaggi","oggi_viaggi","",0)}
        ${this._tile("📍","Distanza","oggi_distanza","km",1)}
        ${this._tile("⏱","Min. guida","oggi_durata_guida","min",0)}
        ${this._tile("🏎","Vel. media","oggi_velocita_media","km/h",1)}
      </div>
      ${this._row("⛽","Carburante totale",this._fmt("oggi_carburante_totale")," L","oggi_carburante_totale")}
      ${this._row("📈","Consumo medio",    this._fmt("oggi_consumo_medio")," km/L","oggi_consumo_medio")}
      ${this._row("💶","Costo stimato",    this._fmt("oggi_costo_stimato")," €","oggi_costo_stimato")}
      ${this._renderAlertList("today")}
    </div>`;
  }

  _renderMonth() {
    if (this._periodView === "today") return this._renderToday();
    return html`<div class="op-body">
      ${this._renderPeriodSwitch()}
      <div class="op-grid">
        ${this._tile("🗓","Viaggi","mese_corrente_viaggi","",0)}
        ${this._tile("📍","Distanza","mese_corrente_distanza","km",1)}
        ${this._tile("⏱","Min. guida","mese_corrente_durata_guida","min",0)}
        ${this._tile("🏎","Vel. media","mese_corrente_velocita_media","km/h",1)}
      </div>
      ${this._row("⛽","Carburante totale",this._fmt("mese_corrente_carburante_totale")," L","mese_corrente_carburante_totale")}
      ${this._row("📈","Consumo medio",    this._fmt("mese_corrente_consumo_medio")," km/L","mese_corrente_consumo_medio")}
      ${this._row("💶","Costo stimato",    this._fmt("mese_corrente_costo_stimato")," €","mese_corrente_costo_stimato")}
      ${this._renderAlertList("month")}
    </div>`;
  }

  // ── Tab: Totali ───────────────────────────────────────────────────────────
  _renderTotal() {
    const rv = this._refuelView;
    const refuelDate = this._state("rifornimento_data_ultimo_rifornimento");
    let refuelDateFmt = null;
    if (refuelDate) {
      try {
        refuelDateFmt = new Date(refuelDate).toLocaleString("it-IT",
          { day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit" });
      } catch { refuelDateFmt = refuelDate; }
    }

    if (rv) {
      return html`<div class="op-body">
        <div class="op-refuel-toggle" @click=${() => { this._refuelView = false; }}>
          <div>
            <div class="op-refuel-toggle-label active">⛽ Dall'ultimo rifornimento</div>
            ${refuelDateFmt ? html`<div class="op-refuel-since">dal ${refuelDateFmt}</div>` : nothing}
          </div>
          <span class="op-refuel-pill">↩ Totali</span>
        </div>
        <div class="op-grid">
          ${this._tile("🗓","Viaggi","rifornimento_viaggi","",0)}
          ${this._tile("📍","Distanza","rifornimento_distanza","km",1)}
          ${this._tile("⏱","Ore guida","rifornimento_ore_di_guida","h",1)}
          ${this._tile("🏎","Vel. media","rifornimento_velocita_media","km/h",1)}
        </div>
        ${this._row("⛽","Carburante usato",   this._fmt("rifornimento_carburante_consumato")," L","rifornimento_carburante_consumato")}
        ${this._row("📈","Consumo medio",       this._fmt("rifornimento_consumo_medio")," km/L","rifornimento_consumo_medio")}
        ${this._row("💶","Costo stimato",       this._fmt("rifornimento_costo_stimato")," €","rifornimento_costo_stimato")}
      </div>`;
    }

    return html`<div class="op-body">
      <div class="op-refuel-toggle" @click=${() => { this._refuelView = true; }}>
        <div class="op-refuel-toggle-label">📊 Totali (da file)</div>
        <span class="op-refuel-pill">⛽ Dal rifornimento</span>
      </div>
      <div class="op-grid">
        ${this._tile("🗓","Viaggi","totale_viaggi","",0)}
        ${this._tile("📍","Distanza","totale_distanza","km",1)}
        ${this._tile("⏱","Ore guida","totale_ore_di_guida","h",1)}
        ${this._tile("🏎","Vel. media","totale_velocita_media","km/h",1)}
      </div>
      ${this._row("⛽","Carburante totale",this._fmt("totale_carburante_consumato")," L","totale_carburante_consumato")}
      ${this._row("📈","Consumo medio",    this._fmt("totale_consumo_medio")," km/L","totale_consumo_medio")}
      ${this._row("💶","Costo totale",     this._fmt("totale_costo_stimato")," €","totale_costo_stimato")}
      ${this._renderAlertList("total")}
    </div>`;
  }

  // ── Tab: Manutenzione ─────────────────────────────────────────────────────
  _renderMaint() {
    const days = this._num("giorni_alla_manutenzione");
    const km   = this._num("km_alla_manutenzione");
    const SERVICE_KM   = 30000;
    const SERVICE_DAYS = 365;
    const kmPct    = km   !== null ? Math.max(0, Math.min(100, km/SERVICE_KM*100))   : null;
    const daysPct  = days !== null ? Math.max(0, Math.min(100, days/SERVICE_DAYS*100)): null;
    const kmCls    = km   !== null ? (km   < 1000 ? "crit" : km   < 5000  ? "warn" : "ok") : "ok";
    const daysCls  = days !== null ? (days < 30   ? "crit" : days < 90    ? "warn" : "ok") : "ok";

    return html`<div class="op-body">
      <div class="op-section-label">Prossimo tagliando</div>

      <div class="op-mbar">
        <div class="op-mbar-head">
          <span class="op-mbar-label">🔧 Km al tagliando</span>
          <span class="op-mbar-val ${kmCls}">${km !== null ? km.toLocaleString("it-IT") : "—"} km</span>
        </div>
        <div class="op-bar-track">
          <div class="op-bar-fill ${kmCls}" style="width:${kmPct??0}%"></div>
        </div>
      </div>

      <div class="op-mbar">
        <div class="op-mbar-head">
          <span class="op-mbar-label">📅 Giorni al tagliando</span>
          <span class="op-mbar-val ${daysCls}">${days !== null ? days : "—"} giorni</span>
        </div>
        <div class="op-bar-track">
          <div class="op-bar-fill ${daysCls}" style="width:${daysPct??0}%"></div>
        </div>
      </div>
    </div>`;
  }

  // ── Render principale ─────────────────────────────────────────────────────
  render() {
    if (!this._config || !this._hass) return nothing;
    const tabs = { trip:this._renderTrip(), month:this._renderMonth(), total:this._renderTotal(), maint:this._renderMaint() };
    return html`
      <ha-card>
        ${this._renderHero()}
        ${this._renderMap()}
        ${this._renderTabs()}
        ${tabs[this._tab] ?? nothing}
      </ha-card>`;
  }

  static getConfigElement() { return document.createElement("myopel-card-editor"); }
  static getStubConfig() {
    return { name:"La mia Opel", vin:"", car_make:"opel", car_model:"corsa", car_year:"2021", car_color:"", tank_capacity:41, plate:"" };
  }
}
customElements.define("myopel-card", MyOpelCard);
window.customCards = window.customCards ?? [];
window.customCards.push({ type:"myopel-card", name:"MyOpel Card", preview:false, description:"Dashboard MyOpel" });
