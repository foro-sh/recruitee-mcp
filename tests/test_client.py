import httpx
import pytest

from recruitee_mcp.client import RateLimitedError, RecruiteeError, query
from recruitee_mcp.config import ConfigError, load_settings


async def test_sends_the_bearer_token_to_the_company_path(client, recruitee):
    recruitee.routes[("GET", "/offers")] = {"offers": []}

    await client.get("/offers", {"statuses": ["published", "internal"], "limit": 5, "page": None})

    request = recruitee.requests[0]
    assert str(request.url).startswith("https://api.recruitee.com/c/123/offers?")
    assert request.headers["Authorization"] == "Bearer token-1"
    assert request.url.params.get_list("statuses[]") == ["published", "internal"]
    assert "page" not in request.url.params


def test_query_spells_booleans_like_phoenix():
    assert query({"qualified": True, "deleted": False, "x": None}) == [("qualified", "true"), ("deleted", "false")]


async def test_waits_out_one_rate_limit_then_retries(client, recruitee, sleeps):
    answers = iter([httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(200, json={"ok": True})])
    recruitee.routes[("GET", "/tags")] = lambda r: next(answers)

    assert await client.get("/tags") == {"ok": True}
    assert sleeps == [2.0]


async def test_a_second_rate_limit_is_an_error(client, recruitee):
    recruitee.routes[("GET", "/tags")] = lambda r: httpx.Response(429)

    with pytest.raises(RateLimitedError):
        await client.get("/tags")


async def test_errors_carry_recruitees_message(client, recruitee):
    recruitee.routes[("POST", "/tasks")] = lambda r: httpx.Response(
        422, json={"error": ["Invalid task"], "error_fields": {"title": ["can't be blank"]}}
    )

    with pytest.raises(RecruiteeError, match=r"422: Invalid task \(title: can't be blank\)"):
        await client.post("/tasks", {"task": {}})


async def test_bad_token_says_where_to_get_a_new_one(client, recruitee):
    recruitee.routes[("GET", "/tags")] = lambda r: httpx.Response(401)

    with pytest.raises(RecruiteeError, match="Personal API|personal API token"):
        await client.get("/tags")


async def test_empty_body_is_an_empty_dict(client, recruitee):
    recruitee.routes[("POST", "/candidates/5/tags")] = lambda r: httpx.Response(200)

    assert await client.post("/candidates/5/tags", {"tags": ["x"]}) == {}


def test_missing_secrets_are_named():
    with pytest.raises(ConfigError, match="RECRUITEE_COMPANY_ID, RECRUITEE_API_TOKEN"):
        load_settings({})


def test_company_id_must_be_a_number():
    with pytest.raises(ConfigError, match="must be a number"):
        load_settings({"RECRUITEE_COMPANY_ID": "acme", "RECRUITEE_API_TOKEN": "t"})


def test_timezone_defaults_to_amsterdam():
    settings = load_settings({"RECRUITEE_COMPANY_ID": " 42 ", "RECRUITEE_API_TOKEN": "t"})
    assert settings.base_url == "https://api.recruitee.com/c/42"
    assert settings.timezone == "Europe/Amsterdam"
