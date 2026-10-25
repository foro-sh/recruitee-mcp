"""Argument types and the name-to-ID lookups the tools share."""

from typing import Annotated, Any

from pydantic import Field

from ..client import RecruiteeClient

CandidateId = Annotated[int, Field(description="Candidate ID, from search_candidates or filter_candidates.")]
JobId = Annotated[int, Field(description="Job (offer) ID, from list_jobs.")]
Limit = Annotated[int, Field(ge=1, le=200, description="Maximum rows to return.")]
Page = Annotated[int, Field(ge=1, description="Page number, starting at 1.")]


def match(items: list[dict], wanted: str | int, *, label: str, name_key: str = "name") -> dict:
    """The item whose ID or (case-insensitive) name is `wanted`. A miss names the choices, so
    the agent can retry without another lookup."""
    key = str(wanted).strip()
    if key.isdigit():
        for item in items:
            if item.get("id") == int(key):
                return item
    lowered = key.lower()
    exact = [i for i in items if str(i.get(name_key, "")).lower() == lowered]
    if len(exact) == 1:
        return exact[0]
    partial = [i for i in items if lowered in str(i.get(name_key, "")).lower()]
    if len(partial) == 1 and not exact:
        return partial[0]
    choices = ", ".join(f"{i.get(name_key)} ({i.get('id')})" for i in items) or "none"
    if len(exact) > 1 or len(partial) > 1:
        raise ValueError(f"More than one {label} matches {wanted!r}. Pass the ID instead. Choices: {choices}")
    raise ValueError(f"No {label} {wanted!r}. Choices: {choices}")


async def job_with_stages(client: RecruiteeClient, job_id: int) -> tuple[dict, list[dict]]:
    offer = (await client.get(f"/offers/{job_id}"))["offer"]
    template = offer.get("pipeline_template") or {}
    stages = template.get("stages") or offer.get("pipeline") or []
    if not isinstance(stages, list):
        stages = []
    return offer, sorted(stages, key=lambda s: s.get("position") or 0)


async def find_placement(client: RecruiteeClient, candidate_id: int, job_id: int) -> dict:
    """A candidate's placement in one job; Recruitee's stage and disqualify calls act on it."""
    candidate = (await client.get(f"/candidates/{candidate_id}"))["candidate"]
    for placement in candidate.get("placements") or []:
        if placement.get("offer_id") == job_id:
            return placement
    jobs = ", ".join(str(p["offer_id"]) for p in candidate.get("placements") or [] if p.get("offer_id"))
    raise ValueError(
        f"Candidate {candidate_id} is not in job {job_id}"
        + (f"; they are in jobs {jobs}." if jobs else "; they are in no job yet.")
        + " Use add_candidate_to_job first."
    )


async def ids_for(client: RecruiteeClient, path: str, collection: str, names: list[str], label: str) -> list[int]:
    """IDs for tag or source names, which is what Recruitee's search filters take."""
    items: list[dict[str, Any]] = (await client.get(path, {"limit": 1000})).get(collection) or []
    return [match(items, name, label=label)["id"] for name in names]
