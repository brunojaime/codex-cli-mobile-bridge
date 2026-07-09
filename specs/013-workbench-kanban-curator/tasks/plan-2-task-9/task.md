# T037 Isolate spec-scoped Kanban boards from workspace observer cards

Status: done

When `spec_id` is provided, the Kanban projection must include only the selected spec's SDD cards unless a draft or job scope is explicitly requested. Workspace observer cards and Project Factory cards remain part of the all-specs workspace board.
