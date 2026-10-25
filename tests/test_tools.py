import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from recruitee_mcp.app import create_server

from .conftest import ADMIN, CANDIDATE, OFFER

WRITE_TOOLS = {
    "create_candidate",
    "update_candidate",
    "add_candidate_to_job",
    "move_candidate",
    "disqualify_candidate",
    "requalify_candidate",
    "add_note",
    "tag_candidate",
    "untag_candidate",
    "create_task",
    "complete_task",
}


async def test_reads_are_read_only_and_writes_say_so(server):
    async with Client(server) as mcp:
        listed = {t.name: t.annotations for t in await mcp.list_tools()}
    assert len(listed) == 28
    assert {name for name, a in listed.items() if not a.read_only_hint} == WRITE_TOOLS
    assert {name for name, a in listed.items() if a.destructive_hint} == {"disqualify_candidate", "untag_candidate"}


async def test_unconfigured_server_answers_with_setup_instructions(monkeypatch):
    monkeypatch.delenv("RECRUITEE_COMPANY_ID", raising=False)
    monkeypatch.delenv("RECRUITEE_API_TOKEN", raising=False)

    async with Client(create_server()) as mcp:
        assert len(await mcp.list_tools()) == 28
        with pytest.raises(ToolError, match="Recruitee is not connected yet.*RECRUITEE_COMPANY_ID"):
            await mcp.call_tool("list_jobs", {})


async def test_list_jobs_defaults_to_open_jobs_and_skips_talent_pools(call, recruitee):
    recruitee.routes[("GET", "/offers")] = {
        "offers": [
            {"id": 10, "title": "Backend Engineer", "kind": "job", "status": "published", "description": "long"},
            {"id": 11, "title": "Pool", "kind": "talent_pool"},
        ]
    }

    result = await call("list_jobs", {})

    assert result["jobs"] == [{"id": 10, "title": "Backend Engineer", "status": "published"}]
    assert recruitee.sent("GET", "/offers").url.params.get_list("statuses[]") == ["published", "internal"]


async def test_get_job_reads_html_as_text_and_orders_stages(call, recruitee):
    recruitee.routes[("GET", "/offers/10")] = OFFER

    result = await call("get_job", {"job_id": 10})

    assert result["description"] == "Build APIs.\n\n- Python\n- Postgres"
    assert [s["name"] for s in result["stages"]] == ["Applied", "Interview", "Hired"]
    assert result["salary"]["currency"] == "EUR"


async def test_list_pipeline_groups_candidates_by_stage(call, recruitee):
    recruitee.routes[("GET", "/offers/10")] = OFFER
    recruitee.routes[("GET", "/offers/10/placements")] = {
        "placements": [
            {"id": 50, "candidate_id": 5, "stage_id": 1, "candidate": {"name": "Joost"}},
            {"id": 51, "candidate_id": 6, "stage_id": 2, "candidate": {"name": "Eva"}, "overdue_at": "2026-10-20"},
            {"id": 52, "candidate_id": 7, "stage_id": 2, "candidate": {"name": "Kim"}},
        ]
    }

    result = await call("list_pipeline", {"job_id": 10})

    counts = {s["name"]: s["count"] for s in result["stages"]}
    assert counts == {"Applied": 1, "Interview": 2, "Hired": 0}
    assert result["stages"][1]["candidates"][0] == {
        "candidate_id": 6,
        "name": "Eva",
        "placement_id": 51,
        "overdue_at": "2026-10-20",
    }
    assert recruitee.sent("GET", "/offers/10/placements").url.params["qualified"] == "true"


async def test_list_pipeline_filters_one_stage_by_name(call, recruitee):
    recruitee.routes[("GET", "/offers/10")] = OFFER
    recruitee.routes[("GET", "/offers/10/placements")] = {"placements": []}

    result = await call("list_pipeline", {"job_id": 10, "stage": "interview"})

    assert [s["name"] for s in result["stages"]] == ["Interview"]
    assert recruitee.sent("GET", "/offers/10/placements").url.params["stage_id"] == "2"


async def test_search_candidates_maps_filters(call, recruitee):
    recruitee.routes[("GET", "/candidates")] = {
        "references": CANDIDATE["references"],
        "candidates": [CANDIDATE["candidate"]],
    }

    result = await call("search_candidates", {"query": "joost", "job_id": 10, "status": "qualified", "limit": 1})

    params = recruitee.sent("GET", "/candidates").url.params
    assert (params["query"], params["offer_id"], params["qualified"], params["limit"]) == ("joost", "10", "true", "1")
    assert "disqualified" not in params
    candidate = result["candidates"][0]
    assert candidate["tags"] == ["python"]
    assert candidate["placements"] == [
        {"placement_id": 50, "offer_id": 10, "stage_id": 1, "stage": "Applied", "job": "Backend Engineer",
         "created_at": "2026-10-01T09:00:00Z"}
    ]  # fmt: skip
    assert result["has_more"] is True


