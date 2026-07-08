# Cloudflare Worker Preview Runtime

Build the Worker runtime that serves Preview API v1.

The Worker owns:

- app config resolution from URL path;
- auth and session handling;
- invite accept and password setup;
- admin user/role APIs;
- notification APIs;
- generic domain CRUD APIs;
- app update metadata;
- preview disable/expiration enforcement;
- CORS for preview hosts.

The Worker must be deployable independently from any generated app.
