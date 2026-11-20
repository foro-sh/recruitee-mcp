import asyncio
from typing import Annotated

from pydantic import Field

from .. import shape
from .common import CandidateId, Limit


def register(tool, get_client) -> None:
    @tool()
    async def list_candidate_notes(
        candidate_id: CandidateId,
        job_id: Annotated[int | None, Field(description="Only notes made in this job.")] = None,
    ) -> dict:
        """Notes the team wrote on a candidate, newest first, with author and replies."""
        client = await get_client()
        # Seen live: don't pass offer_id here; it returns the job's own notes, not the candidate's.
        data = await client.get(f"/candidates/{candidate_id}/notes")
        refs = shape.References(data)
        notes = [n for n in data.get("notes") or [] if job_id is None or n.get("offer_id") == job_id]
        notes.sort(key=lambda n: n.get("created_at") or "", reverse=True)
        return {"notes": [shape.note(n, refs) for n in notes]}

    @tool()
    async def get_candidate_evaluations(
        candidate_id: CandidateId,
        job_id: Annotated[int | None, Field(description="Only evaluations for this job.")] = None,
    ) -> dict:
        """Interview scorecards and questionnaires for a candidate: each reviewer's rating, notes and
        answers, plus Recruitee's overall summary."""
        client = await get_client()
        results, aggregated = await asyncio.gather(
            client.get("/interview/results", {"candidate_id": candidate_id, "kind": "all"}),
            client.get(f"/interview/candidates/{candidate_id}/results/aggregated", {"offer_id": job_id}),
        )
        refs = shape.References(results)
        rows = [r for r in results.get("interview_results") or [] if job_id is None or r.get("offer_id") == job_id]
        summary = (aggregated.get("aggregated_results") or {}).get("summary") or {}
        return shape.compact(
            {
                "summary": shape.slim(summary),
                "evaluations": [shape.evaluation(r, refs) for r in rows],
                "pending_requests": (results.get("meta") or {}).get("counters", {}).get("pending"),
                "hidden": [shape.slim(h) for h in results.get("hidden_results_preview") or []],
            }
        )

    @tool()
    async def get_candidate_activity(candidate_id: CandidateId, limit: Limit = 30) -> dict:
        """The candidate's timeline: applications, stage moves, emails, evaluations, notes and other
        events, newest first."""
        client = await get_client()
        data = await client.get(f"/tracking/candidates/{candidate_id}/activities", {"limit": limit})
        activities = data.get("activities") if isinstance(data, dict) else data
        return {"activities": shape.slim((activities or [])[:limit])}

    @tool()
    async def list_candidate_emails(candidate_id: CandidateId) -> dict:
        """Email threads with a candidate in Recruitee's mailbox. Read one with get_email_thread."""
        client = await get_client()
        data = await client.get(f"/mailbox/candidate/{candidate_id}")
        return {"threads": [shape.email_thread(t) for t in data.get("threads") or []]}

    @tool()
    async def get_email_thread(
        thread_id: Annotated[int, Field(description="Thread ID, from list_candidate_emails.")],
    ) -> dict:
        """One email thread with every message's sender, recipients, date and text."""
        client = await get_client()
        data = await client.get(f"/mailbox/threads/{thread_id}")
        return shape.email_thread(data.get("thread") or {})
