import json
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import Field

from .. import shape
from .common import CandidateId, Limit, Page, ids_for

CV_TEXT_LIMIT = 20_000

SearchSort = Literal[
    "relevance_desc",
    "created_at_desc",
    "created_at_asc",
    "candidate_name_asc",
    "candidate_rating_desc",
    "candidate_positive_ratings_desc",
]


def register(tool, get_client) -> None:
    @tool()
    async def search_candidates(
        query: Annotated[str | None, Field(description="Part of the candidate's name or email.")] = None,
        job_id: Annotated[int | None, Field(description="Only candidates in this job (from list_jobs).")] = None,
        status: Literal["all", "qualified", "disqualified"] = "all",
        created_after: Annotated[date | None, Field(description="Only candidates added after this date.")] = None,
        sort: Literal["newest", "last_message"] = "newest",
        limit: Limit = 25,
        offset: Annotated[int, Field(ge=0, description="Rows to skip, for the next page.")] = 0,
    ) -> dict:
        """Find candidates by name or email, optionally within one job. For skills, tags, sources,
        ratings or experience, use filter_candidates."""
        client = await get_client()
        data = await client.get(
            "/candidates",
            {
                "query": query,
                "offer_id": job_id,
                "qualified": True if status == "qualified" else None,
                "disqualified": True if status == "disqualified" else None,
                "created_after": created_after.isoformat() if created_after else None,
                "sort": "by_last_message" if sort == "last_message" else "by_date",
                "limit": limit,
                "offset": offset,
            },
        )
        refs = shape.References(data)
        rows = data.get("candidates") or []
        return {
            "candidates": [shape.candidate_summary(c, refs) for c in rows],
            "offset": offset,
            "has_more": len(rows) >= limit,
        }

    @tool()
    async def filter_candidates(
        text: Annotated[str | None, Field(description="Free text across the whole profile and CV.")] = None,
        skills: Annotated[list[str] | None, Field(description="Has any of these skills.")] = None,
        past_job_titles: Annotated[list[str] | None, Field(description="Experience title contains any.")] = None,
        past_companies: Annotated[list[str] | None, Field(description="Experience company contains any.")] = None,
        degrees: Annotated[list[str] | None, Field(description="Education degree contains any.")] = None,
        languages: Annotated[
            list[str] | None, Field(description="Speaks all of these (ISO codes, e.g. nl, en).")
        ] = None,
        tags: Annotated[list[str] | None, Field(description="Has all of these tags, by name.")] = None,
        sources: Annotated[list[str] | None, Field(description="Came from any of these sources, by name.")] = None,
        status: Annotated[
            list[Literal["qualified", "disqualified"]] | None, Field(description="Placement status.")
        ] = None,
        min_rating: Annotated[float | None, Field(description="Average evaluation rating at least this.")] = None,
        created_from: date | None = None,
        created_to: date | None = None,
        active_since: Annotated[date | None, Field(description="Had activity on or after this date.")] = None,
        has_cv: bool | None = None,
        raw_filters: Annotated[
            list[dict[str, Any]] | None,
            Field(
                description="Extra Recruitee FilterGroups, passed as-is, e.g. "
                '{"filter": "nationality", "country_code": {"in": ["NL"]}}.'
            ),
        ] = None,
        sort_by: SearchSort = "relevance_desc",
        limit: Limit = 25,
        page: Page = 1,
    ) -> dict:
        """Search all candidates, across every job, by skills, experience, education, languages, tags,
        sources, rating and dates. Filters combine with AND."""
        client = await get_client()
        filters: list[dict[str, Any]] = []
        if text:
            filters.append({"field": "all", "query": text})
        if skills:
            filters.append({"filter": "skills", "text": {"contains": skills}})
        if past_job_titles:
            filters.append({"filter": "experience", "title": {"contains": past_job_titles}})
        if past_companies:
            filters.append({"filter": "experience", "company": {"contains": past_companies}})
        if degrees:
            filters.append({"filter": "education", "degree": {"contains": degrees}})
        if languages:
            filters.append({"filter": "language_skill", "language_code": {"has_all_of": languages}})
        if tags:
            tag_ids = await ids_for(client, "/tags", "tags", tags, "tag")
            filters.append({"filter": "tags", "id": {"all_in": tag_ids}})
        if sources:
            source_ids = await ids_for(client, "/sources", "sources", sources, "source")
            filters.append({"filter": "sources", "id": {"in": source_ids}})
        if status:
            filters.append({"field": "status", "in": status})
        if min_rating is not None:
            filters.append({"field": "rating", "gte": min_rating})
        if created_from or created_to:
            filters.append(
                shape.compact(
                    {
                        "field": "created_at",
                        "gte": created_from.isoformat() if created_from else None,
                        "lte": created_to.isoformat() if created_to else None,
                    }
                )
            )
        if active_since:
            filters.append({"field": "last_activity_at", "gte": active_since.isoformat()})
        if has_cv is not None:
            filters.append({"field": "has_cv", "eq": has_cv})
        filters.extend(raw_filters or [])

        data = await client.get(
            "/search/new/candidates",
            {
                "filters_json": json.dumps(filters),
                "sort_by": sort_by if text or sort_by != "relevance_desc" else "created_at_desc",
                "limit": limit,
                "page": page,
            },
        )
        hits = data.get("hits") or []
        return {
            "total": data.get("total"),
            "candidates": [shape.candidate_summary(h) if "name" in h else shape.slim(h) for h in hits],
            "page": page,
            "has_more": (data.get("total") or 0) > page * limit,
        }

    @tool()
    async def get_candidate(candidate_id: CandidateId) -> dict:
        """One candidate's profile: contact details, every job they're in with stage and status, tags,
        sources, experience and education, custom fields and screening answers."""
        client = await get_client()
        data = await client.get(f"/candidates/{candidate_id}")
        return shape.candidate_detail(data["candidate"], shape.References(data))

    @tool()
    async def get_candidate_cv(candidate_id: CandidateId) -> dict:
        """The plain text of the candidate's CV and their typed cover letter, for reading or comparing
        candidates. Empty for anonymised candidates."""
        client = await get_client()
        data = (await client.get(f"/candidates/{candidate_id}/parsed_cv")).get("data") or {}
        cv_text = data.get("cv_text") or ""
        return shape.compact(
            {
                "cv_text": cv_text[:CV_TEXT_LIMIT],
                "truncated": len(cv_text) > CV_TEXT_LIMIT or None,
                "cover_letter": shape.text(data.get("cover_letter")) or data.get("cover_letter"),
                "has_cover_letter_file": data.get("has_cover_letter") and not data.get("cover_letter") or None,
                "cv_parse_status": data.get("cv_parse_status"),
                "note": None if cv_text else "No CV text: the candidate has no CV, or it was not parsed.",
            }
        )

    @tool(writes=True)
    async def create_candidate(
        name: str,
        emails: list[str] | None = None,
        phones: list[str] | None = None,
        job_id: Annotated[int | None, Field(description="Add them to this job's first stage.")] = None,
        talent_pool_id: Annotated[int | None, Field(description="Add them to this talent pool.")] = None,
        source: Annotated[str | None, Field(description="Where they came from, e.g. 'Referral'.")] = None,
        cover_letter: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        """Add a candidate, optionally straight into a job or talent pool. Says when Recruitee already
        has someone with the same name or email."""
        client = await get_client()
        candidate = shape.compact(
            {
                "name": name,
                "emails": emails,
                "phones": phones,
                "sources": [source] if source else None,
                "cover_letter": cover_letter,
            }
        )
        body: dict[str, Any] = {"candidate": candidate}
        if job_id:
            body["offers"] = [job_id]
        data = await client.post("/candidates", body)
        created = data["candidate"]
        if talent_pool_id:
            await client.post("/placements", {"candidate_id": created["id"], "talent_pool_id": talent_pool_id})
        if tags:
            await client.post(f"/candidates/{created['id']}/tags", {"tags": tags})
        return shape.compact(
            {
                "candidate_id": created["id"],
                "name": created.get("name"),
                "adminapp_url": created.get("adminapp_url"),
                "possible_duplicates": created.get("duplicates"),
            }
        )

    @tool(writes=True, idempotent=True)
    async def update_candidate(
        candidate_id: CandidateId,
        name: str | None = None,
        title: Annotated[str | None, Field(description="Current job title / headline.")] = None,
        emails: Annotated[list[str] | None, Field(description="Replaces the whole email list.")] = None,
        phones: Annotated[list[str] | None, Field(description="Replaces the whole phone list.")] = None,
    ) -> dict:
        """Change a candidate's name, headline, emails or phone numbers. Fields left out stay as they are."""
        changes = shape.compact({"name": name, "title": title, "emails": emails, "phones": phones})
        if not changes:
            raise ValueError("Nothing to change: pass at least one of name, title, emails or phones.")
        client = await get_client()
        data = await client.patch(f"/candidates/{candidate_id}", {"candidate": changes})
        return shape.pick(data["candidate"], ["id", "name", "title", "emails", "phones", "updated_at"])
