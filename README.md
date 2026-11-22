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
| `list_jobs` | Jobs by status, department or title, with candidate counts. Defaults to open jobs |
| `get_job` | One job: description, requirements, salary, location and its pipeline stages |
| `list_pipeline` | A job's candidates per stage, with ratings, overdue flags and upcoming interviews |
| `list_talent_pools` | Talent pools with their candidate counts |

**Candidates**

| Tool | What it does |
| --- | --- |
| `search_candidates` | By name or email, optionally within one job or status |
| `filter_candidates` | Across all jobs by skills, past titles or companies, degree, languages, tags, sources, rating and dates, plus raw Recruitee filters |
| `get_candidate` | Profile, every job they're in with stage, tags, sources, experience, education, custom fields, screening answers |
| `get_candidate_cv` | The CV's plain text and the typed cover letter |
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
| `update_candidate` | Name, headline, emails, phones | Emails and phones replace the whole list |
| `add_candidate_to_job` | Puts an existing candidate in a job or talent pool | |
| `move_candidate` | Moves to a stage, given by name or ID | Stage automations (which can email the candidate) only run with `run_automations=true` |
| `disqualify_candidate` | Rejects in one job with a reason, given by name or ID | The reason's own automations, such as a rejection email, run |
| `requalify_candidate` | Undoes a disqualification | |
| `add_note` | Adds a note, optionally filed under a job | Visible to the whole team |
| `tag_candidate` / `untag_candidate` | Adds or removes tags; new names create the tag | |
| `create_task` / `complete_task` | Creates a to-do, or marks it done or reopens it | Recruitee notifies the assignees |

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

```sh
uv sync
export RECRUITEE_COMPANY_ID=... RECRUITEE_API_TOKEN=...
uv run python server.py           # streamable HTTP on :8000/mcp
```

## Development

```sh
uv sync
uv run pytest
uv run ruff format . && uv run ruff check .
./smoke.sh   # starts without credentials and lists every tool
```

`foro-tools.json` is what foro's blueprint page reads from the latest release: each tool's label and
whether it changes something, which keeps it off until it is turned on. After adding or changing a
tool, add its title to `TITLES` in `recruitee_mcp/tools/__init__.py` and run
`uv run python -m recruitee_mcp.manifest`; a test fails while the file is stale.

Releases are cut by semantic-release from Conventional Commits on `main`.

The layout:

- `recruitee_mcp/client.py`: the HTTP client, with auth, errors and rate-limit handling.
- `recruitee_mcp/shape.py`: trims Recruitee's large responses down to what an agent reads.
- `recruitee_mcp/tools/`: one module per area.
- `recruitee_mcp/manifest.py`: writes `foro-tools.json`.
- `tests/`: tests against a fake Recruitee.

## Status: not yet run against a live Recruitee company

The tests run against response shapes from [Recruitee's API reference](https://apidocs.recruitee.com),
not a real company.

Checked against the reference:

- Every endpoint path and query parameter the tools use.
- The response keys for candidates, offers, placements, notes, tasks, interview events and results,
  memberships, tags, sources, departments, locations and disqualify reasons.
- The search filter groups in `filter_candidates`.
- The request bodies the reference gives: `{"candidate": {...}}`, `{"note": {"body_json": ...}}`,
  `{"task": {...}}` and `{"task": {"completed": ...}}`.

Still to check on a test company:

- **Auth.** The `Authorization: Bearer <token>` header. The reference doesn't document auth, so this
  comes from Recruitee's help centre.
- **Parameter placement.** Whether `change_stage`, `disqualify` and `POST /placements` take their
  parameters as a top-level JSON body, as the reference's "URI parameters" suggest.
- **Note and candidate bodies.** Whether a note accepts `offer_id`, and whether `sources` on a new
  candidate takes names.
- **Undocumented response shapes.** The shapes of `/tracking/candidates/{id}/activities`,
  `/mailbox/candidate/{id}`, `/mailbox/threads/{id}` and the `hits` in candidate search. The tools
  pass these through a generic trim rather than a fixed shape.
- **Query format.** Whether list parameters are read as `key[]=a&key[]=b`, and whether search takes
  `filters_json` on GET as the reference says.
- **Rate limits.** The reference doesn't document them. The server waits once on a 429, for
  `Retry-After` or one second, then reports the limit.
