# T009 Make session list summaries avoid serializing full transcripts

Status: planned
Plan: Backend Pagination

Reduce `GET /sessions` work so list rendering does not require full message body serialization for every session.

