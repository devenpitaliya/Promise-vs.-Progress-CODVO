<div align="center">

# Promise vs. Progress

**Turn what was promised in a meeting into what is verifiably delivered.**

A closed-loop execution tracker for meeting commitments. It extracts commitments from transcripts,<br/>
creates GitHub issues for them after human review, and checks GitHub before the next meeting,<br/>
so the team starts from *what shipped* instead of a round of status questions.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)
![Database](https://img.shields.io/badge/SQLite%20%7C%20Postgres-Alembic-4169E1?logo=postgresql&logoColor=white)
![Tests](https://img.shields.io/badge/tests-157%20backend%20%C2%B7%2026%20frontend-2EA44F)

[Quick start](#-quick-start) · [Using the app](#-using-the-app-step-by-step) · [How it works](#-how-it-works) · [Architecture](docs/ARCHITECTURE.md)

</div>

---

## 💡 The idea

Meeting assistants capture action items, and then the loop stops. Nobody checks, before the next meeting,
whether the work was actually delivered, and "done" often just means *someone said so*.

```
 transcript ──▶ extract commitments ──▶ human review ──▶ GitHub issue / PR
                                                                │
 next meeting ◀── briefing (email) ◀── reconcile against GitHub ◀┘   on demand · hourly · scheduled
```

The core rule is **evidence over claims**. A commitment counts as done only when GitHub shows it: the PR is
**merged**, or the issue is **closed as completed**. If someone says "it's done" but GitHub disagrees, the app
flags it as **Claimed, unverified**, the exact gap this product exists to expose.

## ✨ Highlights

| | |
|---|---|
| 🧠 **AI extraction, grounded** | Gemini or OpenAI extracts owner, title, due date, priority (P1–P3) and ticket references. Names are matched to participants, relative dates ("by Friday") become real dates, and every commitment keeps the exact sentence it came from. Without an AI key, a transparent rule-based parser takes over. |
| 🙋 **Human in the loop** | Nothing reaches GitHub until a person approves it. Reviewers edit, reject, add missed items, or leave them for later. |
| 🔗 **Real GitHub integration** | Each user connects their own GitHub (encrypted token). Approving creates new issues or links existing ones (`Issue #45`, `PR #302`). **Two-way sync:** status changes in the app close, reopen and comment on the issue. |
| ✅ **Verification you can trust** | Reconciliation reads the real state from GitHub. A close made from the app is still only a *claim*; only a close or merge in GitHub counts as verified. |
| 📋 **Pre-meeting briefing** | An executive summary and agenda built from verified data, emailed on demand or on a schedule. |
| 🎙️ **Teams and Zoom transcripts** | Upload `.vtt` or `.srt` caption files. They're converted to clean `Name: text` lines, and the speakers become participants. |
| 🔭 **Production-minded** | One `.env` for everything, migrations, startup checks, rotating logs with request IDs, optional Langfuse tracing (tokens and cost), tenant isolation, SSRF protection, Postgres-ready, CI and Docker. |

---

## 🚀 Quick start

### Prerequisites

| You need | For |
|---|---|
| **Docker Desktop** | Option A, the fastest way to run everything |
| **Python 3.11** and **Node.js 20** | Option B, local development |
| A **Gemini** or **OpenAI** API key *(optional)* | AI extraction. Without one, a rule-based parser is used. |
| A **GitHub account** *(optional)* | Creating real issues. Without it, GitHub is simulated and clearly labelled. |

### 1. Configure (once)

All configuration lives in **one `.env` file at the repository root**, used by the backend, the frontend and Docker.

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Open `.env` and set:

```ini
SECRET_KEY=<paste the value printed above>
GEMINI_API_KEY=<optional: your Gemini key>
```

Everything else has a sensible default and is documented in [`.env.example`](.env.example).

### 2a. Run with Docker (recommended)

```bash
docker compose up --build
```

Open **http://localhost:8080**. nginx serves the web app and forwards `/api` to the backend. The database and
logs are kept in Docker volumes, and migrations run automatically on start.

### 2b. Or run locally for development

Run the **backend** and the **frontend** in two separate terminals, both from the repository root.
Both read the same root `.env` from step 1.

#### Backend: the API (terminal 1)

```bash
cd backend
python3.11 -m venv venv                  # create an isolated Python environment (first time only)
source venv/bin/activate                 # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt      # install dependencies (first time, or after they change)
python -m app                            # start the API
```

You should see the startup checks, then:

```
Promise vs. Progress Engine is ready on http://0.0.0.0:8000/api/v1
```

- The API runs on **http://localhost:8000** (`APP_PORT`), with interactive docs at **http://localhost:8000/docs**.
- The database (SQLite in `backend/data/`) is created and migrated automatically on first start.
- The API reloads by itself when you change backend code (`APP_RELOAD=true`).
- Next time, only `source venv/bin/activate` and `python -m app` are needed.

#### Frontend: the web app (terminal 2)

```bash
cd frontend
npm ci                                   # install dependencies (first time, or after they change)
npm run dev                              # start the web app
```

- Open **http://localhost:5173** (`FRONTEND_PORT`).
- Calls to `/api` are forwarded to the backend on `APP_PORT`, so the backend must be running.
- The page updates instantly when you change frontend code.
- Next time, only `npm run dev` is needed.

> ✅ With both running, open **http://localhost:5173** and continue with [Using the app](#-using-the-app-step-by-step).

### 3. Check it's running

```bash
curl http://localhost:8000/health        # {"status":"ok"}
```

On startup the backend logs a check of every dependency (`OK` / `WARN` / `SKIPPED`): configuration, database,
AI key, GitHub, email, search index and scheduler. Logs are written to the console and to `logs/`.

---

## 🧭 Using the app, step by step

### Step 1: Create an account
Open the app and **Sign up** with your name, email and a password (at least 10 characters, with a letter and a number).
If `DEMO_MODE=true` is set in `.env`, **Try a private demo workspace** creates a throwaway account in one click.

### Step 2: Add an AI key *(optional)*
**Settings → AI providers** → paste a Gemini or OpenAI key → **Test key** → **Save key**.
Your key is encrypted and only used for your workspace. Without a key, the rule-based parser handles
`Name: I will …` style transcripts.

### Step 3: Connect GitHub *(optional, but this is where it shines)*

<details>
<summary><b>Create a GitHub token (2 minutes)</b></summary>

1. On GitHub, create a repository to track work in, e.g. `pvp-demo`.
2. Go to **Profile picture → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
   (or open https://github.com/settings/personal-access-tokens/new).
3. **Repository access:** *Only select repositories* → `pvp-demo`.
4. **Permissions:** *Issues: Read and write* and *Pull requests: Read-only* (*Metadata: Read-only* is added automatically).
5. **Generate token** and copy it (`github_pat_…`). GitHub shows it only once.

</details>

Then, in the app, go to **Settings → Integrations → GitHub**:

| Field | Value |
|---|---|
| Personal access token | `github_pat_…` |
| Default owner | **your GitHub username** (the owner of your repositories, *not* a repository name) |

Click **Connect and test**. You should see ✅ *"Connected as &lt;you&gt;… Default owner '&lt;you&gt;' is a GitHub user."*

### Step 4: Add a meeting
**Meetings → New meeting**:
1. Give it a title, type, date and participants. Relative deadlines like "by Friday" are resolved from the meeting date.
2. Add the transcript in one of three ways:
   - **Paste** it, e.g.
     ```
     Maya: I'll fix the login timeout in pvp-demo by tomorrow.
     Priya: I will add input validation to the signup form in pvp-demo by Wednesday.
     ```
   - **Upload** a `.txt`, or a Teams / Zoom `.vtt` or `.srt`. Captions are converted automatically, and the speakers are added as participants.
   - **Try a sample**: *Sprint 34 standup*, *Sprint 35 planning sync* or *Platform reliability review* (all in [`samples/`](samples/)).
3. Click **Extract commitments**.

### Step 5: Review, where nothing is sent until you approve
Each card is a proposed ticket with the **quote** it came from. For each one:
- **Approve**, **Later** or **Reject**.
- Fix anything: title, owner, priority, target date, **Repository** (e.g. `pvp-demo`) and **Reference**.
  An empty reference creates a new issue; `Issue #12` or `PR #7` links an existing one.
- **Add a missed commitment** if the extraction skipped something.

Set a **Default repository** at the bottom for cards without one, then click **Save and create tickets**.
The new issues appear in your repository's **Issues** tab, with the owner, quote, priority and target date.

> 💡 The samples mention repositories and issue numbers from a fictional company. If you approve them against
> your real GitHub, use **Fix and retry** (step 8) with your repository and *Create new issues* ticked.

### Step 6: Track progress
**Commitments** is the board of everything approved. Click one to open its panel:
- **Reported status** records what the owner *says*: Open, In progress, In review, Blocked, Done or Cancelled.
- **Two-way sync** with GitHub:

  | In the app | On GitHub |
  |---|---|
  | Done | Issue closed as completed, plus a comment |
  | Cancelled | Issue closed as *not planned*, plus a comment |
  | Back to an open status | Issue reopened, plus a comment |
  | Edit the title | Issue retitled |
  | Any change on a **PR** | Comment only. PRs are never closed or merged from the app. |

- **Search** finds commitments by meaning, not just keywords.

### Step 7: Reconcile before the next meeting
**Reconciliation → Check trackers now** asks GitHub for the real state of every item. The same check also runs
hourly and before scheduled briefings. Then:
- **Needs attention:** overdue, due today, blocked or at risk. Discuss these first.
- **Claimed, unverified:** someone says it's done, but GitHub doesn't confirm it. Ask for the proof.
- **Verified done:** merged or closed as completed in GitHub.

Every row shows a risk bar and a plain-English **Why**, e.g. *"Reported done, but GitHub has not confirmed it yet."*

### Step 8: Fix problems in one click
| Banner | When | What it does |
|---|---|---|
| **Fix and retry** | Some tickets could not be created or linked (wrong repository, number doesn't exist) | Sets a repository for all failed items, optionally creates new issues instead of linking, and retries them all |
| **Sync to connected tools** | Items were approved while GitHub was simulated, and GitHub is now connected | Creates or links the real issues. Simulated evidence no longer counts. |

### Step 9: Brief the team
**Reconciliation → Briefing** → **Preview** → **Send email**. The summary and agenda come from verified data only.
**Schedules** sends it automatically, once or every day in a date range (email requires `SMTP_*` in `.env`;
otherwise briefings are saved to history but not sent).

---

## 🏷️ What each verdict means

| Verdict | Meaning |
|---|---|
| ✅ **Verified done** | GitHub confirms it: the PR is merged, or the issue was closed as completed **in GitHub**. The only "done" that counts toward completion. |
| ⚠️ **Claimed, unverified** | Someone says it's done (in the meeting, on the board, or by closing it *from the app*), but GitHub hasn't confirmed it. |
| 🔴 **Overdue** · 🟠 **Due today** | Past or at its target date, and not verified. |
| ⛔ **Blocked** | The owner reported a blocker. |
| 🟡 **At risk** | Due within 2 days with no progress, or its GitHub item was closed without being completed. |
| 🟢 **On track** · ⚪ **No deadline** | Time left before the deadline, or no date was committed. |

Each verdict comes with a risk score (0–100) and the reason behind it. It's a transparent heuristic, not a prediction.

---

## 🧩 How it works

```mermaid
flowchart LR
  UI[React SPA] -->|/api/v1| API[FastAPI]
  API --> DB[(SQLite / Postgres)]
  API --> LLM[Gemini / OpenAI]
  API --> GH[GitHub]
  API --> SMTP[Email]
  API --> VEC[(Semantic search)]
  API -.->|optional| LF[Langfuse]
  SCHED[Scheduler] --> API
```

Every request follows the same path: **router → controller → workflow → (agent → chain → LLM) or connectors, plus repositories.**

```
backend/app
├── routers/v1/      HTTP endpoints (thin)
├── controllers/     use cases and permission checks
├── workflows/       ingest · review · reconcile · briefing · scheduled audit
├── agents/ chains/ llms/ prompts/   AI pipeline: repair loop, validated JSON, provider fallback
├── tools/           deterministic helpers: date resolver, name matching, rule-based extractor, caption converter
├── services/        verdict engine, briefing, email, search, scheduler
│   └── connectors/  GitHub (live) · Jira, Slack (built, switched off) behind one interface
├── models/ repositories/ migrations/   data; every query is scoped to the signed-in user
└── config/ utils/   one .env, logging, tracing, security
frontend/src
├── features/        meetings · commitments · reconciliation · settings
├── api/             typed endpoints and react-query hooks
└── components/ui/   accessible building blocks
```

📐 The full design is in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**: layers, the four flows, the data model,
the AI and security choices, and **how it would scale** (job queue, Redis, webhooks, pgvector), with the trade-offs made on purpose.

### Integrations

| Tool | Status | Notes |
|---|---|---|
| **GitHub** | ✅ Live | Create or link issues and PRs, verify, two-way status sync |
| **Jira Cloud** | 🔜 Coming soon | Built and tested; enable with `ENABLED_INTEGRATIONS=github,jira` |
| **Slack** | 🔜 Coming soon | Briefings and reminders to a channel; enable with `ENABLED_INTEGRATIONS=github,slack` |

Without credentials, trackers run in a **clearly labelled simulation mode**, so the whole loop can be tried offline.

---

## ⚙️ Configuration

The frontend reads its limits (password length, transcript size, demo mode) from the API, so every value is defined
once, in `.env`. Invalid values stop startup with a clear message.

<details>
<summary><b>Main settings</b> (full list with comments in <code>.env.example</code>)</summary>

| Group | Variables |
|---|---|
| App & ports | `APP_PORT` (8000), `FRONTEND_PORT` (5173), `WEB_PORT` (8080, Docker), `API_PREFIX`, `APP_TIMEZONE`, `DEMO_MODE` |
| Security | `SECRET_KEY` (**required** in production), `ACCESS_TOKEN_EXPIRE_MINUTES`, `PASSWORD_MIN_LENGTH`, `LOGIN_ATTEMPTS_PER_MINUTE` |
| AI | `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`, `LLM_TEMPERATURE`, `LLM_TIMEOUT_SECONDS` |
| GitHub | `GITHUB_PERSONAL_ACCESS_TOKEN` (optional server-wide default), `GITHUB_DEFAULT_OWNER`, `GITHUB_API_URL` (Enterprise) |
| Integrations | `ENABLED_INTEGRATIONS` (default `github`), `INTEGRATION_ALLOWED_HOSTS` |
| Database | `DATABASE_URL` (empty = SQLite; e.g. `postgresql+asyncpg://user:pass@host:5432/db`), `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` |
| Reconciliation | `AT_RISK_WINDOW_DAYS` (2), `VERIFICATION_INTERVAL_MINUTES` (60), `ENABLE_SCHEDULER` |
| Email | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` |
| Logging | `LOG_LEVEL`, `LOG_DIR`, `LOG_FILE_MAX_MB` (2), `LOG_MAX_FILES` (6), `LOG_RETENTION_DAYS` (7) |
| Tracing | `LANGFUSE_ENABLED`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`, `LLM_PRICING` |
| Samples | `SAMPLES_DIR` (default `samples`) |

</details>

---

## 🧪 Tests and quality

```bash
cd backend  && ruff check app migrations && pytest -q                       # 157 tests
cd frontend && npm run lint && npm run typecheck && npm test && npm run build  # 26 tests
```

Run the backend suite on Postgres with `TEST_DATABASE_URL=postgresql+asyncpg://…`.
CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs lint, the full test suite on **SQLite and Postgres**,
checks that migrations match the models, audits dependencies, and builds and smoke-tests the Docker stack.

## 🔒 Security

- **Accounts:** bcrypt passwords, JWT sessions, rate-limited sign-in and sign-up, and the same error for a wrong password or an unknown email.
- **Data isolation:** every query is scoped to the signed-in user; other users' records return 404.
- **Secrets:** AI keys and GitHub tokens are encrypted at rest (Fernet), only ever shown masked, and never logged.
- **SSRF protection:** integrations only call the tools' own domains. IP addresses and unknown hosts are rejected.
- **Safe output:** the AI never writes HTML. Emails come from an autoescaped template; the preview is sandboxed.
- **Web hardening:** a strict Content-Security-Policy and security headers in nginx; CORS limited to configured origins.

## 🛟 Troubleshooting

| Symptom | Fix |
|---|---|
| *"…was not found in GitHub, or the credentials have no access"* | Check the repository name, and that the token was given access to that repository. |
| *"No GitHub repository"* | Set the **Repository** field on the card, or a **Default repository** in review. |
| *"Default owner '…' is not a GitHub user"* | Default owner must be your username or organisation, not a repository name. |
| Everything extracted by "rules" | Add an AI key in **Settings**, or check `GEMINI_API_KEY` and the startup log. |
| Briefing "saved, not sent" | Configure `SMTP_*` in `.env`. |
| Port already in use | Change `APP_PORT`, `FRONTEND_PORT` or `WEB_PORT` in `.env`. |

## 🗺️ Roadmap

- **Jira and Slack:** built and tested, switched on per server with `ENABLED_INTEGRATIONS`.
- **Teams auto-capture:** fetch transcripts through Microsoft Graph when a meeting ends. Today, upload the `.vtt`.
- **Real-time verification:** GitHub webhooks instead of polling.
- **Scale-out:** job queue for AI extraction, Redis for shared state, and a single scheduler (see [ARCHITECTURE.md](docs/ARCHITECTURE.md#8-scaling-where-it-stops-and-what-changes)).
- **Accounts:** password reset, SSO and team workspaces.
