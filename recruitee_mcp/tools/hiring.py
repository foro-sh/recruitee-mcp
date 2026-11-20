from typing import Annotated

from pydantic import Field

from .. import shape
from .common import CandidateId, JobId, find_placement, job_with_stages, match

Tags = Annotated[list[str], Field(min_length=1, description="Tag names. New names create the tag.")]


def register(tool, get_client) -> None:
    @tool(writes=True)
    async def add_candidate_to_job(
        candidate_id: CandidateId,
        job_id: Annotated[int | None, Field(description="Add to this job's first stage.")] = None,
        talent_pool_id: Annotated[int | None, Field(description="Or add to this talent pool.")] = None,
    ) -> dict:
        """Put an existing candidate into a job's pipeline, or into a talent pool."""
        if (job_id is None) == (talent_pool_id is None):
            raise ValueError("Pass exactly one of job_id or talent_pool_id.")
        client = await get_client()
        data = await client.post(
            "/placements",
            shape.compact({"candidate_id": candidate_id, "offer_id": job_id, "talent_pool_id": talent_pool_id}),
        )
        return shape.placement(data.get("placement") or {}, shape.References(data))

    @tool(writes=True)
    async def move_candidate(
        candidate_id: CandidateId,
        job_id: JobId,
        stage: Annotated[str, Field(description="Target stage, by name (e.g. 'Interview') or ID.")],
        run_automations: Annotated[
            bool,
            Field(description="Also run the stage's automations, which can email the candidate. Off by default."),
        ] = False,
    ) -> dict:
        """Move a candidate to another stage of a job. Moving to a hired stage may need extra details
        Recruitee asks for (start date, location, opening); its error says which."""
        client = await get_client()
        placement = await find_placement(client, candidate_id, job_id)
        offer, stages = await job_with_stages(client, job_id)
        target = match(stages, stage, label=f"stage in {offer.get('title')!r}")
        current = next((s for s in stages if s["id"] == placement.get("stage_id")), {})
        await client.patch(
            f"/placements/{placement['id']}/change_stage",
            {"stage_id": target["id"], "proceed": True, "run_actions": run_automations},
        )
        return shape.compact(
            {
                "candidate_id": candidate_id,
                "job": offer.get("title"),
                "from_stage": current.get("name"),
                "to_stage": target.get("name"),
                "automations_ran": run_automations,
            }
        )

    @tool(writes=True, destructive=True)
    async def disqualify_candidate(
        candidate_id: CandidateId,
        job_id: JobId,
        reason: Annotated[str, Field(description="Disqualify reason, by name or ID; see list_reference_data.")],
    ) -> dict:
        """Disqualify (reject) a candidate in one job. If the reason has automations in Recruitee,
        such as a rejection email, they run."""
        client = await get_client()
        placement = await find_placement(client, candidate_id, job_id)
        reasons = (await client.get("/disqualify_reasons")).get("disqualify_reasons") or []
        chosen = match(reasons, reason, label="disqualify reason")
        await client.patch(f"/placements/{placement['id']}/disqualify", {"disqualify_reason_id": chosen["id"]})
        return shape.compact(
            {
                "candidate_id": candidate_id,
                "job_id": job_id,
                "reason": chosen.get("name"),
                "reason_automations": [a.get("kind") for a in chosen.get("action_templates") or []],
            }
        )

    @tool(writes=True, idempotent=True)
    async def requalify_candidate(candidate_id: CandidateId, job_id: JobId) -> dict:
        """Undo a disqualification: the candidate is back in the job's pipeline, in the same stage."""
        client = await get_client()
        placement = await find_placement(client, candidate_id, job_id)
        await client.patch(f"/placements/{placement['id']}/requalify")
        return {"candidate_id": candidate_id, "job_id": job_id, "requalified": True}

    @tool(writes=True)
    async def add_note(
        candidate_id: CandidateId,
        text: Annotated[str, Field(min_length=1, description="The note. Line breaks become paragraphs.")],
    ) -> dict:
        """Add a note to a candidate's profile, visible to everyone on the team with access."""
        client = await get_client()
        note = {
            "body_json": shape.doc(text),
            "visibility": {"level": "public", "admin_ids": [], "role_ids": []},
        }
        # ponytail: no job_id. Seen live: offer_id inside `note` is ignored, and at the top level it
        # turns the note into a note on the job, detached from the candidate.
        data = await client.post(f"/candidates/{candidate_id}/notes", {"note": note})
        created = data.get("note") or {}
        return shape.compact({"note_id": created.get("id"), "created_at": created.get("created_at")})

    @tool(writes=True, idempotent=True)
    async def tag_candidate(candidate_id: CandidateId, tags: Tags) -> dict:
        """Add tags to a candidate. Returns the tags added; get_candidate shows all of them."""
        client = await get_client()
        # Seen live: the response echoes only the tags in the request, not the candidate's full set.
        data = await client.post(f"/candidates/{candidate_id}/tags", {"tags": tags})
        return {"candidate_id": candidate_id, "added": shape.tag_names(data.get("tags"))}

    @tool(writes=True, destructive=True, idempotent=True)
    async def untag_candidate(candidate_id: CandidateId, tags: Tags) -> dict:
        """Remove tags from a candidate. Returns the tags removed; get_candidate shows the rest."""
        client = await get_client()
        data = await client.delete(f"/candidates/{candidate_id}/tags", {"tags": tags})
        return {"candidate_id": candidate_id, "removed": shape.tag_names(data.get("tags"))}
