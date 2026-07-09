# Preview Contract And SDD Alignment

Define the Web Preview Delivery contract before implementation.

- Add Preview API v1 contract documents.
- Define web preview final job payload shape.
- Define stable URL and app slug rules.
- Define admin invite request/response schemas.
- Define preview lifecycle states.
- Define cost, security, and blocker reporting language.
- Extend New Project Factory spec references so generated projects are not
  considered shareable until web preview delivery succeeds or is explicitly
  blocked with manual next steps.
- Preserve the existing generated-project release contract. Web Preview
  Delivery is additive and must not replace GitHub publication, Android APK
  workflows, app-updater metadata, release validation, or Bridge installable-app
  registration.