async def test_filter_candidates_builds_filter_groups_and_resolves_tag_names(call, recruitee):
    recruitee.routes[("GET", "/tags")] = {"tags": [{"id": 4, "name": "Python"}, {"id": 9, "name": "Senior"}]}
    recruitee.routes[("GET", "/search/new/candidates")] = {"total": 1, "hits": [{"id": 5, "name": "Joost"}]}

    result = await call("filter_candidates", {"skills": ["django"], "tags": ["senior"], "min_rating": 4})

    filters = json.loads(recruitee.sent("GET", "/search/new/candidates").url.params["filters_json"])
    assert filters == [
        {"filter": "skills", "text": {"contains": ["django"]}},
        {"filter": "tags", "id": {"all_in": [9]}},
        {"field": "rating", "gte": 4},
    ]
    assert result == {"total": 1, "candidates": [{"id": 5, "name": "Joost"}], "page": 1, "has_more": False}


async def test_unknown_tag_lists_the_choices(call, recruitee):
    recruitee.routes[("GET", "/tags")] = {"tags": [{"id": 4, "name": "Python"}]}

    with pytest.raises(ToolError, match=r"No tag 'rust'. Choices: Python \(4\)"):
        await call("filter_candidates", {"tags": ["rust"]})


async def test_get_candidate_keeps_what_matters(call, recruitee):
    recruitee.routes[("GET", "/candidates/5")] = CANDIDATE

    result = await call("get_candidate", {"candidate_id": 5})

    assert result["sources"] == ["LinkedIn"]
    assert result["profile"] == {"experience": [{"title": "Developer", "company": "Bol"}]}
    assert result["placements"][0]["job"] == "Backend Engineer"
    assert result["has_cv"] is True
    assert "photo_thumb_url" not in result


async def test_create_candidate_adds_to_job_pool_and_tags(call, recruitee):
    recruitee.routes[("POST", "/candidates")] = {"candidate": {"id": 8, "name": "Eva", "duplicates": [3]}}
    recruitee.routes[("POST", "/placements")] = {"placement": {"id": 80}}
    recruitee.routes[("POST", "/candidates/8/tags")] = {"tags": [{"name": "referral"}]}

    result = await call(
        "create_candidate",
        {"name": "Eva", "emails": ["eva@example.com"], "job_id": 10, "talent_pool_id": 20, "tags": ["referral"]},
    )

    assert recruitee.body("POST", "/candidates") == {
        "candidate": {"name": "Eva", "emails": ["eva@example.com"]},
        "offers": [10],
    }
    assert recruitee.body("POST", "/placements") == {"candidate_id": 8, "talent_pool_id": 20}
    assert recruitee.body("POST", "/candidates/8/tags") == {"tags": ["referral"]}
    assert result == {"candidate_id": 8, "name": "Eva", "possible_duplicates": [3]}


async def test_update_candidate_needs_a_change(call, recruitee):
    with pytest.raises(ToolError, match="Nothing to change"):
        await call("update_candidate", {"candidate_id": 5})
    assert recruitee.requests == []


async def test_move_candidate_finds_the_placement_and_stage(call, recruitee):
    recruitee.routes[("GET", "/candidates/5")] = CANDIDATE
    recruitee.routes[("GET", "/offers/10")] = OFFER
    recruitee.routes[("PATCH", "/placements/50/change_stage")] = {"placement": {"id": 50, "stage_id": 2}}

    result = await call("move_candidate", {"candidate_id": 5, "job_id": 10, "stage": "Interview"})

    assert recruitee.body("PATCH", "/placements/50/change_stage") == {
        "stage_id": 2,
        "proceed": True,
        "run_actions": False,
    }
    assert result == {
        "candidate_id": 5,
        "job": "Backend Engineer",
        "from_stage": "Applied",
        "to_stage": "Interview",
        "automations_ran": False,
    }


async def test_move_candidate_outside_the_job_says_so(call, recruitee):
    recruitee.routes[("GET", "/candidates/5")] = CANDIDATE

    with pytest.raises(ToolError, match="not in job 99; they are in jobs 10"):
        await call("move_candidate", {"candidate_id": 5, "job_id": 99, "stage": "Interview"})


async def test_disqualify_candidate_resolves_the_reason(call, recruitee):
    recruitee.routes[("GET", "/candidates/5")] = CANDIDATE
    recruitee.routes[("GET", "/disqualify_reasons")] = {
        "disqualify_reasons": [
            {"id": 1, "name": "Not a fit", "action_templates": [{"kind": "email"}]},
            {"id": 2, "name": "Withdrew"},
        ]
    }
    recruitee.routes[("PATCH", "/placements/50/disqualify")] = {"placement": {"id": 50}}

    result = await call("disqualify_candidate", {"candidate_id": 5, "job_id": 10, "reason": "not a fit"})

    assert recruitee.body("PATCH", "/placements/50/disqualify") == {"disqualify_reason_id": 1}
    assert result["reason_automations"] == ["email"]


