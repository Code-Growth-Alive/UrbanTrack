# Urban Track

**The trust layer of urban development in Africa.** Cross-verified certification
of professional experience: companies publish the projects they carried out and
declare the experts who contributed; each expert confirms, adjusts or rejects
their contribution. Only cross-confirmed experience is displayed on public
expert profiles with a certification badge and a traceable link to the project —
ResearchGate's co-author logic applied to the sector.

## Status

Epics -1, 0 and 1 complete: bootstrap, design system foundations, core data
models and the cross-confirmation state machine (68 tests). Full roadmap at
the bottom.

## Core workflow implemented (certification)

```
company declares contributor (auto-links by email if account exists)
        │
publish project ──► unknown email: magic-link ExpertInvitation (UUID, ~14 d)
                 └► registered expert: notification email
        │
expert confirms as-is ──────────────────────────► CONFIRMED ("Certified" badge)
expert adjusts wording ──► company re-validates ─► CONFIRMED
expert rejects ─────────────────────────────────► REJECTED (terminal)
expert disputes ────────────────────────────────► DISPUTED (admin arbitration only)
no response: ≤2 reminders (cron command) ───────► EXPIRED
```

All transitions live in `certification/services.py`; rule 8 (certified data
immutability) is enforced in `ProjectContribution.save()` plus a DB check
constraint. Public pages: `/experts/<OX-ID>/` ↔ `/projects/<id>/` are
mutually traceable; only published+public projects and confirmed
contributions are served.

## Flagged deviations (spec section 4 field list)

Additive fields required by the business rules — none of the mandated
fields were altered:

- `Project.published_by` — ownership by the company user (needed for the
  publishing flow and contribution attribution).
- `ProjectContribution.pending_company_validation` — distinguishes "waiting
  for the expert's first answer" from "company must re-validate adjusted
  wording", which share the same `pending_confirmation` status value.
- `ProjectContribution.rejection_reason` / `dispute_reason` — audit trail
  for arbitration (rule 7).
- `cv_template` lives on `ExpertProfile` (the generator reads profile +
  confirmed contributions; per-expert template preference).

## Stack

| Concern | Choice |
|---|---|
| Backend | Python 3.12 / Django 6.1 (modular monolith) + Django REST Framework |
| Database | **SQLite** (`db.sqlite3`) — project decision |
| Frontend | Django templates + **Tailwind CSS via the browser JS build** (`cdn.tailwindcss.com` + inline `tailwind.config`) — no npm pipeline, project decision |
| Async / scheduled tasks | **No Celery / no Redis** — background work runs as synchronous management commands (cron-triggerable), project decision |
| Email | **SendGrid** chosen as transactional provider (console backend in dev); open/click tracking planned for Epic 6 via webhooks |
| Auth | Django auth + magic-link flow (planned Epic 3) |

## Install & run

```bash
python3.12 -m venv env
source env/bin/activate
pip install -r requirements.txt

cp .env.example .env          # adjust if needed

python manage.py migrate
python manage.py runserver    # http://127.0.0.1:8000/
```

Admin: `python manage.py createsuperuser` then `/admin/`.

## Tests & lint

```bash
python manage.py test          # full suite
ruff check .                   # lint (config in pyproject.toml)
```

CI runs both on every push/PR (`.github/workflows/ci.yml`).

## Layout

```
urbantrack/         Django project (single settings module)
accounts/           custom User: expert | company | donor + permanent OX-XXXXXX professional ID
projects/           Project model & publishing (company side)        [Epic 1-2]
certification/      ProjectContribution + ExpertInvitation flows     [Epic 3-5]
cv_generator/       WeasyPrint multi-template CVs                    [Epic 7]
jobs/               Job board                                        [Epic 8]
templates/          base.html (Tailwind tokens + components), home.html
specs/              product specifications (FR)
```

## Design system

Tokens live in `templates/base.html` inside `tailwind.config`:

- `military` green — headers/nav/primary buttons, "Certified" badges (dominant color)
- `accent` pink — CTAs, confirm actions, pending badges (used sparingly)
- `white` / `charcoal` — surfaces, text, footer

Reusable component classes defined there: `.btn-primary`, `.btn-accent`,
`.btn-outline`, `.card`, `.badge-certified`, `.badge-pending`.

## Business invariants (enforced from Epic 1 onward)

1. Certification comes **only** from independent cross-confirmation
   (company declares → expert personally validates).
2. Adjusting wording re-triggers validation.
3. Existing-account emails are linked, never duplicated.
4. Up to 2 automatic reminders, then invitations expire (~14 days).
5. Admin intervenes **only** for dispute arbitration.
6. Confirmed contributions cannot change without a new validation cycle.

## Roadmap

| Epic | Scope | Status |
|---|---|---|
| -1 | Bootstrap: repo, apps, SQLite, Tailwind JS, User + OX-ID, CI | ✅ done |
| 0 | Design system & UI foundations (tokens, components, badges, profile typography) | ✅ done |
| 1 | Core data models + cross-confirmation state machine + integrity constraints | ✅ done |
| 2 | Project publishing screens (company side) | 🚧 next (service layer ready) |
| 3 | Expert invitation & landing (magic link) | pending |
| 4 | Certification & public profile | pending |
| 5 | Edge cases: reminders/expiry (sync command), disputes | pending |
| 6 | Email infrastructure (SendGrid) & security | pending |
| 7 | Multi-template CV generator (WeasyPrint): World Bank template, AFD and European model | pending |
| 9 | External connectors (World Bank API, AFD API) | pending |
| 10 | AI matchmaking & success prediction | pending |
| 8 | Job board | pending |

## Flagged decisions

- **SQLite instead of PostgreSQL**, **no Celery/Redis**, **Tailwind browser JS
  build instead of npm pipeline**: explicit client decisions overriding the
  original prompt.
- **No health/versioned endpoints**: explicit client decision.
- **SendGrid** retained as the transactional email provider unless told otherwise.
