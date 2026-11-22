from recruitee_mcp.manifest import PATH, manifest, render

WRITES = {
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


async def test_committed_manifest_is_current():
    assert PATH.read_text() == render(await manifest()), "run: uv run python -m recruitee_mcp.manifest"


async def test_every_tool_that_changes_something_is_a_write():
    tools = (await manifest())["tools"]
    assert {t["name"] for t in tools if t["writes"]} == WRITES
    assert all(t["label"] and t["description"] for t in tools)
