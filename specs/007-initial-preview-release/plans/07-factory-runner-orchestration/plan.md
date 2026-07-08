# Factory Runner Orchestration

Orchestrate the complete first-release pipeline.

- Run local validation.
- Publish/verify GitHub repository.
- Run Cloudflare preview apply.
- Run web preview smoke tests.
- Run Android preview release.
- Run Bridge registration.
- Run final readiness validation across all surfaces.
- Persist each phase status and interrupted recovery state.
