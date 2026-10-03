"""Real X.509/Secret/Pod/TLS acceptance cases for the isolated WSL cluster.

Private keys exist only in memory and labelled test Secrets. Evidence contains
public certificate metadata, resource references, and Sentinel output only.
"""

from __future__ import annotations

import base64
import contextlib
import copy
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import tempfile


NAMESPACE = "devopssentinel-e2e-pki"
DOMAIN = "certificates"
TLS_SERVER = r'''import http.server, ssl
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"DevOpsSentinel isolated TLS fixture\n"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_args):
        pass
server = http.server.ThreadingHTTPServer(("0.0.0.0", 8443), Handler)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.minimum_version = ssl.TLSVersion.TLSv1_2
context.load_cert_chain("/etc/tls/tls.crt", "/etc/tls/tls.key")
server.socket = context.wrap_socket(server.socket, server_side=True)
server.serve_forever()
'''


def _crypto():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    return x509, hashes, serialization, rsa, ExtendedKeyUsageOID, NameOID


def generate_certificates():
    """Generate valid, historical, future, SAN, CA and chain certificates."""
    x509, hashes, serialization, rsa, eku, oid = _crypto()
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

    def issue(cn, issuer=None, days=180, start=-1, ca=False, sans=()):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(oid.COMMON_NAME, cn)])
        issuer_cert, issuer_key = issuer if issuer else (None, key)
        builder = (x509.CertificateBuilder().subject_name(name)
                   .issuer_name(issuer_cert.subject if issuer_cert else name)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now + dt.timedelta(days=start))
                   .not_valid_after(now + dt.timedelta(days=days))
                   .add_extension(x509.BasicConstraints(ca=ca, path_length=1 if ca else None), True)
                   .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
                   .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()), False)
                   .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                                                key_encipherment=not ca, data_encipherment=False,
                                                key_agreement=False, key_cert_sign=ca,
                                                crl_sign=ca, encipher_only=False, decipher_only=False), True))
        if not ca:
            builder = builder.add_extension(x509.ExtendedKeyUsage([eku.SERVER_AUTH]), False)
        if sans:
            names = [x509.IPAddress(ipaddress.ip_address(value)) if kind == "IP"
                     else x509.DNSName(value) for kind, value in sans]
            builder = builder.add_extension(x509.SubjectAlternativeName(names), False)
        return builder.sign(issuer_key, hashes.SHA256()), key

    root = issue("ds-e2e-root", days=3650, ca=True)
    intermediate = issue("ds-e2e-intermediate", root, days=730, ca=True)
    sans = (("DNS", "ds-e2e.example.local"), ("DNS", "ds-e2e-web"),
            ("DNS", "ds-e2e-web.devopssentinel-e2e.svc"), ("IP", "127.0.0.1"))
    pairs = {"root": root, "intermediate": intermediate,
             "valid": issue("ds-e2e.example.local", intermediate, sans=sans),
             "expiring": issue("ds-e2e-expiring", intermediate, days=5, sans=sans),
             "expired": issue("ds-e2e-expired", intermediate, days=-2, start=-30, sans=sans),
             "future": issue("ds-e2e-future", intermediate, days=90, start=2, sans=sans),
             "rotated": issue("ds-e2e.example.local", intermediate, days=365, sans=sans),
             "mismatch": issue("ds-e2e-mismatch", intermediate, days=200, sans=sans)}
    result = {}
    for name, (cert, key) in pairs.items():
        result[name] = {"certificate": cert,
                        "pem": cert.public_bytes(serialization.Encoding.PEM),
                        "key": key.private_bytes(serialization.Encoding.PEM,
                                                 serialization.PrivateFormat.PKCS8,
                                                 serialization.NoEncryption())}
    return result


def certificate_metadata(pem):
    x509, hashes, *_ = _crypto()
    cert = x509.load_pem_x509_certificate(pem)
    fingerprint = cert.fingerprint(hashes.SHA256()).hex().upper()
    try:
        sans = [str(item.value) for item in cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value]
    except x509.ExtensionNotFound:
        sans = []
    return {"subject": cert.subject.rfc4514_string(), "issuer": cert.issuer.rfc4514_string(),
            "not_before": cert.not_valid_before.isoformat() + "Z",
            "not_after": cert.not_valid_after.isoformat() + "Z", "serial": format(cert.serial_number, "X"),
            "sha256": ":".join(fingerprint[i:i+2] for i in range(0, len(fingerprint), 2)), "sans": sans}


