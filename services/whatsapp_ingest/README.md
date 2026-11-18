# WhatsApp Group Intake

Silent intake and project/group reconciliation service. It links a dedicated
WhatsApp account as a companion device, discovers its groups, associates each
group with a project, and writes new text, audio, image, and PDF messages as atomic project
inbox records under `.data/whatsapp_ingest/inbox`. Videos are supported too,
including captionless videos and video files sent as documents.

This integration uses the unofficial WhatsApp Web protocol through Baileys. It
must not be used for bulk messaging, unsolicited contact, or automated replies.
WhatsApp may invalidate the session or change the protocol at any time.

## Runtime

- Node.js 20 or newer (Batata uses the NVM-managed Node 22 runtime).
- `@whiskeysockets/baileys` pinned to the reviewed upstream release.
- Admin UI bound to `127.0.0.1:8787` by default.
- Authentication state stored outside Git in `.data/whatsapp_ingest/auth`.

Install and test:

```bash
source "$HOME/.nvm/nvm.sh"
nvm use 22
cd services/whatsapp_ingest
npm ci
npm test
```

Start in the foreground:

```bash
scripts/run_whatsapp_ingest.sh
```

Open `http://127.0.0.1:8787/` locally. The dashboard displays the QR only while
the account needs to be linked.

On Batata, Tailscale Serve exposes the same dashboard privately at:

```text
https://batata-default-string.tail0302c4.ts.net/whatsapp/
```

If WhatsApp explicitly logs the companion device out, create a recoverable
session backup and request a fresh QR with:

```bash
scripts/reset_whatsapp_ingest_session.sh
```

## Automatic project association

On every connection or group change, the service compares the group subject
with direct project directories under `/home/batata/Projects` and with the
`name` and `slug` fields in `.codex/project.yaml`.

- A single exact normalized match is bound automatically.
- The immutable WhatsApp group ID is then remembered, so renaming the group
  does not break its project association.
- A new group with no match gets its own stable `pending-*` inbox immediately.
- That unmatched group also gets one guided Project Factory draft; it does not
  initialize a repository or deploy anything until the normal intake is confirmed.
- Multiple candidates are marked `ambiguous`; the service never guesses.
- If a matching project appears later, pending records are moved into its inbox.
- Groups the account no longer belongs to are retained as inactive history; no
  project directory or captured record is deleted.

The auditable registry lives at
`.data/whatsapp_ingest/group-registry.json`. It is runtime state and is not
committed to Git.

### Optional manual override

`groups.json` remains available only for exceptions. Copy the example:

```bash
cp services/whatsapp_ingest/config/groups.example.json \
  services/whatsapp_ingest/config/groups.json
```

Replace the example group ID with an ID shown by the dashboard and use a safe
project slug:

```json
{
  "version": 1,
  "groups": {
    "120363000000000000@g.us": {
      "enabled": true,
      "project": "moldegom"
    }
  }
}
```

The target must be an existing direct project directory. Changes are loaded
whenever groups are reconciled.

## Automatic group creation

Group creation is opt-in per project because WhatsApp needs to know exactly
which people to add. Add `.codex/integrations/whatsapp.json` inside a project:

```json
{
  "version": 1,
  "enabled": true,
  "create_group": true,
  "subject": "Nienfos · Proyecto Ejemplo",
  "participants": [
    "+5491111111111",
    "+5492222222222",
    "+5493333333333"
  ],
  "description": "Canal del proyecto. Los textos, audios, imágenes y PDFs se incorporan al espacio de trabajo.",
  "aliases": ["Proyecto Ejemplo"]
}
```

Once WhatsApp is linked, the service first looks for an existing group and
binds it. Only if none exists does it create one. The dedicated receiver is the
creator; `participants` should contain the owner, partner, and client numbers.
Creating the group produces WhatsApp's normal visible system event, but the
service never sends chat messages or automatic replies.

## Private group administration

The receiver maintains a dedicated administrative group named
`Nienfos · Alta de grupos`. On first bootstrap it discovers Bruno's WhatsApp
identity from the already captured local manifests and creates the group with
Bruno as its only participant. The private state, including participant JIDs,
lives in `.data/whatsapp_ingest/admin-group.json` and is never committed.

Only Bruno, and later Mariano after Bruno registers his number, can issue
commands there. Sharing Mariano's contact card records his identity privately
without adding him to the administrative group. The service never replies in
WhatsApp. Supported inputs are:

```text
Este es el número de Mariano Muratore: +54 ...

Crear grupo: Nombre visible
proyecto: slug o nombre del proyecto
clientes: +54 ..., +54 ...
```

Every created project group automatically includes Bruno and Mariano; Nienfos
Codex is the creator. The immutable group ID is bound immediately to the
resolved project. Resolution accepts exact identities and unique,
high-confidence spacing/prefix variants such as `Rent ID` → `rentid`; ambiguous
matches are refused. Unauthorized senders and non-text administrative messages
are silently ignored.

