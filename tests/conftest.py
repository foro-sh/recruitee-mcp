import json
from collections.abc import Callable

import httpx
import pytest
from fastmcp import Client, FastMCP

from recruitee_mcp import tools
from recruitee_mcp.client import RecruiteeClient
from recruitee_mcp.config import load_settings

ENV = {"RECRUITEE_COMPANY_ID": "123", "RECRUITEE_API_TOKEN": "token-1"}
BASE = "/c/123"


class FakeRecruitee:
    """Answers `(method, path)` with the JSON a test set in `routes`, and records every request.
    Paths are relative to the company, e.g. `/candidates/5`."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.routes: dict[tuple[str, str], dict | Callable[[httpx.Request], httpx.Response]] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get((request.method, request.url.path.removeprefix(BASE)))
        if route is None:
            return httpx.Response(404, json={"error": ["Page not found"]})
        return route(request) if callable(route) else httpx.Response(200, json=route)

    def http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self))

    def sent(self, method: str, path: str) -> httpx.Request:
        for request in self.requests:
            if request.method == method and request.url.path == BASE + path:
                return request
        raise AssertionError(f"no {method} {path} in {[(r.method, r.url.path) for r in self.requests]}")

    def body(self, method: str, path: str) -> dict:
        return json.loads(self.sent(method, path).content)


@pytest.fixture
def recruitee():
    return FakeRecruitee()


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def client(recruitee, sleeps):
    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    return RecruiteeClient(recruitee.http(), load_settings(ENV), sleep=sleep)


@pytest.fixture
def server(client):
    async def get_client():
        return client

    mcp = FastMCP("test")
    tools.register(mcp, get_client)
    return mcp


@pytest.fixture
def call(server):
    async def call(name, args=None):
        async with Client(server) as mcp:
            return (await mcp.call_tool(name, args or {})).structured_content

    return call


ADMIN = {"id": 7, "type": "Admin", "first_name": "Sanne", "last_name": "de Vries", "email": "sanne@acme.nl"}

OFFER = {
    "offer": {
        "id": 10,
        "title": "Backend Engineer",
        "status": "published",
        "kind": "job",
        "description_html": "<p>Build <b>APIs</b>.</p><ul><li>Python</li><li>Postgres</li></ul>",
        "salary": {"min": 4000, "max": 5500, "currency": "EUR", "period": "month"},
        "pipeline_template": {
            "stages": [
                {"id": 2, "name": "Interview", "position": 2, "group": "interview"},
                {"id": 1, "name": "Applied", "position": 1, "group": "applicants"},
                {"id": 3, "name": "Hired", "position": 3, "group": "hires", "category": "hire"},
            ]
        },
    }
}

CANDIDATE = {
    "references": [
        {"id": 10, "type": "Offer", "title": "Backend Engineer"},
        {"id": 1, "type": "Stage", "name": "Applied"},
    ],
    "candidate": {
        "id": 5,
        "name": "Joost Jansen",
        "emails": ["joost@example.com"],
        "phones": [],
        "tags": [{"id": 1, "name": "python"}],
        "sources": [{"name": "LinkedIn"}],
        "placements": [{"id": 50, "offer_id": 10, "stage_id": 1, "created_at": "2026-10-01T09:00:00Z"}],
        "fields": [
            {"kind": "experience", "visible": True, "values": [{"title": "Developer", "company": "Bol"}]},
            {"kind": "education", "visible": True, "values": []},
        ],
        "photo_thumb_url": "https://cdn/x.png",
        "cv_url": "https://cdn/cv.pdf",
    },
}
