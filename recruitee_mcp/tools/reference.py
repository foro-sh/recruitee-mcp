from typing import Annotated, Literal

from pydantic import Field

from .. import shape

# kind -> (path, response key, fields worth returning)
REFERENCE_DATA = {
    "tags": ("/tags", "tags", ["id", "name", "taggings_count"]),
    "sources": ("/sources", "sources", ["id", "name", "taggings_count"]),
    "departments": ("/departments", "departments", ["id", "name", "status", "offers_count", "talent_pools_count"]),
    "locations": ("/locations", "locations", ["id", "name", "full_address", "city", "country_code", "archived_at"]),
    "disqualify_reasons": ("/disqualify_reasons", "disqualify_reasons", ["id", "name"]),
}


def register(tool, get_client) -> None:
    @tool()
    async def list_team_members(
        query: Annotated[str | None, Field(description="Part of a name or email.")] = None,
    ) -> dict:
        """People on the Recruitee team with their role and whether they recruit or hire. Use their IDs
        to assign tasks or filter interviews."""
        client = await get_client()
        data = await client.get("/memberships", {"query": query, "limit": 500})
        refs = shape.References(data)
        members = []
        for m in data.get("memberships") or []:
            admin = refs.get("Admin", m.get("admin_id")) or {}
            role = m.get("role")
            members.append(
                shape.compact(
                    {
                        "id": m.get("admin_id"),
                        "name": shape.person_name(admin) if admin else None,
                        "email": admin.get("email"),
                        "role": role.get("name") if isinstance(role, dict) else role,
                        "is_recruiter": m.get("is_recruiter") or None,
                        "is_hiring_manager": m.get("is_hiring_manager") or None,
                        "active": m.get("is_active"),
                    }
                )
            )
        return {"members": members}

    @tool()
    async def list_reference_data(
        kind: Literal["tags", "sources", "departments", "locations", "disqualify_reasons"],
        query: Annotated[str | None, Field(description="Only names containing this.")] = None,
    ) -> dict:
        """The company's tags, candidate sources, departments, locations or disqualify reasons, with IDs
        for the other tools."""
        path, key, fields = REFERENCE_DATA[kind]
        client = await get_client()
        data = await client.get(path, {"limit": 1000})
        rows = [shape.pick(r, fields) for r in data.get(key) or []]
        if query:
            rows = [r for r in rows if query.lower() in str(r.get("name", "")).lower()]
        return {kind: rows}
