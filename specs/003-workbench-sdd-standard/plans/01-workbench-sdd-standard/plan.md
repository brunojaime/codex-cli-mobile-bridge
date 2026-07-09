# Workbench SDD Standard

Define `workbench-sdd/v1` as the platform-owned contract. The standard must
describe artifact families, lifecycle states, metadata, diagram taxonomy,
traceability links, context pack names, generated index schemas, and LLM rules.
The source-of-truth artifact is
`backend/app/infrastructure/config/sdd_standards/workbench-sdd/v1.yaml`, loaded
through `SddStandardService`. This phase also defines unknown-version errors,
compatibility behavior, and fixture coverage.
