#!/usr/bin/env python3
"""Read-only CLI/API comparison suite; setup and Flux writes live in scripts/."""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'DevOps_K8s_Sentinel_FINAL_GP.sh'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--context', required=True)
parser.add_argument('--namespace', required=True)
parser.add_argument('--workload', required=True, help='Deployment name in the selected namespace')
parser.add_argument('--output', type=Path, default=Path.home() / '.devopssentinel/e2e-results')
parser.add_argument('--fault-fixtures', action='store_true')
args = parser.parse_args()
os.umask(0o077)
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out = args.output / stamp
out.mkdir(parents=True)
base = ['bash', str(SCRIPT), '--context', args.context, '--namespace', args.namespace,
        '--output', str(Path.home() / '.devopssentinel/e2e-runtime'), '--no-color']
results = []

def record(name, ok, detail=''):
    row = {'check': name, 'passed': bool(ok), 'detail': detail}
    results.append(row)
    print(f'{"PASS" if ok else "FAIL"} {name}: {detail}', flush=True)

def execute(name, options, expected=(0,), structured=True):
    start = time.monotonic()
    try:
        proc = subprocess.run(base + options + (['--json'] if structured else []),
                              text=True, capture_output=True, timeout=180)
        (out / (name + '.stdout')).write_text(proc.stdout)
        (out / (name + '.stderr')).write_text(proc.stderr)
        data = json.loads(proc.stdout) if structured else None
        ok = proc.returncode in expected and not re.search(
            r'Permission denied|jq: error|command not found|syntax error|unbound variable',
            proc.stdout + proc.stderr)
        if structured:
            ok = ok and data['exit_status'] == proc.returncode and data['namespace'] == args.namespace
        record(name, ok, f'exit={proc.returncode}; seconds={time.monotonic()-start:.2f}')
        return data, proc
    except (subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        record(name, False, str(exc))
        return None, None

kube = ['kubectl', '--context', args.context, '-n', args.namespace, '--request-timeout=15s']
pods = json.loads(subprocess.check_output(kube + ['get', 'pods', '-o', 'json']))
expected_pods = {pod['metadata']['name'] for pod in pods['items']}
record('nonempty-live-pod-baseline', bool(expected_pods), f'{len(expected_pods)} pods')

modes = ['resources', 'network', 'storage', 'gitops', 'gitops-graph', 'certificates',
         'cert-expiry', 'health', 'triage', 'etdp', 'postgres-discovery', 'kafka-discovery',
         'doctor', 'capabilities', 'live-validate', 'performance', 'snapshot']
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    jobs = {mode: pool.submit(execute, mode, ['--'+mode], (0, 1, 4)) for mode in modes}
    reports = {mode: job.result()[0] for mode, job in jobs.items()}

resource_text = '\n'.join((reports.get('resources') or {}).get('lines', []))
record('pod-inventory-matches-api', all(name in resource_text for name in expected_pods))
live_text = '\n'.join((reports.get('live-validate') or {}).get('lines', []))
record('required-live-collectors', 'pods=OK PASS' in live_text and 'PARTIAL/FAIL' not in live_text)
execute('workload-triage', ['--triage-workload', 'Deployment/'+args.workload], (0, 1, 4))
execute('dependency', ['--dependency', 'Deployment/'+args.workload])
execute('quiet-resources', ['--resources', '--quiet'], structured=False)
execute('offline-self-test', ['--self-test'], structured=False)
execute('ui-debug', ['--ui-debug'], structured=False)
execute('explain', ['--explain', 'gitops'], structured=False)
execute('missing-context', ['--doctor', '--context', 'sentinel-no-such-context'], (4,))
execute('missing-namespace', ['--resources', '--namespace', 'sentinel-no-such-namespace'], (2,), False)
execute('invalid-threshold', ['--resources', '--cpu-warn', '99', '--cpu-critical', '90'], (2,), False)
execute('conflicting-modes', ['--resources', '--health'], (2,), False)
execute('missing-workload', ['--triage-workload', 'Deployment/sentinel-no-such-workload'], (2,))

_, evidence = execute('evidence', ['--evidence', 'e2e-'+stamp], structured=False)
if evidence:
    match = re.search(r'Evidence bundle: (.+)', evidence.stdout)
    if match:
        directory = Path(match.group(1))
        verify = subprocess.run(['sha256sum', '-c', 'checksums.sha256'], cwd=directory, capture_output=True)
        record('evidence-checksums', verify.returncode == 0)
        findings = json.loads((directory / 'findings.json').read_text())
        record('evidence-findings-structure', isinstance(findings, list) and all(
            isinstance(row.get('severity'), str) and isinstance(row.get('finding'), str) for row in findings))
        all_text = '\n'.join(path.read_text(errors='replace') for path in directory.rglob('*') if path.is_file())
        record('evidence-no-secret-payload', 'SENTINEL_E2E_CANARY_DO_NOT_EXPORT' not in all_text and
               not re.search(r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----', all_text))
        record('evidence-private-permissions', all(path.stat().st_mode & 0o077 == 0
               for path in directory.rglob('*')))
        if args.fault_fixtures:
            record('evidence-preserves-findings', bool(findings))
    else:
        record('evidence-bundle-created', False)

if args.fault_fixtures:
    storage_text = '\n'.join((reports.get('storage') or {}).get('lines', []))
    cert_text = '\n'.join((reports.get('cert-expiry') or {}).get('lines', []))
    health_text = '\n'.join((reports.get('health') or {}).get('lines', []))
    record('pending-pvc-visible', 'PVC/sentinel-pending phase=Pending' in storage_text and 'UNBOUND' in storage_text)
    record('short-lived-cert-critical', 'sentinel-test-tls' in cert_text and 'CRITICAL' in cert_text)
    record('failed-pod-detected', 'sentinel-failed' in health_text and (reports.get('health') or {}).get('exit_status') == 1)

summary = {'context': args.context, 'namespace': args.namespace, 'collected': stamp,
           'source_sha256': hashlib.sha256(SCRIPT.read_bytes()).hexdigest(), 'results': results,
           'passed': sum(row['passed'] for row in results), 'failed': sum(not row['passed'] for row in results)}
(out / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
print(f'SUMMARY {summary["passed"]} passed, {summary["failed"]} failed; {out / "summary.json"}')
sys.exit(bool(summary['failed']))