@contextlib.contextmanager
def trust_environment(root, empty_directory):
    previous = {name: os.environ.get(name) for name in ("SSL_CERT_FILE", "SSL_CERT_DIR")}
    os.environ["SSL_CERT_FILE"] = str(root)
    os.environ["SSL_CERT_DIR"] = str(empty_directory)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def run(h):
    try:
        fixtures = generate_certificates()
    except ImportError:
        h.block("Python cryptography is required to generate real historical X.509 fixtures")
        return
    with tempfile.TemporaryDirectory(prefix=".devopssentinel-pki-", dir=Path.home()) as temporary:
        _run(h, fixtures, Path(temporary))


def _run(h, fixtures, temporary):
    ns = NAMESPACE
    labels = dict(h.labels)
    app_labels = {**labels, "app": "ds-e2e-tls"}
    root_path = temporary / "root.pem"
    root_path.write_bytes(fixtures["root"]["pem"])
    (temporary / "intermediate.pem").write_bytes(fixtures["intermediate"]["pem"])
    (temporary / "valid.pem").write_bytes(fixtures["valid"]["pem"])
    (temporary / "empty-trust").mkdir()
    observed = []
    cached = {}

    def record(name, result):
        text = result.stdout + ("\n" + result.stderr if result.stderr else "")
        assert "PRIVATE KEY-----" not in text, "private key marker in Sentinel output"
        assert "-----BEGIN CERTIFICATE-----" not in text, "raw certificate escaped metadata projection"
        observed.append(text)
        h.evidence(name, {"returncode": result.returncode, "output": text})
        return text

    def sentinel_report(name, args):
        if name not in cached:
            cached[name] = record(name, h.sentinel(args, ns=ns, timeout=120))
        return cached[name]

    def inventory():
        return sentinel_report("pki-inventory", ["--certificates", "--no-color"])

    def expiry():
        return sentinel_report("pki-expiry", ["--cert-expiry", "--no-color"])

    def secret_manifest(name, fixture, full_chain=True):
        entry = fixtures[fixture]
        pem = entry["pem"]
        if full_chain and fixture not in ("root", "intermediate"):
            pem += fixtures["intermediate"]["pem"]
        data = {"tls.crt": pem, "tls.key": entry["key"], "ca.crt": fixtures["root"]["pem"],
                "reference": b"synthetic-pki-reference-only"}
        return {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": name, "labels": labels},
                "type": "kubernetes.io/tls", "data": {key: base64.b64encode(value).decode() for key, value in data.items()}}

    def truth(name):
        obj = h.get("secret", name, ns=ns)
        assert obj["type"] == "kubernetes.io/tls", "unexpected Secret type"
        pem = base64.b64decode(obj["data"]["tls.crt"])
        metadata = certificate_metadata(pem)
        h.evidence(name + "-certificate-truth", {"name": name, "namespace": ns, **metadata})
        return metadata

    def check_expiry(name, expected):
        metadata = truth(name)
        row = next((row for row in expiry().splitlines() if f"\tSecret/{name}\t" in row), "")
        assert row, f"missing expiry row for {name}"
        assert row.endswith("\t" + expected), f"expected {expected}; observed {row}"
        return {"certificate": metadata, "sentinel_row": row}

    for suffix, fixture, full_chain in (("valid", "valid", True), ("duplicate", "valid", True),
                                        ("expiring", "expiring", True), ("expired", "expired", True),
                                        ("future", "future", True), ("incomplete", "valid", False),
                                        ("root", "root", False), ("intermediate", "intermediate", False),
                                        ("mismatch", "mismatch", True)):
        h.apply(secret_manifest("ds-e2e-cert-" + suffix, fixture, full_chain), ns=ns)
    h.apply({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "ds-e2e-tls-server", "labels": labels},
             "data": {"server.py": TLS_SERVER}}, ns=ns)
    deployment = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "ds-e2e-tls", "labels": labels},
                  "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "ds-e2e-tls"}},
                           "template": {"metadata": {"labels": app_labels}, "spec": {
                               "automountServiceAccountToken": False,
                               "containers": [{"name": "tls", "image": h.tools_image, "imagePullPolicy": "Never",
                                               "command": ["python3", "/app/server.py"], "ports": [{"containerPort": 8443}],
                                               "env": [{"name": "E2E_CERT_REFERENCE", "valueFrom": {"secretKeyRef": {"name": "ds-e2e-cert-valid", "key": "reference"}}}],
                                               "resources": {"requests": {"cpu": "10m", "memory": "32Mi"}, "limits": {"cpu": "200m", "memory": "96Mi"}},
                                               "readinessProbe": {"tcpSocket": {"port": 8443}, "periodSeconds": 2},
                                               "volumeMounts": [{"name": "tls", "mountPath": "/etc/tls", "readOnly": True}, {"name": "script", "mountPath": "/app", "readOnly": True}]}],
                               "volumes": [{"name": "tls", "secret": {"secretName": "ds-e2e-cert-valid"}}, {"name": "script", "configMap": {"name": "ds-e2e-tls-server"}}]}}}}
    h.apply(deployment, ns=ns)
    h.apply({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "ds-e2e-tls", "labels": labels},
             "spec": {"selector": {"app": "ds-e2e-tls"}, "ports": [{"name": "https", "port": 443, "targetPort": 8443}]}}, ns=ns)
    for suffix, secret in (("match", "ds-e2e-cert-valid"), ("mismatch", "ds-e2e-cert-mismatch")):
        h.apply({"apiVersion": "networking.k8s.io/v1", "kind": "Ingress", "metadata": {"name": "ds-e2e-tls-" + suffix, "labels": labels},
                 "spec": {"tls": [{"hosts": ["ds-e2e.example.local"], "secretName": secret}],
                          "rules": [{"host": "ds-e2e.example.local", "http": {"paths": [{"path": "/", "pathType": "Prefix", "backend": {"service": {"name": "ds-e2e-tls", "port": {"number": 443}}}}]}}]}}, ns=ns)

    def ready():
        return h.wait("deployment", "ds-e2e-tls", lambda obj: obj.get("status", {}).get("availableReplicas") == 1
                      and obj.get("status", {}).get("updatedReplicas") == 1
                      and obj.get("status", {}).get("replicas") == 1
                      and obj.get("status", {}).get("observedGeneration", 0) >= obj["metadata"]["generation"], ns=ns, timeout=120)

    def valid():
        metadata = truth("ds-e2e-cert-valid")
        output = inventory()
        assert "[OK] ds-e2e-cert-valid" in output
        for value in (metadata["sha256"], "notBefore=", "notAfter=", "serial=", "issuer=", "subject="):
            assert value in output, f"certificate metadata absent: {value}"
        return check_expiry("ds-e2e-cert-valid", "HEALTHY")

    def expired():
        result = check_expiry("ds-e2e-cert-expired", "EXPIRED")
        path = temporary / "expired.pem"
        path.write_bytes(fixtures["expired"]["pem"])
        independent = h.command(["openssl", "x509", "-in", str(path), "-noout", "-checkend", "0"])
        assert independent.returncode == 1, "independent openssl expiry check did not fail"
        h.evidence("pki-expired-openssl", independent.stdout)
        return result

    def sans():
        metadata = truth("ds-e2e-cert-valid")
        for item in metadata["sans"]:
            assert item in inventory(), f"SAN missing from Sentinel: {item}"
        return metadata

    def duplicates():
        first, second = truth("ds-e2e-cert-valid"), truth("ds-e2e-cert-duplicate")
        assert first["sha256"] == second["sha256"]
        result = h.function("certificate_duplicate_report", [], ns=ns)
        text = record("pki-duplicate-fingerprints", result)
        assert result.returncode == 0
        row = next((row for row in text.splitlines() if row.startswith("DUPLICATE ") and first["sha256"] in row), "")
        assert "Secret/ds-e2e-cert-valid" in row and "Secret/ds-e2e-cert-duplicate" in row, "duplicate identity group absent"
        return {"sha256": first["sha256"], "sentinel_row": row}

    def chain():
        metadata = truth("ds-e2e-cert-valid")
        independent = h.command(["openssl", "verify", "-CAfile", str(root_path), "-untrusted", str(temporary / "intermediate.pem"), str(temporary / "valid.pem")])
        assert independent.returncode == 0, independent.stderr
        h.evidence("pki-chain-openssl", independent.stdout)
        result = h.function("certificate_trust_secret_report", ["ds-e2e-cert-valid"], ns=ns)
        text = record("pki-full-chain", result)
        assert result.returncode == 0 and "VERIFIED AGAINST ca.crt" in text
        assert re.search(r"CHAIN LENGTH\s*:\s*2", text)
        return metadata

    def incomplete():
        truth("ds-e2e-cert-incomplete")
        independent = h.command(["openssl", "verify", "-CAfile", str(root_path), str(temporary / "valid.pem")])
        assert independent.returncode != 0, "leaf unexpectedly verified without intermediate"
        h.evidence("pki-incomplete-openssl", independent.stdout + independent.stderr)
        result = h.function("certificate_trust_secret_report", ["ds-e2e-cert-incomplete"], ns=ns)
        text = record("pki-incomplete-chain", result)
        assert result.returncode == 1 and "VERIFY_FAILED" in text

    def self_issued():
        for suffix in ("root", "intermediate"):
            truth("ds-e2e-cert-" + suffix)
            result = h.function("certificate_trust_secret_report", ["ds-e2e-cert-" + suffix], ns=ns)
            text = record("pki-trust-" + suffix, result)
            assert result.returncode == 0 and "VERIFIED AGAINST ca.crt" in text
            assert re.search(r"SELF-ISSUED\s*:\s*" + ("YES" if suffix == "root" else "NO"), text)

    def mounts():
        ready()
        pods = json.loads(h.k(["get", "pods", "-l", "app=ds-e2e-tls", "-o", "json"], ns=ns).stdout)["items"]
        pod = next(pod for pod in pods if any(condition["type"] == "Ready" and condition["status"] == "True" for condition in pod.get("status", {}).get("conditions", [])))
        container = pod["spec"]["containers"][0]
        assert any(mount["mountPath"] == "/etc/tls" for mount in container["volumeMounts"])
        assert container["env"][0]["valueFrom"]["secretKeyRef"]["name"] == "ds-e2e-cert-valid"
        replicas = h.get("replicaset", pod["metadata"]["ownerReferences"][0]["name"], ns=ns)
        assert replicas["metadata"]["ownerReferences"][0]["name"] == "ds-e2e-tls"
        h.evidence("pki-consumer-truth", {"pod": pod["metadata"]["name"], "deployment": "ds-e2e-tls", "mount": "/etc/tls", "secret": "ds-e2e-cert-valid", "env_reference": "E2E_CERT_REFERENCE"})
        text = record("pki-mounts", h.function("cert_mounts_report", [], ns=ns))
        assert "ds-e2e-cert-valid" in text and pod["metadata"]["name"] in text and "/etc/tls" in text
        dependencies = record("pki-pod-dependencies", h.sentinel(["--dependency", "Pod/" + pod["metadata"]["name"]], ns=ns))
        assert "ds-e2e-cert-valid" in dependencies and ("SecretRef" in dependencies or "env" in dependencies.lower())

    def endpoint_truth(port):
        context = ssl.create_default_context(cafile=str(root_path))
        with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
            with context.wrap_socket(raw, server_hostname="127.0.0.1") as wrapped:
                certificate = ssl.DER_cert_to_PEM_cert(wrapped.getpeercert(binary_form=True)).encode()
                metadata = certificate_metadata(certificate)
                metadata["protocol"] = wrapped.version()
                h.evidence("pki-live-certificate-truth", metadata)
                return metadata

    def compare(mismatch=False):
        ready()
        name = "ds-e2e-cert-mismatch" if mismatch else "ds-e2e-cert-valid"
        ingress = h.get("ingress", "ds-e2e-tls-mismatch" if mismatch else "ds-e2e-tls-match", ns=ns)
        assert ingress["spec"]["tls"][0]["secretName"] == name
        metadata = truth(name)
        with h.forward("ds-e2e-tls", 443, ns=ns) as port, trust_environment(root_path, temporary / "empty-trust"):
            actual = endpoint_truth(port)
            assert (actual["sha256"] != metadata["sha256"]) == mismatch
            result = h.function("tls_secret_compare_report", [name, "127.0.0.1", str(port)], ns=ns)
            text = record("pki-live-mismatch" if mismatch else "pki-live-match", result)
            assert result.returncode == (1 if mismatch else 0)
            assert "RESULT: " + ("MISMATCH" if mismatch else "MATCH") in text
            assert actual["sha256"] in text and metadata["sha256"] in text
        return {"secret_sha256": metadata["sha256"], "live_sha256": actual["sha256"], "expected": "MISMATCH" if mismatch else "MATCH"}

    def live(mode="trusted"):
        ready()
        with h.forward("ds-e2e-tls", 443, ns=ns) as port:
            actual = endpoint_truth(port)
            trust = temporary / "valid.pem" if mode == "untrusted" else root_path
            with trust_environment(trust, temporary / "empty-trust"):
                result = h.function("tls_report", ["localhost" if mode == "hostname" else "127.0.0.1", str(port)], ns=ns)
            text = record("pki-live-" + mode, result)
            if mode == "trusted":
                assert result.returncode == 0 and "TLS HANDSHAKE: COMPLETED" in text
                assert actual["sha256"] in text
                assert re.search(r"TLS 1\.2\s+SUPPORTED", text)
                assert re.search(r"TLS 1\.3\s+SUPPORTED", text)
            else:
                assert result.returncode == 1 and "TLS HANDSHAKE: FAILED" in text
        return actual

    def rotation():
        ready()
        before = truth("ds-e2e-cert-valid")
        h.apply(secret_manifest("ds-e2e-cert-valid", "rotated"), ns=ns)
        after = truth("ds-e2e-cert-valid")
        assert before["sha256"] != after["sha256"] and before["not_after"] != after["not_after"]
        refreshed = record("pki-rotation-inventory", h.sentinel(["--certificates"], ns=ns))
        assert after["sha256"] in refreshed
        with h.forward("ds-e2e-tls", 443, ns=ns) as port, trust_environment(root_path, temporary / "empty-trust"):
            live_before = endpoint_truth(port)
            assert live_before["sha256"] == before["sha256"], "server did not retain original loaded TLS context"
            result = h.function("tls_secret_compare_report", ["ds-e2e-cert-valid", "127.0.0.1", str(port)], ns=ns)
            assert result.returncode == 1 and "RESULT: MISMATCH" in record("pki-rotation-before-reload", result)
        updated = copy.deepcopy(deployment)
        updated["spec"]["template"]["metadata"]["annotations"] = {"devopssentinel.io/test-rotation": after["serial"]}
        h.apply(updated, ns=ns)
        ready()
        matched = compare()
        return {"before": before, "after": after, "reloaded_endpoint": matched}

    def cert_manager(failure=False):
        api = h.k(["get", "crd", "certificates.cert-manager.io", "-o", "name"], timeout=30)
        if api.returncode:
            h.block("cert-manager CRDs are unavailable. Install the pinned release with "
                    "`run-all.sh --install-prereqs`, or `kubectl apply -f "
                    "https://github.com/cert-manager/cert-manager/releases/download/v1.15.3/cert-manager.yaml`, "
                    "then rerun --domain certificates.")
        name = "ds-e2e-managed-failure" if failure else "ds-e2e-managed"
        if not failure:
            h.apply({"apiVersion": "cert-manager.io/v1", "kind": "Issuer", "metadata": {"name": "ds-e2e-selfsigned", "labels": labels}, "spec": {"selfSigned": {}}}, ns=ns)
        h.apply({"apiVersion": "cert-manager.io/v1", "kind": "Certificate", "metadata": {"name": name, "labels": labels},
                 "spec": {"secretName": name, "secretTemplate": {"labels": labels}, "commonName": "ds-e2e-managed.local", "dnsNames": ["ds-e2e-managed.local"],
                          "duration": "2160h", "issuerRef": {"name": "ds-e2e-missing-issuer" if failure else "ds-e2e-selfsigned", "kind": "Issuer"}}}, ns=ns)
        expected = "False" if failure else "True"
        obj = h.wait("certificate", name, lambda obj: any(c.get("type") == "Ready" and c.get("status") == expected for c in obj.get("status", {}).get("conditions", [])), ns=ns, timeout=180)
        h.evidence(name + "-conditions", obj.get("status", {}))
        if not failure:
            secret = h.get("secret", name, ns=ns)
            assert "tls.crt" in secret["data"] and "tls.key" in secret["data"]
            requests = json.loads(h.k(["get", "certificaterequests", "-o", "json"], ns=ns).stdout)["items"]
            assert any(any(owner.get("name") == name for owner in request["metadata"].get("ownerReferences", [])) for request in requests), "real CertificateRequest absent"
        text = record(name + "-sentinel", h.function("cert_manager_extended_report", [], ns=ns))
        row = next((row for row in text.splitlines() if row.startswith("Certificate\t" + name + "\t")), "")
        assert "\t" + expected + "\t" in row, "cert-manager Ready condition not surfaced"
        return {"conditions": obj.get("status", {}).get("conditions", []), "sentinel_row": row}

    def exports():
        truth("ds-e2e-cert-valid")
        json_result = h.sentinel(["--certificates", "--json"], ns=ns, timeout=120)
        text = record("pki-json-output", json_result)
        parsed = json.loads(text)
        assert parsed["namespace"] == ns and isinstance(parsed["lines"], list)
        exported = h.shell('{ printf "Certificate export\\nNamespace: %s\\n" "$SENTINEL_NAMESPACE"; '
                           'certificates_report; } > "$RUN_DIR/inventory.txt" 2>&1; '
                           '_export_file_core "$RUN_DIR/inventory.txt" pki-inventory json', ns=ns, timeout=180)
        assert exported.returncode == 0, exported.stderr[-500:]
        path = Path(next(row.removeprefix("EXPORTED ") for row in exported.stdout.splitlines() if row.startswith("EXPORTED ")))
        contents = path.read_text()
        json.loads(contents)
        assert path.stat().st_mode & 0o077 == 0, "export permissions are not private"
        for output in observed + [contents]:
            assert "PRIVATE KEY-----" not in output and "synthetic-pki-reference-only" not in output
            for fixture in fixtures.values():
                key_line = fixture["key"].decode().splitlines()[1]
                assert key_line not in output, "private key content leaked without its PEM header"
        h.evidence("pki-export-check", {"path": str(path), "json_valid": True, "private_permissions": True, "redaction": "no private key or Secret reference payload"})

    # Order keeps duplicate and initial endpoint checks before the rotation.
    h.case("DS-E2E-050", DOMAIN, "Valid TLS Secret metadata and healthy expiry", valid)
    h.case("DS-E2E-051", DOMAIN, "Real five-day certificate is critical", lambda: check_expiry("ds-e2e-cert-expiring", "CRITICAL"))
    h.case("DS-E2E-052", DOMAIN, "Historical X.509 certificate is expired", expired)
    h.case("DS-E2E-053", DOMAIN, "Complete multi-DNS and IP SAN parsing", sans)
    h.case("DS-E2E-054", DOMAIN, "Duplicate leaf fingerprint detection", duplicates)
    h.case("DS-E2E-055", DOMAIN, "Root/intermediate/leaf trust chain", chain)
    h.case("DS-E2E-150", DOMAIN, "Omitted intermediate fails trust verification", incomplete)
    h.case("DS-E2E-151", DOMAIN, "Root self-issuance and intermediate trust", self_issued)
    h.case("DS-E2E-152", DOMAIN, "Actual Secret volume/env and workload ownership", mounts)
    h.case("DS-E2E-153", DOMAIN, "Actual TLS Pod and verified TLS 1.2/1.3", live)
    h.case("DS-E2E-154", DOMAIN, "TLS endpoint hostname mismatch fails", lambda: live("hostname"))
    h.case("DS-E2E-155", DOMAIN, "Untrusted CA fails live verification", lambda: live("untrusted"))
    h.case("DS-E2E-056", DOMAIN, "Live TLS fingerprint matches mounted Secret", compare)
    h.case("DS-E2E-057", DOMAIN, "Different Ingress Secret produces factual mismatch", lambda: compare(True))
    h.case("DS-E2E-058", DOMAIN, "Secret rotation refresh and server reload", rotation)
    h.case("DS-E2E-059", DOMAIN, "Real cert-manager issuance and CertificateRequest", cert_manager)
    h.case("DS-E2E-156", DOMAIN, "Real cert-manager missing Issuer failure", lambda: cert_manager(True))
    h.case("DS-E2E-157", DOMAIN, "Certificate JSON/export and private-key redaction", exports)
    h.case("DS-E2E-158", DOMAIN, "Future certificate validity is explicit", lambda: check_expiry("ds-e2e-cert-future", "NOT_YET_VALID"))
