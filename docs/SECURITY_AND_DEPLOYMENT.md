# Security and deployment notes

This prototype is intentionally bound to `127.0.0.1`. Do not expose it to the
public internet as-is.

For a controlled demonstration:
- Use a unique `SECRET_KEY` environment variable.
- Change all demo passwords and remove demo accounts before sharing.
- Keep the SQLite database and backups access-restricted.
- Use HTTPS through a properly configured reverse proxy if deployed internally.
- Add CSRF protection, rate limiting, MFA, session expiry, secure cookie flags,
  centralized secrets management, monitoring and tested backups before any
  network deployment.
- Use PostgreSQL, a formal migration framework, an external append-only audit
  store and independent security testing for production.
- Never insert real subscriber identities, live CDRs or real tracking data into
  this prototype.

The audit hash chain detects accidental or unsophisticated modification of
records but is not equivalent to an independently administered WORM store or
HSM-backed signature system.
