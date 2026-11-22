"""Every tool, grouped by what it works on. To drop a group from your fork, remove its module from
MODULES; to drop a single tool, delete its function. On foro you can also leave the code alone
and switch tools off on the Bridge page, which blocks them at the gate."""

import functools
from collections.abc import Awaitable, Callable

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from ..client import RecruiteeClient, RecruiteeError
from ..config import ConfigError
from . import candidates, hiring, history, jobs, reference, schedule

GetClient = Callable[[], Awaitable[RecruiteeClient]]

MODULES = (jobs, candidates, history, hiring, schedule, reference)

# The human name each tool goes by: the MCP `title`, and the label foro's blueprint page shows. A tool
# missing here fails at startup, so a new one can't ship without it.
TITLES = {
    "list_jobs": "List jobs",
    "get_job": "Get a job",
    "list_pipeline": "Read a job's pipeline",
    "list_talent_pools": "List talent pools",
    "search_candidates": "Find candidates",
    "filter_candidates": "Filter candidates",
    "get_candidate": "Get a candidate",
    "get_candidate_cv": "Read a candidate's CV",
    "create_candidate": "Add candidates",
    "update_candidate": "Edit candidates",
    "list_candidate_notes": "Read notes",
    "get_candidate_evaluations": "Read evaluations",
    "get_candidate_activity": "Read a candidate's activity",
    "list_candidate_emails": "List emails",
    "get_email_thread": "Read an email thread",
    "add_candidate_to_job": "Add candidates to jobs",
    "move_candidate": "Move candidates between stages",
    "disqualify_candidate": "Disqualify candidates",
    "requalify_candidate": "Requalify candidates",
    "add_note": "Add notes",
    "tag_candidate": "Tag candidates",
    "untag_candidate": "Remove tags",
    "list_interviews": "List interviews",
    "list_tasks": "List tasks",
    "create_task": "Create tasks",
    "complete_task": "Complete tasks",
    "list_team_members": "List team members",
    "list_reference_data": "Read tags, sources and departments",
}

# Every failure a caller can act on, surfaced as the tool's error text rather than masked.
_USER_ERRORS = (ConfigError, RecruiteeError, ValueError)


def register(mcp: FastMCP, get_client: GetClient) -> None:
    def tool(*, writes: bool = False, destructive: bool = False, idempotent: bool = False):
        annotations = ToolAnnotations(
            read_only_hint=not writes,
            destructive_hint=destructive if writes else None,
            idempotent_hint=idempotent if writes else None,
            open_world_hint=True,
        )

        def decorate(fn):
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                try:
                    return await fn(*args, **kwargs)
                except _USER_ERRORS as err:
                    raise ToolError(str(err)) from err

            return mcp.tool(title=TITLES[fn.__name__], annotations=annotations)(wrapper)

        return decorate

    for module in MODULES:
        module.register(tool, get_client)
