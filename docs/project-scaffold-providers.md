# Manifest v2 Compatibility and Provider Authoring

## Manifest compatibility

Manifest v2 stores `creation.mode`, independent `targets.mobile`,
`targets.web`, and `targets.api`, infrastructure modes, normalized artifacts,
capability evidence, and lifecycle state. Reads of manifest v1 use
`ProjectManifestCompatibilityAdapter` to create an in-memory view only. The
adapter never rewrites the source manifest or its recorded artifacts.

Legacy behavior remains explicit:

- absent creation mode means `product`;
- Flutter remains Flutter mobile plus Flutter Web;
- legacy Svelte is exposed as `svelte_legacy`, not silently changed to
  SvelteKit;
- a recorded Go declaration remains Go even if an older generator happened to
  emit FastAPI files;
- legacy and interrupted lifecycle aliases are preserved in the compatibility
  view.

Migration is opt-in: create a reviewed v2 manifest beside a backup, validate
each selected provider, compare artifact/resource identities, and switch the
consumer only after approval. Reading a project is never a migration trigger.
Rollback means restoring the original v1 consumer path; never delete or
retag recorded releases/resources as part of manifest migration.

## Add a provider

1. Add one `ProviderDescriptor` to the central registry with a stable id,
   target kind, source root, required tools, capabilities, and logical runtime
   bindings. Provider ids and capabilities must not be duplicated elsewhere.
2. Implement the provider adapter methods: plan, scaffold, validate, runtime
   contract, release contract, and doctor. Keep framework-specific decisions
   inside this boundary.
3. Generate only owned paths. Refuse to overwrite differing existing files,
   reject traversal, use argv commands from the allowlist, and record content
   hashes plus tool/command evidence. Post-baseline infrastructure phases must
   report their exact generated files so the final scoped evidence commit can
   track them without staging user-owned paths.
4. Pin direct dependencies and tool constraints. Bootstrap must create the
   native package lock; validation must use the locked installer.
5. Add neutral-output, forbidden-product-content, secret, compile/build, and
   capability tests. API providers must pass the shared OpenAPI black-box
   contract. Mobile Android providers must return the normalized Android
   artifact contract.
6. Add a stack preset only when the independent provider combination is known
   to validate. A preset is convenience, not a separate source of capability
   truth.

Rollout stays behind `PROJECT_SCAFFOLD_ENABLED`. Command execution and remote
writes have separate flags. Keep Product as the advertised/default creation
mode until v1 regression, provider build, infrastructure, Android release,
security, and end-to-end evidence are approved.
