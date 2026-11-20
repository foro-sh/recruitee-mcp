# Recruitee MCP

An [MCP](https://modelcontextprotocol.io) server for [Recruitee](https://recruitee.com), built to
deploy on [foro.sh](https://foro.sh) as a Bridge. It lets an agent read jobs, pipelines and
candidates (profiles, CVs, evaluations, notes, emails, interviews and tasks), and, once you allow
it, add candidates, move them through stages, disqualify them, and write notes, tags and tasks.

Recruitee calls a job an *offer*, and a candidate's place in one job a *placement*. The tools say
*job* and take `candidate_id` plus `job_id`; they find the placement themselves.

## Tools

28 tools: 17 reads and 11 writes. On foro, reads are on and writes are off when you set the Bridge
up, and anything you switch off is blocked at foro's gate.

**Jobs**

| Tool | What it does |
| --- | --- |
| `list_jobs` | Jobs by status, department or title. Defaults to open jobs. Counts and location are in `get_job` |
| `get_job` | One job: description, requirements, salary, location and its pipeline stages |
| `list_pipeline` | A job's candidates per stage, with ratings, overdue flags and upcoming interviews |
| `list_talent_pools` | Talent pools with their candidate counts |

**Candidates**

| Tool | What it does |
| --- | --- |
| `search_candidates` | By name or email, optionally within one job or status |
| `filter_candidates` | Across all jobs by skills, past titles or companies, degree, languages, tags, sources, rating and dates, plus raw Recruitee filters |
| `get_candidate` | Profile, every job they're in with stage, tags, sources, experience, education, custom fields, screening answers |
| `get_candidate_cv` | The CV's plain text and the typed cover letter. When Recruitee hasn't parsed the CV, the text is read from its PDF |
| `list_candidate_notes` | The team's notes, with author and replies |
| `get_candidate_evaluations` | Scorecards and questionnaires per reviewer, plus Recruitee's summary score |
| `get_candidate_activity` | The candidate's timeline |
| `list_candidate_emails` / `get_email_thread` | Mailbox threads with the candidate; one thread's messages |

**Scheduling and team**

| Tool | What it does |
| --- | --- |
| `list_interviews` | Upcoming or past interviews, by candidate, interviewer or date range |
| `list_tasks` | Open or completed tasks, by candidate or assignee |
| `list_team_members` | Team members with role, recruiter and hiring-manager flags |
| `list_reference_data` | Tags, sources, departments, locations or disqualify reasons, with IDs |

**Writes**

| Tool | What it does | Watch out |
| --- | --- | --- |
| `create_candidate` | Adds a candidate, optionally to a job, a talent pool and with tags | Reports possible duplicates |
| `update_candidate` | Name, emails, phones | Emails and phones replace the whole list |
| `add_candidate_to_job` | Puts an existing candidate in a job or talent pool | |
| `move_candidate` | Moves to a stage, given by name or ID | Stage automations (which can email the candidate) only run with `run_automations=true` |
| `disqualify_candidate` | Rejects in one job with a reason, given by name or ID | The reason's own automations, such as a rejection email, run |
| `requalify_candidate` | Undoes a disqualification | |
| `add_note` | Adds a note to the candidate | Visible to the whole team |
| `tag_candidate` / `untag_candidate` | Adds or removes tags; new names create the tag | |
| `create_task` / `complete_task` | Creates a to-do, or marks it done or reopens it. A due date alone means 17:00 | Recruitee notifies the assignees |

### Left out on purpose

The Recruitee API has about 900 endpoints, and most of them run the Recruitee web app: billing,
SSO, careers-site layout, pipeline and form templates, translations, requisition approval flows,
bulk actions and GDPR deletion. They are left out because a recruiter rarely asks an agent for them
and a wrong call is costly. A few more could come later:

- **Sending email and scheduling interviews.** Both reach the candidate directly, and Recruitee's
  docs don't spell out the request body (the recipient format for `/mailbox/send`, the event body for
  `/interview/candidates/{id}/events`). Add them once they have been tried on a test company.
- **Creating, publishing and closing jobs.** These are admin work, usually done in Recruitee itself.
- **Deleting candidates.** Never exposed, because it can't be undone.

To add one, put a function in the matching module in `recruitee_mcp/tools/` and a test next to the
others in `tests/test_tools.py`.

## Setup

**1. Create a personal API token.** In Recruitee, open *Settings* → *Apps and plugins* →
*Personal API tokens* and create a token. The token acts as you, so the server can see and do what
your Recruitee user can. For a narrower scope, create the token as a Recruitee user with a narrower
role. The company ID is on the same page.

**2. Deploy on foro.** Set up the Recruitee Bridge, or fork this repo into your workspace. Then add
these secrets in the project's dashboard and redeploy:

| Secret | Value |
| --- | --- |
| `RECRUITEE_COMPANY_ID` | Your company ID, a number |
| `RECRUITEE_API_TOKEN` | The token from step 1 |
| `RECRUITEE_TIMEZONE` | Optional: the timezone for task due dates and interview date ranges. Default `Europe/Amsterdam` |

Until the secrets are set, the server still deploys, and every tool answers with the list of
missing secrets.

**Run it locally:**

Put the secrets in a `.env` file in the repo (git ignores it), then:

```sh
uv sync
uv run --env-file .env python server.py   # streamable HTTP on :8000/mcp
```

## Development

```sh
uv sync
uv run pytest
uv run ruff format . && uv run ruff check .
```

The layout:

- `recruitee_mcp/client.py`: the HTTP client, with auth, errors and rate-limit handling.
- `recruitee_mcp/shape.py`: trims Recruitee's large responses down to what an agent reads.
- `recruitee_mcp/tools/`: one module per area.
- `tests/`: tests against a fake Recruitee.

## Status: tested against a live Recruitee trial company

Every tool was run on a Recruitee trial company with its sample data on 2026-11-20. Where the live
API differed from the reference, the code follows what was seen, with a "Seen live" comment, and
the tests use the live shape.

Confirmed live:

- **Auth.** `Authorization: Bearer <token>` with a personal API token.
- **Request bodies.** `change_stage`, `disqualify` and `POST /placements` take top-level JSON;
  a new candidate's `sources` takes names; list parameters are read as `key[]=a&key[]=b`; search
  takes `filters_json` on GET.
- **Pipeline.** `/offers/{id}/placements` groups placements per stage (`stages[].placements`), but
  returns a flat `placements` list when filtered by `stage_id`.
- **Search hits** nest the `offer` and `stage` objects in each placement.
- **Evaluations** use flat `question_title` keys, keep rating scores in `scores`, and put HTML in
  `rating_note`.
- **Mail threads** carry each body in several HTML variants; the tools keep one.
- **Task due dates** must include a time, and a time without an offset is read as UTC whatever
  `timezone` says, so the tool sends an offset-aware time in `RECRUITEE_TIMEZONE`.
- **Tag endpoints** answer with the tags in the request, not all of the candidate's tags.
- **CV text.** Recruitee left `cv_text` empty for every sample CV, but `cv_url` always links to a
  PDF version of the CV, Word files included. When `cv_text` is empty, `get_candidate_cv` downloads
  that PDF (without the API token) and reads its text layer with pypdf. That worked for all 14
  sample CVs, in 0.1 to 0.3 seconds each.

Found not to work, so left out:

- **Notes per job.** A candidate note can't be filed under a job: `offer_id` inside `note` is
  ignored, and at the top level of the body it creates a note on the job itself, detached from the
  candidate. `add_note` has no `job_id`.
- **Candidate title.** `PATCH /candidates/{id}` answers 422 "Title is invalid" to any `title`.

Still to check:

- **Interviews.** The trial has no interview events, so `list_interviews` has only returned empty.
- **Scanned and two-column CVs.** A scan has no text layer and there is no OCR, so
  `get_candidate_cv` returns the signed PDF link (valid about 10 hours) instead. A two-column CV
  comes out with both columns on one line. Neither showed up in the sample CVs; check how often
  they occur in real ones.
- **Rate limits.** Not hit during testing. The server waits once on a 429, for `Retry-After` or one
  second, then reports the limit.
- **Talent pool counts.** `/talent_pools` reported `candidates_count: 0` for a pool with candidates.
  That's Recruitee's own number, passed through as is.
