# Security & Read-Only Verification

## 1. Threat model

DevOpsSentinel Web runs on an operator workstation, binds to `127.0.0.1`, and exposes a
**read-only** view of a Kubernetes cluster. The realistic threats are:

1. A malicious web page in the same browser attempting to reach the local API.
2. A secret leaking to the browser through logs, errors, exports or evidence.
3. The browser being turned into a generic shell / cluster-mutation proxy.
4. An unbounded operation hanging the workstation or the cluster API server.
5. Credentials being persisted in browser storage.

## 2. Controls

| Threat | Control | Where |
| --- | --- | --- |
| Cross-origin access | Strict CORS allowlist (no wildcard) + origin check on every state-changing request | `config.allowed_origins`, `main.guard` |
| Clickjacking | `X-Frame-Options: DENY`, `frame-ancestors 'none'` | `main.SECURITY_HEADERS` |
| XSS / injection | `Content-Security-Policy` with `default-src 'self'`, `object-src 'none'`, no inline scripts | `main.SECURITY_HEADERS` |
| MIME sniffing | `X-Content-Type-Options: nosniff` | `main.SECURITY_HEADERS` |
| Referrer leakage | `Referrer-Policy: no-referrer` | `main.SECURITY_HEADERS` |
| Oversized requests | `Content-Length` bound (2 MB) on mutating methods | `main.guard` |
| Command injection | argv arrays only, `shell=False` equivalent, DNS-1123 name/context/kind validation | `security.py`, `runner.py` |
| Cluster mutation | Read-only verb guard + operation allowlist + no generic endpoint | `security.assert_read_only`, `sentinel.OPERATIONS` |
| Secret leakage | Independent backend redaction of every stdout/stderr, plus the engine's own redaction | `security.redact_text`, `runner.Run` |
| Path traversal | Evidence reads are confined to the evidence root; identifiers are path-safe | `services/evidence.py` |
| Unbounded work | Per-operation timeouts (≤ 300 s), output cap (8 MB), child termination, TTL cache + single-flight | `config`, `runner`, `cache` |
| Credential persistence | Only theme/panel/table preferences are stored; never tokens, passwords, Secrets or keys | `state/AppContext.tsx` |
| LAN exposure | 127.0.0.1 default; `--listen` requires an explicit `--token` | `devopssentinel-web` |

## 3. Redaction

`security.redact_text()` is applied to **every** subprocess stream before it is cached, returned or
exported. Structured (JSON) lines are redacted token-by-token so the payload stays parseable;
unstructured sensitive lines are dropped wholesale.

Covered: `Authorization`/`Bearer` headers, JWTs (`eyJ…`), `ghp_`/`github_pat_`/`glpat-`/`xox[bp]-`
tokens, `password=`/`token=`/`client_secret=` key-value pairs, URL userinfo (`scheme://user:pass@`),
and PEM private-key blocks.

Proof: `backend/tests/test_security.py` plus `test_api.py::test_secrets_are_redacted_in_api_output`,
which asserts the planted `eyJhbGciOiJIUzI1NiJ9…` token never reaches the API payload while
`[REDACTED]` does appear in the raw stream.

## 4. Read-only verification

```bash
python -m pytest backend/tests/test_security.py -q          # guard + validation
python -m pytest backend/tests/test_api.py -q               # /exec, /shell, /kubectl must 404
(cd frontend && npx playwright test -g "mutation controls") # no Reconcile/Suspend/Resume/Rollback/Upgrade control
```

Three independent layers enforce read-only behaviour:

1. **No generic endpoint.** `/api/v1/exec`, `/api/v1/shell` and `/api/v1/kubectl` do not exist and
   are asserted to return 404.
2. **Operation allowlist.** The browser can only name an id present in `OPERATIONS`
   (`sentinel.py`); unknown ids raise before any process is spawned.
3. **Verb guard.** `assert_read_only()` inspects the final argv and raises `PermissionError` on any
   mutation verb, including `apply`, `create`, `delete`, `patch`, `edit`, `scale`, `replace`,
   `rollout`, `drain`, `cordon`, `taint`, `exec`, `port-forward`, `reconcile`, `suspend`, `resume`,
   `install`, `upgrade`, `uninstall`.

The adapter's kubectl usage is limited to three read-only invocations, each asserted in
`services/kube.py::_ALLOWED`:

```
kubectl config get-contexts -o name
kubectl config current-context
kubectl [--context C] get namespaces -o name
```

## 5. Data handling

* Runtime state lives under `~/.devopssentinel-web` (created with mode `0700` where supported) and
  `~/.devopssentinel` (the engine's own root). Nothing is written into the repository or the
  cluster.
* Evidence previews are read-only and size-bounded.
* Exports are generated server-side from engine values and redacted before download; they are never
  produced by screenshotting a table.
* Audit records store operation id, context, namespace, duration, exit status, record count and
  source — never command output or credentials.

## 6. Known limitations (disclosed)

* The origin allowlist is a string comparison against configured origins. A browser extension that
  strips the `Origin` header on a state-changing request is treated as a non-browser client
  (allowed). This is acceptable for a localhost tool but is not a substitute for authentication.
* `--listen` + `--token` is a deliberate escape hatch for advanced users; the token is not yet
  enforced on every route and LAN mode is **not** recommended. The default configuration never
  exposes the service.
* Live TLS inspection and interactive database/Kafka sessions are intentionally not implemented in
  the browser (see the parity matrix), which removes an entire class of credential-handling risk.
