import httpx
from fastmcp import FastMCP

from . import tools
from .client import RecruiteeClient
from .config import load_settings

INSTRUCTIONS = """\
Access to one Recruitee company: jobs (Recruitee calls them "offers"), talent pools, candidates,
their pipelines, evaluations, notes, emails, interviews and tasks.

- A candidate's place in one job is a "placement"; stage moves and disqualifications act on it.
  The write tools take candidate_id plus job_id and find the placement themselves.
- Stages, tags, sources and disqualify reasons can be given by name; the tools resolve them.
- Find IDs with list_jobs, search_candidates, list_team_members and list_reference_data.
- move_candidate and disqualify_candidate can trigger Recruitee automations that email the
  candidate. Confirm with the user before calling them on real candidates."""


class Connection:
    """Built on the first tool call, not at startup, so a freshly templated server deploys and
    answers with setup instructions before its secrets exist."""

    def __init__(self) -> None:
        self._client: RecruiteeClient | None = None

    async def client(self) -> RecruiteeClient:
        if self._client is None:
            self._client = RecruiteeClient(httpx.AsyncClient(timeout=30), load_settings())
        return self._client


def create_server() -> FastMCP:
    mcp = FastMCP("recruitee", instructions=INSTRUCTIONS)
    tools.register(mcp, Connection().client)
    return mcp
