# OneNote Skill Investigation

## Goal

Build a Codex skill that can:

- connect to a user's OneNote account
- list notebooks and sections
- create pages in a target section
- upload images, files, and HTML/text content into OneNote pages
- optionally append to an existing page later

This note documents the recommended technical path and the inputs required to implement it.

## Bottom line

The correct integration path is **Microsoft Graph + delegated user authentication**.

Do **not** build this around app-only client-credentials flow for OneNote. Microsoft states that the OneNote API in Microsoft Graph no longer supports app-only authentication, effective **March 31, 2025**.

That changes the architecture:

- the skill must authenticate as a real user
- the best fit for a CLI skill is device-code or interactive browser login
- the skill should cache tokens locally so the user does not sign in every time
- uploads should use OneNote page creation and page update endpoints, not a generic file-upload API

## Current Microsoft constraints

### 1. OneNote requires delegated auth

Official Microsoft Graph OneNote docs state:

- OneNote access is through Microsoft Graph
- OneNote supports delegated permissions
- OneNote app-only authentication is not supported
- the deprecation date for app-only support is March 31, 2025

Implication:

- a service principal with only `client_id + client_secret` is not enough for a durable OneNote integration
- the user must sign in at least once
- if the tenant enforces MFA, the flow must tolerate MFA

### 2. Password-based auth is the wrong default

Microsoft's ROPC flow exists, but it is a poor fit here:

- Microsoft advises against using it in most cases
- it is incompatible with many MFA and federation scenarios
- it requires handling a user's password directly

Implication:

- even if you can provide username/password, the skill should prefer device-code or interactive browser auth
- only consider password flow as a last-resort fallback, and only if the tenant policy explicitly allows it

### 3. OneNote has its own content model

Uploads are not a generic "send binary file to notebook" operation. OneNote page content is HTML-based and supports:

- text and formatted HTML
- embedded images
- file attachments via `object` elements
- multipart requests for binary content
- PATCH-based content updates for existing pages

Implication:

- the skill should expose high-level actions such as `create_page`, `append_page_content`, `attach_file`, and `embed_image`
- the implementation should assemble valid OneNote HTML and multipart payloads

## Recommended auth design

### Preferred flow

Use a **public client** Microsoft Entra app with delegated Microsoft Graph permissions and authenticate with:

1. device-code flow for headless or terminal-first usage
2. interactive browser flow as an optional fallback

For a Codex skill, device-code is the cleanest default because it works well in terminal sessions and with MFA.

### Token handling

The skill should cache tokens locally, for example in a file under the skill directory or a user config directory.

Recommended behavior:

- first run: start device-code sign-in
- successful login: store MSAL token cache locally
- later runs: silently refresh tokens when possible
- add an explicit `logout` or `clear-auth` command

### App registration settings

The Azure / Entra app registration should include:

- delegated Microsoft Graph permissions for OneNote
- public client enabled if using device-code or desktop-style login
- tenant choice based on your environment:
  - single-tenant if only your Microsoft 365 tenant will use it
  - multi-tenant only if you explicitly need cross-tenant sign-in

### Permissions to request

Start minimal:

- `Notes.ReadWrite`
- `offline_access`
- `openid`
- `profile`

Consider adding only if required by your scenario:

- `User.Read`

Notes:

- `Notes.ReadWrite` is the main delegated permission for reading and writing OneNote notebooks on behalf of the signed-in user.
- `offline_access` is important for refreshable sessions.

## Recommended skill behavior

The skill should wrap a small deterministic CLI script instead of relying on ad hoc HTTP calls each time.

### Proposed commands

- `connect`
  - authenticate the user and cache tokens
- `whoami`
  - confirm which Microsoft account is connected
- `list-notebooks`
  - list notebook ids and display names
- `list-sections --notebook <id>`
  - list sections within a notebook
- `create-page --section <id> --title <title> --html-file <path>`
  - create a page from HTML/text content
- `create-page-with-assets --section <id> --title <title> --asset <path> ...`
  - create a page with images and file attachments using multipart/form-data
- `append-page --page <id> --html-file <path>`
  - append or insert content into an existing page
- `attach-to-page --page <id> --file <path>`
  - update an existing page with a new embedded file or image

### Suggested skill trigger language

This skill should trigger for requests like:

- "connect to OneNote"
- "upload this file to OneNote"
- "create a OneNote page from these notes"
- "attach these images to a OneNote section"
- "append this summary to my OneNote page"
- "list my notebooks and sections"

## Graph endpoints to wrap

### Notebook discovery

- `GET /me/onenote/notebooks`
- `GET /me/onenote/sections`
- `GET /me/onenote/notebooks/{id}/sections`

These are enough for the first implementation.

Later, if needed:

- `GET /users/{id-or-upn}/onenote/...`
- `GET /sites/{site-id}/onenote/...`

### Create a page

Create pages in a section with:

- `POST /me/onenote/sections/{section-id}/pages`

Use:

- `text/html` when the page only contains HTML/text
- `multipart/form-data` when the page contains binary image or file parts

### Update an existing page

Update page content with:

