# Security

necto is pre-release software. Security fixes land on `main`.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private vulnerability reporting
(**Security → Report a vulnerability**) on the repository, and include:

- affected component and version/commit,
- reproduction steps,
- impact you believe it has.

You should get a response within a few days. Thanks for keeping users safe.

## Deployment notes

- **No authentication by default.** The API is meant for `127.0.0.1`. If you expose it, set
  `NECTO_API_KEY` (the SDK sends `X-API-Key`) and put it behind a reverse proxy with TLS.
- **Runs contain prompts and outputs.** Payload snippet fields are truncated by default
  (`store_full` keeps longer values), but treat the database and the UI as sensitive: prompts can
  contain customer data or secrets. Postgres is not encrypted at rest by necto itself.
- **The web UI has no CSP by default**; host it behind a proxy that sets security headers when
  exposing it publicly.
- necto never sends data anywhere except the server you configure.
