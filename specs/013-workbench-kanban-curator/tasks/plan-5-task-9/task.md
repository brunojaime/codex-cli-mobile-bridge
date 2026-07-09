# T043 Align default Kanban scope selection across backend, selector, fallback, and board requests

Status: done

Use a single default-scope rule end to end: when a workspace is present, default to the workspace `All specs` board even if Project Factory scopes sort first; when no workspace is present, default to the first Project Factory scope. Ensure the Flutter selector, fallback scope list, initial board request, refresh, and polling cannot disagree.
