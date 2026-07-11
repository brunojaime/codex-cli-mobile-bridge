# Web Preview Invite Email with Amazon SES SMTP

Amazon SES is the recommended low-cost path for real preview invite delivery
when invites must go to arbitrary recipient addresses.

## Free Tier And Sandbox

AWS currently lists an SES free tier of up to 3,000 message charges per month
for 12 months after you start using SES. New AWS account free-tier credit rules
may also apply depending on account creation date.

SES sandbox is separate from pricing. While an SES account is in sandbox, both
sender identities and recipient addresses must be verified. To send preview
invites to arbitrary customer/admin emails, request SES production access in the
same region where the sending identity is verified.

## Bridge Configuration

Use the same SMTP style already used by Ambientando Calendar:

```bash
WEB_PREVIEW_EMAIL_PROVIDER=smtp
WEB_PREVIEW_EMAIL_FROM=preview@nienfos.com
WEB_PREVIEW_SMTP_HOST=email-smtp.us-east-1.amazonaws.com
WEB_PREVIEW_SMTP_PORT=587
WEB_PREVIEW_SMTP_USERNAME=<ses-smtp-username>
WEB_PREVIEW_SMTP_PASSWORD=<ses-smtp-password>
WEB_PREVIEW_SMTP_USE_TLS=true
WEB_PREVIEW_SMTP_IMPLICIT_TLS=false
WEB_PREVIEW_SMTP_TIMEOUT_SECONDS=10
WEB_PREVIEW_INVITE_SECRET=<same-secret-as-preview-worker>
```

SSL alternative:

```bash
WEB_PREVIEW_SMTP_PORT=465
WEB_PREVIEW_SMTP_USE_TLS=false
WEB_PREVIEW_SMTP_IMPLICIT_TLS=true
```

## AWS Setup Checklist

1. Verify the sender domain or sender address in Amazon SES.
2. Publish DKIM records in DNS.
3. Configure SPF and DMARC for the sender domain.
4. Create SES SMTP credentials in the same region.
5. Request production access if the account is still in sandbox.
6. Keep bounce and complaint monitoring enabled.
7. Run `GET /web-previews/invite-email-preflight`; it should report `ready`.