Once both core identities are available, the receiver creates the `Nienfos`
community exactly once. WhatsApp membership is established through project
groups: creating the first linked project group adds Bruno and Mariano to the
community without creating a separate placeholder group. Private idempotency
state lives in `.data/whatsapp_ingest/community.json`.

## Temporary direct intake

Bruno can send private text, voice notes, images, videos, and PDFs to Nienfos Codex while
project groups are still being provisioned. The receiver accepts only Bruno's
stored WhatsApp identities and silently ignores every other private sender.

Each batch requires one exact routing message sent within the same 45-second
quiet window:

```text
Proyecto: proyecto-inmobiliaria
```

`Proyecto:` is case-insensitive, but the colon is mandatory and the value must
match one project slug, declared name, WhatsApp subject, or configured alias.
An exact normalized workspace directory name takes precedence over names and
aliases inherited by other checkouts. If there is no exact directory match,
ambiguous aliases still remain pending.
The directive and every adjacent text, voice note, and image are first stored
together under the neutral `direct-bruno` inbox. After the quiet window, all
audio is transcribed locally and the complete batch is moved into the selected
project's inbox and opens a project chat unconditionally, without semantic
triage. Questions, greetings, captionless images, and even a routing directive
by itself all open the chat. The agent answers questions or asks for missing
context there; project changes still require approval inside that chat.
Images, videos and PDFs are attached to the project chat; the Bridge extracts PDF
text before Codex runs. Missing, conflicting, unresolved, or ambiguous
directives remain pending and never create a Codex chat. No WhatsApp reply is
sent.

Each resolved private batch keeps a stable batch ID and is processed as one
request, even when it exceeds the group worker's default 20-message batch size.
Separate private batches remain independent. A pause of 45 seconds closes the
batch, so send the routing directive and all related content within that window.

The original text/media, audio transcript, sender, project-resolution decision,
triage, and Codex submission markers remain together for auditability.

### Transparent CLI bridge

An exact standalone `CLI` text in Bruno's private batch selects the
`codex-cli-mobile-bridge` workspace on the DEV Bridge and bypasses triage. The
DEV endpoint defaults to `http://127.0.0.1:8118` and can be overridden with
`WHATSAPP_DIRECT_CLI_BRIDGE_URL`; the ordinary group/project route continues to
use `WHATSAPP_BRIDGE_URL`. After the same quiet window, the receiver creates a
standard default-profile DEV chat and forwards the ordered text and audio
transcripts without a WhatsApp wrapper; images and PDFs are attached normally.
The `CLI` control message itself is omitted. The frontend therefore treats the
result like an ordinary chat created in the DEV app. This mode does not send a
WhatsApp reply, and its session/job identifiers remain recorded locally for
deduplication and auditability. A standalone `CLI` with no other content also
opens the chat, asking what the user wishes to consult or do.

## Stored record

Each accepted message becomes an immutable directory:

```text
.data/whatsapp_ingest/inbox/<project>/<YYYY-MM-DD>/<message-id>/
├── message.json
├── message.txt          # text messages only
├── audio-original.ogg   # audio messages only; extension follows MIME type
├── image-original.jpg   # image messages only; extension follows MIME type
├── video-original.mp4   # videos, including videos sent as documents
├── document-original.pdf # PDF messages only
└── READY
```

`READY` is written last. Downstream Drive or Codex workers should only consume
directories containing that marker.

### Videos

Send `Proyecto: <slug>` (or `CLI`) as a separate message, then the video within
the same quiet window. A caption is optional. The original received bytes are
preserved without transcoding; the manifest records `video_seconds`, MIME type,
caption and original document filename when available. Known file extensions
include MP4, MOV, M4V, WebM, MKV, AVI, 3GP and 3G2. Playback depends on the device's
codecs. Before launching the agent, the Bridge now decodes timestamped PNG previews
with local PyAV (no ffmpeg command or model API required). Native image inputs work
in read-only planning chats too. Up to 12 frames per video and 24 per batch are
sampled across the duration, approximately every 3 seconds for short clips, with
a maximum image edge of 1280 px. This is sampled visual inspection, not continuous
playback: brief events can be missed. Video speech is automatically transcribed
by the configured local faster-whisper backend (offline cached model, no model
API), with approximate timestamps in the agent context. This also applies to
direct video attachments and videos sent as documents. Other transcription
backends never receive video audio automatically: the prompt reports unavailable.

Audio preprocessing is bounded to 10 minutes of source audio, 180 seconds elapsed,
150 seconds CPU and 8 GiB address space per process. No audio track, no detected
speech, duration limit and unavailable/error are explicit states; the original
and frames are still delivered. Speech recognition can contain errors and is not
human listening verification. Atomic, hash-verified cache entries depend on media
SHA256, model, language and parameters. Repeated jobs retain the prepared context;
concurrent equivalent preprocessing uses a local file lock. WhatsApp multipart
uploads allow 240 seconds per video for decoding and recognition. No outbound
WhatsApp response is sent.

