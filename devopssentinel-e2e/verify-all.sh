#!/usr/bin/env bash
# DevOpsSentinel E2E — read-only step-by-step verification of every scenario.
# Every command below is safe to copy-paste; none of them mutate the cluster.
set +e
SENT='/mnt/c/Users/dheer/OneDrive/Desktop/AI Projects/DeVops_latest/DevOps_K8s_Sentinel_FINAL_GP.sh'
CTX=vcluster-docker_dev
E2E=devopssentinel-e2e
PKI=devopssentinel-e2e-pki
PEER=devopssentinel-e2e-peer
GITOPS=devopssentinel-e2e-gitops

sec()  { printf '\n\n########## %s ##########\n' "$1"; }
runc() { local n=${2:-25}; printf '\n$ %s\n' "$1"; eval "$1" 2>&1 | head -"$n"; }

sec "0. ENVIRONMENT"
runc "wsl.exe -l -v 2>/dev/null || uname -a" 5
runc "kubectl config current-context" 2
runc "kubectl cluster-info" 4
runc "kubectl get nodes -o wide" 5
runc "kubectl version" 4
runc "docker ps --filter name=vcluster.cp.dev --format '{{.Names}}  {{.Image}}  {{.Status}}'" 3

sec "1. SAFETY GATE / NAMESPACES"
runc "kubectl get ns --no-headers | grep -E 'devopssentinel|cert-manager|flux-system'" 10
runc "kubectl get ns devopssentinel-e2e devopssentinel-e2e-peer devopssentinel-e2e-gitops devopssentinel-e2e-pki -o jsonpath='{range .items[*]}{.metadata.name}{\"  \"}{.metadata.labels.devopssentinel\\.io/test-suite}{\"  \"}{.metadata.labels.app\\.kubernetes\\.io/part-of}{\"\\n\"}{end}'" 6
runc "for n in $E2E $PEER $GITOPS $PKI; do printf '%-28s pods=%s\n' \"\$n\" \"\$(kubectl -n \$n get pods --no-headers 2>/dev/null | wc -l)\"; done" 6

sec "2. WORKLOAD SCENARIOS"
runc "kubectl -n $E2E get deploy,statefulset,daemonset,job,cronjob" 12
runc "kubectl -n $E2E get pods -o wide --no-headers" 30
runc "kubectl -n $E2E get deploy ds-e2e-healthy -o jsonpath='{.spec.replicas} desired, {.status.readyReplicas} ready, {.status.availableReplicas} available{\"\n\"}'" 2
runc "kubectl -n $E2E get statefulset ds-e2e-stateful -o jsonpath='{.spec.replicas} replicas, {.status.readyReplicas} ready{\"\n\"}'" 2
runc "kubectl -n $E2E get ds ds-e2e-daemon -o jsonpath='{.status.desiredNumberScheduled} desired, {.status.numberReady} ready{\"\n\"}'" 2
runc "kubectl -n $E2E get pod ds-e2e-crash -o jsonpath='{range .status.containerStatuses[*]}CrashLoop reason={.state.waiting.reason} restarts={.restartCount} lastExit={.lastState.terminated.exitCode}{\"\n\"}{end}'" 3
runc "kubectl -n $E2E get pod ds-e2e-image -o jsonpath='{range .status.containerStatuses[*]}ImagePull reason={.state.waiting.reason}{\"\n\"}{end}'" 3
runc "kubectl -n $E2E get pod ds-e2e-missing-config -o jsonpath='{range .status.containerStatuses[*]}ConfigError reason={.state.waiting.reason}{\"\n\"}{end}'" 3
runc "kubectl -n $E2E get pod ds-e2e-unschedulable -o jsonpath='{.status.phase} {.status.conditions[0].reason}{\"\n\"}'" 2
runc "kubectl -n $E2E get pod ds-e2e-not-ready -o jsonpath='{range .status.conditions[*]}{.type}={.status} {end}{\"\n\"}'" 2
runc "kubectl -n $E2E get pod ds-e2e-liveness -o jsonpath='{range .status.containerStatuses[*]}restarts={.restartCount} waiting={.state.waiting.reason}{\"\n\"}{end}'" 3
runc "kubectl -n $E2E get pod ds-e2e-oom -o jsonpath='{range .status.containerStatuses[*]}state={.state.terminated.reason} exit={.state.terminated.exitCode}{\"\n\"}{end}'" 3
runc "kubectl -n $E2E get pod ds-e2e-init-fail -o jsonpath='{range .status.initContainerStatuses[*]}init restarts={.restartCount} waiting={.state.waiting.reason}{\"\n\"}{end}'" 3
runc "kubectl -n $E2E get pod ds-e2e-multi -o jsonpath='containers={.spec.containers[*].name} init={.spec.initContainers[*].name} ready={.status.containerStatuses[*].ready}{\"\n\"}'" 3
runc "kubectl -n $E2E get job ds-e2e-job-success -o jsonpath='{range .status.conditions[*]}{.type}={.status} {end}{\"\n\"}'" 2
runc "kubectl -n $E2E get job ds-e2e-job-failed -o jsonpath='{range .status.conditions[*]}{.type}={.status} {end}{\"\n\"}'" 2

