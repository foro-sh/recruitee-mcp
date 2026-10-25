import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from .config import Settings

# One wait inside a tool call is fine; a second 429 goes back to the caller.
MAX_RETRY_WAIT = 30.0

Params = dict[str, Any]


class RecruiteeError(Exception):
    pass


class RateLimitedError(RecruiteeError):
    pass


def _error_message(response: httpx.Response) -> str:
    """Recruitee answers errors as {"error": [...]} or {"errors": [{"message": ...}]}."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:300] or response.reason_phrase
    if isinstance(body, dict):
        if isinstance(body.get("error"), list) and body["error"]:
            message = "; ".join(str(e) for e in body["error"])
            fields = body.get("error_fields")
            if isinstance(fields, dict) and fields:
                message += " (" + ", ".join(f"{k}: {'; '.join(map(str, v))}" for k, v in fields.items()) + ")"
            return message
        if isinstance(body.get("errors"), list) and body["errors"]:
            return "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in body["errors"])
    return response.text[:300] or response.reason_phrase


def query(params: Params) -> list[tuple[str, str]]:
    """Query string the way Recruitee's Phoenix backend reads it: lists as `key[]=a&key[]=b`,
    booleans as `true`/`false`, and None dropped."""
    pairs: list[tuple[str, str]] = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, list | tuple):
            pairs.extend((f"{key}[]", _scalar(v)) for v in value)
        else:
            pairs.append((key, _scalar(value)))
    return pairs


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class RecruiteeClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        settings: Settings,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._http = http
        self._base_url = settings.base_url
        self._headers = {
            "Authorization": f"Bearer {settings.api_token}",
            "Accept": "application/json",
        }
        self._sleep = sleep
        self.timezone = settings.timezone

    async def get(self, path: str, params: Params | None = None) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, body: Params | None = None) -> Any:
        return await self.request("POST", path, body=body)

    async def patch(self, path: str, body: Params | None = None) -> Any:
        return await self.request("PATCH", path, body=body)

    async def delete(self, path: str, body: Params | None = None) -> Any:
        return await self.request("DELETE", path, body=body)

    async def request(self, method: str, path: str, *, params: Params | None = None, body: Params | None = None) -> Any:
        """`path` is relative to the company, e.g. `/candidates/12`."""
        for attempt in range(2):
            response = await self._http.request(
                method,
                f"{self._base_url}{path}",
                params=query(params or {}),
                json=body,
                headers=self._headers,
            )
            if response.status_code == 429:
                wait = _retry_after(response)
                if attempt == 0 and wait is not None and wait <= MAX_RETRY_WAIT:
                    await self._sleep(wait)
                    continue
                raise RateLimitedError("Recruitee's API rate limit is used up; try again in a minute.")
            if response.status_code == 401:
                raise RecruiteeError(
                    "Recruitee rejected the API token (401). Check RECRUITEE_API_TOKEN, or create a new "
                    "personal API token in Recruitee under Settings > Apps and plugins."
                )
            if response.status_code == 403:
                raise RecruiteeError(
                    "Recruitee refused this (403): the token's user lacks the permission for it, or "
                    f"RECRUITEE_COMPANY_ID is not their company. {_error_message(response)}"
                )
            if response.status_code == 404:
                raise RecruiteeError(f"Recruitee has no such record ({method} {path}).")
            if response.is_error:
                raise RecruiteeError(f"Recruitee returned {response.status_code}: {_error_message(response)}")
            if not response.content:
                return {}
            return response.json()
        raise AssertionError("unreachable")


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        # ponytail: no documented reset header, so assume a one-second window.
        return 1.0
    try:
        return max(float(value), 0.0)
    except ValueError:
        return None
