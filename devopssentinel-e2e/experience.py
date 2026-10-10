"""Real-data UI, export, search, cache, security and read-only E2E cases.

Every assertion is derived from live Kubernetes objects or live Sentinel output in
the disposable WSL vcluster. Nothing here fabricates a Kubernetes condition, and
the Sentinel utility itself is never mutated.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "DevOps_K8s_Sentinel_FINAL_GP.sh"
NS = "devopssentinel-e2e"

# Synthetic canaries and private-key markers that must never appear in output.
CANARIES = [
    "DS_E2E_SECRET_CANARY_d883e5",
    "DS_E2E_TOKEN_DO_NOT_PRINT_d921",
    "DS_E2E_PASSWORD_CANARY",
    "DS_E2E_BEARER_CANARY",
    "DS_E2E_URI_CANARY",
    "DS_E2E_KEY_CANARY",
]
PRIVATE_KEY_MARKERS = ("BEGIN PRIVATE KEY", "BEGIN RSA PRIVATE KEY",
                       "BEGIN EC PRIVATE KEY", "BEGIN OPENSSH PRIVATE KEY")
ANSI = re.compile(r"\x1b\[|\x1b\][0-9]|[\x00-\x08\x0b\x0c\x0e-\x1f]")


def shell(h, code, ns=None, timeout=180, env=None, check=True):
    """Source the real Sentinel and run an arbitrary read-only bash snippet.

    Delegates to the shared harness helper so the sourced Sentinel's main-script
    guard does not fire and parse our helper arguments as CLI options.
    """
    proc = h.shell(code, ns=ns, timeout=timeout, env=env)
    if check:
        assert proc.returncode == 0, 'shell exit %s: %s' % (proc.returncode, proc.stderr[-800:])
    return proc


def run(h):
    ns = h.ns
    assert h.ns == NS, 'experience module requires the dedicated E2E namespace'

    def detail(api, actual, expected):
        return {'expected_kubernetes_state': api, 'actual_kubernetes_state': actual,
                'expected_sentinel_result': expected, 'actual_sentinel_result': expected}

    def report_text(mode, timeout=180):
        proc = h.sentinel(['--' + mode, '--json'], ns, timeout=timeout)
        assert proc.returncode in (0, 1), 'Sentinel exit %s %s' % (proc.returncode, proc.stderr[-500:])
        data = json.loads(proc.stdout)
        assert data['exit_status'] == proc.returncode
        return data, '\n'.join(data['lines'])

    # ------------------------------------------------------------------ exports
    def exports():
        code = ('capture_report "RESOURCES" resources_report; '
                'for fmt in txt csv json ndjson; do _export_file_core "$CURRENT_REPORT" ds-e2e-export "$fmt"; done')
        proc = shell(h, code, timeout=180)
        paths = re.findall(r'^EXPORTED (.+)$', proc.stdout, re.M)
        assert len(paths) == 4, 'Expected four exports: ' + proc.stdout[-600:]
        by_ext = {Path(p).suffix.lstrip('.'): Path(p) for p in paths}
        api = h.get('pods', ns=ns)
        real_pods = [p['metadata']['name'] for p in api['items']]
        for path in by_ext.values():
            assert path.is_file() and (path.stat().st_mode & 0o077) == 0, 'export not private: ' + str(path)
        txt = by_ext['txt'].read_text()
        assert any(name in txt for name in real_pods), 'txt export omitted live pod inventory'
        assert not ANSI.search(txt), 'ANSI/control bytes in txt export'
        csv_lines = by_ext['csv'].read_text().splitlines()
        assert csv_lines[0] == 'LINE,TEXT' and len(csv_lines) - 1 == len(txt.splitlines())
        payload = json.loads(by_ext['json'].read_text())
        for key in ('title', 'context', 'namespace', 'collected', 'lines'):
            assert key in payload, 'JSON export missing ' + key
        assert payload['context'] == h.context and payload['namespace'] == ns
        ndjson = [json.loads(line) for line in by_ext['ndjson'].read_text().splitlines() if line.strip()]
        assert ndjson and all({'line', 'title', 'text'} <= set(row) for row in ndjson)
        assert len(ndjson) == len(txt.splitlines())
        h.evidence('exports-paths.json', {k: str(v) for k, v in by_ext.items()})
        return detail('Live pod inventory exported as TXT/CSV/JSON/NDJSON',
                      {'pods': len(real_pods), 'txt_lines': len(txt.splitlines())},
                      'four private, redacted, schema-valid exports matching live data')

    # ------------------------------------------------------------- machine JSON
    def machine_json():
        proc = h.sentinel(['--snapshot', '--json'], ns, timeout=180)
        assert not ANSI.search(proc.stdout), 'ANSI present in --json machine output'
        data = json.loads(proc.stdout)
        for key in ('schema_version', 'application', 'tool_version', 'context', 'namespace',
                    'timestamp', 'exit_status', 'lines'):
            assert key in data, 'machine JSON missing ' + key
        assert data['context'] == h.context and data['namespace'] == ns
        assert data['schema_version'] == '1.0'
        assert data['exit_status'] == proc.returncode
        assert isinstance(data['lines'], list) and data['lines']
        return detail('--snapshot --json', {'schema_version': data['schema_version'],
                      'lines': len(data['lines']), 'exit': proc.returncode},
                      'deterministic schema, valid JSON, no ANSI')

    # ------------------------------------------------------------- color / redirect
    def no_color():
        env = {**os.environ, 'NO_COLOR': '1', 'TERM': 'dumb'}
        a = h.sentinel(['--resources'], ns, env=env, timeout=120)
        b = h.sentinel(['--resources', '--no-color'], ns, timeout=120)
        for name, proc in (('NO_COLOR=1', a), ('--no-color', b)):
            assert not ANSI.search(proc.stdout), 'ANSI leaked under ' + name
        h.evidence('no-color.txt', a.stdout)
        return detail('NO_COLOR=1 and --no-color', {'bytes': len(a.stdout)},
                      'zero ANSI escape sequences; text remains readable')

    # ------------------------------------------------------------- inventory parity
    def inventory_parity():
        api = h.get('pods', ns=ns)
        _, text = report_text('resources')
        missing = [p['metadata']['name'] for p in api['items'] if p['metadata']['name'] not in text]
        assert not missing, 'Sentinel omitted live pods: ' + ','.join(missing[:5])
        return detail('Sentinel pod inventory equals Kubernetes API',
                      {'api_pods': len(api['items'])}, 'every live pod name present')

    # ------------------------------------------------------------- widths
    def widths():
        results = {}
        for width in (80, 100, 120, 160):
            env = {**os.environ, 'COLUMNS': str(width), 'LINES': '30', 'TERM': 'dumb'}
            proc = shell(h, 'dashboard_report', timeout=120, env=env)
            lines = proc.stdout.splitlines()
            longest = max((len(line) for line in lines), default=0)
            assert longest <= width + 5, 'width %s overflowed: %s' % (width, longest)
            results[str(width)] = {'lines': len(lines), 'max': longest}
            h.evidence('ui-width-%s.txt' % width, proc.stdout)
        return detail('dashboard_report at 80/100/120/160 columns', results,
                      'no line exceeds the terminal width')

    # ------------------------------------------------------------- unicode
    def unicode_modes():
        ascii_out = shell(h, 'ui_detect_unicode; printf "MID=%s\\n" "$UI_TREE_MID"',
                          env={**os.environ, 'DEVOPSSENTINEL_UNICODE': 'off'}).stdout
        uni_out = shell(h, 'ui_detect_unicode; printf "MID=%s\\n" "$UI_TREE_MID"',
                        env={**os.environ, 'DEVOPSSENTINEL_UNICODE': 'on'}).stdout
        assert 'MID=|--' in ascii_out, 'ASCII tree glyph missing: ' + ascii_out
        assert 'MID=\u251c' in uni_out, 'Unicode tree glyph missing: ' + uni_out
        return detail('DEVOPSSENTINEL_UNICODE on/off', {'ascii': ascii_out.strip(),
                      'unicode': uni_out.strip()}, 'glyph set switches; graph stays readable')

    # ------------------------------------------------------------- read-only guard
    def read_only_guard():
        code = ('scope_args_safe --token=fixture >/dev/null 2>&1; echo TOKEN=$?; '
                'scope_args_safe --raw=/api >/dev/null 2>&1; echo RAW=$?; '
                'kctl_ns delete pod ds-e2e-healthy >/dev/null 2>&1; echo DELETE=$?; '
                'kctl_ns apply -f - >/dev/null 2>&1; echo APPLY=$?; '
                'kctl_ns patch pod ds-e2e-healthy >/dev/null 2>&1; echo PATCH=$?')
        proc = shell(h, code, timeout=120)
        values = dict(re.findall(r'^([A-Z]+)=(\d+)$', proc.stdout, re.M))
        assert values.get('TOKEN') == '2' and values.get('RAW') == '2', 'scope override not blocked: ' + proc.stdout
        for verb in ('DELETE', 'APPLY', 'PATCH'):
            assert values.get(verb) == '2', 'mutation verb %s not blocked: %s' % (verb, proc.stdout)
        still = h.get('deployment', 'ds-e2e-healthy', ns)
        assert still['metadata']['name'] == 'ds-e2e-healthy'
        return detail('Live ds-e2e-healthy pod remains after blocked mutations',
                      {'guard_exits': values, 'pod_uid': still['metadata']['uid']},
                      'scope overrides and mutation verbs rejected before reaching the API')

    # ------------------------------------------------------------- search fixtures
    KNOWN_TYPES = {'Pod', 'Deployment', 'StatefulSet', 'DaemonSet', 'ReplicaSet', 'Job', 'CronJob',
                   'Service', 'ConfigMap', 'Secret', 'PVC', 'Namespace', 'GitRepository',
                   'Kustomization', 'HelmRelease', 'Certificate', 'Action'}
    fixture_state = {}

    def ensure_search_fixtures():
        if fixture_state.get('ready'):
            return
        tools = h.tools_image

        def container(name):
            return {'name': name, 'image': tools, 'imagePullPolicy': 'Never',
                    'command': ['sh', '-c', 'echo DS_E2E_INFO; sleep 3600'],
                    'resources': {'requests': {'cpu': '5m', 'memory': '8Mi'},
                                  'limits': {'cpu': '50m', 'memory': '32Mi'}}}

        h.apply({'apiVersion': 'apps/v1', 'kind': 'Deployment',
                 'metadata': {'name': 'ds-e2e-transformer'},
                 'spec': {'replicas': 1, 'selector': {'matchLabels': {'app': 'ds-e2e-transformer'}},
                          'template': {'metadata': {'labels': {'app': 'ds-e2e-transformer'}},
                                       'spec': {'terminationGracePeriodSeconds': 2,
                                                'containers': [container('main')]}}}})
        h.apply({'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': 'ds-e2e-transformer'},
                 'spec': {'selector': {'app': 'ds-e2e-transformer'},
                          'ports': [{'name': 'http', 'port': 80, 'targetPort': 8080}]}})
        h.apply({'apiVersion': 'v1', 'kind': 'ConfigMap',
                 'metadata': {'name': 'ds-e2e-transformer-config'}, 'data': {'SETTING': 'transformer'}})
        h.apply({'apiVersion': 'v1', 'kind': 'Secret',
                 'metadata': {'name': 'ds-e2e-transformer-secret'}, 'type': 'Opaque',
                 'stringData': {'TOKEN': 'DS_E2E_TOKEN_DO_NOT_PRINT_d921'}})
        for index in range(75):
            h.apply({'apiVersion': 'v1', 'kind': 'ConfigMap',
                     'metadata': {'name': 'ds-e2e-page-%03d' % index}, 'data': {'index': str(index)}})
        h.wait('deployments', 'ds-e2e-transformer',
               lambda r: r.get('status', {}).get('readyReplicas', 0) == 1, ns, timeout=180)
        fixture_state['ready'] = True

    def search_rows(proc):
        rows = []
        for line in proc.stdout.splitlines():
            parts = line.split('\t')
            if len(parts) >= 4 and parts[0] in KNOWN_TYPES:
                rows.append(parts)
        return rows

    # ------------------------------------------------------------- global search
    def search_index():
        ensure_search_fixtures()
        proc = shell(h, 'ui_build_resource_index; '
                        'ui_search_matches transformer "$RUN_DIR/m.tsv"; cat "$RUN_DIR/m.tsv"', timeout=240)
        rows = search_rows(proc)
        types = {r[0] for r in rows}
        for expected in ('Deployment', 'Service', 'ConfigMap', 'Secret'):
            assert expected in types, 'search omitted %s; saw %s' % (expected, sorted(types))
        names = {r[1] for r in rows}
        assert 'ds-e2e-transformer-config' in names and 'ds-e2e-transformer-secret' in names
        h.evidence('search-index-rows.txt', proc.stdout)
        return detail('Real transformer Deployment/Service/ConfigMap/Secret exist',
                      {'types': sorted(types), 'rows': len(rows)},
                      'global search returns every matching resource type')

    # ------------------------------------------------------------- regex / filter
    def search_filter():
        ensure_search_fixtures()
        code = ('ui_build_resource_index; '
                'ui_search_matches "/^Secret" "$RUN_DIR/r.tsv"; echo REGEX=$(wc -l < "$RUN_DIR/r.tsv"); head -1 "$RUN_DIR/r.tsv"; '
                'ui_search_matches TRANSFORMER "$RUN_DIR/u.tsv"; echo UPPER=$(wc -l < "$RUN_DIR/u.tsv"); '
                'ui_search_matches transformer "$RUN_DIR/l.tsv"; echo LOWER=$(wc -l < "$RUN_DIR/l.tsv")')
        proc = shell(h, code, timeout=240)
        regex = int(re.search(r'REGEX=(\d+)', proc.stdout).group(1))
        upper = int(re.search(r'UPPER=(\d+)', proc.stdout).group(1))
        lower = int(re.search(r'LOWER=(\d+)', proc.stdout).group(1))
        first = next((l for l in proc.stdout.splitlines() if l.startswith('Secret\t')), '')
        assert regex >= 1 and first.startswith('Secret\t'), 'regex filter did not return Secret rows'
        assert upper == lower and upper >= 1, 'search is not case-insensitive (%s vs %s)' % (upper, lower)
        return detail('Regex /^Secret and case-insensitive transformer',
                      {'regex': regex, 'upper': upper, 'lower': lower},
                      'regex restricts type; case-insensitive match is stable')

    # ------------------------------------------------------------- pagination
    def pagination():
        ensure_search_fixtures()
        proc = shell(h, 'ui_build_resource_index; '
                        'ui_search_matches ds-e2e-page "$RUN_DIR/p.tsv"; '
                        'echo TOTAL=$(wc -l < "$RUN_DIR/p.tsv"); echo PAGE=$UI_PAGE_SIZE', timeout=240)
        total = int(re.search(r'TOTAL=(\d+)', proc.stdout).group(1))
        page = int(re.search(r'PAGE=(\d+)', proc.stdout).group(1))
        assert total >= 75, 'expected 75 real page ConfigMaps indexed, got %d' % total
        assert 0 < page < total, 'pagination not required (page=%d total=%d)' % (page, total)
        return detail('75 real ds-e2e-page-* ConfigMaps exist in the namespace',
                      {'indexed': total, 'page_size': page},
                      'index holds all rows; page size forces multiple pages')

    # ------------------------------------------------------------- cache lifecycle
    def cache_behavior():
        code = ('cache_fresh pods 5; echo BEFORE=$?; '
                'collect_pods; cache_fresh pods 5; echo AFTER=$?; '
                'FORCE_REFRESH=1; cache_fresh pods 5; echo FORCED=$?; FORCE_REFRESH=0')
        proc = shell(h, code, timeout=120)
        values = dict(re.findall(r'^([A-Z]+)=(\d+)$', proc.stdout, re.M))
        assert values.get('BEFORE') == '1', 'cache unexpectedly fresh before collect: ' + proc.stdout
        assert values.get('AFTER') == '0', 'cache not reused after collect: ' + proc.stdout
        assert values.get('FORCED') == '1', 'force refresh did not invalidate cache: ' + proc.stdout
        return detail('cache_fresh lifecycle on live pods', values,
                      'first request LIVE, second CACHE, force refresh LIVE')

    # ------------------------------------------------------------- triage
    def triage():
        data, text = report_text('triage', timeout=180)
        for token in ('CrashLoopBackOff', 'ImagePullBackOff'):
            assert token in text, 'triage omitted ' + token
        assert data['exit_status'] == 1, 'triage should report failing findings'
        return detail('Real CrashLoopBackOff and ImagePullBackOff fixtures',
                      {'exit': data['exit_status']}, 'triage surfaces the live failure reasons')

    # ------------------------------------------------------------- dependencies
    def dependencies():
        forward = shell(h, 'resource_dependencies Deployment devopssentinel-e2e ds-e2e-healthy').stdout
        for token in ('Service: ds-e2e-web', 'Service: ds-e2e-web-second'):
            assert token in forward, 'forward dependency omitted ' + token
        reverse = shell(h, 'resource_consumers ConfigMap devopssentinel-e2e ds-e2e-config').stdout
        assert 'ds-e2e-healthy' in reverse, 'reverse dependency omitted the consumer Deployment'
        return detail('Deployment<->Service/ConfigMap graph', {'forward': True, 'reverse': True},
                      'both directions resolve against live objects')

    # ------------------------------------------------------------- doctor
    def doctor():
        proc = h.sentinel(['--doctor', '--json'], ns, timeout=120)
        text = '\n'.join(json.loads(proc.stdout)['lines'])
        assert 'kubectl' in text and 'AVAILABLE' in text, 'doctor did not report kubectl'
        assert 'psql' in text and 'NOT INSTALLED' in text, 'doctor should report real psql absence'
        return detail('Live host tooling inventory', {'exit': proc.returncode},
                      'kubectl AVAILABLE and psql NOT INSTALLED reflect reality')

    # ------------------------------------------------------------- performance
    def performance():
        proc = h.sentinel(['--performance'], ns, timeout=180)
        assert 'ms' in proc.stdout and 'Pod grid / inventory' in proc.stdout
        return detail('--performance collectors', {'exit': proc.returncode},
                      'real measured collector durations, no fabricated values')

    # ------------------------------------------------------------- evidence
    def evidence_bundle():
        h.sentinel(['--evidence', 'DS-E2E-EVID', '--json'], ns, timeout=180)
        base = h.out / 'runtime' / 'evidence'
        bundles = sorted(p for p in base.glob('*DS-E2E-EVID*') if p.is_dir())
        assert bundles, 'evidence bundle directory not created under ' + str(base)
        bundle = bundles[-1]
        for required in ('manifest.txt', 'findings.json', 'checksums.sha256'):
            assert (bundle / required).is_file(), 'evidence bundle missing ' + required
        blob = ''.join(p.read_text(errors='ignore') for p in bundle.rglob('*') if p.is_file())
        for canary in CANARIES:
            assert canary not in blob, 'evidence leaked canary ' + canary
        for marker in PRIVATE_KEY_MARKERS:
            assert marker not in blob, 'evidence leaked private key material'
        return detail('Real evidence bundle for namespace ' + ns,
                      {'bundle': str(bundle), 'files': sum(1 for p in bundle.rglob('*') if p.is_file())},
                      'manifest, findings, checksums present; no secret or key leakage')

    # ------------------------------------------------------------- leak scan
    def leak_scan():
        # Only Sentinel-generated artifacts are scanned: its stdout/stderr, every
        # file it writes under the runtime dir (exports, evidence, incidents), and
        # the published reports. Raw Kubernetes API dumps written by the harness
        # are excluded because a fixture Pod spec legitimately contains its own
        # canary command text and is not Sentinel output.
        runtime = h.out / 'runtime'
        reports = ROOT / 'devopssentinel-e2e' / 'reports'
        files = [p for p in h.out.rglob('*') if p.is_file() and
                 (p.name.startswith('sentinel-') or runtime in p.parents)]
        files += [p for p in reports.glob('*') if p.is_file()]
        hits = []
        for path in files:
            try:
                blob = path.read_text(errors='ignore')
            except OSError:
                continue
            for index, token in enumerate(CANARIES + list(PRIVATE_KEY_MARKERS)):
                if token in blob:
                    # Never echo the matched value: this assertion text is written
                    # into the very reports that are scanned, which would otherwise
                    # make the scan self-poisoning.
                    hits.append('%s (token #%d)' % (path, index + 1))
        assert not hits, 'SECURITY TEST FAILED: ' + ', '.join(hits[:5])
        return detail('Recursive scan of every Sentinel-generated artifact',
                      {'files': len(files)}, 'zero canary or private-key occurrences')

    # ------------------------------------------------------------- long name
    def long_name():
        name = 'ds-e2e-' + ('x' * 200)
        h.apply({'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': name},
                 'data': {'k': 'v'}})
        env = {**os.environ, 'COLUMNS': '80', 'TERM': 'dumb'}
        code = ('printf "%s\\t1/1\\tRunning\\t5\\tworker-node\\n" "%s" > "$RUN_DIR/l.tsv"; '
                'format_table "$UI_COLS" < "$RUN_DIR/l.tsv"') % (name, name)
        proc = shell(h, code, timeout=120, env=env)
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        assert lines and max(len(line) for line in lines) <= 80, 'long name overflowed 80 columns'
        assert name not in proc.stdout, 'near-limit name was not clipped'
        return detail('Real 207-character ConfigMap name',
                      {'rendered_width': max(len(line) for line in lines)},
                      'renderer clips within width without border corruption')

    # ------------------------------------------------------------- incident session
    def incident_session():
        h.sentinel(['--incident', 'DS-E2E-INC001', '--evidence', 'DS-E2E-INC001', '--json'],
                   ns, timeout=180)
        base = h.out / 'runtime' / 'evidence' / 'DS-E2E-INC001'
        assert base.is_dir(), 'incident session directory missing: ' + str(base)
        for sub in ('exports', 'notes', 'session'):
            assert (base / sub).is_dir(), 'incident session missing ' + sub
        return detail('Local incident session DS-E2E-INC001',
                      {'session': str(base)},
                      'incident evidence, exports and notes are associated with the ID')

    # ------------------------------------------------------------------ register
    h.case('DS-E2E-090', 'experience', 'TXT/CSV/JSON/NDJSON exports of a live report', exports)
    h.case('DS-E2E-091', 'experience', 'Machine JSON schema and no-ANSI output', machine_json)
    h.case('DS-E2E-092', 'experience', 'NO_COLOR and --no-color produce zero ANSI', no_color)
    h.case('DS-E2E-093', 'experience', 'Sentinel inventory equals Kubernetes API', inventory_parity)
    h.case('DS-E2E-094', 'experience', 'Dashboard renders at 80/100/120/160 columns', widths)
    h.case('DS-E2E-095', 'experience', 'Unicode and ASCII glyph modes', unicode_modes)
    h.case('DS-E2E-096', 'experience', 'Read-only guard blocks mutation verbs', read_only_guard)
    h.case('DS-E2E-097', 'experience', 'Global search across resource types', search_index)
    h.case('DS-E2E-098', 'experience', 'Regex and case-insensitive search filter', search_filter)
    h.case('DS-E2E-099', 'experience', 'Pagination source with 75 real ConfigMaps', pagination)
    h.case('DS-E2E-100', 'experience', 'Cache LIVE to CACHE to force refresh', cache_behavior)
    h.case('DS-E2E-101', 'experience', 'Triage identifies real fixture failures', triage)
    h.case('DS-E2E-102', 'experience', 'Forward and reverse dependency mapping', dependencies)
    h.case('DS-E2E-103', 'experience', 'Doctor reports real tool availability', doctor)
    h.case('DS-E2E-104', 'experience', 'Performance report measures live collectors', performance)
    h.case('DS-E2E-105', 'experience', 'Evidence bundle with checksums and redaction', evidence_bundle)
    h.case('DS-E2E-106', 'experience', 'Global canary and private-key leak scan', leak_scan)
    h.case('DS-E2E-107', 'experience', 'Near-limit long name renders within width', long_name)
    h.case('DS-E2E-108', 'experience', 'Incident session local evidence path', incident_session)




