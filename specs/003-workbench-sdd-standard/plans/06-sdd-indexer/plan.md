# SDD Indexer

Generate `.sdd/` indexes from project artifacts. Indexes must let the Workbench
and LLMs identify relevant specs, diagrams, modules, domains, statuses, and
traceability without scanning every spec. Missing or stale indexes must produce
observable status. Context pack flows attempt deterministic regeneration first;
if regeneration fails, they return a degraded pack or a hard failure depending
on the action instead of reading all specs.
