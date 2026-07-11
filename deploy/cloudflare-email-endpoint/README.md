# Cloudflare Email Endpoint for Web Preview Invites

This Worker is the operator-provided endpoint used by:

```bash
WEB_PREVIEW_EMAIL_PROVIDER=cloudflare_email
WEB_PREVIEW_EMAIL_ENDPOINT=https://<worker-host>/send
WEB_PREVIEW_EMAIL_API_TOKEN=<same value as EMAIL_ENDPOINT_TOKEN secret>
WEB_PREVIEW_EMAIL_FROM=preview@nienfos.com
```

The Bridge posts invite email payloads to this Worker. The Worker validates the
Bearer token and sends through the configured provider.

## Cloudflare Plan Constraint

Cloudflare Workers Free can host this endpoint. Cloudflare Email Routing is
inbound/forwarding only for this workflow and is not enough to send preview
invites.

For a free-compatible setup, use:

```toml
EMAIL_PROVIDER = "brevo"
```

and configure `BREVO_API_KEY` as a Worker secret. Brevo provides the outbound
transactional email API; Cloudflare provides the Worker runtime.

Cloudflare Email Service can send to verified destination addresses on all
plans. Sending to arbitrary invite recipients through native Cloudflare Email
Service requires Workers Paid. If you use the Free plan with native Cloudflare
Email Service, every invite recipient must be a verified destination address in
the Cloudflare account, or the Worker should restrict recipients with
`ALLOWED_RECIPIENTS`.

## Deploy Checklist

1. Onboard the sender domain in Cloudflare Email Service.
2. Choose `EMAIL_PROVIDER=brevo` for Workers Free, or
   `EMAIL_PROVIDER=cloudflare_email_service` for native Cloudflare Email
   Service.
3. Set the `EMAIL_ENDPOINT_TOKEN` Worker secret.
4. For Brevo, set `BREVO_API_KEY`. For native Cloudflare Email Service,
   configure the `EMAIL` send binding in Wrangler.
5. Set `EMAIL_FROM` to the verified sender address.
6. Optionally set `ALLOWED_RECIPIENTS` as a comma-separated allowlist.
7. Deploy the Worker and set the Bridge env vars shown above.
8. Run `GET /web-previews/invite-email-preflight`; it should report `ready`.

## Local Validation

```bash
scripts/validate_cloudflare_email_endpoint.sh
```
