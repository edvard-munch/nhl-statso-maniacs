# OAuth artifact review

Reviewed 2026-11-06 after retirement of `upd_vids`. This is a sanitized local
structure/history review: no token, secret, client/project ID or account value is
included here. No credential was sent to Google, refreshed, validated or revoked.

## Findings

| Files | Local findings |
| --- | --- |
| `client_secret-1.json` through `client_secret-11.json` | Eleven valid JSON web-client configurations, each containing a client ID, client secret and project ID. They represent eleven distinct clients/projects. |
| `credentials-*.json`, excluding `credentials-5.json` | Ten serialized `oauth2client.client.OAuth2Credentials` stores, each containing nonempty access-token, refresh-token, client-ID and client-secret fields. The ten refresh-token strings are distinct. |
| `credentials-5.json` | Empty. Its matching client configuration still contains a web-client secret; an empty local store does not establish that no grant exists elsewhere. |

All ten nonempty credential stores match the client ID and secret in their
same-numbered configuration. All record access-token expiry dates of
**2019-09-24** and `invalid: false`. Those flags describe old local state, not a
Google verification. Access-token expiry does not establish refresh-token
revocation; Google lists inactivity, revocation and other expiry conditions, but
this review cannot determine whether any particular grant still works. See
[Google token lifecycle](https://developers.google.com/identity/protocols/oauth2#expiration).

The recorded scope is `https://www.googleapis.com/auth/youtube.force-ssl`.
Google documents permission to read, modify and permanently delete YouTube content
and related ratings/comments/captions. See [YouTube scope documentation](https://developers.google.com/youtube/data/guides/authentication#api-scopes).
The retired command only searched for videos, but its saved authorization scope
was broader than public search.

Repository metadata reports **public** visibility. These paths are tracked from
initial commit `b350465` dated **2019-10-09**; that does not establish when repository
visibility became public. Treat the committed credential material as exposed.
The files are not ordinary fixtures. No current source uses their paths or the
retired Google client libraries. The OAuth callback route/view still exists and
renders the supplied authorization code; it does not consume these stored tokens.
Its retention is a separate application behavior decision.

## Owner actions before marking the cleanup resolved

1. Identify the owning Google accounts/projects for all eleven configurations
   privately, and check whether another application still uses any client. Do not
   copy identifiers or credential values into an issue, PR, terminal transcript
   or this report.
2. Revoke the retired application's grants from the owning Google accounts and
   rotate/delete the exposed **web-client secrets** in the relevant Google Cloud
   projects. If a client supports another application, coordinate its replacement
   before changing access. Current credential validity and owner actions remain
   unverified by this review.
3. Revocation can affect other scopes/clients associated with the same project;
   review ownership before applying it. Google describes this behavior and the
   revocation options in [its revocation documentation](https://developers.google.com/identity/protocols/oauth2/web-server#tokenrevoke).
   Do not test these old tokens by refreshing them as a way to establish safety.
4. In a focused repository cleanup, remove the 22 files and add an ignore rule
   for the retired credential directory to prevent accidental reintroduction.
   Keep credentials outside source control if a future video integration is built.
5. Separately decide whether coordinated Git-history cleanup is warranted after
   revocation/rotation. Deleting tracked files or adding `.gitignore` does not
   erase history or revoke credentials. Rewriting history changes commit IDs and
   affects other clones; do not force-push a rewrite as part of routine cleanup.

GitHub recommends revoking/rotating exposed credentials first, then considering
whether history removal is needed: [GitHub sensitive-data guidance](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

## Review boundary and status

The initial review left files unchanged and did not use credentials. Following
the user's confirmation that the artifacts are unused, a separate cleanup now
deletes all 22 files and ignores the retired credential directory. No replacement
credential or sample containing real values is added.

No account access, OAuth flow, token refresh, API test, revocation, rotation or
history rewrite was performed. Local deletion does not establish account ownership,
current token validity, unauthorized use or completion of exposure remediation.
The owner still needs to address revocation/rotation and decide whether coordinated
history cleanup is warranted. Existing Git history is unchanged.

Cleanup validation confirms exactly 22 file deletions, a matching scoped ignore
rule and unchanged application/schema/dependency/test-fixture files. Static,
requirements-export and whitespace checks pass; the normal offline suite still
collects 901 tests with 43 deselected. No database or authenticated request is
needed for this file cleanup; the full suite was not rerun in this batch.
