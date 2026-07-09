# T036 Add regression coverage for Done-state Kanban consistency

Status: done

Cover the case where `tree.json` reports Workbench tasks and plans as `done` while `tasks.md` cannot provide T-number checkbox evidence. The board must still render the corresponding task and phase cards in Done.
