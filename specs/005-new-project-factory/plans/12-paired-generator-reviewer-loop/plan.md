# Paired Generator Reviewer Loop

Fix the Project Factory creation loop so review feedback arrives after every
generator pass instead of after all generator passes have already completed.

The previous behavior executed the configured generator count first, then the
configured reviewer count. With the default 20 + 20 workflow, that meant 20
generator passes could change the project before a reviewer inspected the first
slice. This plan changes the workflow to 20 generator/reviewer pairs:

```text
generator-01 -> reviewer-01
generator-02 -> reviewer-02
...
generator-20 -> reviewer-20
```

Required outcomes:

- The spec contract names paired generator/reviewer passes as the required
  creation behavior.
- The manifest/API creation workflow mode describes pairs, not batches.
- The job runner executes generator pass N immediately followed by reviewer
  pass N before generator pass N+1.
- Mismatched generator/reviewer run counts are rejected before the build starts.
- Project Factory doctor reports mismatched effective counts, including
  overrides, as blocked before a user starts generation.
- Regression tests prove the execution order is paired.
