# MarketPulse India — API Reference

Base URL: `http://localhost:8000`  
All protected endpoints require `Authorization: Bearer <token>`.  
All timestamps are IST. All monetary values are ₹ Crore unless noted.

---

## Authentication

### `POST /api/auth/login`

Exchange credentials for a JWT access token (24-hour expiry).

```bash
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "demo123"}'
```

**Response `200 OK`**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZW1vIiwiZXhwIjoxNzE2ODk2MDAwfQ.abc123",
  "token_type": "bearer"
}
```

Use the token in all subsequent requests:
```bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

## Analysis

### `POST /api/analyze`

Trigger the 9-node LangGraph CRAG pipeline for a symbol. Returns immediately
with a `session_id`; connect to the WebSocket endpoint to stream live
node-by-node progress.

```bash
curl -s -X POST http://localhost:8000/api/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "nse_symbol": "INFY",
    "announcement_type": "quarterly_results",
    "announcement_raw": "Infosys Q2 FY25: Revenue ₹40,986 Cr (+3.7% QoQ, +2.9% YoY). PAT ₹6,506 Cr (+4.7% YoY). EBIT margin 21.1%. FY25 revenue guidance raised to 4.5-5.0% in CC. Management tone: cautiously optimistic on BFSI recovery."
  }'
```

**Response `200 OK`** *(abbreviated — full signal arrives via WebSocket)*
```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "thread_id": "api-infy-f3a2b1c0",
  "status": "running",
  "nse_symbol": "INFY",
  "ws_url": "ws://localhost:8000/ws/analyze/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "Analysis started for INFY"
}
```

**Signal payload delivered via WebSocket `signal_ready` event:**
```json
{
  "event": "signal_ready",
  "nse_symbol": "INFY",
  "direction": "BUY",
  "confidence": 0.74,
  "current_price_inr": 1847.50,
  "target_price_inr": 2050.00,
  "upside_pct": 10.9,
  "time_horizon_days": 90,
  "rationale": "Guidance upgrade signals FY25 recovery confidence. BFSI vertical showing early green shoots. Margin at 21.1% leaves room for operating leverage. FII net buyers ₹1,240 Cr in trailing 5 sessions. Promoter pledging 0% — no collateral risk.",
  "sebi_disclaimer": "⚠️ MarketPulse India is not a SEBI-registered investment advisor. Output is for educational/informational purposes only and is not investment advice. Markets carry risk; consult a registered advisor before making decisions."
}
```

---

## Signals

### `GET /api/signals`

Paginated signal history across all symbols, newest first.

```bash
curl -s "http://localhost:8000/api/signals?limit=5" \
  -H "Authorization: Bearer $TOKEN"
```

**Response `200 OK`**
```json
{
  "signals": [
    {
      "signal_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "nse_symbol": "TCS",
      "direction": "BUY",
      "confidence": 0.81,
      "target_inr": 4200.00,
      "upside_pct": 8.2,
      "horizon_days": 90,
      "created_ist": "2025-10-15T14:22:05+05:30",
      "sebi_disclaimer": "⚠️ MarketPulse India is not a SEBI-registered investment advisor. Output is for educational/informational purposes only and is not investment advice. Markets carry risk; consult a registered advisor before making decisions."
    },
    {
      "signal_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
      "nse_symbol": "HDFCBANK",
      "direction": "HOLD",
      "confidence": 0.61,
      "target_inr": 1680.00,
      "upside_pct": 2.1,
      "horizon_days": 60,
      "created_ist": "2025-10-15T11:08:33+05:30",
      "sebi_disclaimer": "⚠️ MarketPulse India is not a SEBI-registered investment advisor. Output is for educational/informational purposes only and is not investment advice. Markets carry risk; consult a registered advisor before making decisions."
    }
  ],
  "total": 2,
  "sebi_disclaimer": "⚠️ MarketPulse India is not a SEBI-registered investment advisor. Output is for educational/informational purposes only and is not investment advice. Markets carry risk; consult a registered advisor before making decisions."
}
```

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 20 | Results per page (max 100) |
| `offset` | int | 0 | Pagination offset |
| `direction` | string | — | Filter: `BUY`, `HOLD`, or `SELL` |

---

## Sector Analysis

### `POST /api/sector/analyze`

Trigger parallel sector analysis using the LangGraph Send API. Runs up to 5
peer pipelines concurrently and returns a composite sector ranking.

```bash
curl -s -X POST http://localhost:8000/api/sector/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sector": "IT"}'
```

**Response `200 OK`**
```json
{
  "sector": "IT",
  "sector_signal": "neutral",
  "sector_winner": "TCS",
  "analysis_summary": "IT sector shows mixed signals in Q2 FY25. TCS leads on deal wins and margin resilience; INFY guidance upgrade offsets muted near-term revenue. BFSI slowdown weighs on Wipro and HCL. USD/INR at 84.1 adds ~120bps margin tailwind for all exporters.",
  "peer_rankings": [
    {
      "nse_symbol": "TCS",
      "rank": 1,
      "composite_score": 0.79,
      "direction": "BUY",
      "confidence": 0.81,
      "upside_pct": 8.2
    },
    {
      "nse_symbol": "INFY",
      "rank": 2,
      "composite_score": 0.71,
      "direction": "BUY",
      "confidence": 0.74,
      "upside_pct": 10.9
    },
    {
      "nse_symbol": "HCLTECH",
      "rank": 3,
      "composite_score": 0.63,
      "direction": "HOLD",
      "confidence": 0.65,
      "upside_pct": 4.1
    },
    {
      "nse_symbol": "WIPRO",
      "rank": 4,
      "composite_score": 0.51,
      "direction": "HOLD",
      "confidence": 0.58,
      "upside_pct": 1.8
    },
    {
      "nse_symbol": "TECHM",
      "rank": 5,
      "composite_score": 0.42,
      "direction": "HOLD",
      "confidence": 0.49,
      "upside_pct": -0.5
    }
  ],
  "sebi_disclaimer": "⚠️ MarketPulse India is not a SEBI-registered investment advisor. Output is for educational/informational purposes only and is not investment advice. Markets carry risk; consult a registered advisor before making decisions."
}
```

