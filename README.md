# Seismic — Athena Earthquake Activity Explorer

A focused Athena AI agent with a real MCP server and an embedded, interactive earthquake explorer. Live data comes from the public USGS M2.5+ GeoJSON feeds. No API key or runtime package installation is required.

## Live submission

- Athena agent: https://athenachat.bot/chatbot/agent/seismic-earthquake-explorer5473
- Hosted MCP endpoint: https://seismic-earthquake-explorer-lalith.lalithgautam.chatgpt.site/api/mcp
- Standalone preview: https://seismic-earthquake-explorer-lalith.lalithgautam.chatgpt.site/

The production endpoint runs as a self-contained Cloudflare Worker through Sites. It is public, read-only and requires no API key. `/api/mcp` avoids the hosting platform's reserved `/mcp` authentication route.

## Run

Requires Python 3.10+.

```sh
python server.py
```

- MCP Streamable HTTP: `http://localhost:8787/mcp`
- Standalone preview: `http://localhost:8787/`
- Health check: `http://localhost:8787/health`
- Configure the listening port with `PORT` (default 8787).

For an Athena development connection, expose the server with Cloudflare Tunnel or ngrok:

```sh
cloudflared tunnel --url http://localhost:8787
```

Use the returned HTTPS origin followed by `/mcp` in Athena. Quick tunnels require the local server and tunnel processes to remain running and may change URL after a restart. For durable hosting, deploy the included Dockerfile to a Python/container host.

## Athena setup

Create an agent at https://athenachat.bot/chatbot/mybots/create.

**Name:** Seismic — Earthquake Explorer

**Description:** Explore recent M2.5+ earthquakes with live USGS data, an interactive global map, magnitude and depth filters, place search, and event details.

**Agent prompt:**

```text
You are Seismic, a concise earthquake activity guide. For any request to explore recent earthquake activity, always call explore_earthquakes to retrieve real USGS data and render the embedded explorer. Default to the last 7 days, minimum magnitude 2.5, maximum depth 1000 km, and no place filter. Use only supported time ranges: 1, 7, or 30 days. If the user requests earthquakes below M2.5, explain that this focused explorer covers M2.5+ events. Place is a case-insensitive substring of the USGS place description; do not claim it is a geographical boundary search. After calling the tool, give at most one short sentence and let the widget carry the experience. Never fabricate events or predictions. For tool errors, explain that live retrieval failed and suggest retrying. USGS events are preliminary and may be revised.
```

**Starter:** Show recent earthquakes worldwide in the interactive explorer.

## MCP contract

The dependency-free HTTP server implements stateless MCP JSON-RPC over HTTP, including `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`, `resources/list`, `resources/read`, and `resources/templates/list`. It has been checked using the official Python MCP client.

Tool: `explore_earthquakes`

| Argument | Values | Default |
|---|---|---|
| days | 1, 7, 30 | 7 |
| min_magnitude | 2.5–10 | 2.5 |
| max_depth | -10–1000 km | 1000 |
| place | USGS place-description substring | empty |

`structuredContent.events` includes the entire M2.5+ catalog for the requested time range, allowing filters to be widened without a network call. `count` is the number matching the requested filters; `catalogCount` is the entire returned catalog. Sources and retrieval timestamps are returned with the data. Results are cached for at most 60 seconds to avoid unnecessary USGS traffic. Failures return `isError: true`; no mock or fallback earthquake data is used.

The HTML resource `ui://seismic/explorer.html` uses MIME type `text/html+skybridge`. The tool points to this resource using `openai/outputTemplate`, and `openai/widgetAccessible` allows time-range changes to call MCP again through `window.openai.callTool`. The widget consumes `window.openai.toolOutput`, listens for `openai:set_globals`, and persists UI preferences with `window.openai.setWidgetState`.

## Meaningful interactions

1. Change minimum magnitude and maximum depth; map, event list and summary metrics update together.
2. Search place descriptions, including an explicit empty-results state.
3. Switch 24 hours / 7 days / 30 days; this retrieves the corresponding USGS feed through MCP inside Athena.
4. Select map circles or list rows to inspect event magnitude, depth, location, UTC time and review status.
5. Sort by newest, largest magnitude or shallowest; zoom/reset the map; open the official USGS event page.

All widget CSS, JavaScript and vector map paths are inline. No external widget scripts, map tiles, API keys or CDN dependencies are needed. Dynamic strings are HTML-escaped. Source data is read-only and earthquake prediction is outside scope.

## Sources

- USGS feeds: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
- Feed URLs: `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_{day|week|month}.geojson`
- Athena SDK documentation: https://athenachat.bot/docs
- Map outlines: Natural Earth 1:110m public-domain country outlines, https://www.naturalearthdata.com/ and https://github.com/nvkelso/natural-earth-vector

USGS catalog coverage varies by region. M2.5+ is a feed threshold, not a guarantee of globally complete monitoring. Magnitude is not the same as local shaking intensity. Depth estimates can be negative when hypocenters are above the reference level.

## Validation

Runtime uses only Python's standard library. For an optional MCP integration check:

```sh
python -m pip install mcp
python verify_mcp.py http://localhost:8787/mcp
```

The check validates discovery, tool execution with actual USGS data, filtering invariants, resource metadata, and an invalid-input failure. Browser verification covers filters, sorting, time-range refresh, selection and embedded Athena rendering.

## Hosted Worker build

```sh
python build_worker.py
```

This creates `worker/index.js`, a self-contained Worker ESM module exporting `fetch`. The shared HTML and MCP tool definition are embedded at build time; `worker/logic.js` implements the same retrieval and JSON-RPC contract for a Worker runtime. It supports both `/api/mcp` and `/mcp` (the production host reserves `/mcp` for its own authenticated plugin). The generated Worker contains no credentials.

Widget state saves are deduplicated, and unchanged `openai:set_globals` data is ignored to prevent render feedback loops in Athena.