async def test_add_note_sends_rich_text(call, recruitee):
    recruitee.routes[("POST", "/candidates/5/notes")] = {"note": {"id": 70, "created_at": "2026-10-25T10:00:00Z"}}

    result = await call("add_note", {"candidate_id": 5, "text": "Strong on SQL", "job_id": 10})

    note = recruitee.body("POST", "/candidates/5/notes")["note"]
    assert note["body_json"]["doc"]["content"][0]["content"][0]["text"] == "Strong on SQL"
    assert note["offer_id"] == 10
    assert result == {"note_id": 70, "created_at": "2026-10-25T10:00:00Z"}


async def test_list_candidate_notes_names_the_author(call, recruitee):
    recruitee.routes[("GET", "/candidates/5/notes")] = {
        "references": [ADMIN],
        "notes": [
            {"id": 1, "admin_id": 7, "body_html": "<p>Old</p>", "created_at": "2026-10-01"},
            {"id": 2, "admin_id": 7, "text": "New", "created_at": "2026-10-20", "offer_id": 10},
        ],
    }

    result = await call("list_candidate_notes", {"candidate_id": 5})

    assert result["notes"][0] == {
        "id": 2,
        "author": "Sanne de Vries",
        "text": "New",
        "job_id": 10,
        "created_at": "2026-10-20",
    }
    assert result["notes"][1]["text"] == "Old"


async def test_evaluations_combine_scorecards_and_summary(call, recruitee):
    recruitee.routes[("GET", "/interview/results")] = {
        "references": [ADMIN],
        "meta": {"counters": {"pending": 1}},
        "interview_results": [
            {"id": 3, "admin_id": 7, "offer_id": 10, "rating": 4, "interview_template_name": "Tech",
             "rating_note": "Good"},
            {"id": 4, "admin_id": 7, "offer_id": 11, "rating": 2},
        ],
    }  # fmt: skip
    recruitee.routes[("GET", "/interview/candidates/5/results/aggregated")] = {
        "aggregated_results": {"summary": {"score": 80, "reviewers_count": 1}}
    }

    result = await call("get_candidate_evaluations", {"candidate_id": 5, "job_id": 10})

    assert result["evaluations"] == [
        {"id": 3, "form": "Tech", "reviewer": "Sanne de Vries", "job_id": 10, "rating": 4, "note": "Good"}
    ]
    assert result["summary"] == {"score": 80, "reviewers_count": 1}
    assert result["pending_requests"] == 1


async def test_create_task_adds_the_timezone_to_a_due_date(call, recruitee):
    recruitee.routes[("POST", "/tasks")] = {"references": [ADMIN], "task": {"id": 9, "title": "Call", "admin_ids": [7]}}

    result = await call("create_task", {"title": "Call", "candidate_id": 5, "due": "2026-10-30", "assignee_ids": [7]})

    assert recruitee.body("POST", "/tasks") == {
        "task": {
            "title": "Call",
            "candidate_id": 5,
            "admin_ids": [7],
            "due_date": "2026-10-30",
            "timezone": "Europe/Amsterdam",
        }
    }
    assert result == {"id": 9, "title": "Call", "assignees": ["Sanne de Vries"]}


async def test_list_tasks_maps_status_and_scope(call, recruitee):
    recruitee.routes[("GET", "/tasks")] = {"tasks": []}

    await call("list_tasks", {"assigned": "me"})

    params = recruitee.sent("GET", "/tasks").url.params
    assert (params["status"], params["scope"], params["sort_by"]) == ("uncompleted", "my", "due_date")


async def test_list_interviews_names_candidate_and_interviewers(call, recruitee):
    recruitee.routes[("GET", "/interview/events")] = {
        "meta": {"total_count": 1},
        "references": [ADMIN, {"id": 5, "type": "Candidate", "name": "Joost"}],
        "interview_events": [
            {"id": 1, "kind": "video", "candidate_id": 5, "admin_ids": [7], "starts_at": "2026-10-28T10:00:00Z"}
        ],
    }

    result = await call("list_interviews", {"start_date": "2026-10-27"})

    assert result["interviews"][0]["candidate"] == "Joost"
    assert result["interviews"][0]["interviewers"] == ["Sanne de Vries"]
    params = recruitee.sent("GET", "/interview/events").url.params
    assert (params["status"], params["timezone"]) == ("upcoming", "Europe/Amsterdam")


async def test_list_team_members_joins_admin_details(call, recruitee):
    recruitee.routes[("GET", "/memberships")] = {
        "references": [ADMIN],
        "memberships": [{"admin_id": 7, "role": "admin", "is_recruiter": True, "is_active": True}],
    }

    result = await call("list_team_members", {})

    assert result["members"] == [
        {"id": 7, "name": "Sanne de Vries", "email": "sanne@acme.nl", "role": "admin", "is_recruiter": True,
         "active": True}
    ]  # fmt: skip


async def test_list_reference_data_filters_by_name(call, recruitee):
    recruitee.routes[("GET", "/disqualify_reasons")] = {
        "disqualify_reasons": [{"id": 1, "name": "Not a fit", "position": 1}, {"id": 2, "name": "Withdrew"}]
    }

    result = await call("list_reference_data", {"kind": "disqualify_reasons", "query": "fit"})

    assert result == {"disqualify_reasons": [{"id": 1, "name": "Not a fit"}]}
