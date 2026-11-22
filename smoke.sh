#!/usr/bin/env bash
# Starts the server with no Recruitee credentials, as a fresh foro deploy does, and checks it
# answers tools/list over streamable HTTP with every tool in foro-tools.json.
set -euo pipefail
cd "$(dirname "$0")"

port=${SMOKE_PORT:-8765}
env -u RECRUITEE_API_TOKEN -u RECRUITEE_COMPANY_ID PORT="$port" uv run python server.py >smoke.log 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT

uv run python - "$port" <<'PY'
import asyncio, json, sys
from fastmcp import Client

async def main(port: str) -> None:
    for _ in range(60):
        try:
            async with Client(f"http://127.0.0.1:{port}/mcp") as client:
                names = {tool.name for tool in await client.list_tools()}
                break
        except Exception:
            await asyncio.sleep(0.5)
    else:
        sys.exit("server never answered; see smoke.log")
    expected = {tool["name"] for tool in json.load(open("foro-tools.json"))["tools"]}
    if names != expected:
        sys.exit(f"tools differ from foro-tools.json: {sorted(names ^ expected)}")
    print(f"smoke ok: {len(names)} tools without credentials")

asyncio.run(main(sys.argv[1]))
PY
