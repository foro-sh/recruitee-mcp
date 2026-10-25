from typing import Annotated, Literal

from pydantic import Field

from .. import shape
from .common import JobId, Limit, Page, job_with_stages, match

JobStatus = Literal["draft", "published", "internal", "closed", "archived"]

JOB_FIELDS = [
    "id",
    "title",
    "status",
    "department",
    "department_id",
    "location",
    "city",
    "country_code",
    "remote",
    "hybrid",
    "on_site",
    "employment_type",
    "candidates_count",
    "qualified_candidates_count",
    "disqualified_candidates_count",
    "hired_candidates_count",
    "number_of_openings",
    "priority",
    "recruiter_id",
    "hiring_manager_id",
    "created_at",
    "published_at",
    "closed_at",
    "careers_url",
]


def stage_summary(stage: dict) -> dict:
    return shape.pick(stage, ["id", "name", "group", "category", "time_limit", "placements_count"])


def register(tool, get_client) -> None:
    @tool()
    async def list_jobs(
        status: Annotated[
            list[JobStatus] | None,
            Field(description="Only jobs in these statuses. Default: published and internal (the open ones)."),
        ] = None,
        query: Annotated[str | None, Field(description="Part of the job title.")] = None,
        department_id: Annotated[int | None, Field(description="From list_reference_data('departments').")] = None,
        limit: Limit = 50,
        page: Page = 1,
    ) -> dict:
        """Jobs with status, department, location and candidate counts."""
        client = await get_client()
        data = await client.get(
            "/offers",
            {
                "statuses": status or ["published", "internal"],
                "department_ids": [department_id] if department_id else None,
                "limit": limit,
                "page": page,
            },
        )
        offers = [o for o in data.get("offers") or [] if o.get("kind", "job") == "job"]
        if query:
            offers = [o for o in offers if query.lower() in (o.get("title") or "").lower()]
        return {"jobs": [shape.pick(o, JOB_FIELDS) for o in offers], "page": page, "has_more": len(offers) >= limit}

    @tool()
    async def get_job(job_id: JobId) -> dict:
        """One job in full: description, requirements, salary, location, team and its pipeline stages."""
        client = await get_client()
        offer, stages = await job_with_stages(client, job_id)
        out = shape.pick(offer, [*JOB_FIELDS, "experience", "education", "min_hours", "max_hours", "url", "slug"])
        out["description"] = shape.text(offer.get("description_html") or offer.get("description"))
        out["requirements"] = shape.text(offer.get("requirements_html") or offer.get("requirements"))
        salary = shape.compact(offer.get("salary") or {})
        if salary:
            out["salary"] = salary
        out["tags"] = shape.tag_names(offer.get("tags") or offer.get("offer_tags"))
        out["stages"] = [stage_summary(s) for s in stages]
        return shape.compact(out)

    @tool()
    async def list_pipeline(
        job_id: JobId,
        stage: Annotated[str | None, Field(description="Only this stage, by name or ID.")] = None,
        include_disqualified: bool = False,
    ) -> dict:
        """A job's pipeline: candidates per stage, with when they applied, ratings, overdue flags and
        upcoming interviews. Disqualified candidates are left out unless asked for."""
        client = await get_client()
        offer, stages = await job_with_stages(client, job_id)
        by_id = {s["id"]: s for s in stages}
        params: dict = {
            "with_tags": True,
            "with_last_activity_at": True,
            "qualified": None if include_disqualified else True,
        }
        stage_id = match(stages, stage, label="stage")["id"] if stage else None
        params["stage_id"] = stage_id
        data = await client.get(f"/offers/{job_id}/placements", params)

        columns: dict[int | None, dict] = {
            s["id"]: {**stage_summary(s), "candidates": []} for s in stages if stage_id in (None, s["id"])
        }
        disqualified = []
        for p in data.get("placements") or []:
            candidate = p.get("candidate") or {}
            row = shape.compact(
                {
                    "candidate_id": p.get("candidate_id"),
                    "name": candidate.get("name"),
                    "placement_id": p.get("id"),
                    "applied_at": p.get("created_at"),
                    "last_activity_at": candidate.get("last_activity_at") or p.get("last_activity_at"),
                    "positive_ratings": p.get("positive_ratings"),
                    "overdue_at": p.get("overdue_at"),
                    "upcoming_interview_at": candidate.get("upcoming_event_starts_at"),
                    "tags": shape.tag_names(candidate.get("tags") or p.get("tags")),
                    "hired_at": p.get("hired_at"),
                }
            )
            if p.get("disqualified_at") or p.get("disqualify_reason_id") or p.get("status") == "disqualified":
                disqualified.append({**row, "stage": by_id.get(p.get("stage_id"), {}).get("name")})
                continue
            column = columns.get(p.get("stage_id"))
            if column is None:
                column = columns.setdefault(p.get("stage_id"), {"id": p.get("stage_id"), "candidates": []})
            column["candidates"].append(row)

        out = {
            "job": offer.get("title"),
            "stages": [{**c, "count": len(c["candidates"])} for c in columns.values()],
        }
        if include_disqualified:
            out["disqualified"] = disqualified
        return out

    @tool()
    async def list_talent_pools(
        include_archived: bool = False,
        limit: Limit = 100,
    ) -> dict:
        """Talent pools (candidate lists outside a specific job) with their candidate counts."""
        client = await get_client()
        data = await client.get(
            "/talent_pools", {"scope": None if include_archived else "not_archived", "limit": limit}
        )
        return {
            "talent_pools": [
                shape.pick(t, ["id", "title", "status", "candidates_count", "department_id", "created_at"])
                for t in data.get("talent_pools") or []
            ]
        }
