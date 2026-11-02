"""Integration check using the official MCP client and actual USGS data."""
import asyncio
import sys
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

def field(model, snake, camel):
    return getattr(model, snake, getattr(model, camel, None))

async def main(url):
    async with streamable_http_client(url) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            assert len(tools) == 1 and tools[0].name == "explore_earthquakes"
            result = await session.call_tool("explore_earthquakes", {"days": 7, "min_magnitude": 4, "max_depth": 70, "place": "Japan"})
            assert not field(result, "is_error", "isError")
            data = field(result, "structured_content", "structuredContent")
            assert data["sourceUrl"].startswith("https://earthquake.usgs.gov/")
            matches = [e for e in data["events"] if e["magnitude"] >= 4 and e["depth"] <= 70 and "japan" in e["place"].lower()]
            assert len(matches) == data["count"]
            assert all(-90 <= e["latitude"] <= 90 and -180 <= e["longitude"] <= 180 for e in data["events"])
            resource = await session.read_resource("ui://seismic/explorer.html")
            html = resource.contents[0].text
            assert "window.openai" in html and "__WORLD_PATHS__" not in html
            bad = await session.call_tool("explore_earthquakes", {"days": 999})
            assert field(bad, "is_error", "isError")
            print(f"PASS: MCP discovery, real USGS retrieval ({len(data['events'])} events, {len(matches)} matches), coordinates, widget resource, input validation")

if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8787/mcp"))