- `PATCH /me/onenote/pages/{page-id}/content`

Use:

- `application/json` for non-binary changes
- `multipart/form-data` with a `Commands` part when sending binary content

Important detail:

- if we patch a page, we often need `GET /me/onenote/pages/{page-id}/content?includeIDs=true` first so we know the current target element ids for append/replace operations

## Content model to support

### 1. Simple text/HTML page

Use HTML like:

- page title in `<title>`
- page body in `<body>`
- paragraphs, lists, headings, tables

This is the simplest starting point and should be the first supported mode.

### 2. Image upload

For images, use:

- `<img src="name:imageBlock1" ... />` in the HTML
- a multipart part named `imageBlock1` containing the binary image

### 3. File attachment upload

For attachments, use:

- an `object` element in the HTML
- a multipart part containing the binary file
- correct MIME type, for example `application/pdf`

### 4. Mixed page creation

One request can create a page that contains:

- text
- one or more images
- one or more file attachments

This is the best UX for "upload elements to OneNote" because it avoids piecemeal operations.

## Suggested implementation layout

If we build this as a real Codex skill, the clean structure is:

```text
onenote-connect/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── onenote_cli.py
│   ├── auth.py
│   ├── graph_client.py
│   └── html_builder.py
└── references/
    ├── graph-endpoints.md
    └── auth-setup.md
```

### Script responsibilities

- `auth.py`
  - MSAL device-code login
  - token cache load/save
  - access token retrieval
- `graph_client.py`
  - low-level HTTP calls to Graph
  - JSON and multipart requests
  - error normalization
- `html_builder.py`
  - produce valid OneNote input HTML
  - map files/images to multipart block names
- `onenote_cli.py`
  - human-facing commands used by the skill

## Why raw HTTP is better than hiding everything behind an SDK

For this integration, direct HTTP to Microsoft Graph is likely the better first implementation.

Reason:

- OneNote page creation and updates rely heavily on exact HTML and multipart payload composition
- direct control over headers, boundaries, and body parts is useful
- debugging failed OneNote payloads is easier when the request is explicit

Inference:

- we can still use MSAL for auth
- but we should use `httpx` or `requests` for Graph calls rather than over-abstracting this behind a high-level SDK immediately

## Failure modes to design for

### Auth failures

- user not consented to required Graph scopes
- tenant blocks public client or device-code flow
- MFA required but unsupported by a bad auth flow
- cached token revoked or expired

### Content failures

- malformed HTML
- wrong multipart part names
- wrong MIME type
- trying to target stale element ids during page updates

### Service limits

Microsoft Graph documents OneNote throttling limits. For delegated requests, OneNote has per-app-per-user rate and concurrency limits.

Implication:

- the script should retry on `429`
- avoid parallel uploads by default
- serialize page creation/update operations unless there is a good reason not to

### Section limits

Microsoft documents a page-count limit per section. Creating too many pages in one section can return HTTP `507`.

Implication:

- the script should surface this clearly
- optionally support choosing another section automatically later

## Security handling

Recommended minimum:

- never store the user's password in the skill
- store token cache with user-only filesystem permissions
- keep client secret out of the design unless we later find a specific delegated confidential-client need
- avoid logging access tokens, refresh tokens, or raw authorization responses
- support explicit cache clearing

## Inputs required from you for implementation

For the actual build, I need:

- Microsoft tenant id, if this is tenant-scoped
- app registration client id
- confirmation whether the app is single-tenant or multi-tenant
- confirmation that delegated Graph permissions were added
- confirmation that public client flows are enabled
- the Microsoft account that should authenticate initially
- whether you want device-code only, browser login only, or both
- the target location for the skill:
  - recommended default: `~/.codex/skills`

Optional but useful:

- preferred default notebook name
- preferred default section name
- whether uploads should create new pages or append to an existing page by default

## Recommended implementation order

1. Create the skill scaffold in `~/.codex/skills`.
2. Implement `connect`, `whoami`, `list-notebooks`, and `list-sections`.
3. Implement `create-page` with plain HTML only.
4. Implement multipart page creation with images and file attachments.
5. Implement `append-page` and `attach-to-page`.
6. Add retry handling for throttling and better Graph error messages.
7. Validate against a real tenant and real OneNote notebook.

## Sources

- Microsoft Graph OneNote overview: https://learn.microsoft.com/en-us/graph/integrate-with-onenote
- Use the OneNote REST API: https://learn.microsoft.com/en-us/graph/api/resources/onenote-api-overview?view=graph-rest-1.0
- Create OneNote pages: https://learn.microsoft.com/en-gb/graph/onenote-create-page
- Update OneNote page content: https://learn.microsoft.com/en-us/graph/onenote-update-page
- Input and output HTML on OneNote pages: https://learn.microsoft.com/en-us/graph/onenote-input-output-html
- Microsoft Graph permissions reference: https://learn.microsoft.com/en-us/graph/permissions-reference
- MSAL Python token acquisition: https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens
- Microsoft identity platform ROPC guidance: https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth-ropc
- Microsoft Graph throttling limits: https://learn.microsoft.com/en-us/graph/throttling-limits
