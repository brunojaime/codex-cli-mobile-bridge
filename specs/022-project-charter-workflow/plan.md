# Project Charter Workflow Plan

## Implementation

1. Materialize and integrity-check the approved Markdown and metadata during
   deterministic init.
2. Add hard gates and charter-first prompts to Project Factory and Domain
   Factory.
3. Project the charter through SDD summaries, snapshots, and Workbench views.
4. Add the email share API with SMTP and Cloudflare provider support.
5. Add the responsive Flutter reader and share dialog.
6. Validate backend contracts, mobile responsiveness, and blocked workflow
   behavior.

## Compatibility

The charter is mandatory for projects generated through New Project. Existing
non-generated repositories remain readable in SDD without a new missing-file
error. Existing generated projects can be migrated by rerunning deterministic
init from an approved draft and domain brief.

