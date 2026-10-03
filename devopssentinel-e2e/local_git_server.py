#!/usr/bin/env python3
"""Disposable cluster-internal Git smart HTTP and Helm fixture repository.

Only the fixture repository can be read. There is no receive-pack endpoint and
the sole write operation creates the next known test revision in this local repo.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(os.environ.get("FIXTURE_ROOT", "/data"))
REPO = ROOT / "fixture.git"
NS = os.environ.get("FIXTURE_NAMESPACE", "devopssentinel-e2e-gitops")
IMAGE = os.environ.get("FIXTURE_IMAGE", "ds-e2e-tools:local")
LABELS = {"devopssentinel.io/test-suite": "true", "app.kubernetes.io/part-of": "devopssentinel-e2e"}
LOCK = threading.Lock()


def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args], text=True, stderr=subprocess.STDOUT).strip()


def metadata(name):
    return {"name": name, "namespace": NS, "labels": dict(LABELS)}


def deployment(name):
    labels = {**LABELS, "app": name}
    return {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": metadata(name), "spec": {
        "replicas": 1, "selector": {"matchLabels": {"app": name}}, "template": {
            "metadata": {"labels": labels}, "spec": {"automountServiceAccountToken": False, "containers": [{
                "name": "web", "image": IMAGE, "imagePullPolicy": "Never",
                "command": ["python3", "-m", "http.server", "8080"], "ports": [{"containerPort": 8080}],
                "resources": {"requests": {"cpu": "5m", "memory": "16Mi"}, "limits": {"cpu": "100m", "memory": "64Mi"}},
                "readinessProbe": {"httpGet": {"path": "/", "port": 8080}, "periodSeconds": 2}}]}}}}


def write_revision(number):
    apps = REPO / "apps"
    apps.mkdir(exist_ok=True)
    dep = deployment("ds-e2e-git-app")
    dep["metadata"]["annotations"] = {"devopssentinel.io/fixture-revision": str(number)}
    dep["spec"]["template"]["metadata"]["annotations"] = {"devopssentinel.io/fixture-revision": str(number)}
    release = {"apiVersion": "helm.toolkit.fluxcd.io/v2", "kind": "HelmRelease",
               "metadata": metadata("ds-e2e-chart-app"), "spec": {
                   "interval": "10s", "timeout": "45s", "releaseName": "ds-e2e-chart-app",
                   "chart": {"spec": {"chart": "ds-e2e-chart", "version": "0.1.0", "interval": "10s",
                                      "sourceRef": {"kind": "HelmRepository", "name": "ds-e2e-local-chart"}}}}}
    (apps / "deployment.json").write_text(json.dumps(dep, indent=2) + "\n")
    (apps / "release.json").write_text(json.dumps(release, indent=2) + "\n")
    (apps / "kustomization.yaml").write_text("apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n- deployment.json\n- release.json\n")
    (REPO / "revision.txt").write_text(str(number) + "\n")
    git("add", "apps", "revision.txt")
    git("commit", "-m", "Isolated DevOpsSentinel E2E revision " + str(number))
    return git("rev-parse", "HEAD")


def chart_archive():
    dep = deployment("ds-e2e-chart-app")
    dep["metadata"]["labels"]["app.kubernetes.io/instance"] = "ds-e2e-chart-app"
    # Helm supplies its own ownership annotations on the real installed workload.
    service = {"apiVersion": "v1", "kind": "Service", "metadata": metadata("ds-e2e-chart-app"),
               "spec": {"selector": {"app": "ds-e2e-chart-app"}, "ports": [{"name": "http", "port": 80, "targetPort": 8080}]}}
    files = {"Chart.yaml": "apiVersion: v2\nname: ds-e2e-chart\nversion: 0.1.0\nappVersion: '1.0'\ntype: application\n",
             "values.yaml": "fail: false\n",
             "templates/deployment.yaml": '{{ if .Values.fail }}{{ fail "intentional ds-e2e Helm validation failure" }}{{ end }}\n' + json.dumps(dep),
             "templates/service.yaml": json.dumps(service)}
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, content in files.items():
            encoded = content.encode()
            info = tarfile.TarInfo("ds-e2e-chart/" + name)
            info.size, info.mode, info.mtime = len(encoded), 0o644, 0
            archive.addfile(info, io.BytesIO(encoded))
    return stream.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Paths and status only: the service has no credentials or secret data.
        print("local-fixture " + fmt % args, flush=True)

    def respond(self, code, content, content_type="application/json"):
        if isinstance(content, (dict, list)):
            content = json.dumps(content).encode()
        elif isinstance(content, str):
            content = content.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            return self.respond(200, {"ready": True})
        if path == "/revision":
            with LOCK:
                return self.respond(200, {"commit": git("rev-parse", "HEAD"), "revision": int((REPO / "revision.txt").read_text())})
        if path == "/charts/index.yaml":
            index = {"apiVersion": "v1", "entries": {"ds-e2e-chart": [{"apiVersion": "v2", "name": "ds-e2e-chart",
                     "version": "0.1.0", "appVersion": "1.0", "description": "Disposable local E2E chart",
                     "urls": ["ds-e2e-chart-0.1.0.tgz"], "digest": hashlib.sha256(CHART).hexdigest(),
                     "created": "2026-01-01T00:00:00Z"}]}}
            return self.respond(200, index, "application/yaml")
        if path == "/charts/ds-e2e-chart-0.1.0.tgz":
            return self.respond(200, CHART, "application/gzip")
        return self.git_request()

    def do_POST(self):
        if urlsplit(self.path).path == "/advance":
            with LOCK:
                number = int((REPO / "revision.txt").read_text()) + 1
                commit = write_revision(number)
                return self.respond(200, {"commit": commit, "revision": number})
        return self.git_request()

    def git_request(self):
        parsed = urlsplit(self.path)
        if parsed.path not in ("/fixture.git/info/refs", "/fixture.git/git-upload-pack"):
            return self.respond(404, {"error": "fixture endpoint not found"})
        if "git-receive-pack" in parsed.query or self.headers.get("Content-Length", "0").isdigit() is False:
            return self.respond(403, {"error": "Git writes are disabled"})
        size = int(self.headers.get("Content-Length", "0"))
        if size > 8 * 1024 * 1024:
            return self.respond(413, {"error": "request too large"})
        body = self.rfile.read(size) if size else b""
        env = {**os.environ, "GIT_PROJECT_ROOT": str(ROOT), "GIT_HTTP_EXPORT_ALL": "1",
               "PATH_INFO": parsed.path, "QUERY_STRING": parsed.query, "REQUEST_METHOD": self.command,
               "CONTENT_TYPE": self.headers.get("Content-Type", ""), "CONTENT_LENGTH": str(size),
               "SERVER_PROTOCOL": self.request_version, "REMOTE_ADDR": self.client_address[0]}
        if self.headers.get("Git-Protocol"):
            env["HTTP_GIT_PROTOCOL"] = self.headers["Git-Protocol"]
        completed = subprocess.run(["git", "http-backend"], input=body, capture_output=True, env=env, timeout=30)
        header, separator, payload = completed.stdout.partition(b"\r\n\r\n")
        if not separator:
            return self.respond(502, {"error": "Git backend failed"})
        headers = [line.split(b":", 1) for line in header.split(b"\r\n") if b":" in line]
        status = next((int(v.strip().split()[0]) for k, v in headers if k.lower() == b"status"), 200)
        self.send_response(status)
        for key, value in headers:
            if key.lower() not in (b"status", b"content-length", b"connection"):
                self.send_header(key.decode(), value.strip().decode())
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    REPO.mkdir(exist_ok=True)
    if not (REPO / ".git").exists():
        git("init", "-b", "main")
        git("config", "user.email", "fixture@devopssentinel.invalid")
        git("config", "user.name", "DevOpsSentinel isolated fixture")
        git("config", "http.receivepack", "false")
        write_revision(1)
    CHART = chart_archive()
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("FIXTURE_PORT", "8080"))), Handler).serve_forever()