Preview decoding runs in a separate bounded process (35 s wall time, 25 s CPU,
1.5 GiB address space), accepts clips up to 2 hours and 4K source pixels, and
rejects playlist/network formats. Corrupt or unsupported media keep their original
attachment with an explicit preview failure note. SHA256-verified previews are
reused; retries preserve the exact original and images. The agent must not claim
to have seen or heard content when the corresponding input is unavailable.
Tests: `.venv/bin/python -m pytest tests/test_video_preview.py tests/test_whatsapp_video.py -q`.

The updated Bridge retains video download descriptors across SQLite reloads and
job retries. The updated mobile client shows an explicit **Abrir video** action.
Downloads retain the managed attachment directory boundary used by images.
Uploads use the Bridge's configured `document_max_upload_bytes` limit (25 MB by
default). Failed downloads never create `READY`; upload failures leave error
records pending rather than marking them as delivered.
No automated reply is sent in WhatsApp.

Reproducible offline checks: `.venv/bin/python scripts/check_whatsapp_videos.py`.
The WhatsApp transport and Codex execution are replaced only in the test harness;
the parser, persistence, worker, multipart API, download and SQLite paths execute
real project code. Live activation requires updating the intake service, worker,
Bridge backend and mobile client, then testing an actual WhatsApp message.

## Local transcription and Codex triage

The companion worker scans only complete `READY` records. For matched groups
without explicit private routing directives,
it:

1. transcribes audio locally with the existing `faster-whisper` installation;
2. waits for a quiet window and batches messages from the same WhatsApp group;
3. runs an internal, archived Codex triage with the
   `whatsapp-project-triage` skill and `sandbox_mode=read-only`;
4. archives non-actionable conversation without creating a visible chat;
5. creates a new `WhatsApp · <task>` chat only for actionable work;
6. applies the green `WhatsApp Intake` agent profile to that chat;
7. asks Codex to inspect and propose the implementation without changing files;
8. writes `triage.json` and `codex-submission.json` for audit and idempotency.

The persistent `WhatsApp Intake` profile is the chat's system instruction. It
requires the first turn to present a plan and wait. WhatsApp content never
counts as implementation approval. Only a later explicit approval from Bruno
Jaime inside that Codex chat enables implementation. No reply is ever sent to
WhatsApp.

Requests longer than the Bridge's 10,000-character message limit are uploaded
as a complete `whatsapp-request.txt` attachment, alongside any original media.
This applies to triage, planning, and direct CLI delivery; conversation JSON is
never truncated to fit the message limit. Temporary upload files are removed
after submission, while the Bridge retains its normal attachment copy.

Install the worker as a user service:

```bash
scripts/install_whatsapp_intake_worker_service.sh --enable-now
```

Pending or ambiguous groups are retained without Codex submission until the
reconciler promotes their intake directory to a real project.

## Environment

| Variable | Default |
| --- | --- |
| `WHATSAPP_ADMIN_HOST` | `127.0.0.1` |
| `WHATSAPP_ADMIN_PORT` | `8787` |
| `WHATSAPP_DATA_DIR` | `<repo>/.data/whatsapp_ingest` |
| `WHATSAPP_DIRECT_INBOX_PROJECT` | `direct-bruno` |
| `WHATSAPP_AUTH_DIR` | `<data>/auth` |
| `WHATSAPP_PROJECTS_ROOT` | `/home/batata/Projects` on this installation |
| `WHATSAPP_PROJECT_FACTORY_URL` | `http://127.0.0.1:8000` |
| `WHATSAPP_GROUP_REGISTRY_FILE` | `<data>/group-registry.json` |
| `WHATSAPP_GROUPS_FILE` | `<service>/config/groups.json` |
| `WHATSAPP_LOG_LEVEL` | `info` |
| `WHATSAPP_PROTOCOL_LOG_LEVEL` | `warn` |
| `WHATSAPP_BRIDGE_URL` | `http://127.0.0.1:8000` |
| `WHATSAPP_WORKER_POLL_SECONDS` | `3` |
| `WHATSAPP_WORKER_SETTLE_SECONDS` | `45` |
| `WHATSAPP_WORKER_BATCH_SIZE` | `20` |
| `WHATSAPP_TRIAGE_CONTEXT_MESSAGES` | `20` |
| `WHATSAPP_TRIAGE_MAX_PARALLEL` | `10` |
| `WHATSAPP_TRIAGE_TIMEOUT_SECONDS` | `300` |
| `WHATSAPP_TRANSCRIPTION_MODEL` | `small` |
