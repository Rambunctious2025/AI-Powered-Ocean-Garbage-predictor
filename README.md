# OceanScan AI — UI

Production-grade React dashboard for the AI Ocean Garbage Hotspot Predictor.

## Quick Start

```bash
npm install
npm run dev
# → http://localhost:5173
```

## File Structure

```
oceanscan-ui/
├── index.html
├── vite.config.js
├── package.json
└── src/
    ├── main.jsx          # React entry point
    ├── App.jsx           # Main app + OceanMap canvas component
    └── App.css           # All styles (CSS variables + component styles)
```

## Connecting Real HYCOM Data

The `OceanMap` component currently uses a synthetic current field.
To swap in real HYCOM data:

1. Run the Python data pipeline (see `/backend/hycom_pipeline.py`)
2. Place exported `day_00.json` … `day_13.json` in `public/currents/`
3. In `App.jsx`, replace the `currentVec()` function with:

```js
// Load grid when day changes
useEffect(() => {
  fetch(`/currents/day_${String(forecastDay).padStart(2,'0')}.json`)
    .then(r => r.json())
    .then(data => { gridRef.current = buildUVIndex(data.grid); });
}, [forecastDay]);

// Replace synthetic currentVec with real lookup
const currentVec = (nx, ny) => {
  const lon = nx * 360 - 180;
  const lat = 90 - ny * 180;
  return lookupUV(gridRef.current, lon, lat);
};
```

## Adding Mapbox GL + deck.gl TripsLayer

```bash
npm install mapbox-gl @deck.gl/react @deck.gl/layers @deck.gl/geo-layers react-map-gl
```

Then replace `<OceanMap>` in App.jsx with the DeckGL + Map component
from the full Mapbox integration guide.

Set your token in `.env`:
```
VITE_MAPBOX_TOKEN=pk.your_token_here
```

## Environment Variables

| Variable | Description |
|---|---|
| `VITE_MAPBOX_TOKEN` | Mapbox GL access token (required for satellite tiles) |
| `VITE_API_BASE` | FastAPI backend URL (default: http://localhost:8000) |

## Features

- **Animated ocean canvas** — real-time particle drift, current arrows, divergence heatmap
- **14-day forecast timeline** — slider + dot navigation, all data updates live
- **4 convergence zones** — click to select, metrics update in right panel
- **Layer toggles** — hotspots / currents / particles / divergence field independently
- **Hover tooltip** — probability, ∇·u, and current speed on mouse hover
- **Model info overlay** — architecture, validation metrics, impact estimates
- **API endpoint preview** — expandable request payload with current forecast date
- **Responsive** — collapses to single column on mobile
