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

            return mcp.tool(annotations=annotations)(wrapper)

        return decorate

    for module in MODULES:
        module.register(tool, get_client)
