# Release Mode Contract

Define the first-release state model before changing runner behavior.

- Add `preview` as the default New Project first-release mode.
- Define mutually exclusive `preview`, `real`, and `mock` release profiles.
- Define release tag prefixes and metadata for each profile.
- Define when a New Project job may report `ready`, `blocked`, or `failed`.
- Define the promotion path from preview to later production.
