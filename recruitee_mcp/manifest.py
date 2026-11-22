"""foro-tools.json: the tools this server registers and which of them change something. foro's
blueprint page reads it from the latest release to list the tools and keep every write tool off
until it is named. Regenerate with `uv run python -m recruitee_mcp.manifest`; a test fails when the
committed file is stale."""

import asyncio
import json
import re
from pathlib import Path

from .app import create_server

PATH = Path(__file__).parent.parent / "foro-tools.json"


async def manifest() -> dict:
    return {
        "tools": [
            {
                "name": tool.name,
                "label": tool.title,
                "description": re.split(r"(?<=\.)\s", " ".join((tool.description or "").split()), maxsplit=1)[0],
                "writes": not tool.annotations.read_only_hint,
            }
            for tool in await create_server().list_tools()
        ]
    }


def render(data: dict) -> str:
    return json.dumps(data, indent=2) + "\n"


if __name__ == "__main__":
    PATH.write_text(render(asyncio.run(manifest())))
