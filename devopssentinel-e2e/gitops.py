"""Real, namespace-isolated Flux E2E cases. Never uses an external Git remote."""
import copy
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen

NS = "devopssentinel-e2e-gitops"
LABELS = {"devopssentinel.io/test-suite": "true", "app.kubernetes.io/part-of": "devopssentinel-e2e"}
IMAGE = "ds-e2e-tools:local"
GR = "gitrepositories.source.toolkit.fluxcd.io"
KS = "kustomizations.kustomize.toolkit.fluxcd.io"
HR = "helmreleases.helm.toolkit.fluxcd.io"
HELM_REPO = "helmrepositories.source.toolkit.fluxcd.io"


def obj(api, kind, name, spec=None, **extra):
    resource = {"apiVersion": api, "kind": kind, "metadata": {"name": name, "namespace": NS, "labels": dict(LABELS)}, **extra}
    if spec is not None:
        resource["spec"] = spec
    return resource


def ready(resource, value="True"):
    return any(c.get("type") == "Ready" and c.get("status") == value for c in resource.get("status", {}).get("conditions", []))


def current_ready(resource):
    conditions = resource.get("status", {}).get("conditions", [])
    observed = resource.get("status", {}).get("observedGeneration")
    if observed is None:
        observed = next((c.get("observedGeneration") for c in conditions if c.get("type") == "Ready"), None)
    return ready(resource) and observed == resource["metadata"]["generation"]


