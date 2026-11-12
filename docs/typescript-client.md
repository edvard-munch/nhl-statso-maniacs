# Generated TypeScript API client

The client foundation lives in the [Vue/Vite application](../frontend/README.md)
under `frontend/`. The responsive shell is implemented; scoreboard/game workflows
are next. The existing Django website remains available.

## Install and check

Use Node **24.13.0** (`frontend/.node-version`) and Corepack. The package metadata
pins pnpm **10.34.9**; `corepack pnpm` honors it even if another pnpm is on PATH.
From the repository root:

```bash
make frontend-sync       # frozen pnpm lockfile; dependency scripts disabled
make api-client-check   # regenerate in temporary storage and compare; no writes
make frontend-typecheck # SDK and compile-only contract assertions
make frontend-test      # mocked Fetch and generation regression tests
```

After an intentional backend contract change:

```bash
make schema
make api-client
make schema-check api-client-check frontend-typecheck frontend-test
```

Review and commit the schema and generated diff together. Never edit
`frontend/src/api/generated/` manually. Generation consumes the checked
`api/openapi.json`, rejects external references and needs no running Django server,
application database, `.env` or NHL connection. Failed generation preserves the
existing output; check mode detects missing, changed and extra files without
rewriting them. Dependencies must already be installed; commands do not install
missing dependencies automatically. Installation itself requires registry access
unless the package-manager cache is populated.

The separate CI frontend job installs the frozen lockfile, checks generation drift,
compiles Vue/TypeScript, lints/formats, tests the proxy/components/client and builds
and checks the shell in Chromium after the backend schema check. Existing Python
coverage and browser checks retain their current scope. Hosted execution still
needs verification after push.

## Transport and usage

```ts
import {
  authCsrfRetrieve, authLoginCreate, playersList,
} from './api/index.js';

await authCsrfRetrieve();
await authLoginCreate({ body: { username: 'example', password: 'example' } });
const { data } = await playersList({ query: { season_id: '20262027' } });
```

The default client resolves the browser origin when called. Requests stay under
same-origin `/api/v1/`, use session cookies through Fetch's `same-origin`
credentials policy and reject redirects. The Vite development proxy preserves
Host and Origin together; see the [local workflow](../frontend/README.md).

Bootstrap CSRF before mutations. The transport stores the returned token only in
memory and captures rotations from login/logout. It supplies `X-CSRFToken` without
requiring cookie access, JWTs or browser storage. Individual client instances keep
separate tokens. On a CSRF failure it clears the token; the caller must bootstrap
again and decide whether to retry. Requests are never automatically replayed.

Generated functions accept `signal` for cancellation and a custom `client` for
tests. The factory accepts an explicit origin and Fetch implementation outside a
browser. Encoded pagination URLs can be followed through the transport; the same
origin/path checks still apply. Prefer the typed SDK query options when building
new requests.

JSON API errors throw `ApiError`, carrying the error envelope, native response and
`X-Request-ID`; `throwOnError: false` instead returns a typed success/error union.
HTML proxy responses, malformed JSON and invalid error envelopes throw
`ApiProtocolError`. Network and abort errors propagate. Avoid displaying raw
proxy HTML. Successful 204/205 responses return `data: undefined`.

Account image uploads accept `File`/`Blob` fields; Fetch constructs FormData and its
multipart boundary. Dates remain wire-format strings, nullable values remain
nullable, and statistics retain their discriminated skater/goalie unions. Generated
TypeScript checks callers at compile time; it does not validate every successful
response at runtime. Backend serializers remain the contract source.

## Generator choice

Pinned minimal Kubb core, OpenAPI adapter, TypeScript parser and client/type plugins
produce named functions for all **41 operations** plus shared DTOs. The app owns
`http.ts`; generated code imports its transport contract. This keeps session/CSRF,
uploads, error handling and cancellation out of generated files. See Kubb's
[client plugin](https://docs.kubb.dev/extensions/kubb-labs/plugin-client) and
[custom client contract](https://docs.kubb.dev/extensions/kubb-labs/plugin-client/guides/write-your-client).
The larger Kubb CLI/Studio bundle is unnecessary for this workflow. Type-only
OpenAPI generators were considered; named SDK operations suit the planned Vue
integration while leaving the transport under application control.

Schema/generator warnings fail generation, with one documented exception:
OpenAPI `format: password` is represented as its base string type. The generator's
unsupported-password-format warning is accepted; password values are not trimmed
or otherwise transformed. Other warnings and validation errors remain failures.
The lockfile, simple generated banner and LF attributes keep output reproducible
across checkout paths. Regression tests check regeneration in another directory,
nonmutating drift detection and failure preservation.
