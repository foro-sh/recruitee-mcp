from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field

from .. import shape
from .common import Limit, Page

AdminIds = Annotated[list[int] | None, Field(description="Team member IDs, from list_team_members.")]


def register(tool, get_client) -> None:
    @tool()
    async def list_interviews(
        when: Literal["upcoming", "past_due", "all"] = "upcoming",
        mine_only: Annotated[bool, Field(description="Only interviews of the token's own user.")] = False,
        candidate_id: int | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        interviewer_ids: AdminIds = None,
        limit: Limit = 50,
        page: Page = 1,
    ) -> dict:
        """Scheduled interviews with candidate, job, time, place or video link, and interviewers."""
        client = await get_client()
        data = await client.get(
            "/interview/events",
            {
                "status": when,
                "scope": "my" if mine_only else "all",
                "candidate_id": candidate_id,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "timezone": client.timezone if start_date or end_date else None,
                "admin_ids": interviewer_ids,
                "limit": limit,
                "page": page,
            },
        )
        refs = shape.References(data)
        events = data.get("interview_events") or []
        return {
            "interviews": [shape.interview(e, refs) for e in events],
            "total": (data.get("meta") or {}).get("total_count"),
            "page": page,
        }

    @tool()
    async def list_tasks(
        candidate_id: Annotated[int | None, Field(description="Only this candidate's tasks.")] = None,
        status: Literal["open", "completed", "all"] = "open",
        assigned: Literal["anyone", "me", "unassigned"] = "anyone",
        assignee_ids: AdminIds = None,
        limit: Limit = 50,
        page: Page = 1,
    ) -> dict:
        """To-dos for the hiring team, soonest due first."""
        client = await get_client()
        status_param = {"open": "uncompleted", "completed": "completed", "all": None}[status]
        if candidate_id:
            data = await client.get(f"/candidates/{candidate_id}/tasks", {"status": status_param})
        else:
            data = await client.get(
                "/tasks",
                {
                    "status": status_param,
                    "scope": {"anyone": "all", "me": "my", "unassigned": "unassigned"}[assigned],
                    "admin_ids": assignee_ids,
                    "sort_by": "due_date",
                    "sort_order": "asc",
                    "limit": limit,
                    "page": page,
                },
            )
        refs = shape.References(data)
        return {"tasks": [shape.task(t, refs) for t in data.get("tasks") or []]}

    @tool(writes=True)
    async def create_task(
        title: str,
        candidate_id: Annotated[int | None, Field(description="Link the task to this candidate.")] = None,
        due: Annotated[
            date | datetime | None,
            Field(union_mode="left_to_right", description="Due date, or date and time."),
        ] = None,
        assignee_ids: AdminIds = None,
        description: str | None = None,
    ) -> dict:
        """Create a to-do for the hiring team, optionally about one candidate. Assignees are notified
        by Recruitee."""
        client = await get_client()
        task = shape.compact(
            {
                "title": title,
                "description": description,
                "candidate_id": candidate_id,
                "admin_ids": assignee_ids,
                "due_date": due.isoformat() if due else None,
                "timezone": client.timezone if due else None,
            }
        )
        data = await client.post("/tasks", {"task": task})
        return shape.task(data.get("task") or {}, shape.References(data))

    @tool(writes=True, idempotent=True)
    async def complete_task(
        task_id: Annotated[int, Field(description="Task ID, from list_tasks.")],
        completed: Annotated[bool, Field(description="False reopens the task.")] = True,
    ) -> dict:
        """Mark a task done, or reopen it."""
        client = await get_client()
        data = await client.patch(f"/tasks/{task_id}/completion", {"task": {"completed": completed}})
        return shape.task(data.get("task") or {}, shape.References(data))
