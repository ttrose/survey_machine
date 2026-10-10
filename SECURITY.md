# Security and privacy

The service uses per-workspace authorization for all private survey, response and key
operations. A shared deployment is not a shared customer data space. Customer accounts
currently have one owner; team roles and MFA are not implemented.

Operator access uses a random deployment secret. Customer passwords use PBKDF2-HMAC-
SHA256 with 600,000 iterations and independent random salts. Browser sessions and
one-time invitation/recovery tokens have 256 bits of randomness; only their digests
are persisted. Password changes and access changes invalidate existing sessions.

Session cookies are HttpOnly, SameSite=Lax and Secure in production. Browser mutations
require a session-specific CSRF token. Login/activation also reject cross-origin
requests. API keys use a separate header and are restricted to their workspace and
explicit permissions.

Authentication is limited to 30 attempts per address and 10 per email in five-minute
windows. Only hashes of those identifiers are stored in rate-limit buckets; expired
buckets are removed on subsequent authentication attempts. This is a first layer of
abuse protection, not a substitute for edge/network controls under distributed attack.

Public surveys are deliberately accessible by link. They allow multiple submissions
and do not verify a respondent's identity. Anonymous submissions have no collected
name/IP/user-agent metadata in application records, but answers can still contain
personal information. Hosting providers and proxy logs have separate retention rules.

Before public use, configure HTTPS, production secrets, backups and an appropriate
Cloudflare plan. Set exact CORS origins when needed. Keep operator keys, invitation
links, database backups, .env and .dev.vars out of commits and public logs. Restrict
access to test servers and local emulators to localhost.

The current release uses manual invitations and manual recovery-link delivery. It
does not offer public signup, automated email, MFA, billing or team access. Treat
the holder of a recovery link as able to take over its intended account.

Report suspected vulnerabilities privately to the contact listed in LICENSE. Do not
include real customer responses, passwords, tokens or database backups in public
issues.
