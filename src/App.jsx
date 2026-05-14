import { useState, useEffect, useRef, useCallback } from "react";
import "./App.css";

// ─── Mock data generators ────────────────────────────────────────────────────
// Replace these with real HYCOM/ERA5 API calls in production

function generateMockGrid(day) {
  const grid = [];
  for (let lat = 15; lat <= 45; lat += 1) {
    for (let lon = -170; lon <= -120; lon += 1) {
      const nx = (lon + 170) / 50;
      const ny = (lat - 15) / 30;
      const u = Math.sin(ny * 3.2 + day * 0.1) * Math.cos(nx * 2.1) * 0.6;
      const v = Math.cos(nx * 2.8 + day * 0.08) * Math.sin(ny * 1.9) * 0.5;
      const div = (Math.sin(nx * 5.1 + day * 0.05) * Math.cos(ny * 4.3)) * 0.5;
      grid.push({ lat, lon, u, v, div });
    }
  }
  return grid;
}

const ZONES = [
  {
    id: 0, name: "North Pacific Gyre", shortName: "N. Pacific",
    lat: 30, lon: -148, region: "Pacific Ocean",
    coords: "30.0°N 148.0°W",
    baseProb: 0.92, divergence: -0.42, speed: 0.28, wind: 12.4, density: 3.2,
    trend: "rising",
  },
  {
    id: 1, name: "South Pacific Subtropical", shortName: "S. Pacific",
    lat: -32, lon: -125, region: "Pacific Ocean",
    coords: "32.0°S 125.0°W",
    baseProb: 0.76, divergence: -0.31, speed: 0.22, wind: 9.8, density: 2.1,
    trend: "stable",
  },
  {
    id: 2, name: "Indian Ocean Patch", shortName: "Indian Ocean",
    lat: -15, lon: 74, region: "Indian Ocean",
    coords: "15.7°S 74.3°E",
    baseProb: 0.61, divergence: -0.24, speed: 0.19, wind: 8.1, density: 1.7,
    trend: "falling",
  },
  {
    id: 3, name: "North Atlantic Gyre", shortName: "N. Atlantic",
    lat: 33, lon: -40, region: "Atlantic Ocean",
    coords: "33.2°N 40.1°W",
    baseProb: 0.48, divergence: -0.17, speed: 0.15, wind: 6.5, density: 1.1,
    trend: "rising",
  },
];

function dayProb(baseProb, day, zoneId) {
  const wave = Math.sin((day + zoneId * 3) * 0.45) * 0.06;
  return Math.min(0.99, Math.max(0.1, baseProb + wave));
}

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function formatDate(day) {
  const d = new Date(2026, 3, 1);
  d.setDate(d.getDate() + day);
  return `${MONTHS[d.getMonth()]} ${String(d.getDate()).padStart(2, "0")}`;
}

