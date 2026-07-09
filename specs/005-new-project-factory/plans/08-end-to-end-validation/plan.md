# End-To-End Validation

- Add a doctor endpoint with Projects root and toolchain checks.
- Add generated-project validation script.
- Add regression coverage for the SAT Showroom gap: remote publication phases
  must run before `ready`, and missing GitHub/release/Bridge config must end as
  `blocked`.
- Validate Workbench discovery, Flutter, backend, auth/RBAC, admin, notifications,
  and no-secret output.