---

### `GET /api/sector/rankings/{sector}`

Return the latest cached peer rankings for a sector without triggering a
fresh pipeline run.

```bash
curl -s http://localhost:8000/api/sector/rankings/Banking \
  -H "Authorization: Bearer $TOKEN"
```

**Response `200 OK`**
```json
{
  "sector": "Banking",
  "as_of_ist": "2025-10-15T16:00:00+05:30",
  "rankings": [
    {
      "nse_symbol": "HDFCBANK",
      "rank": 1,
      "direction": "HOLD",
      "confidence": 0.61,
      "upside_pct": 2.1,
      "key_catalyst": "NIM compression stabilising; credit cost at 5-year low"
    },
    {
      "nse_symbol": "ICICIBANK",
      "rank": 2,
      "direction": "BUY",
      "confidence": 0.77,
      "upside_pct": 11.4,
      "key_catalyst": "Retail loan growth +18% YoY; GNPA at 2.2% — sector best"
    },
    {
      "nse_symbol": "AXISBANK",
      "rank": 3,
      "direction": "HOLD",
      "confidence": 0.58,
      "upside_pct": 3.6,
      "key_catalyst": "Integration synergies from Citi acquisition starting to show"
    },
    {
      "nse_symbol": "KOTAKBANK",
      "rank": 4,
      "direction": "HOLD",
      "confidence": 0.55,
      "upside_pct": 1.2,
      "key_catalyst": "RBI restriction on new credit card customers partially lifted"
    },
    {
      "nse_symbol": "SBIN",
      "rank": 5,
      "direction": "BUY",
      "confidence": 0.68,
      "upside_pct": 9.8,
      "key_catalyst": "PSB recapitalisation + rural lending momentum"
    }
  ],
  "sebi_disclaimer": "⚠️ MarketPulse India is not a SEBI-registered investment advisor. Output is for educational/informational purposes only and is not investment advice. Markets carry risk; consult a registered advisor before making decisions."
}
```

---

## WebSocket — Live Pipeline Streaming

### `WS /ws/analyze/{session_id}`

Connect after calling `POST /api/analyze` to receive live node-by-node updates.
The server pushes JSON messages as the LangGraph pipeline progresses.

**JavaScript connection example:**
```javascript
const SESSION_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";
const TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...";

const ws = new WebSocket(
  `ws://localhost:8000/ws/analyze/${SESSION_ID}?token=${TOKEN}`
);

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  switch (msg.event) {
    case "connected":
      console.log("Pipeline session open:", msg.session_id);
      break;

    case "pipeline_start":
      console.log("Pipeline started for:", msg.nse_symbol);
      break;

    case "node_start":
      console.log(`Node starting: ${msg.node}  (elapsed: ${msg.elapsed_ms}ms)`);
      break;

    case "node_complete":
      console.log(`Node done: ${msg.node}  (${msg.duration_ms}ms)`);
      // msg.preview contains a short human-readable summary of node output
      break;

    case "signal_ready":
      console.log(`Signal: ${msg.direction} ${msg.nse_symbol}`);
      console.log(`Target: ₹${msg.target_price_inr}  Upside: ${msg.upside_pct}%`);
      console.log(msg.sebi_disclaimer);
      break;

    case "pipeline_end":
      console.log(`Complete in ${msg.total_ms}ms. Status: ${msg.status}`);
      ws.close();
      break;
  }
};
```

**Event reference:**

| Event | When | Key fields |
|---|---|---|
| `connected` | Immediately on connect | `session_id`, `nse_symbol` |
| `pipeline_start` | Pipeline begins | `nse_symbol`, `thread_id` |
| `node_start` | Each node begins | `node`, `elapsed_ms` |
| `node_complete` | Each node finishes | `node`, `duration_ms`, `preview` |
| `signal_ready` | `score_signal` completes | `direction`, `confidence`, `target_price_inr`, `upside_pct`, `sebi_disclaimer` |
| `pipeline_end` | All nodes done | `status`, `total_ms` |

---

## Health

### `GET /health`

Liveness + market status check. No authentication required. Used by the ALB
target group health check and the GitHub Actions smoke test.

```bash
curl -s http://localhost:8000/health
```

**Response `200 OK`** *(market open)*
```json
{
  "status": "healthy",
  "market_open": true,
  "ist_time": "14:32:15 IST",
  "db": "ok",
  "redis": "ok",
  "version": "0.1.0"
}
```

**Response `200 OK`** *(market closed)*
```json
{
  "status": "healthy",
  "market_open": false,
  "ist_time": "17:05:42 IST",
  "db": "ok",
  "redis": "ok",
  "version": "0.1.0"
}
```

---

## Error Responses

All errors follow RFC 7807 (Problem Details):

```json
{
  "detail": "Symbol XYZABC not found in the database."
}
```

| Status | Meaning |
|---|---|
| `400` | Malformed request body |
| `401` | Missing or expired JWT |
| `404` | Symbol / resource not found |
| `422` | Validation error (field-level detail in response) |
| `429` | Rate limit exceeded (100 analyses/day per user) |
| `500` | Pipeline error — check `/health` and logs |
