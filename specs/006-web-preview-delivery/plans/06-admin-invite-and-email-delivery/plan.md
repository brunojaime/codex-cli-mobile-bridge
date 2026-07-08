# Admin Invite And Email Delivery

Add the invite workflow end to end.

- Collect admin emails during chat-first New Project intake.
- Validate email syntax and duplicate emails.
- Generate one invite per email.
- Store token hashes, never plaintext tokens.
- Send email through a provider abstraction.
- Return manual invite links when the provider is missing.
- Mark invites as sent, failed, used, expired, or revoked.
- Add resend and revoke operations.
