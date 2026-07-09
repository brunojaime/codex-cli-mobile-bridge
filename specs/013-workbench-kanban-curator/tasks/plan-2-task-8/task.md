# T035 Normalize Workbench `done` status as authoritative Kanban completion

Status: done

Treat Workbench SDD `done`, `completed`, and `complete` values as the same authoritative completion state when building task cards and phase progress cards. The Kanban board must not place a completed Workbench task or phase in Ready or Backlog because of status spelling differences between frontend-visible SDD state and backend projection internals.
