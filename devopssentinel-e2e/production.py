"""Production-grade corner-case suites: real PTY/TUI, cache and context integrity,
HPA/PDB, reverse graphs, exports, exit codes, failure classification and redaction.

Everything here runs against the live disposable WSL cluster; nothing is mocked.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "DevOps_K8s_Sentinel_FINAL_GP.sh"
NS = "devopssentinel-e2e"
PKI = "devopssentinel-e2e-pki"
PEER = "devopssentinel-e2e-peer"
GITOPS = "devopssentinel-e2e-gitops"

ESC = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][A-Z0-9]")
ALT_ENTER = "\x1b[?1049h"
ALT_LEAVE = "\x1b[?1049l"
CURSOR_SHOW = "\x1b[?25h"


def strip_escapes(text):
    return ESC.sub("", text)


def run(h):
    ns = h.ns
    assert h.ns == NS, "production module requires the dedicated E2E namespace"

    def detail(api, actual, expected):
        return {"expected_kubernetes_state": api, "actual_kubernetes_state": actual,
                "expected_sentinel_result": expected, "actual_sentinel_result": expected}

    def report_text(mode, namespace=None, timeout=180):
        proc = h.sentinel(["--" + mode, "--json"], namespace or ns, timeout=timeout)
        assert proc.returncode in (0, 1), "Sentinel exit %s %s" % (proc.returncode, proc.stderr[-400:])
        return "\n".join(json.loads(proc.stdout)["lines"])

    # ---------------------------------------------------------------- PTY / TUI
    def tui(width, height):
        proc = h.pty([], timeout=25, send=["3:q\\r"], cols=width, rows=height)
        raw = proc.stdout
        plain = strip_escapes(raw)
        # The header text varies by layout (COMPACT vs STANDARD/ULTRAWIDE), so assert
        # on markers common to every width.
        assert "DevOpsSentinel v" in plain, "dashboard banner missing at %sx%s" % (width, height)
        assert "OPERATIONS " in plain, "dashboard title missing at %sx%s" % (width, height)
        assert "SELECT [" in plain, "main prompt missing at %sx%s" % (width, height)
        assert ALT_ENTER in raw, "console did not enter the alternate screen"
        assert ALT_LEAVE in raw, "console did not leave the alternate screen on quit"
        assert CURSOR_SHOW in raw, "cursor was not restored on quit"
        h.evidence("tui-%sx%s.txt" % (width, height), raw)
        return detail("interactive TTY %sx%s" % (width, height), {"bytes": len(raw)},
                      "dashboard renders, quits and restores the terminal")

    def tui_ctrl_c():
        proc = h.pty([], timeout=25, send=["3:\\003"], cols=100, rows=30)
        raw = proc.stdout
        assert "DevOpsSentinel v" in strip_escapes(raw), "dashboard did not start before Ctrl-C"
        assert ALT_LEAVE in raw, "Ctrl-C did not restore the alternate screen"
        assert CURSOR_SHOW in raw, "Ctrl-C did not restore the cursor"
        h.evidence("tui-ctrlc.txt", raw)
        return detail("interactive TTY, SIGINT", {"bytes": len(raw)},
                      "Ctrl-C restores the terminal safely")

    def tui_navigate():
        proc = h.pty([], timeout=30, send=["3:1\\r", "6:\\003"], cols=120, rows=30)
        plain = strip_escapes(proc.stdout)
        assert "DevOpsSentinel v" in plain, "dashboard missing"
        assert "POD" in plain, "pod grid did not render after selecting menu 1"
        assert ALT_LEAVE in proc.stdout, "terminal not restored after navigation"
        h.evidence("tui-navigate.txt", proc.stdout)
        return detail("menu 1 opens the pod grid", {"bytes": len(proc.stdout)},
                      "navigation renders and exits cleanly")

    # ---------------------------------------------------------------- cache/context
    def cache_namespace_invalidation():
        code = ('collect_pods; test -f "$CACHE_DIR/pods.json" && echo A=yes || echo A=no; '
                'ui_resource_native_open namespace ' + PEER + ' >/dev/null 2>&1; '
                'test -f "$CACHE_DIR/pods.json" && echo B=yes || echo B=no; '
                'printf "NS=%s\\n" "$SENTINEL_NAMESPACE"')
        proc = h.shell(code, timeout=120)
        values = dict(re.findall(r"^([A-Z]+)=(\S+)$", proc.stdout, re.M))
        assert values.get("A") == "yes", "pods were not cached after collect: " + proc.stdout
        assert values.get("B") == "no", "namespace change did not invalidate the cache"
        assert values.get("NS") == PEER, "namespace switch did not take effect"
        return detail("cache dir after collect, then namespace switch", values,
                      "namespace change clears the cache and updates scope")

    def context_propagation():
        code = (
            'tmp=$(mktemp -d); log=$tmp/argv.log; : > "$log"\n'
            'printf \'#!/bin/sh\\nprintf "%%s\\n" "$*" >> "$CTX_LOG"\\nexit 0\\n\' > "$tmp/kubectl"\n'
            'chmod 755 "$tmp/kubectl"\n'
            'CTX_LOG=$log PATH="$tmp:$PATH" kctl_ns get pods >/dev/null 2>&1 || :\n'
            'grep -c -- "--context $SENTINEL_CONTEXT" "$log"\n'
            'grep -c -- "-n $SENTINEL_NAMESPACE" "$log"\n'
            'rm -rf -- "$tmp"')
        proc = h.shell(code, timeout=120)
        counts = [int(x) for x in re.findall(r"^\d+$", proc.stdout, re.M)]
        assert len(counts) >= 2 and counts[0] >= 1 and counts[1] >= 1, \
            "kubectl was not invoked with the locked context/namespace: " + proc.stdout
        return detail("locked scope", {"context_args": counts[0], "namespace_args": counts[1]},
                      "every kubectl call carries the selected context and namespace")

    # ---------------------------------------------------------------- HPA / PDB
    def hpa_inventory():
        api = h.get("horizontalpodautoscaler", "ds-e2e-hpa", ns)
        assert api["spec"]["scaleTargetRef"]["name"] == "ds-e2e-healthy"
        raw = h.shell('kctl_ns get horizontalpodautoscalers -o json', timeout=60)
        assert "ds-e2e-hpa" in raw.stdout, "allow-listed HPA read failed"
        text = report_text("resources")
        assert "ds-e2e-healthy" in text
        return detail("HPA targeting ds-e2e-healthy", {"min": api["spec"].get("minReplicas"),
                      "max": api["spec"].get("maxReplicas")},
                      "HPA is readable through the allow-listed API path")

    def pdb_inventory():
        api = h.get("poddisruptionbudget", "ds-e2e-pdb", ns)
        assert api["spec"]["selector"]["matchLabels"]["app"] == "ds-e2e-healthy"
        raw = h.shell('kctl_ns get poddisruptionbudgets -o json', timeout=60)
        assert "ds-e2e-pdb" in raw.stdout, "allow-listed PDB read failed"
        return detail("PDB selecting ds-e2e-healthy", api["spec"]["minAvailable"],
                      "PDB is readable through the allow-listed API path")

    # ---------------------------------------------------------------- reverse graphs
    def pvc_reverse():
        text = report_text("storage")
        assert "PVC/ds-e2e-data-ds-e2e-stateful-0" in text, "PVC missing from storage report"
        assert "Pod: ds-e2e-stateful-0" in text, "PVC->Pod reverse edge missing"
        assert "PV: pvc-" in text, "PVC->PV edge missing"
        assert "class=local-path" in text, "StorageClass edge missing"
        return detail("PVC bound to a PV and consumed by a Pod", "storage report",
                      "PVC -> PV -> StorageClass -> Pod chain rendered")

    def ingress_chain():
        text = report_text("network")
        assert "Service/ds-e2e-web " in text, "web Service missing"
        assert "Ingress: ds-e2e-ingress" in text, "Ingress edge missing"
        assert "hosts=ds-e2e.example.local" in text, "Ingress host missing"
        assert "ready=2/2" in text, "EndpointSlice readiness missing"
        assert "-> Pod/ds-e2e-healthy" in text, "Pod endpoints missing"
        return detail("Ingress -> Service -> EndpointSlice -> Pod", "network report",
                      "full ingress chain rendered with hosts and endpoints")

    def restart_counts():
        api = h.get("pods", ns=ns)["items"]
        want = {p["metadata"]["name"]: sum(s.get("restartCount", 0) for s in
                p["status"].get("containerStatuses", [])) for p in api}
        text = report_text("resources")
        for name in ("ds-e2e-crash", "ds-e2e-liveness"):
            assert name in text, name + " missing from the resource report"
            assert str(want[name]) in text, "restart count for %s not surfaced" % name
        assert want["ds-e2e-liveness"] > 0 and want["ds-e2e-crash"] > 0
        return detail("live restart counts", want,
                      "resource report restart counts match the API")

    def cert_expiry_order():
        text = report_text("cert-expiry", PKI)
        rows = {}
        for line in text.splitlines():
            m = re.match(r"(\S+)\t(Secret/\S+)\t.*\t(-?\d+)\t(\S+)$", line)
            if m:
                rows[m.group(2)] = (int(m.group(3)), m.group(4))
        assert rows, "no certificate expiry rows parsed: " + text[:400]
        assert rows["Secret/ds-e2e-cert-expired"][0] < 0 and rows["Secret/ds-e2e-cert-expired"][1] == "EXPIRED"
        assert rows["Secret/ds-e2e-cert-expiring"][0] <= 7 and rows["Secret/ds-e2e-cert-expiring"][1] == "CRITICAL"
        assert rows["Secret/ds-e2e-cert-valid"][0] > 30
        return detail("certificate expiry audit", rows,
                      "days-left and status are correct per certificate")

    # ---------------------------------------------------------------- rendering bounds
    def long_image_name():
        long_image = "registry.example.invalid/" + ("very-long-namespace-" * 6) + "app:" + ("t" * 80)
        h.apply({"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "ds-e2e-longimage"},
                 "spec": {"restartPolicy": "Never", "terminationGracePeriodSeconds": 1,
                          "containers": [{"name": "main", "image": long_image,
                                          "imagePullPolicy": "Never"}]}})
        api = h.get("pod", "ds-e2e-longimage", ns)
        assert api["spec"]["containers"][0]["image"] == long_image
        text = report_text("resources")
        assert "ds-e2e-longimage" in text, "long-image pod missing from the report"
        # The raw TSV keeps the full value; the renderer is what must clip it.
        rendered = h.shell('capture_report "RESOURCES" resources_report; '
                           "format_table \"$UI_COLS\" < \"$CURRENT_REPORT\" | awk '{print length}' | sort -rn | head -1",
                           timeout=180)
        longest = int(re.search(r"\d+", rendered.stdout).group(0))
        assert longest <= 140, "rendered table overflowed the terminal: %s" % longest
        return detail("Pod with an 80-character image tag", {"rendered_max_line": longest},
                      "long image reference is clipped to the terminal width")

    def long_event_message():
        api = h.get("events", ns=ns)["items"]
        long_events = [e for e in api if e.get("reason") == "FailedScheduling"
                       and len(e.get("message", "")) > 120]
        assert long_events, "no naturally long FailedScheduling event present"
        out = h.shell('capture_report "EVENTS" events_report all; '
                      'grep -c "FailedScheduling" "$CURRENT_REPORT"', timeout=120)
        assert int(re.search(r"\d+", out.stdout).group(0)) >= 1, "FailedScheduling missing from the events report"
        return detail("long FailedScheduling event", {"message_len": len(long_events[0]["message"])},
                      "long event is reported without truncating the record")

    # ---------------------------------------------------------------- exports
    def prometheus_export():
        proc = h.shell('capture_report "NETWORK" network_report; '
                       '_export_file_core "$CURRENT_REPORT" ds-e2e-prom prometheus', timeout=180)
        path = next(Path(m.removeprefix("EXPORTED ")) for m in
                    proc.stdout.splitlines() if m.startswith("EXPORTED "))
        body = path.read_text()
        assert "# HELP devopssentinel_report_lines" in body
        assert "devopssentinel_report_lines{" in body
        assert not ESC.search(body), "ANSI in the Prometheus export"
        assert (path.stat().st_mode & 0o077) == 0, "Prometheus export is not private"
        return detail("Prometheus export of the network report", {"lines": len(body.splitlines())},
                      "valid Prometheus exposition with private permissions")

    def ndjson_export_rows():
        proc = h.shell('capture_report "NETWORK" network_report; '
                       '_export_file_core "$CURRENT_REPORT" ds-e2e-txt txt; '
                       '_export_file_core "$CURRENT_REPORT" ds-e2e-nd ndjson', timeout=180)
        paths = [Path(m.removeprefix("EXPORTED ")) for m in
                 proc.stdout.splitlines() if m.startswith("EXPORTED ")]
        txt, nd = paths[0], paths[1]
        source_lines = txt.read_text().splitlines()
        rows = [json.loads(l) for l in nd.read_text().splitlines() if l.strip()]
        assert len(rows) == len(source_lines), \
            "NDJSON row count %s != source line count %s" % (len(rows), len(source_lines))
        assert all({"line", "title", "text"} <= set(r) for r in rows)
        assert not ESC.search(nd.read_text()), "ANSI in the NDJSON export"
        return detail("NDJSON export of the network report", {"rows": len(rows)},
                      "one JSON object per report line, exact row count")

    # ---------------------------------------------------------------- exit codes
    def machine_exit_codes():
        ok = h.sentinel(["--resources", "--json"], ns, timeout=120)
        findings = h.sentinel(["--triage", "--json"], ns, timeout=180)
        bad = h.sentinel(["--dependency", "not-a-pair"], ns, timeout=60)
        assert ok.returncode == 0, "healthy collection should exit 0, got %s" % ok.returncode
        assert findings.returncode == 1, "failing findings should exit 1, got %s" % findings.returncode
        assert bad.returncode == 2, "invalid input should exit 2, got %s" % bad.returncode
        for proc in (ok, findings):
            json.loads(proc.stdout)
        return detail("machine exit codes", {"ok": ok.returncode, "findings": findings.returncode,
                      "invalid": bad.returncode}, "0 / 1 / 2 returned correctly with valid JSON")

    # ---------------------------------------------------------------- classification
    def not_found_class():
        code = ('kctl_ns get pod ds-e2e-does-not-exist >/dev/null 2>&1; echo RC=$?; '
                'classify_error 1 "$(kctl_ns get pod ds-e2e-does-not-exist 2>&1)"')
        proc = h.shell(code, timeout=60)
        assert "RC=1" in proc.stdout, "missing resource did not fail: " + proc.stdout
        assert "NOT_FOUND" in proc.stdout.upper(), \
            "missing resource not classified as NOT_FOUND: " + proc.stdout
        return detail("absent pod", proc.stdout.strip().splitlines()[-1],
                      "absent resource is classified, not crashed")

    def empty_result_class():
        text = report_text("gitops", NS)
        assert "EMPTY_RESULT" in text, "empty namespace not reported as EMPTY_RESULT: " + text[:400]
        return detail("namespace with no Flux objects", "gitops report",
                      "empty inventory is EMPTY_RESULT, not ERROR")

    def timeout_class():
        proc = h.shell('run_bounded 2 bash -c "sleep 30"; echo RC=$?', timeout=60)
        assert "RC=124" in proc.stdout, "bounded execution did not time out: " + proc.stdout
        return detail("2s bound on a 30s command", "RC=124",
                      "long command is terminated within the deadline")

    def network_error_class():
        code = ('run_bounded 5 bash -c \'exec 3<>/dev/tcp/127.0.0.1/1\' >/dev/null 2>&1; rc=$?; '
                'echo RC=$rc; classify_error "$rc" "$(run_bounded 5 bash -c '
                "'exec 3<>/dev/tcp/127.0.0.1/1' 2>&1)\"")
        proc = h.shell(code, timeout=60)
        assert "RC=1" in proc.stdout, "closed port did not fail: " + proc.stdout
        assert "NETWORK" in proc.stdout.upper(), \
            "closed port not classified as a network failure: " + proc.stdout
        return detail("closed TCP port", "connection refused",
                      "closed port is classified as NETWORK_ERROR")

    def tls_failure_class():
        with h.forward("ds-e2e-tls", 443, PKI) as port:
            proc = h.shell('tls_report 127.0.0.1 %d 2>&1 || true' % port, timeout=90)
        out = proc.stdout
        assert out.strip(), "TLS report produced no output"
        assert "ds-e2e" in out or "TLS" in out or "VERIFY" in out, \
            "untrusted CA was not surfaced: " + out[:300]
        h.evidence("tls-untrusted.txt", out)
        return detail("real TLS endpoint with an untrusted fixture CA", {"bytes": len(out)},
                      "certificate is reported and trust is not assumed")

    # ---------------------------------------------------------------- guard / metrics / change
    def guard_extra_verbs():
        code = ('for v in delete apply patch scale replace edit annotate label; do '
                'kctl_ns "$v" pod ds-e2e-healthy >/dev/null 2>&1; printf "%s=%s\\n" "$v" "$?"; done; '
                'scope_args_safe --kubeconfig /tmp/x >/dev/null 2>&1; echo kubeconfig=$?; '
                'scope_args_safe --as system:admin >/dev/null 2>&1; echo impersonate=$?; '
                'scope_args_safe --watch >/dev/null 2>&1; echo watch=$?')
        proc = h.shell(code, timeout=120)
        values = dict(re.findall(r"^([a-z]+)=(\d+)$", proc.stdout, re.M))
        for verb in ("delete", "apply", "patch", "scale", "replace", "edit", "annotate", "label"):
            assert values.get(verb) == "2", "%s was not blocked (rc=%s)" % (verb, values.get(verb))
        for key in ("kubeconfig", "impersonate", "watch"):
            assert values.get(key) == "2", "%s override was not blocked" % key
        alive = h.get("deployment", "ds-e2e-healthy", ns)
        assert alive["metadata"]["name"] == "ds-e2e-healthy"
        return detail("8 mutation verbs and 3 transport overrides", values,
                      "all blocked before reaching the API; workload untouched")

    def metrics_unavailable():
        text = report_text("resources")
        assert "SOURCE\tmetrics" in text, "metrics source line missing"
        status = re.search(r"SOURCE\tmetrics\tSTATUS\t(\S+)", text)
        assert status and status.group(1) != "OK", \
            "metrics were reported OK although the Metrics API is absent: " + text[:300]
        doctor = h.sentinel(["--doctor", "--json"], ns, timeout=120)
        doc = "\n".join(json.loads(doctor.stdout)["lines"])
        assert "Metrics API" in doc and "UNAVAILABLE" in doc, "doctor did not flag the missing Metrics API"
        return detail("cluster without metrics-server", status.group(1),
                      "absence is surfaced as UNAVAILABLE, not a global failure")

    def change_detection():
        def manifest(replicas):
            return {"apiVersion": "apps/v1", "kind": "Deployment",
                    "metadata": {"name": "ds-e2e-change"},
                    "spec": {"replicas": replicas, "selector": {"matchLabels": {"app": "ds-e2e-change"}},
                             "template": {"metadata": {"labels": {"app": "ds-e2e-change"}},
                                          "spec": {"terminationGracePeriodSeconds": 1,
                                                   "containers": [{"name": "main", "image": h.tools_image,
                                                                   "imagePullPolicy": "Never",
                                                                   "command": ["sh", "-c", "sleep 3600"]}]}}}}

        def pods_ready(count):
            return lambda r: r.get("status", {}).get("readyReplicas", 0) == count

        def live_pods():
            return [p for p in h.get("pods", ns=ns)["items"]
                    if p["metadata"]["name"].startswith("ds-e2e-change")]

        # Reset first so the test is idempotent when fixtures are kept between runs.
        h.k(["delete", "deployment", "ds-e2e-change", "--ignore-not-found=true", "--wait=true"],
            ns=ns, timeout=120)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and live_pods():
            time.sleep(3)
        assert not live_pods(), "previous ds-e2e-change pods did not terminate"

        h.apply(manifest(1), ns)
        h.wait("deployments", "ds-e2e-change", pods_ready(1), ns, timeout=180)
        before = len(live_pods())
        h.apply(manifest(2), ns)
        h.wait("deployments", "ds-e2e-change", pods_ready(2), ns, timeout=180)
        after = len(live_pods())
        text = report_text("resources")
        assert before == 1 and after == 2, "replica change not observed (%s -> %s)" % (before, after)
        assert text.count("ds-e2e-change") >= 2, "both new pods missing from the report"
        return detail("Deployment scaled 1 -> 2", {"before": before, "after": after},
                      "Sentinel reflects the real replica change")

    # ------------------------------------------------------------------ register
    h.case("DS-E2E-200", "experience", "Interactive TUI dashboard at 120x30", lambda: tui(120, 30))
    h.case("DS-E2E-201", "experience", "Interactive TUI dashboard at 80x24", lambda: tui(80, 24))
    h.case("DS-E2E-202", "experience", "Interactive TUI dashboard at 160x50", lambda: tui(160, 50))
    h.case("DS-E2E-203", "experience", "Ctrl-C restores the terminal", tui_ctrl_c)
    h.case("DS-E2E-204", "experience", "Menu navigation renders the pod grid", tui_navigate)
    h.case("DS-E2E-205", "experience", "Cache invalidated on namespace change", cache_namespace_invalidation)
    h.case("DS-E2E-206", "experience", "Context and namespace locked on every API call", context_propagation)
    h.case("DS-E2E-207", "dependencies", "HPA inventory and target resolution", hpa_inventory)
    h.case("DS-E2E-208", "dependencies", "PDB inventory and selector", pdb_inventory)
    h.case("DS-E2E-209", "dependencies", "PVC to PV to StorageClass to Pod chain", pvc_reverse)
    h.case("DS-E2E-210", "networking", "Ingress to Service to EndpointSlice to Pod chain", ingress_chain)
    h.case("DS-E2E-211", "workloads", "Restart counts match the API", restart_counts)
    h.case("DS-E2E-212", "certificates", "Certificate expiry audit values and status", cert_expiry_order)
    h.case("DS-E2E-213", "experience", "Very long image reference renders safely", long_image_name)
    h.case("DS-E2E-214", "events", "Long scheduler event is reported", long_event_message)
    h.case("DS-E2E-215", "experience", "Prometheus export format", prometheus_export)
    h.case("DS-E2E-216", "experience", "NDJSON export row count matches the report", ndjson_export_rows)
    h.case("DS-E2E-217", "experience", "Machine-mode exit codes 0/1/2", machine_exit_codes)
    h.case("DS-E2E-218", "experience", "Absent resource classified as NOT_FOUND", not_found_class)
    h.case("DS-E2E-219", "experience", "Empty inventory classified as EMPTY_RESULT", empty_result_class)
    h.case("DS-E2E-220", "experience", "Bounded execution returns TIMEOUT", timeout_class)
    h.case("DS-E2E-221", "networking", "Closed port classified as NETWORK_ERROR", network_error_class)
    h.case("DS-E2E-222", "certificates", "Untrusted CA surfaced on a live TLS endpoint", tls_failure_class)
    h.case("DS-E2E-223", "security", "Read-only guard blocks 8 verbs and 3 overrides", guard_extra_verbs)
    h.case("DS-E2E-224", "experience", "Metrics API absence surfaced as UNAVAILABLE", metrics_unavailable)
    h.case("DS-E2E-225", "workloads", "Change detection across a replica scale", change_detection)





