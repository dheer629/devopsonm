#!/usr/bin/env python3
"""Run a command under a real pseudo-terminal, optionally send keys, and report
what the terminal actually received. Used by the E2E harness for interactive
(TUI) tests: dashboard startup, navigation, quit, Ctrl-C and terminal restore.

Usage:
  python3 ptyrun.py --cols 120 --rows 30 --keys 'q' --delay 2 --timeout 20 -- \
      bash DevOps_K8s_Sentinel_FINAL_GP.sh --context X --namespace Y

Writes the raw terminal byte stream to stdout (and to --output if given).
"""
import argparse
import fcntl
import os
import pty
import select
import struct
import sys
import termios
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cols', type=int, default=120)
    ap.add_argument('--rows', type=int, default=30)
    ap.add_argument('--send', action='append', default=[],
                    help='SECONDS:KEYS step, e.g. --send 3:q\\r (repeatable)')
    ap.add_argument('--timeout', type=float, default=20.0)
    ap.add_argument('--output', default='')
    ap.add_argument('cmd', nargs=argparse.REMAINDER)
    args = ap.parse_args()

    steps = []
    for spec in args.send:
        when, _, keys = spec.partition(':')
        steps.append((float(when), keys))
    steps.sort()

    cmd = args.cmd
    if cmd and cmd[0] == '--':
        cmd = cmd[1:]
    if not cmd:
        print('no command', file=sys.stderr)
        return 2

    pid, fd = pty.fork()
    if pid == 0:                                  # child: becomes the command
        try:
            os.execvp(cmd[0], cmd)
        except OSError as exc:
            sys.stderr.write('exec failed: %s\n' % exc)
            os._exit(127)

    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', args.rows, args.cols, 0, 0))

    buf = bytearray()
    start = time.time()
    deadline = start + args.timeout
    pending = list(steps)
    while time.time() < deadline:
        elapsed = time.time() - start
        while pending and elapsed >= pending[0][0]:
            _, keys = pending.pop(0)
            os.write(fd, keys.encode().decode('unicode_escape').encode('latin-1'))
        readable, _, _ = select.select([fd], [], [], 0.2)
        if readable:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
        else:
            try:
                done, _ = os.waitpid(pid, os.WNOHANG)
                if done:
                    break
            except ChildProcessError:
                break

    try:
        os.kill(pid, 15)
    except OSError:
        pass
    time.sleep(0.3)
    try:
        os.waitpid(pid, 0)
    except OSError:
        pass

    text = buf.decode('utf-8', 'replace')
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as handle:
            handle.write(text)
    sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