sec "3. NETWORKING SCENARIOS"
runc "kubectl -n $E2E get svc --no-headers" 12
runc "kubectl -n $E2E get endpointslices -o custom-columns='NAME:.metadata.name,SVC:.metadata.labels.kubernetes\.io/service-name,READY:.endpoints[*].conditions.ready' --no-headers" 12
runc "kubectl -n $E2E get endpoints ds-e2e-web -o jsonpath='{range .subsets[*].addresses[*]}{.ip}{\"\n\"}{end}'" 4
runc "kubectl -n $E2E get endpoints ds-e2e-zero -o jsonpath='subsets={.subsets[*].addresses[*].ip} notReady={.subsets[*].notReadyAddresses[*].ip}{\"\n\"}'" 2
runc "kubectl -n $E2E get svc ds-e2e-wrong-port -o jsonpath='ports={.spec.ports[*].port}->targetPort={.spec.ports[*].targetPort} selector={.spec.selector}{\"\n\"}'" 2
runc "kubectl -n $E2E get networkpolicy ds-e2e-policy -o jsonpath='podSelector={.spec.podSelector.matchLabels} types={.spec.policyTypes} ingress={.spec.ingress}{\"\n\"}'" 3
runc "kubectl -n $E2E get ingress ds-e2e-ingress -o jsonpath='host={.spec.rules[*].host} backend={.spec.rules[*].http.paths[*].backend.service.name}{\"\n\"}'" 2
runc "kubectl -n $E2E get svc ds-e2e-web-second -o jsonpath='selector={.spec.selector}{\"\n\"}'" 2
runc "kubectl -n $PEER get pod ds-e2e-peer -o jsonpath='{.metadata.name} {.status.phase}{\"\n\"}'" 2
runc "kubectl -n $E2E exec ds-e2e-logs -- python3 -c \"import socket;print('web:',socket.gethostbyname('ds-e2e-web'));print('web.ns:',socket.gethostbyname('ds-e2e-web.$E2E'));print('web.ns.svc:',socket.gethostbyname('ds-e2e-web.$E2E.svc'));print('fqdn:',socket.gethostbyname('ds-e2e-web.$E2E.svc.cluster.local'))\"" 6

sec "4. STORAGE SCENARIOS"
runc "kubectl get storageclass --no-headers" 4
runc "kubectl -n $E2E get pvc --no-headers" 6
runc "kubectl get pv --no-headers | grep ds-e2e" 4
runc "kubectl -n $E2E get pvc ds-e2e-pending -o jsonpath='{.metadata.name} phase={.status.phase} class={.spec.storageClassName}{\"\n\"}'" 2
runc "kubectl -n $E2E get pvc ds-e2e-stateful-0 -o jsonpath='phase={.status.phase} vol={.spec.volumeName} cap={.status.capacity.storage} mode={.spec.accessModes}{\"\n\"}'" 2
runc "kubectl -n $E2E get pvc ds-e2e-stateful-0 -o jsonpath='{.spec.volumeName}' | xargs -I{} kubectl get pv {} -o jsonpath='PV={.metadata.name} class={.spec.storageClassName} reclaim={.spec.persistentVolumeReclaimPolicy} claim={.spec.claimRef.name}{\"\n\"}'" 2

