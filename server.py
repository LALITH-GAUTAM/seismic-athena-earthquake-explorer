"""Seismic: dependency-free, stateless MCP Streamable HTTP server."""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
RESOURCE = "ui://seismic/explorer.html"
CACHE = {}
SCHEMA = {"type": "object", "properties": {
    "days": {"type": "integer", "enum": [1, 7, 30], "default": 7, "description": "Recent time range in days."},
    "min_magnitude": {"type": "number", "minimum": 2.5, "maximum": 10, "default": 2.5},
    "max_depth": {"type": "number", "minimum": -10, "maximum": 1000, "default": 1000},
    "place": {"type": "string", "maxLength": 100, "default": "", "description": "Case-insensitive substring of USGS place description, e.g. Alaska or Japan."}
}, "additionalProperties": False}
TOOL = {"name": "explore_earthquakes", "title": "Explore recent earthquakes", "description": "Use this to retrieve real recent earthquakes from USGS and render the interactive Seismic explorer. Supports recent 1, 7 or 30 days, minimum magnitude, maximum depth in km, and place substring. Returns an embedded widget with map, filters, sorting and event details. Use default 7 days and M2.5 when unspecified.", "inputSchema": SCHEMA,
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True, "idempotentHint": True},
    "_meta": {"openai/outputTemplate": RESOURCE, "openai/widgetAccessible": True, "openai/toolInvocation/invoking": "Retrieving USGS earthquakes…", "openai/toolInvocation/invoked": "Earthquake explorer ready"}}

def retrieve(args):
    days = args.get("days", 7)
    if isinstance(days, bool) or days not in (1, 7, 30):
        raise ValueError("days must be 1, 7 or 30")
    mag = args.get("min_magnitude", 2.5)
    depth = args.get("max_depth", 1000)
    if not isinstance(mag, (int, float)) or not 2.5 <= mag <= 10:
        raise ValueError("min_magnitude must be between 2.5 and 10")
    if not isinstance(depth, (int, float)) or not -10 <= depth <= 1000:
        raise ValueError("max_depth must be between -10 and 1000")
    place = args.get("place", "")
    if not isinstance(place, str) or len(place) > 100:
        raise ValueError("place must be a string of at most 100 characters")
    period = {1: "day", 7: "week", 30: "month"}[days]
    source = f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_{period}.geojson"
    cached = CACHE.get(days)
    if cached and time.time() - cached[0] < 60:
        data, fetched = cached[1:]
    else:
        req = urllib.request.Request(source, headers={"User-Agent": "SeismicEarthquakeExplorer/1.0"})
        with urllib.request.urlopen(req, timeout=25) as response:
            data = json.load(response)
        fetched = datetime.now(timezone.utc).isoformat()
        CACHE[days] = (time.time(), data, fetched)
    events = []
    for f in data.get("features", []):
        p, c = f["properties"], f["geometry"]["coordinates"]
        if p.get("type") != "earthquake" or p.get("mag") is None:
            continue
        events.append({"id": f["id"], "magnitude": p["mag"], "place": p.get("place") or "Location not reported", "time": p["time"], "updated": p.get("updated"), "longitude": c[0], "latitude": c[1], "depth": c[2], "url": p.get("url"), "status": p.get("status"), "magType": p.get("magType"), "felt": p.get("felt")})
    events.sort(key=lambda e: e["time"], reverse=True)
    count = sum(e['magnitude'] >= mag and e['depth'] <= depth and place.lower() in e['place'].lower() for e in events)
    return {"events": events, "count": count, "catalogCount": len(events), "source": "USGS Earthquake Hazards Program", "sourceUrl": source, "fetchedAt": fetched, "feedGenerated": data.get("metadata", {}).get("generated"), "filters": {"days": days, "min_magnitude": mag, "max_depth": depth, "place": place}, "note": "Catalog includes M2.5+ earthquakes. Count matches requested filters; events includes the full time-range catalog so widget filters can be widened. Preliminary data may be revised. Place searches match USGS descriptions. No earthquake prediction."}

def rpc(body):
    method, args = body.get("method"), body.get("params", {})
    if "id" not in body:
        return None
    rid = body["id"]
    result = {}
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}, "resources": {}}, "serverInfo": {"name": "seismic-usgs-explorer", "version": "1.0.0"}, "instructions": "Call explore_earthquakes to retrieve USGS data and show the embedded interactive explorer."}
    elif method == "ping":
        pass
    elif method == "tools/list":
        result = {"tools": [TOOL]}
    elif method == "resources/list":
        result = {"resources": [{"uri": RESOURCE, "name": "Seismic explorer", "mimeType": "text/html+skybridge"}]}
    elif method == "resources/templates/list":
        result = {"resourceTemplates": []}
    elif method == "resources/read":
        if args.get("uri") != RESOURCE:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": "Unknown resource URI"}}
        result = {"contents": [{"uri": RESOURCE, "mimeType": "text/html+skybridge", "text": (ROOT / "public/widget.html").read_text(encoding="utf-8"), "_meta": {"openai/widgetDescription": "Interactive USGS earthquake map and event explorer with magnitude, depth, place and time filters.", "openai/widgetPrefersBorder": True, "openai/widgetCSP": {"connect_domains": [], "resource_domains": []}}}]}
    elif method == "tools/call":
        try:
            if args.get("name") != TOOL["name"]:
                raise ValueError("Unknown tool")
            data = retrieve(args.get("arguments") or {})
            result = {"content": [{"type": "text", "text": f"Retrieved {data['count']} earthquakes from USGS for the last {data['filters']['days']} days. The embedded explorer shows the data; use its controls to filter and inspect events. Source: {data['sourceUrl']}. Fetched: {data['fetchedAt']}."}], "structuredContent": data, "_meta": {"openai/outputTemplate": RESOURCE}}
        except Exception as exc:
            result = {"content": [{"type": "text", "text": "USGS retrieval failed: " + str(exc)}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data=b"", kind="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, MCP-Protocol-Version, Mcp-Session-Id")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.reply(204)

    def do_GET(self):
        if self.path in ("/", "/widget"):
            self.reply(200, (ROOT / "public/widget.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path.startswith("/api/earthquakes"):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            try:
                data = retrieve({"days": int(q.get("days", [7])[0])})
                self.reply(200, json.dumps(data).encode())
            except Exception as exc:
                self.reply(502, json.dumps({"error": str(exc)}).encode())
        elif self.path == "/health":
            self.reply(200, b'{"status":"ok","service":"seismic-usgs-mcp"}')
        elif self.path == "/mcp":
            self.reply(405, b'{"error":"Use POST for stateless MCP requests"}')
        else:
            self.reply(404, b'{"error":"Not found"}')

    def do_POST(self):
        if self.path.rstrip("/") != "/mcp":
            return self.reply(404)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 1_000_000:
                return self.reply(413)
            body = json.loads(self.rfile.read(size))
            response = rpc(body)
            if response is None:
                self.reply(202)
            else:
                self.reply(200, json.dumps(response).encode())
        except Exception:
            self.reply(400, b'{"jsonrpc":"2.0","id":null,"error":{"code":-32700,"message":"Invalid JSON-RPC request"}}')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8787"))
    print(f"Seismic MCP listening on http://localhost:{port}/mcp", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()

