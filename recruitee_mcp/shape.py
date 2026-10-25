"""Turns Recruitee's responses into what an agent needs to read. Recruitee answers with the full
record plus a `references` list of related records (admins, offers, stages, placements); these
helpers keep the fields worth reading and put names next to the IDs."""

from html.parser import HTMLParser
from typing import Any

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "blockquote"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.parts.append("\n- ")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS and tag != "li":
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def text(html: str | None) -> str | None:
    """Plain text from Recruitee's HTML fields (job descriptions, notes, emails)."""
    if not html:
        return None
    parser = _Text()
    parser.feed(html)
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip() or None


def doc(plain: str) -> dict:
    """Recruitee's rich-text JSON for a note: one paragraph per line."""
    paragraphs = [
        {"type": "paragraph", "content": [{"type": "text", "text": line}]} if line else {"type": "paragraph"}
        for line in plain.strip().splitlines()
    ]
    return {"doc": {"type": "doc", "content": paragraphs}}


class References:
    """Lookup over a response's `references`, keyed by type and ID."""

    def __init__(self, data: dict | None):
        self._by_key: dict[tuple[str, Any], dict] = {}
        for ref in (data or {}).get("references") or []:
            if isinstance(ref, dict) and "type" in ref:
                self._by_key[(ref["type"], ref.get("id"))] = ref

    def get(self, kind: str, ref_id: Any) -> dict | None:
        return self._by_key.get((kind, ref_id))

    def admin_name(self, admin_id: Any) -> str | None:
        admin = self.get("Admin", admin_id)
        return person_name(admin) if admin else None


def person_name(admin: dict) -> str | None:
    name = " ".join(p for p in (admin.get("first_name"), admin.get("last_name")) if p)
    return name or admin.get("name") or admin.get("email")


def compact(record: dict) -> dict:
    """Drops empty values, so a sparse record doesn't read as a wall of nulls."""
    return {k: v for k, v in record.items() if v not in (None, "", [], {})}


def pick(record: dict, fields: list[str]) -> dict:
    return compact({f: record.get(f) for f in fields})


def placement(p: dict, refs: References | None = None, stages: dict[int, dict] | None = None) -> dict:
    """A candidate's place in one job or talent pool."""
    out = pick(
        p,
        [
            "id",
            "offer_id",
            "talent_pool_id",
            "stage_id",
            "status",
            "disqualify_reason",
            "created_at",
            "updated_at",
            "hired_at",
            "job_starts_at",
            "overdue_at",
            "positive_ratings",
        ],
    )
    out["placement_id"] = out.pop("id", None)
    stage = (stages or {}).get(p.get("stage_id")) or (refs.get("Stage", p.get("stage_id")) if refs else None)
    if stage:
        out["stage"] = stage.get("name")
    if refs:
        offer = refs.get("Offer", p.get("offer_id"))
        if offer:
            out["job"] = offer.get("title")
    if p.get("disqualified_at") or p.get("disqualify_reason_id"):
        out["disqualified"] = True
    return compact(out)


CANDIDATE_FIELDS = [
    "id",
    "name",
    "title",
    "emails",
    "phones",
    "links",
    "social_links",
    "source",
    "sources",
    "referrer",
    "created_at",
    "updated_at",
    "last_activity_at",
    "is_hired",
    "positive_ratings",
    "ratings_count",
    "notes_count",
    "tasks_count",
    "attachments_count",
    "has_cover_letter",
    "gdpr_status",
    "gdpr_expires_at",
    "adminapp_url",
]


def candidate_summary(c: dict, refs: References | None = None) -> dict:
    out = pick(c, ["id", "name", "title", "emails", "phones", "created_at", "last_activity_at", "positive_ratings"])
    tags = tag_names(c.get("tags"))
    if tags:
        out["tags"] = tags
    if c.get("placements"):
        out["placements"] = [placement(p, refs) for p in c["placements"]]
    return out


def tag_names(tags: Any) -> list[str]:
    return [t["name"] if isinstance(t, dict) else str(t) for t in tags or []]


def candidate_detail(c: dict, refs: References) -> dict:
    out = pick(c, CANDIDATE_FIELDS)
    if "tags" in c:
        out["tags"] = tag_names(c.get("tags"))
    out["sources"] = [s["name"] if isinstance(s, dict) else s for s in c.get("sources") or []]
    out["placements"] = [placement(p, refs) for p in c.get("placements") or []]
    if c.get("cover_letter"):
        out["cover_letter"] = text(c["cover_letter"]) or c["cover_letter"]
    profile = _profile_fields(c.get("fields") or [])
    if profile:
        out["profile"] = profile
    custom = _custom_fields(c.get("custom_fields") or [])
    if custom:
        out["custom_fields"] = custom
    answers = [
        compact({"question": a.get("title") or a.get("question"), "answer": a.get("content") or a.get("answer")})
        for a in c.get("open_question_answers") or []
        if isinstance(a, dict)
    ]
    if answers:
        out["screening_answers"] = answers
    if c.get("cv_url"):
        out["has_cv"] = True
    return compact(out)


