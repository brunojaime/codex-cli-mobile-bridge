# Cloudflare Configuration And Client Boundary

Create a bridge-host Cloudflare integration boundary that reads operator-owned
configuration and never depends on generated project secrets.

Expected configuration:

```text
CLOUDFLARE_API_TOKEN
CLOUDFLARE_DNS_API_TOKEN
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_ZONE_ID
CLOUDFLARE_ZONE_NAME=nienfos.com
PREVIEW_BASE_DOMAIN=preview.nienfos.com
```

The service should support:

- account lookup;
- zone lookup;
- DNS record create/update/read for preview records;
- Worker script deploy;
- D1 database create/lookup;
- D1 migration execution;
- Pages project/artifact publication;
- R2 bucket create/lookup when enabled;
- safe dry-run output.
