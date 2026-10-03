#!/usr/bin/env python3
"""Real API-denial checks plus a PTY dashboard smoke test, without cluster writes."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import struct
import subprocess
import tempfile
import termios
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--context', required=True)
p.add_argument('--namespace', required=True)
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
base = ['bash', str(root / 'DevOps_K8s_Sentinel_FINAL_GP.sh'), '--context', a.context,
        '--namespace', a.namespace, '--no-color']
os.umask(0o077)
failed = []

def check(name, ok):
    print(f'{"PASS" if ok else "FAIL"} {name}', flush=True)
    if not ok:
        failed.append(name)

# Real Kubernetes impersonation. Only a temporary local kubectl wrapper changes;
# the utility receives no unrestricted CLI override and no kubeconfig is copied.
with tempfile.TemporaryDirectory(prefix='.sentinel-access-', dir=Path.home()) as temp:
    real = shutil.which('kubectl')
    wrapper = Path(temp) / 'kubectl'
    wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(real) +
                       ' --as=system:serviceaccount:' + a.namespace + ':sentinel-no-access "$@"\n')
    wrapper.chmod(0o700)
    env = dict(os.environ, PATH=temp+os.pathsep+os.environ['PATH'])
    for mode in ['doctor', 'live-validate', 'triage', 'health']:
        result = subprocess.run(base + ['--'+mode, '--json'], env=env, text=True,
                                capture_output=True, timeout=120)
        try:
            data = json.loads(result.stdout)
        except ValueError:
            data = {}
        check('RBAC-denied-'+mode, result.returncode == 4 and data.get('exit_status') == 4
              and ('RBAC_DENIED' in result.stdout or 'PARTIAL' in result.stdout))

# A real terminal exercises startup, navigation, and restoring terminal modes.
for width in [80, 120]:
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, width, 0, 0))
    before = termios.tcgetattr(slave)
    env = dict(os.environ, TERM='xterm-256color', COLUMNS=str(width), LINES='40')
    proc = subprocess.Popen(base, stdin=slave, stdout=slave, stderr=slave, env=env,
                            start_new_session=True)
    buf = b''
    pending = b''
    stage = 0
    deadline = time.monotonic()+30
    while proc.poll() is None and time.monotonic() < deadline:
        if select.select([master], [], [], 0.2)[0]:
            try:
                chunk = os.read(master, 65536)
                buf += chunk
                pending += chunk
            except OSError:
                break
        if stage == 0 and b'SELECT [1-40 / hotkey]' in pending:
            os.write(master, b'1\n')
            stage, pending = 1, b''
        elif stage == 1 and b'ACTION >' in pending:
            os.write(master, b'v\n')
            stage, pending = 2, b''
        elif stage == 2 and b'ACTION >' in pending:
            os.write(master, b'b\n')
            stage, pending = 3, b''
        elif stage == 3 and b'SELECT [1-40 / hotkey]' in pending:
            os.write(master, b'q\n')
            stage, pending = 4, b''
    if proc.poll() is None:
        proc.terminate()
    proc.wait(timeout=10)
    after = termios.tcgetattr(slave)
    check('dashboard-PTY-'+str(width), stage == 4 and proc.returncode == 0
          and b'View: DETAIL' in buf
          and b'Permission denied' not in buf and b'command not found' not in buf)
    check('terminal-restored-'+str(width), before == after)
    os.close(master)
    os.close(slave)
raise SystemExit(bool(failed))
