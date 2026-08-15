# 24–25. Security, Privacy and GDPR

## 24. Security

### Threat model (what actually applies to this system)

| Asset | Threat | Control |
|---|---|---|
| Provider API keys | Leak via repository, logs, client bundle | Server-side only; env/secret manager; secret scanning in CI; keys never reach the client; log redaction filter |
| User account | Credential stuffing, session theft | Argon2id password hashing or OAuth; short-lived access tokens + rotating refresh; rate limiting on auth |
| User location history | Exposure — this is the most sensitive data in the system | Minimisation, coordinate rounding, per-user isolation, encryption at rest, retention limits |
| Sailing log | Cross-user access | Authorisation enforced in the repository layer (every query is user-scoped by construction, not by remembering a `WHERE`) |
| Provider quota | Abuse driving cost or a ban | Per-user and global rate limits; cache-first; circuit breaker |
| The API itself | Injection, SSRF, DoS | Parameterised queries only; strict allow-list of outbound hosts; request size limits; timeouts everywhere |
| Assistant | Prompt injection via POI/user text | Data/instruction separation + numeric grounding check ([07-ai-layer.md](07-ai-layer.md)) |

### Controls by layer

**Transport & headers.** TLS only, HSTS, CSP, `X-Content-Type-Options`, `Referrer-Policy:
no-referrer`, CORS restricted to known origins.

**AuthN/AuthZ.** OAuth 2.1 / OIDC where possible; otherwise email + Argon2id. Access tokens ~15 min,
refresh tokens rotating with reuse detection. Authorisation is deny-by-default; every user-scoped
repository method takes `user_id` as a required argument so that "forgot to filter" is a type error
rather than a data breach.

**Input.** Pydantic validation at the edge; coordinates bounded; dates bounded; `limit` capped;
uploads (GPX traces) parsed with a hardened parser (XML external entities disabled) and size-capped.

**Outbound.** Explicit allow-list of provider hosts — this is the SSRF control and it also stops a
misconfigured adapter from calling somewhere unexpected. Timeouts, bounded retries with jittered
backoff, circuit breaker per provider.

**Secrets.** `.env` for local development only and git-ignored; production secrets from the platform
secret manager; rotation documented; a leaked key is revoked, not renamed.

**Dependencies.** Pinned with lock files, digest-pinned base images, automated vulnerability scanning,
non-root containers, read-only root filesystem where possible.

**Logging.** Structured JSON, correlation IDs, no secrets, no raw coordinates at debug level in
production. Security-relevant events (login, export, deletion) are audit-logged with actor and time.

## 25. Privacy and GDPR

### Data inventory and lawful basis

| Category | Examples | Basis | Retention |
|---|---|---|---|
| Account | email, password hash | Contract | Until deletion |
| Preferences | wind band, profile, boat | Contract | Until deletion |
| Sailing log | dates, spots, routes, ratings, notes | Contract | Until deletion (user-deletable per entry) |
| Derived aggregates | affinity, visited spots | Legitimate interest (the service the user asked for) | Recomputed; deleted with the source |
| Assistant transcripts | utterances, engine payloads | **Consent**, separately revocable | 30 days default, user-configurable, deletable |
| Technical logs | IP, user agent, request IDs | Legitimate interest (security) | 30 days |
| Anonymous telemetry | latency, cache hit rate | Legitimate interest | Aggregated, no user identifier |

### Privacy by design — the concrete decisions

1. **Minimisation is a schema decision.** There is no field for full name, phone number, date of
   birth or address. What is not collected cannot leak.
2. **Coordinate precision reduction.** Cache keys use ~1.2 km geohashes. Analytics never receive
   precise coordinates. Live GPS, if ever added, stays on the device.
3. **Local-first where possible.** An anonymous user's log lives in browser/device storage; a server
   account is opt-in, and the migration path is explicit.
4. **Separation.** Assistant transcripts sit in their own store with their own retention, so revoking
   AI consent deletes a table rather than requiring a scavenger hunt.
5. **No third-party trackers.** No analytics SDKs, no ad networks, no social pixels.
6. **Processors documented.** Weather, geo, routing and LLM providers are listed in the privacy
   policy with what is sent to each. For the default stack, what is sent to a weather provider is a
   *rounded coordinate and a date* — no identifier.

### Data subject rights

| Right | Implementation |
|---|---|
| Access / portability | `POST /v1/me/export` → JSON + GPX archive, generated asynchronously, delivered over an expiring link |
| Erasure | `DELETE /v1/me` → hard delete within 30 days, including backups on their rotation schedule; audit record of the deletion event retained (no personal data) |
| Rectification | Profile and log entries are directly editable |
| Restriction / objection | AI consent, telemetry and account can be toggled independently |
| Automated decision-making | The score is decision *support*, fully explainable by construction (component breakdown), and produces no legal or similarly significant effect |

### Encryption and residency

TLS in transit; database and backup encryption at rest; sensitive columns (assistant transcripts,
notes) encrypted at the application layer with a rotatable key. EU hosting for an EU-facing service so
that no transfer mechanism is needed for the primary store; any non-EU processor (an LLM provider, for
example) is listed with its transfer basis.

### Operational commitments

- Privacy policy and processor list versioned in `docs/legal/` and changed by pull request.
- A breach runbook with a 72-hour notification path.
- A data protection impact assessment before any feature that processes location continuously — a
  live-tracking feature would need one, which is a good reason to keep it out of the near roadmap.
