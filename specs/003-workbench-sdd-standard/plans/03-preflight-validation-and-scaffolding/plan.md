# Preflight Validation And Scaffolding

Add standard, manifest, template, and scaffold dry-run validators first. Only
after preflight passes, add a bootstrap write flow that creates missing SDD
artifacts for a repo that wants to use Workbench. The write flow must detect
existing files, avoid destructive writes, and produce actionable next steps for
incomplete projects.