def _profile_fields(fields: list[dict]) -> dict:
    """Experience, education, skills and languages from the CV parser or manual entry."""
    out: dict[str, list] = {}
    for field in fields:
        values = [compact(v) if isinstance(v, dict) else v for v in field.get("values") or []]
        if field.get("visible", True) and values:
            out.setdefault(field.get("kind") or "other", []).extend(values)
    return out


def _custom_fields(fields: list[dict]) -> dict:
    out: dict[str, Any] = {}
    for field in fields:
        name = field.get("name") or field.get("kind")
        values = field.get("values")
        if name and values:
            flat = [v.get("text") or v.get("value") or v if isinstance(v, dict) else v for v in values]
            out[name] = flat[0] if len(flat) == 1 else flat
    return out


def note(n: dict, refs: References) -> dict:
    return compact(
        {
            "id": n.get("id"),
            "author": refs.admin_name(n.get("admin_id")),
            "text": n.get("text") or text(n.get("body_html") or n.get("body")),
            "job_id": n.get("offer_id"),
            "talent_pool_id": n.get("talent_pool_id"),
            "pinned": bool(n.get("pinned_at")) or None,
            "created_at": n.get("created_at"),
            "replies": [note(r, refs) for r in n.get("replies") or [] if isinstance(r, dict)],
        }
    )


def task(t: dict, refs: References) -> dict:
    assignees = t.get("admin_ids") or ([t["admin_id"]] if t.get("admin_id") else [])
    return compact(
        {
            "id": t.get("id"),
            "title": t.get("title"),
            "description": t.get("description"),
            "candidate_id": t.get("candidate_id"),
            "due_date": t.get("due_date"),
            "completed": t.get("completed"),
            "completed_at": t.get("completed_at"),
            "assignees": [refs.admin_name(a) or a for a in assignees],
            "created_at": t.get("created_at"),
        }
    )


def interview(e: dict, refs: References) -> dict:
    return compact(
        {
            "id": e.get("id"),
            "name": e.get("custom_name") or e.get("kind"),
            "kind": e.get("kind"),
            "candidate_id": e.get("candidate_id"),
            "candidate": (refs.get("Candidate", e.get("candidate_id")) or {}).get("name"),
            "job_id": e.get("offer_id"),
            "job": (refs.get("Offer", e.get("offer_id")) or {}).get("title"),
            "stage": (refs.get("Stage", e.get("stage_id")) or {}).get("name"),
            "starts_at": e.get("starts_at"),
            "duration_minutes": e.get("duration"),
            "timezone": e.get("timezone"),
            "location": e.get("location"),
            "video_url": e.get("video_url"),
            "organizer": refs.admin_name(e.get("organizer_id") or e.get("admin_id")),
            "interviewers": [refs.admin_name(a) or a for a in e.get("admin_ids") or []],
            "note": text(e.get("note")) if e.get("note") else None,
            "rescheduled": e.get("rescheduled") or None,
        }
    )


def evaluation(r: dict, refs: References) -> dict:
    answers = []
    for a in r.get("interview_result_answers") or []:
        if not isinstance(a, dict):
            continue
        question = a.get("question") if isinstance(a.get("question"), dict) else {}
        answers.append(
            compact(
                {
                    "question": question.get("title") or a.get("title"),
                    "answer": a.get("content") or text(a.get("content_html")) or a.get("value"),
                    "score": a.get("score") or a.get("rating"),
                }
            )
        )
    return compact(
        {
            "id": r.get("id"),
            "kind": r.get("kind"),
            "form": r.get("interview_template_name"),
            "reviewer": refs.admin_name(r.get("admin_id")),
            "job_id": r.get("offer_id"),
            "stage": (refs.get("Stage", r.get("stage_id")) or {}).get("name"),
            "rating": r.get("rating"),
            "score": r.get("score"),
            "note": r.get("rating_note") or text(r.get("rating_note_html")),
            "answers": [a for a in answers if a],
            "created_at": r.get("created_at"),
        }
    )


_NOISE_SUFFIXES = ("_json", "_thumb_url", "_normal_url", "photo_url")


def slim(value: Any, depth: int = 0) -> Any:
    """Generic trim for responses without a fixed shape here (activity feeds, mail threads):
    drops empty values, rich-text JSON twins of text fields and photo URLs, and turns HTML
    fields into text."""
    if depth > 6:
        return value
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k == "references" or any(k.endswith(s) for s in _NOISE_SUFFIXES):
                continue
            if k.endswith("_html"):
                plain = k.removesuffix("_html")
                if value.get(plain) or value.get(plain + "_text"):
                    continue
                k, v = plain, text(v) if isinstance(v, str) else v
            v = slim(v, depth + 1)
            if v not in (None, "", [], {}):
                out[k] = v
        return out
    if isinstance(value, list):
        return [slim(v, depth + 1) for v in value]
    return value
