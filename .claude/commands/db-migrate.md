---
description: Generate and apply an Alembic migration
argument-hint: <message> [--apply]
---

# /db-migrate — generate + apply a DB migration

Generate an Alembic migration from the current SQLAlchemy models.

Steps:

1. Make sure the local Postgres is running (`docker compose up -d db`).
2. Generate the migration:
   `alembic revision --autogenerate -m "$1"`
3. **Open the generated file** and review it:
   - Confirm column types match the SQLAlchemy model.
   - Confirm timestamp columns are `TIMESTAMPTZ`, not `TIMESTAMP`.
   - Add explicit `server_default` / `default` where applicable.
   - Hand-write any data migrations Alembic can't autogenerate.
4. If the user passed `--apply`, run `alembic upgrade head` against the
   **local** DB only. Never auto-apply to remote environments.

Constraints:

- All timestamp columns are `TIMESTAMPTZ` (IST is enforced at the app layer;
  the DB stores aware timestamps).
- Each migration must be reversible — implement `downgrade()` properly.
- Do not squash existing migrations without explicit user instruction.
- Never apply migrations to staging/prod from this command; that goes
  through the deploy pipeline.