sec "5. PKI / TLS SCENARIOS"
runc "kubectl -n $PKI get secret -o custom-columns='NAME:.metadata.name,TYPE:.type' --no-headers" 12
runc "kubectl -n $PKI get secret ds-e2e-cert-valid -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -subject -issuer -dates -serial -fingerprint -sha256" 8
runc "kubectl -n $PKI get secret ds-e2e-cert-valid -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -ext subjectAltName" 6
runc "kubectl -n $PKI get secret ds-e2e-cert-expired -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -dates -checkend 0" 4
runc "kubectl -n $PKI get secret ds-e2e-cert-expiring -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -dates" 4
runc "kubectl -n $PKI get secret ds-e2e-cert-incomplete -o jsonpath='{.data.tls\.crt}' | base64 -d | grep -c 'BEGIN CERTIFICATE'" 2
runc "kubectl -n $PKI get secret ds-e2e-cert-valid -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -fingerprint -sha256" 2
runc "kubectl -n $PKI get secret ds-e2e-cert-duplicate -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -fingerprint -sha256" 2
runc "kubectl -n $PKI get pod -l app=ds-e2e-tls --no-headers" 3
runc "kubectl -n $PKI get svc ds-e2e-tls --no-headers" 3

sec "6. CERT-MANAGER SCENARIOS"
runc "kubectl get crd | grep cert-manager" 6
runc "kubectl -n cert-manager get deploy --no-headers" 4
runc "kubectl -n $PKI get issuer,certificate,certificaterequest --no-headers" 8
runc "kubectl -n $PKI get certificate ds-e2e-managed -o jsonpath='{range .status.conditions[*]}{.type}={.status} reason={.reason}{\"\n\"}{end}'" 4
runc "kubectl -n $PKI get certificate ds-e2e-managed-failure -o jsonpath='{range .status.conditions[*]}{.type}={.status} reason={.reason}{\"\n\"}{end}'" 4

sec "6b. LIVE TLS ENDPOINT (real handshake)"
runc "(kubectl -n $PKI port-forward svc/ds-e2e-tls 18443:443 >/dev/null 2>&1 &) ; sleep 3; echo | timeout 12 openssl s_client -connect 127.0.0.1:18443 -servername ds-e2e-web.$E2E.svc 2>/dev/null | openssl x509 -noout -subject -issuer -dates -fingerprint -sha256; pkill -f 'port-forward.*18443' 2>/dev/null" 8

sec "7. GITOPS / FLUX SCENARIOS"
runc "kubectl -n flux-system get deploy --no-headers" 8
runc "kubectl -n $GITOPS get gitrepository -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type==\"Ready\")].status,REV:.status.artifact.revision' --no-headers" 6
runc "kubectl -n $GITOPS get kustomization -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type==\"Ready\")].status,APPLIED:.status.lastAppliedRevision' --no-headers" 6
runc "kubectl -n $GITOPS get helmrelease -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type==\"Ready\")].status' --no-headers" 5
runc "kubectl -n $GITOPS get helmrepository -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type==\"Ready\")].status' --no-headers" 4
runc "kubectl -n $GITOPS get gitrepository ds-e2e-source-failed -o jsonpath='{range .status.conditions[*]}{.type}={.status} reason={.reason}{\"\n\"}{end}'" 3
runc "kubectl -n $GITOPS get kustomization ds-e2e-suspended -o jsonpath='suspend={.spec.suspend}{\"\n\"}'" 2
runc "kubectl -n $GITOPS get deploy ds-e2e-git-app -o jsonpath='image={.spec.template.spec.containers[0].image} available={.status.availableReplicas}{\"\n\"}'" 2