// ─── Canvas Map Component ─────────────────────────────────────────────────────
function OceanMap({ selectedZone, forecastDay, layers, hotspots, onZoneClick, onZoneHover }) {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const tickRef = useRef(0);
  const particlesRef = useRef([]);
  const gridRef = useRef(null);

  // Map projection helpers (simple equirectangular)
  const project = useCallback((lon, lat, W, H) => {
    const x = ((lon + 180) / 360) * W;
    const y = ((90 - lat) / 180) * H;
    return [x, y];
  }, []);

  // Map zones to canvas coordinates
  const zoneCanvasPos = useCallback((zone, W, H) => {
    return project(zone.lon, zone.lat, W, H);
  }, [project]);

  useEffect(() => {
  fetch(`/api/v1/currents/${forecastDay}`)
    .then(r => r.json())
    .then(data => { gridRef.current = data.grid; })
    .catch(() => {
      // fallback to synthetic if API is down
      gridRef.current = generateMockGrid(forecastDay);
    });
  }, [forecastDay]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const initParticles = (W, H) => {
      particlesRef.current = Array.from({ length: 160 }, () => {
        const z = ZONES[Math.floor(Math.random() * 4)];
        const [cx, cy] = project(z.lon, z.lat, W, H);
        return {
          x: cx + (Math.random() - 0.5) * W * 0.09,
          y: cy + (Math.random() - 0.5) * H * 0.08,
          vx: (Math.random() - 0.5) * 0.5,
          vy: (Math.random() - 0.5) * 0.4,
          life: Math.random(),
          size: 1.2 + Math.random() * 2,
          zoneId: Math.floor(Math.random() * 4),
        };
      });
    };

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const W = canvas.parentElement.clientWidth;
      const H = canvas.parentElement.clientHeight;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      canvas.style.width = W + "px";
      canvas.style.height = H + "px";
      const ctx = canvas.getContext("2d");
      ctx.scale(dpr, dpr);
      initParticles(W, H);
    };
    resize();

    const getCtxSize = () => ({
      W: parseInt(canvas.style.width),
      H: parseInt(canvas.style.height),
    });

    const currentVec = (nx, ny) => {
      const t = tickRef.current;
      const u = Math.sin(ny * 3.2 + 0.8 + t * 0.002) * Math.cos(nx * 2.1 + t * 0.0015) * 0.6;
      const v = Math.cos(nx * 2.8 + 1.2 + t * 0.0018) * Math.sin(ny * 1.9 + t * 0.002) * 0.5;
      return [u, v];
    };

    const probColor = (p, alpha = 1) => {
      if (p > 0.82) return `rgba(255,69,0,${alpha})`;
      if (p > 0.66) return `rgba(255,130,0,${alpha})`;
      if (p > 0.50) return `rgba(255,210,0,${alpha})`;
      return `rgba(0,220,190,${alpha})`;
    };

    const draw = () => {
      const ctx = canvas.getContext("2d");
      const { W, H } = getCtxSize();
      tickRef.current++;
      const tick = tickRef.current;

      // ── Ocean base ──────────────────────────────────────────────────────
      ctx.clearRect(0, 0, W, H);
      const bg = ctx.createLinearGradient(0, 0, W, H);
      bg.addColorStop(0, "#031524");
      bg.addColorStop(0.5, "#04192e");
      bg.addColorStop(1, "#051f38");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, W, H);

      // ── Subtle depth lines ──────────────────────────────────────────────
      ctx.strokeStyle = "rgba(26,143,207,0.04)";
      ctx.lineWidth = 0.5;
      for (let i = 0; i < 10; i++) {
        ctx.beginPath();
        const y = H * (0.1 + i * 0.09);
        for (let x = 0; x <= W; x += 6) {
          const ny = y + Math.sin(x * 0.008 + i * 1.2 + tick * 0.004) * 6;
          x === 0 ? ctx.moveTo(x, ny) : ctx.lineTo(x, ny);
        }
        ctx.stroke();
      }

      // ── Lat/lon grid ────────────────────────────────────────────────────
      ctx.strokeStyle = "rgba(26,143,207,0.06)";
      ctx.lineWidth = 0.5;
      ctx.setLineDash([2, 8]);
      for (let lng = -180; lng <= 180; lng += 30) {
        const [x] = project(lng, 0, W, H);
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
      }
      for (let lt = -90; lt <= 90; lt += 30) {
        const [, y] = project(0, lt, W, H);
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
      }
      ctx.setLineDash([]);

      // ── Divergence field ────────────────────────────────────────────────
      if (layers.divergence) {
        const STEP = 20;
        for (let gx = 0; gx < W; gx += STEP) {
          for (let gy = 0; gy < H; gy += STEP) {
            const nx = gx / W, ny = gy / H;
            const div = Math.sin(nx * 5.1 + tick * 0.003) * Math.cos(ny * 4.3) * 0.5;
            if (div < -0.18) {
              ctx.fillStyle = `rgba(255,215,0,${Math.abs(div) * 0.28})`;
              ctx.fillRect(gx, gy, STEP, STEP);
            }
          }
        }
      }

      // ── Current arrows ──────────────────────────────────────────────────
      if (layers.currents) {
        const STEP = 38;
        for (let gx = STEP / 2; gx < W; gx += STEP) {
          for (let gy = STEP / 2; gy < H; gy += STEP) {
            const [u, v] = currentVec(gx / W, gy / H);
            const len = 14;
            const ex = gx + u * len, ey = gy + v * len;
            const speed = Math.sqrt(u * u + v * v);
            const alpha = 0.15 + speed * 0.3;
            ctx.strokeStyle = `rgba(74,182,232,${alpha})`;
            ctx.lineWidth = 0.6;
            ctx.beginPath(); ctx.moveTo(gx, gy); ctx.lineTo(ex, ey); ctx.stroke();
            const angle = Math.atan2(ey - gy, ex - gx);
            ctx.save();
            ctx.translate(ex, ey);
            ctx.rotate(angle);
            ctx.fillStyle = `rgba(74,182,232,${alpha * 1.2})`;
            ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(-5, -2.5); ctx.lineTo(-5, 2.5); ctx.closePath();
            ctx.fill();
            ctx.restore();
          }
        }
      }

      // ── Hotspot blobs ───────────────────────────────────────────────────
      if (layers.hotspots) {
        if (hotspots && hotspots.length > 0) {
      hotspots.forEach(({ lat, lon, risk }) => {
        const [hx, hy] = project(lon, lat, W, H);
        const radius = 3 + risk * 5;

        const color =
          risk > 0.75 ? "255,69,0" :
          risk > 0.55 ? "255,165,0" :
          "0,220,190";

        ctx.beginPath();
        ctx.arc(hx, hy, radius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${color}, ${0.4 + risk * 0.5})`;
        ctx.fill();

        ctx.strokeStyle = `rgba(${color}, 0.9)`;
        ctx.lineWidth = 1;
        ctx.stroke();
      });
    }  
        ZONES.forEach((zone, i) => {
          const p = dayProb(zone.baseProb, forecastDay, i);
          const [cx, cy] = zoneCanvasPos(zone, W, H);
          const baseRad = Math.min(W, H) * 0.07 * (0.7 + p * 0.5);
          const pulse = 1 + Math.sin(tick * 0.05 + i) * 0.04;
          const rad = baseRad * pulse;

          // Outer glow
          const grd = ctx.createRadialGradient(cx, cy, 0, cx, cy, rad * 1.5);
          grd.addColorStop(0, probColor(p, p * 0.7));
          grd.addColorStop(0.4, probColor(p, p * 0.3));
          grd.addColorStop(0.7, probColor(p, 0.08));
          grd.addColorStop(1, "rgba(0,0,0,0)");
          ctx.fillStyle = grd;
          ctx.beginPath(); ctx.arc(cx, cy, rad * 1.5, 0, Math.PI * 2); ctx.fill();

          // Core
          const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, rad * 0.45);
          core.addColorStop(0, probColor(p, 0.95));
          core.addColorStop(1, probColor(p, 0.4));
          ctx.fillStyle = core;
          ctx.beginPath(); ctx.arc(cx, cy, rad * 0.45, 0, Math.PI * 2); ctx.fill();

          // Selection ring
          if (i === selectedZone) {
            ctx.strokeStyle = "rgba(255,255,255,0.55)";
            ctx.lineWidth = 1.5;
            ctx.setLineDash([5, 4]);
            ctx.beginPath(); ctx.arc(cx, cy, rad, 0, Math.PI * 2); ctx.stroke();
            ctx.setLineDash([]);

            // Label
            ctx.fillStyle = "rgba(255,255,255,0.85)";
            ctx.font = "bold 11px 'Space Mono', monospace";
            ctx.textAlign = "center";
            ctx.fillText(zone.shortName, cx, cy - rad - 10);
          }
        });
      }

      // ── Particles ───────────────────────────────────────────────────────
      if (layers.particles) {
        particlesRef.current.forEach((p) => {
          p.life += 0.004;
          if (p.life > 1) {
            const z = ZONES[p.zoneId];
            const [cx, cy] = zoneCanvasPos(z, W, H);
            p.x = cx + (Math.random() - 0.5) * W * 0.12;
            p.y = cy + (Math.random() - 0.5) * H * 0.1;
            p.life = 0;
          }
          const [cu, cv] = currentVec(p.x / W, p.y / H);
          p.x += cu * 0.45 + p.vx * 0.06;
          p.y += cv * 0.35 + p.vy * 0.06;
          const alpha = Math.sin(p.life * Math.PI) * 0.65;
          ctx.fillStyle = `rgba(0,229,196,${alpha})`;
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
          ctx.fill();
        });
      }

      // ── Scan line effect ────────────────────────────────────────────────
      const scanY = (tick * 1.5) % H;
      const scanGrd = ctx.createLinearGradient(0, scanY - 60, 0, scanY + 4);
      scanGrd.addColorStop(0, "rgba(74,182,232,0)");
      scanGrd.addColorStop(1, "rgba(74,182,232,0.04)");
      ctx.fillStyle = scanGrd;
      ctx.fillRect(0, scanY - 60, W, 64);

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);

    const handleResize = () => resize();
    window.addEventListener("resize", handleResize);

    return () => {
      cancelAnimationFrame(animRef.current);
      window.removeEventListener("resize", handleResize);
    };
  }, [selectedZone, forecastDay, layers, project, zoneCanvasPos]);

  // Mouse interaction
  const handleMouseMove = useCallback((e) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const W = parseInt(canvas.style.width);
    const H = parseInt(canvas.style.height);

    let found = null;
    ZONES.forEach((z, i) => {
      const [cx, cy] = project(z.lon, z.lat, W, H);
      const p = dayProb(z.baseProb, forecastDay, i);
      const rad = Math.min(W, H) * 0.07 * (0.7 + p * 0.5) * 1.5;
      const dx = mx - cx, dy = my - cy;
      if (Math.sqrt(dx * dx + dy * dy) < rad) found = i;
    });
    onZoneHover(found);
  }, [forecastDay, project, onZoneHover]);

  const handleClick = useCallback((e) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const W = parseInt(canvas.style.width);
    const H = parseInt(canvas.style.height);

    ZONES.forEach((z, i) => {
      const [cx, cy] = project(z.lon, z.lat, W, H);
      const rad = Math.min(W, H) * 0.07 * 1.5;
      const dx = mx - cx, dy = my - cy;
      if (Math.sqrt(dx * dx + dy * dy) < rad) onZoneClick(i);
    });
  }, [project, onZoneClick]);

  return (
    <canvas
      ref={canvasRef}
      style={{ display: "block", width: "100%", height: "100%", cursor: "crosshair" }}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => onZoneHover(null)}
      onClick={handleClick}
    />
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [forecastDay, setForecastDay] = useState(0);
  const [selectedZone, setSelectedZone] = useState(0);
  const [hotspots, setHotspots] = useState([]);
  const [hoveredZone, setHoveredZone] = useState(null);
  const [layers, setLayers] = useState({
    hotspots: true,
    currents: true,
    particles: true,
    divergence: false,
  });
  const [apiOpen, setApiOpen] = useState(false);
  const [modelPanelOpen, setModelPanelOpen] = useState(false);
  useEffect(() => {
  fetch(`/api/v1/predict?forecast_days=${forecastDay + 1}&resolution=0.5`)
    .then(res => res.json())
    .then(data => {
      setHotspots(data.hotspots);  // data.hotspots = [{lat, lon, risk, wind_speed, ...}]
    })
    .catch(err => console.error("Predict API error:", err));
}, [forecastDay]);  // re-fetches whenever the slider moves
  const toggleLayer = (key) =>
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));

  const zone = ZONES[selectedZone];
  const hzone = hoveredZone !== null ? ZONES[hoveredZone] : null;

  // 14-day bar chart data for selected zone
  const barData = Array.from({ length: 14 }, (_, d) => ({
    day: d,
    prob: dayProb(zone.baseProb, d, selectedZone),
  }));

  const probColor = (p) => {
    if (p > 0.82) return "#ff4500";
    if (p > 0.66) return "#ff8c00";
    if (p > 0.50) return "#ffd700";
    return "#00e5c4";
  };

  const trendIcon = (t) =>
    t === "rising" ? "↑" : t === "falling" ? "↓" : "→";
  const trendColor = (t) =>
    t === "rising" ? "#ff6b35" : t === "falling" ? "#00e5c4" : "#8ab4c8";

  return (
    <div className="app">
      {/* ── Header ─────────────────────────────────────────────────── */}
      <header className="header">
        <div className="logo">
          <svg width="32" height="32" viewBox="0 0 32 32">
            <circle cx="16" cy="16" r="15" fill="rgba(6,42,71,0.9)" stroke="#1a8fcf" strokeWidth="0.5" />
            <path d="M4 18Q10 11 16 14Q22 17 28 12" stroke="#4ab6e8" strokeWidth="1.4" fill="none" strokeLinecap="round" />
            <path d="M4 22Q11 16 17 19Q23 22 28 17" stroke="#1a8fcf" strokeWidth="0.9" fill="none" strokeLinecap="round" opacity="0.6" />
            <circle cx="16" cy="14" r="4.5" fill="rgba(255,69,0,0.25)" stroke="#ff4500" strokeWidth="0.6" />
            <circle cx="16" cy="14" r="2" fill="#ff4500" opacity="0.9" />
          </svg>
          <div className="logo-text-wrap">
            <span className="logo-name">OceanScan<span className="logo-ai"> AI</span></span>
            <span className="logo-sub">Debris Hotspot Forecasting · v2.4</span>
          </div>
        </div>

        <div className="header-stats">
          {[
            { val: "87", lbl: "Zones Tracked" },
            { val: "14", lbl: "Day Horizon" },
            { val: "94.2%", lbl: "Model Accuracy" },
            { val: "0.89", lbl: "AUPRC Score" },
          ].map(({ val, lbl }) => (
            <div key={lbl} className="h-stat">
              <span className="h-stat-val">{val}</span>
              <span className="h-stat-lbl">{lbl}</span>
            </div>
          ))}
        </div>

        <div className="header-right">
          <div className="live-pill">
            <span className="live-dot" />
            <span>HYCOM Live</span>
          </div>
          <button className="header-btn" onClick={() => setModelPanelOpen(!modelPanelOpen)}>
            Model Info
          </button>
        </div>
      </header>

      {/* ── Body ───────────────────────────────────────────────────── */}
      <div className="body">
        {/* ── Left Sidebar ─────────────────────────────────────────── */}
        <aside className="sidebar left-sidebar">

          {/* Timeline */}
          <section className="sidebar-section">
            <div className="section-hd">
              <span className="section-label">Forecast Timeline</span>
              <span className="section-badge">{formatDate(forecastDay)}</span>
            </div>
            <div className="timeline-card">
              <div className="timeline-top">
                <div>
                  <div className="timeline-date">{formatDate(forecastDay)}</div>
                  <div className="timeline-sub">{forecastDay === 0 ? "Today — Nowcast" : `Day +${forecastDay} Forecast`}</div>
                </div>
                <div className="timeline-daybadge">D+{forecastDay}</div>
              </div>

              <div className="slider-wrap">
                <input
                  type="range" className="day-slider"
                  min={0} max={13} value={forecastDay}
                  onChange={(e) => setForecastDay(+e.target.value)}
                  style={{ "--pct": `${(forecastDay / 13) * 100}%` }}
                />
              </div>

              <div className="day-dots">
                {Array.from({ length: 14 }, (_, i) => (
                  <button
                    key={i}
                    className={`day-dot ${i === forecastDay ? "active" : i < forecastDay ? "past" : ""}`}
                    onClick={() => setForecastDay(i)}
                    title={formatDate(i)}
                  />
                ))}
              </div>
              <div className="day-dot-labels">
                <span>Apr 01</span><span>Apr 07</span><span>Apr 14</span>
              </div>
            </div>
          </section>

          {/* Layers */}
          <section className="sidebar-section">
            <div className="section-hd">
              <span className="section-label">Map Layers</span>
            </div>
            {[
              { key: "hotspots", color: "#ff4500", label: "Hotspot Probabilities", sub: "XGBoost predictions" },
              { key: "currents", color: "#1a8fcf", label: "Ocean Currents", sub: "HYCOM u/v vectors" },
              { key: "particles", color: "#00e5c4", label: "Particle Drift Sim", sub: "Lagrangian advection" },
              { key: "divergence", color: "#ffd700", label: "Divergence Field ∇·u", sub: "Convergence zones" },
            ].map(({ key, color, label, sub }) => (
              <div
                key={key}
                className={`layer-row ${layers[key] ? "layer-on" : ""}`}
                onClick={() => toggleLayer(key)}
              >
                <div className="layer-dot-sq" style={{ background: color }} />
                <div className="layer-text">
                  <span className="layer-name">{label}</span>
                  <span className="layer-sub">{sub}</span>
                </div>
                <div className={`toggle ${layers[key] ? "tog-on" : ""}`}>
                  <div className="toggle-thumb" />
                </div>
              </div>
            ))}
          </section>

          {/* Zones */}
          <section className="sidebar-section">
            <div className="section-hd">
              <span className="section-label">Convergence Zones</span>
              <span className="section-badge">{ZONES.length} active</span>
            </div>
            {ZONES.map((z, i) => {
              const p = dayProb(z.baseProb, forecastDay, i);
              const pPct = Math.round(p * 100);
              return (
                <div
                  key={z.id}
                  className={`zone-card ${selectedZone === i ? "zone-selected" : ""}`}
                  onClick={() => setSelectedZone(i)}
                >
                  <div className="zone-top">
                    <div className="zone-rank">#{i + 1}</div>
                    <div className="zone-info">
                      <span className="zone-name">{z.name}</span>
                      <span className="zone-coords">{z.coords}</span>
                    </div>
                    <div className="zone-prob-wrap">
                      <span className="zone-pct" style={{ color: probColor(p) }}>{pPct}%</span>
                      <span className="zone-trend" style={{ color: trendColor(z.trend) }}>
                        {trendIcon(z.trend)}
                      </span>
                    </div>
                  </div>
                  <div className="zone-bar-track">
                    <div
                      className="zone-bar-fill"
                      style={{
                        width: `${pPct}%`,
                        background: `linear-gradient(to right, ${probColor(p)}88, ${probColor(p)})`,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </section>
        </aside>

        {/* ── Map ──────────────────────────────────────────────────── */}
        <main className="map-container">
          <OceanMap
            selectedZone={selectedZone}
            forecastDay={forecastDay}
            layers={layers}
            hotspots={hotspots}
            onZoneClick={setSelectedZone}
            onZoneHover={setHoveredZone}
          />

          {/* Map overlay: hover tooltip */}
          {hzone && (
            <div className="map-hover-info">
              <div className="mhi-name">{hzone.name}</div>
              <div className="mhi-prob" style={{ color: probColor(dayProb(hzone.baseProb, forecastDay, hzone.id)) }}>
                {Math.round(dayProb(hzone.baseProb, forecastDay, hzone.id) * 100)}% probability
              </div>
              <div className="mhi-row">
                <span>∇·u</span>
                <span>{hzone.divergence.toFixed(2)} s⁻¹</span>
              </div>
              <div className="mhi-row">
                <span>Speed</span>
                <span>{hzone.speed.toFixed(2)} m/s</span>
              </div>
            </div>
          )}

          {/* Map legend */}
          <div className="map-legend">
            <span className="legend-lbl">Low</span>
            <div className="legend-grad" />
            <span className="legend-lbl">High</span>
            <span className="legend-title">Accumulation Probability</span>
          </div>

          {/* Corner coords label */}
          <div className="map-coords-label">
            Pacific Basin · Equirectangular · HYCOM 1/12°
          </div>
        </main>

        {/* ── Right Sidebar ─────────────────────────────────────────── */}
        <aside className="sidebar right-sidebar">

          {/* Zone detail */}
          <section className="sidebar-section">
            <div className="section-hd">
              <span className="section-label">Zone Analysis</span>
            </div>
            <div className="zone-detail-header">
              <div
                className="zone-detail-indicator"
                style={{ background: probColor(dayProb(zone.baseProb, forecastDay, selectedZone)) }}
              />
              <div>
                <div className="zd-name">{zone.name}</div>
                <div className="zd-region">{zone.region} · {zone.coords}</div>
              </div>
            </div>

            <div className="metrics-grid">
              {[
                { val: dayProb(zone.baseProb, forecastDay, selectedZone).toFixed(2), lbl: "Probability", unit: "", highlight: true },
                { val: zone.divergence.toFixed(2), lbl: "Divergence ∇·u", unit: "s⁻¹" },
                { val: zone.speed.toFixed(2), lbl: "Current Speed", unit: "m/s" },
                { val: zone.wind.toFixed(1), lbl: "Wind Stress", unit: "kn" },
                { val: zone.density.toFixed(1), lbl: "Est. Density", unit: "kg/km²" },
                { val: "94%", lbl: "Confidence", unit: "" },
              ].map(({ val, lbl, unit, highlight }) => (
                <div key={lbl} className={`metric-cell ${highlight ? "metric-highlight" : ""}`}>
                  <div className="metric-val">
                    {val}<span className="metric-unit">{unit}</span>
                  </div>
                  <div className="metric-lbl">{lbl}</div>
                </div>
              ))}
            </div>
          </section>

          {/* 14-day forecast bars */}
          <section className="sidebar-section">
            <div className="section-hd">
              <span className="section-label">14-Day Forecast</span>
              <span className="section-badge">{zone.shortName}</span>
            </div>
            <div className="forecast-bars">
              {barData.map(({ day, prob }) => (
                <div
                  key={day}
                  className={`fbar-col ${day === forecastDay ? "fbar-active" : ""}`}
                  onClick={() => setForecastDay(day)}
                  title={`Day +${day}: ${Math.round(prob * 100)}%`}
                >
                  <div
                    className="fbar-fill"
                    style={{
                      height: `${prob * 100}%`,
                      background: probColor(prob),
                      opacity: day === forecastDay ? 1 : 0.45,
                    }}
                  />
                  {day % 4 === 0 && (
                    <span className="fbar-label">D{day}</span>
                  )}
                </div>
              ))}
            </div>
            <div className="forecast-range">
              <span>Min: {Math.round(Math.min(...barData.map(b => b.prob)) * 100)}%</span>
              <span>Peak: {Math.round(Math.max(...barData.map(b => b.prob)) * 100)}%</span>
            </div>
          </section>

          {/* Confidence ring */}
          <section className="sidebar-section">
            <div className="section-hd">
              <span className="section-label">Model Confidence</span>
            </div>
            <div className="conf-wrap">
              <svg width="88" height="88" viewBox="0 0 88 88">
                <circle cx="44" cy="44" r="36" fill="none" stroke="rgba(26,143,207,0.12)" strokeWidth="8" />
                <circle
                  cx="44" cy="44" r="36"
                  fill="none"
                  stroke="url(#cg)"
                  strokeWidth="8"
                  strokeDasharray="226.2"
                  strokeDashoffset="13.6"
                  strokeLinecap="round"
                  transform="rotate(-90 44 44)"
                />
                <defs>
                  <linearGradient id="cg" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="#1a8fcf" />
                    <stop offset="100%" stopColor="#4ab6e8" />
                  </linearGradient>
                </defs>
                <text x="44" y="40" textAnchor="middle" fill="#4ab6e8" fontSize="16" fontWeight="700" fontFamily="'Space Mono',monospace">94%</text>
                <text x="44" y="54" textAnchor="middle" fill="#4a7a96" fontSize="9" fontFamily="'Space Mono',monospace">CONF.</text>
              </svg>
              <div className="conf-details">
                <div className="conf-row"><span>Model</span><span>XGBoost 1.7</span></div>
                <div className="conf-row"><span>CV Strategy</span><span>5-fold spatial</span></div>
                <div className="conf-row"><span>AUPRC</span><span>0.891</span></div>
                <div className="conf-row"><span>F1 Score</span><span>0.847</span></div>
              </div>
            </div>
          </section>

          {/* Data feeds */}
          <section className="sidebar-section">
            <div className="section-hd">
              <span className="section-label">Data Feeds</span>
            </div>
            {[
              { name: "HYCOM OPeNDAP", status: "live", latency: "3hr" },
              { name: "ERA5 Wind (CDS)", status: "live", latency: "6hr" },
              { name: "NOAA Marine Debris", status: "cached", latency: "24hr" },
              { name: "IUCN Red List", status: "cached", latency: "static" },
            ].map(({ name, status, latency }) => (
              <div key={name} className="feed-row">
                <div className={`feed-dot ${status}`} />
                <span className="feed-name">{name}</span>
                <span className="feed-latency">{latency}</span>
              </div>
            ))}
            <div className="feed-footer">Last inference: 2m ago · Next: 58m</div>
          </section>

          {/* API Endpoint */}
          <section className="sidebar-section">
            <div className="section-hd">
              <span className="section-label">API Endpoint</span>
            </div>
            <button className="api-btn" onClick={() => setApiOpen(!apiOpen)}>
              <span className="api-method">POST</span>
              <span className="api-path">/api/v1/predict</span>
              <span className="api-arrow">{apiOpen ? "↑" : "↗"}</span>
            </button>
            {apiOpen && (
              <div className="api-code">
                <pre>{`{
  "bbox": [-170, 15, -120, 45],
  "date": "${new Date(2026, 3, 1 + forecastDay).toISOString().split("T")[0]}",
  "resolution": 0.25,
  "features": ["divergence","wind_stress","sst"]
}`}</pre>
                <div className="api-response-label">→ Returns GeoJSON hotspot grid</div>
              </div>
            )}
          </section>
        </aside>
      </div>

      {/* ── Model info overlay ──────────────────────────────────────── */}
      {modelPanelOpen && (
        <div className="model-overlay" onClick={() => setModelPanelOpen(false)}>
          <div className="model-panel" onClick={(e) => e.stopPropagation()}>
            <div className="mp-header">
              <span className="mp-title">Model Architecture</span>
              <button className="mp-close" onClick={() => setModelPanelOpen(false)}>✕</button>
            </div>
            <div className="mp-body">
              {[
                { label: "Algorithm", value: "XGBoost 1.7 · scikit-learn pipeline" },
                { label: "Key Feature", value: "Oceanic divergence ∇·u (surface convergence zones)" },
                { label: "Training Data", value: "NOAA Marine Debris Program · 1980–2024" },
                { label: "Input Features", value: "Divergence, wind stress, SST gradient, rolling 7-day mean currents, bathymetry depth" },
                { label: "Output", value: "P(accumulation > threshold) per 0.25° grid cell" },
                { label: "Validation", value: "Held-out ocean regions · Temporal cross-validation" },
                { label: "Impact Estimate", value: "2–3× plastic recovered per fuel hour vs reactive routing" },
              ].map(({ label, value }) => (
                <div key={label} className="mp-row">
                  <span className="mp-lbl">{label}</span>
                  <span className="mp-val">{value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