def run(h):
    """Register and execute GitOps cases through the shared traceable harness."""
    setup_done = False
    source = obj("source.toolkit.fluxcd.io/v1", "GitRepository", "ds-e2e-local-source", {
        "interval": "10s", "timeout": "20s", "url": "http://ds-e2e-git-server." + NS + ".svc.cluster.local:8080/fixture.git", "ref": {"branch": "main"}})
    kust = obj("kustomize.toolkit.fluxcd.io/v1", "Kustomization", "ds-e2e-ready", {
        "interval": "10s", "retryInterval": "10s", "timeout": "60s", "path": "./apps", "prune": True,
        "sourceRef": {"kind": "GitRepository", "name": "ds-e2e-local-source"}, "targetNamespace": NS,
        "wait": True, "suspend": False})

    def setup():
        nonlocal setup_done
        if setup_done:
            return
        for resource in (GR, KS, HR, HELM_REPO):
            response = h.k(["get", resource, "-o", "name"], NS)
            if response.returncode:
                h.block("Flux prerequisite unavailable: " + resource + "; existing Flux objects are untouched. Restore the local Flux controllers/CRDs and rerun --domain gitops.")
        server_code = Path(__file__).with_name("local_git_server.py").read_text()
        h.apply(obj("v1", "ConfigMap", "ds-e2e-git-server-code", data={"server.py": server_code}), NS)
        podlabels = {**LABELS, "app": "ds-e2e-git-server"}
        h.apply(obj("apps/v1", "Deployment", "ds-e2e-git-server", {
            "replicas": 1, "selector": {"matchLabels": {"app": "ds-e2e-git-server"}}, "template": {
                "metadata": {"labels": podlabels}, "spec": {"automountServiceAccountToken": False, "containers": [{
                    "name": "repository", "image": IMAGE, "imagePullPolicy": "Never", "command": ["python3", "/fixture/server.py"],
                    "env": [{"name": "FIXTURE_NAMESPACE", "value": NS}], "ports": [{"containerPort": 8080}],
                    "resources": {"requests": {"cpu": "10m", "memory": "32Mi"}, "limits": {"cpu": "300m", "memory": "128Mi"}},
                    "readinessProbe": {"httpGet": {"path": "/healthz", "port": 8080}, "periodSeconds": 2},
                    "volumeMounts": [{"name": "code", "mountPath": "/fixture", "readOnly": True}, {"name": "data", "mountPath": "/data"}]}],
                    "volumes": [{"name": "code", "configMap": {"name": "ds-e2e-git-server-code"}}, {"name": "data", "emptyDir": {}}]}}}), NS)
        h.apply(obj("v1", "Service", "ds-e2e-git-server", {"selector": {"app": "ds-e2e-git-server"}, "ports": [{"name": "http", "port": 8080, "targetPort": 8080}]}), NS)
        h.wait("deployments", "ds-e2e-git-server", lambda r: r.get("status", {}).get("availableReplicas", 0) == 1, NS, timeout=180)
        h.apply(obj("source.toolkit.fluxcd.io/v1", "HelmRepository", "ds-e2e-local-chart", {
            "interval": "10s", "timeout": "20s", "url": "http://ds-e2e-git-server." + NS + ".svc.cluster.local:8080/charts"}), NS)
        h.apply(source, NS)
        h.apply(kust, NS)
        suspended = copy.deepcopy(kust)
        suspended["metadata"]["name"] = "ds-e2e-suspended"
        suspended["spec"]["suspend"] = True
        h.apply(suspended, NS)
        failure = copy.deepcopy(source)
        failure["metadata"]["name"] = "ds-e2e-source-failed"
        failure["spec"]["url"] = "http://ds-e2e-git-server." + NS + ".svc.cluster.local:8080/ds-e2e-does-not-exist.git"
        h.apply(failure, NS)
        failed_kust = copy.deepcopy(kust)
        failed_kust["metadata"]["name"] = "ds-e2e-kustomization-failed"
        failed_kust["spec"]["path"] = "./ds-e2e-nonexistent-path"
        failed_kust["spec"]["wait"] = False
        h.apply(failed_kust, NS)
        h.apply(obj("helm.toolkit.fluxcd.io/v2", "HelmRelease", "ds-e2e-helm-failed", {
            "interval": "10s", "timeout": "30s", "releaseName": "ds-e2e-helm-failed",
            "chart": {"spec": {"chart": "ds-e2e-chart", "version": "0.1.0", "interval": "10s",
                               "sourceRef": {"kind": "HelmRepository", "name": "ds-e2e-local-chart"}}},
            "values": {"fail": True}}), NS)
        setup_done = True

    def report(mode="gitops"):
        completed = h.sentinel(["--" + mode, "--json"], NS, timeout=120)
        assert completed.returncode in (0, 1), "Unexpected Sentinel exit: " + str(completed.returncode) + " " + completed.stderr[-1000:]
        data = json.loads(completed.stdout)
        assert data.get("namespace") == NS and data["exit_status"] == completed.returncode
        text = "\n".join(data["lines"])
        h.evidence("sentinel-" + mode + ".json", data)
        h.evidence("sentinel-" + mode + ".txt", text)
        return text

    def truth(resource, name, predicate, timeout=240):
        setup()
        state = h.wait(resource, name, predicate, NS, timeout=timeout)
        if not isinstance(state, dict):
            state = h.get(resource, name, NS)
        assert predicate(state), "API state does not match expected condition: " + name
        h.evidence("kubernetes-" + name + ".json", state)
        return state

    def resource_block(text, kind, name):
        match = re.search(r"(?:^|\n)" + re.escape(kind + "/" + name) + r" \[[^\n]+\][\s\S]*?(?=\n\n|\Z)", text)
        assert match, "Missing Sentinel resource block: " + kind + "/" + name
        return match.group(0)

    def suspended_case():
        state = truth(KS, "ds-e2e-suspended", lambda r: r.get("spec", {}).get("suspend") is True)
        block = resource_block(report(), "Kustomization", "ds-e2e-suspended")
        assert "WARN SUSPENDED" in block and "suspend=true" in block
        return {"expected_kubernetes_state": "spec.suspend=true", "actual_kubernetes_state": state["spec"]["suspend"], "expected_sentinel_result": "WARN SUSPENDED", "actual_sentinel_result": block}

    def failed_source_case():
        state = truth(GR, "ds-e2e-source-failed", lambda r: ready(r, "False"))
        condition = next(c for c in state["status"]["conditions"] if c["type"] == "Ready")
        block = resource_block(report(), "GitRepository", "ds-e2e-source-failed")
        assert "Ready=False" in block and "FAIL RECONCILIATION_FAILED" in block
        assert condition["reason"] in block and condition["message"] in block
        # A failing source is retried continuously, so its Ready lastTransitionTime
        # can advance between the API read and the Sentinel read. Assert the block
        # surfaces a real transition timestamp instead of exact equality.
        assert re.search(r"transition=\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", block), \
            "Sentinel block did not surface a transition timestamp"
        return {"expected_kubernetes_state": "Ready=False with controller fetch error", "actual_kubernetes_state": condition, "expected_sentinel_result": "Failure reason, message and transition", "actual_sentinel_result": block}

    def ready_source_case():
        state = truth(GR, "ds-e2e-local-source", current_ready)
        block = resource_block(report(), "GitRepository", "ds-e2e-local-source")
        assert "OK NO_DRIFT_EVIDENCE" in block and state["status"]["artifact"]["revision"] in block
        return {"expected_kubernetes_state": "Ready=True generation observed", "actual_kubernetes_state": state["status"], "expected_sentinel_result": "Ready source and exact Git revision", "actual_sentinel_result": block}

    def ready_kust_case():
        state = truth(KS, "ds-e2e-ready", current_ready)
        dep = truth("deployments", "ds-e2e-git-app", lambda r: r.get("status", {}).get("availableReplicas", 0) == 1)
        assert dep["metadata"]["labels"]["kustomize.toolkit.fluxcd.io/name"] == "ds-e2e-ready"
        block = resource_block(report(), "Kustomization", "ds-e2e-ready")
        assert "OK NO_DRIFT_EVIDENCE" in block and state["status"]["lastAppliedRevision"] in block
        return {"expected_kubernetes_state": "Kustomization Ready=True; Git deployment available=1", "actual_kubernetes_state": {"revision": state["status"]["lastAppliedRevision"], "available": dep["status"]["availableReplicas"]}, "expected_sentinel_result": "Ready Kustomization and applied revision", "actual_sentinel_result": block}

    def failed_kust_case():
        state = truth(KS, "ds-e2e-kustomization-failed", lambda r: ready(r, "False"))
        block = resource_block(report(), "Kustomization", "ds-e2e-kustomization-failed")
        assert "FAIL RECONCILIATION_FAILED" in block and "Ready=False" in block and "ds-e2e-nonexistent-path" in block
        return {"expected_kubernetes_state": "Ready=False from missing repository path", "actual_kubernetes_state": state["status"], "expected_sentinel_result": "Reconciliation failure with path", "actual_sentinel_result": block}

    def ready_helm_case():
        state = truth(HR, "ds-e2e-chart-app", current_ready)
        dep = truth("deployments", "ds-e2e-chart-app", lambda r: r.get("status", {}).get("availableReplicas", 0) == 1)
        assert dep["metadata"]["annotations"]["meta.helm.sh/release-name"] == "ds-e2e-chart-app"
        svc = h.get("services", "ds-e2e-chart-app", NS)
        h.evidence("kubernetes-ds-e2e-chart-service.json", svc)
        block = resource_block(report(), "HelmRelease", "ds-e2e-chart-app")
        assert "OK NO_DRIFT_EVIDENCE" in block and "installedVersion=0.1.0" in block
        return {"expected_kubernetes_state": "HelmRelease Ready=True with actual installed deployment and Service", "actual_kubernetes_state": state["status"], "expected_sentinel_result": "Ready HelmRelease with installed chart version", "actual_sentinel_result": block}

    def failed_helm_case():
        state = truth(HR, "ds-e2e-helm-failed", lambda r: ready(r, "False") and any("intentional ds-e2e" in c.get("message", "") for c in r.get("status", {}).get("conditions", [])))
        block = resource_block(report(), "HelmRelease", "ds-e2e-helm-failed")
        assert "Ready=False" in block and "intentional ds-e2e Helm validation failure" in block
        assert "FAIL HELM_FAILURE" in block or "FAIL RECONCILIATION_FAILED" in block
        return {"expected_kubernetes_state": "Ready=False from actual Helm template failure", "actual_kubernetes_state": state["status"], "expected_sentinel_result": "Helm failure with controller message", "actual_sentinel_result": block}

    def graph_case():
        state = truth(KS, "ds-e2e-ready", current_ready)
        truth(HR, "ds-e2e-chart-app", current_ready)
        entries = state["status"]["inventory"]["entries"]
        assert any(e["id"] == NS + "_ds-e2e-chart-app_helm.toolkit.fluxcd.io_HelmRelease" for e in entries)
        text = report("gitops-graph")
        assert re.search(r"GitRepository/ds-e2e-local-source[\s\S]*?Kustomization/ds-e2e-ready[\s\S]*?HelmRelease/ds-e2e-chart-app", text)
        assert "HelmRelease/ds-e2e-chart-app chart=ds-e2e-chart source=HelmRepository/ds-e2e-local-chart ready=True" in text
        return {"expected_kubernetes_state": "Explicit sourceRef and Flux inventory connect source, Kustomization and HelmRelease", "actual_kubernetes_state": entries, "expected_sentinel_result": "Complete GitOps dependency graph", "actual_sentinel_result": text}

    def revision_case():
        old = truth(KS, "ds-e2e-ready", current_ready)["status"]["lastAppliedRevision"]
        original = copy.deepcopy(kust)
        paused = copy.deepcopy(kust)
        paused["spec"]["suspend"] = True
        h.apply(paused, NS)
        try:
            with h.forward("ds-e2e-git-server", 8080, NS) as port:
                with urlopen(Request("http://127.0.0.1:" + str(port) + "/advance", data=b"", method="POST"), timeout=30) as response:
                    commit = json.load(response)
            h.evidence("local-second-commit.json", commit)
            state = truth(GR, "ds-e2e-local-source", lambda r: current_ready(r) and r.get("status", {}).get("artifact", {}).get("revision", "").endswith(commit["commit"]))
            newer = state["status"]["artifact"]["revision"]
            assert newer != old
            applied = h.get(KS, "ds-e2e-ready", NS)
            assert applied["spec"]["suspend"] and applied["status"]["lastAppliedRevision"] == old
            h.evidence("kubernetes-suspended-revision-gap.json", applied)
            during = report()
            expected = "Kustomization/ds-e2e-ready -> GitRepository/ds-e2e-local-source: REVISION_DRIFT / POTENTIAL_DRIFT"
            assert expected in during and newer in during and old in during
            h.evidence("sentinel-revision-gap.txt", during)
        finally:
            h.apply(original, NS)
        recovered = truth(KS, "ds-e2e-ready", lambda r: current_ready(r) and r.get("status", {}).get("lastAppliedRevision") == newer)
        dep = truth("deployments", "ds-e2e-git-app", lambda r: r.get("metadata", {}).get("annotations", {}).get("devopssentinel.io/fixture-revision") == str(commit["revision"]) and r.get("status", {}).get("availableReplicas", 0) == 1)
        after = report()
        assert "Kustomization/ds-e2e-ready -> GitRepository/ds-e2e-local-source: NO_DRIFT_EVIDENCE (revision matches)" in after
        return {"expected_kubernetes_state": "New local commit fetched, temporarily unapplied while suspended, then successfully applied", "actual_kubernetes_state": {"old_revision": old, "new_revision": newer, "applied_revision": recovered["status"]["lastAppliedRevision"], "workload_revision": dep["metadata"]["annotations"]["devopssentinel.io/fixture-revision"]}, "expected_sentinel_result": "Observed revision difference followed by revision matches", "actual_sentinel_result": after}

    def mapping_case():
        truth(HR, "ds-e2e-chart-app", current_ready)
        state = truth(KS, "ds-e2e-ready", current_ready)
        dep = truth("deployments", "ds-e2e-chart-app", lambda r: r.get("status", {}).get("availableReplicas", 0) == 1)
        response = h.k(["get", "pods", "-l", "app=ds-e2e-chart-app", "-o", "json"], NS)
        assert response.returncode == 0
        pods = json.loads(response.stdout)
        assert pods["items"]
        h.evidence("kubernetes-helm-pods.json", pods)
        for pod in pods["items"]:
            owner = next(o for o in pod["metadata"]["ownerReferences"] if o.get("controller"))
            assert owner["kind"] == "ReplicaSet"
            rs = h.get("replicasets", owner["name"], NS)
            h.evidence("kubernetes-" + owner["name"] + ".json", rs)
            assert any(o["kind"] == "Deployment" and o["name"] == dep["metadata"]["name"] for o in rs["metadata"]["ownerReferences"])
        output = h.function("deployment_chain_report", ["Deployment/ds-e2e-chart-app"], NS, timeout=120)
        h.evidence("sentinel-deployment-chain.txt", output.stdout)
        assert output.returncode == 0
        for token in ("HelmRelease=ds-e2e-chart-app", "Kustomization=ds-e2e-ready", "source=GitRepository/ds-e2e-local-source", state["status"]["lastAppliedRevision"], "ReplicaSet/", "Deployment/ds-e2e-chart-app"):
            assert token in output.stdout, "Missing deployment chain token: " + token
        return {"expected_kubernetes_state": "Pod -> ReplicaSet -> Deployment -> Helm release -> Kustomization -> Git revision", "actual_kubernetes_state": {"pod_names": [p["metadata"]["name"] for p in pods["items"]], "deployment_uid": dep["metadata"]["uid"], "revision": state["status"]["lastAppliedRevision"]}, "expected_sentinel_result": "Exact workload ownership and Git revision correlation", "actual_sentinel_result": output.stdout}

    cases = [
        ("060", "Suspended Flux resource", suspended_case),
        ("061", "Failed local Git source with message and transition", failed_source_case),
        ("062", "Ready local Git source and exact artifact revision", ready_source_case),
        ("063", "Local Git Kustomization deploys a real workload", ready_kust_case),
        ("064", "Failed Kustomization from missing path", failed_kust_case),
        ("065", "Local Helm chart installs real Deployment and Service", ready_helm_case),
        ("066", "Actual Helm template failure", failed_helm_case),
        ("067", "GitOps source, inventory and Helm dependency graph", graph_case),
        ("068", "Second local commit, revision gap and recovery", revision_case),
        ("069", "Workload owner and exact Git revision mapping", mapping_case),
    ]
    for number, title, callback in cases:
        h.case("DS-E2E-" + number, "gitops", title, callback)
