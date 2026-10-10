# DevOpsSentinel release build

Build-time only. Nothing here ships inside the runtime payload, and the operator
artifact never executes any of it (section 34).

## Pipeline (section 64)

| Step | Script | Purpose |
|---|---|---|
| 1 | `fetch-components.sh [PLATFORM]` | Download each pinned component and verify its upstream SHA-256. Refuses on mismatch (sections 22, 38). |
| 2 | `build-payload.sh [PLATFORM]` | Stage `bin/` + `components.tsv` + `release-manifest.json`, then tar (sections 21, 64). |
| 3 | `build-self-extracting.sh [PLATFORM]` | Wrap the payload in one self-extracting `devopssentinel` (sections 18, 19, 82). |
| 4 | `test-bundle.sh [ARTIFACT]` | Run the real artifact under an isolated `HOME` and a minimal `PATH` (sections 66-70, 77-81). |

```bash
build/fetch-components.sh linux-amd64
build/build-payload.sh linux-amd64
build/build-self-extracting.sh linux-amd64
build/test-bundle.sh
```

## Pins

`components.lock.tsv` is the single source of truth (section 37). It is
tab-separated; see the header comment for the columns. Never substitute
"latest" — bump a version, re-run the fetch, and commit the digests so the build
stays reproducible (section 65).

Status values:

* `verified` — an upstream SHA-256 is pinned and enforced.
* `pending` — upstream publishes no clean digest; the fetch records one for
  human review and the release stays blocked until it is pinned (section 87).
* `source-required` — no official static Linux binary exists, so bundling means
  choosing a third-party build. That is a supply-chain and licensing decision
  the operator must make explicitly (sections 25, 26, 38, 39). Until a source is
  pinned the engine's fallback hierarchy (section 62) uses the host copy and
  reports the capability as degraded rather than failing.

## Runtime behaviour

The launcher detects the platform, extracts once into
`$HOME/.devopssentinel/bin`, verifies every component against
`components.tsv`, publishes the runtime atomically, and reuses it on later runs
(sections 41-43). The engine then prefers the bundled copy of each tool and
falls back to a host copy only when the operator sets
`DEVOPSSENTINEL_USE_SYSTEM_TOOLS=1` (section 16).