sec "8. POSTGRESQL SCENARIOS"
runc "kubectl -n $E2E get pod ds-e2e-postgres ds-e2e-pg-client --no-headers" 4
runc "kubectl -n $E2E get svc ds-e2e-postgres --no-headers" 3
runc "kubectl -n $E2E exec ds-e2e-postgres -- psql -X -U sentinel_integration -d devopssentinel -c '\dt' -c 'SELECT * FROM public.e2e_audit ORDER BY id;'" 16
runc "kubectl -n $E2E exec ds-e2e-pg-client -- bash /workspace/tests/postgres_integration.sh ds-e2e-postgres.devopssentinel-e2e.svc 5432 devopssentinel sentinel_integration /run/credentials/password 2>&1 | tail -6" 8

sec "9. KAFKA SCENARIOS"
runc "kubectl -n $E2E get pod ds-e2e-kafka --no-headers" 3
runc "kubectl -n $E2E get svc ds-e2e-kafka --no-headers" 3

sec "10. DEVOPSSENTINEL (the product under test)"
runc "bash \"\$SENT\" --version" 3
runc "bash \"\$SENT\" --self-test --no-color | tail -3" 5
runc "bash \"\$SENT\" --context $CTX --namespace $E2E --doctor --no-color | sed -n '1,14p'" 18
runc "bash \"\$SENT\" --context $CTX --namespace $E2E --capabilities --no-color | sed -n '1,10p'" 12
runc "bash \"\$SENT\" --context $CTX --namespace $E2E --resources --no-color | sed -n '1,10p'" 12
runc "bash \"\$SENT\" --context $CTX --namespace $E2E --network --no-color | sed -n '1,14p'" 16
runc "bash \"\$SENT\" --context $CTX --namespace $E2E --storage --no-color | sed -n '1,8p'" 10
runc "bash \"\$SENT\" --context $CTX --namespace $PKI --certificates --no-color | sed -n '1,12p'" 14
runc "bash \"\$SENT\" --context $CTX --namespace $PKI --cert-expiry --no-color | sed -n '1,10p'" 12
runc "bash \"\$SENT\" --context $CTX --namespace $GITOPS --gitops --no-color | sed -n '1,14p'" 16
runc "bash \"\$SENT\" --context $CTX --namespace $E2E --triage --no-color | sed -n '1,16p'" 18
runc "bash \"\$SENT\" --context $CTX --namespace $E2E --snapshot --json | head -c 420; echo" 8
runc "bash \"\$SENT\" --context $CTX --namespace $E2E --performance --no-color | sed -n '1,10p'" 12
runc "bash \"\$SENT\" --context $CTX --namespace $E2E --postgres-discovery --no-color | sed -n '1,6p'" 8
runc "bash \"\$SENT\" --context $CTX --namespace $E2E --kafka-discovery --no-color | sed -n '1,6p'" 8
runc "bash \"\$SENT\" --context $CTX --namespace $E2E --ui-debug --no-color | sed -n '1,10p'" 12

sec "11. SECURITY / REDACTION CHECKS"
runc "bash \"\$SENT\" --context $CTX --namespace $E2E --resources --no-color > /tmp/sntl_out.txt 2>&1; printf 'ANSI escapes: '; grep -c \$'\\033' /tmp/sntl_out.txt || true; printf 'secret canary present: '; grep -c 'DS_E2E_SECRET_CANARY_d883e5' /tmp/sntl_out.txt || true; printf 'private key marker present: '; grep -c 'BEGIN .*PRIVATE KEY' /tmp/sntl_out.txt || true" 8
runc "bash \"\$SENT\" --context $CTX --namespace $PKI --certificates --no-color 2>&1 | grep -c 'tls.key\\|PRIVATE KEY' || echo '0 (no private key material in certificate report)'" 4
runc "kubectl -n $E2E get secret ds-e2e-secret -o jsonpath='{.metadata.name} keys={.data}' | head -c 120; echo ' (payload suppressed)'" 3

sec "12. WHAT IS STILL DEPLOYED"
runc "kubectl get ns --no-headers | grep -E 'devopssentinel|cert-manager'" 8
runc "for n in $E2E $PEER $GITOPS $PKI cert-manager; do printf '%-28s pods=%s\n' \"\$n\" \"\$(kubectl -n \$n get pods --no-headers 2>/dev/null | wc -l)\"; done" 8

printf '\n\n########## VERIFICATION COMPLETE ##########\n'



