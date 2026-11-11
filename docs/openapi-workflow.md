# Reviewed OpenAPI contract workflow

The backend serializers and API declarations produce the live JSON schema at
`/api/v1/schema/`. The reviewed, generated snapshot is
[`api/openapi.json`](../api/openapi.json). It is the reproducible input for the
[generated TypeScript client](typescript-client.md). Regenerate and review the SDK
with schema changes using `make api-client`; `make api-client-check` checks drift.

## Commands

After an intentional API/schema change:

```bash
make schema
```

Review the generated diff and commit it with the source change. Do not hand-edit
the JSON or patch generated client code to compensate for incorrect declarations.
The snapshot is the complete OpenAPI document, so the first addition is sizeable;
subsequent changes should describe the affected operations/components.

Check that code and the reviewed snapshot agree:

```bash
make schema-check
```

This is non-mutating. Missing or stale JSON returns a nonzero exit with a reminder
to regenerate and review; a matching check does not rewrite the file. Validation
errors or schema warnings also fail, preserving the existing snapshot. Export
publishes atomically only after successful generation and validation.

Both commands use `uv run --locked` and the project's pinned Python/dependencies.
Generation canonicalizes UTF-8 JSON with sorted object keys, two-space indentation,
LF newlines, no nonfinite numbers and no timestamps. Git attributes retain LF even
on checkouts that otherwise convert line endings. Arrays retain contract order;
the isolated child's fixed hash seed removes ambient Python hash-seed variation.

## Offline isolation

No running Django server, `.env`, test database configuration, application database,
RabbitMQ, email service or NHL access is required. The exporter starts a fresh
Python child with only platform environment inherited; deployment/Python overrides
and credentials are excluded. Canonical `nhl_web_app.schema_settings` import the
real API policy while using placeholder configuration, console logging, disabled
scheduling and the dummy database engine. These settings are tooling-only.

The child additionally refuses database connections, TCP/DNS access and `.env`
loading during setup/introspection. A declaration that starts querying data or
fetching remote resources must be corrected rather than granting export access.
`NHL_READ_ENV_FILE=false` disables `.env` reading before base settings import; the
normal application's default remains to read `.env` as before. The exporter sets
that flag only inside its child process and does not alter the calling shell.

The exported contract uses canonical default configuration, including the default
session-cookie scheme. Runtime customization must remain compatible or be reviewed
as an explicit contract/configuration change. A database-blocked API test compares
the checked document with the actual public schema endpoint, and clean-checkout
tests verify reproducibility under hostile/changed ambient configuration.

## CI and the next step

The `Reviewed OpenAPI contract` job runs `make schema-check` on pushes and pull
requests. It has no database service, deployment environment or test credentials.
The existing regression/browser job keeps its own PostgreSQL service and tests.
The checked artifact must be updated in the same API-changing commit, otherwise
CI fails before any frontend generator depends on an outdated contract.

This detects backend/schema drift. TypeScript client generation and its own drift,
type/build/component checks remain the next tooling slice. Select and pin that
generator against this actual schema, including enum/null/polymorphic responses,
session/CSRF, multipart uploads, errors, pagination and cancellation requirements.
The projection/admin decisions and auth deployment work remain prerequisites for
their affected UI cutovers, not work implicitly performed by schema export.
