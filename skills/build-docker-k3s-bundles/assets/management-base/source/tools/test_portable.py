"""Verify a release in an empty Linux filesystem without host runtime libraries."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import tarfile
import tempfile
import termios
import time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--busybox", type=Path, required=True,
                        help="Static test-only BusyBox; not shipped in the release")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    with tempfile.TemporaryDirectory(prefix="portable-") as temp:
        release = Path(temp) / "relocated 中文 path"
        release.mkdir()
        with tarfile.open(args.artifact, "r:gz") as archive:
            archive.extractall(release, filter="data")
        for line in (release / "management/checksums.txt").read_text().splitlines():
            expected, name = line.split("  ", 1)
            if hashlib.sha256((release / name).read_bytes()).hexdigest() != expected:
                raise AssertionError(f"Checksum mismatch: {name}")
        check("all release file checksums", True)
        binary = release / "runtime/python/bin/python3.12"
        check("no ELF interpreter",
              b"INTERP" not in subprocess.check_output(["readelf", "-l", str(binary)]))
        check("no shared library dependencies",
              b"NEEDED" not in subprocess.check_output(["readelf", "-d", str(binary)]))
        root = "/portable 中文 path"
        launcher = root + "/manage.sh"
        interpreter = root + "/runtime/python/bin/python3.12"
        sandbox = [
            "bwrap", "--unshare-user", "--unshare-pid", "--unshare-net", "--die-with-parent",
            "--ro-bind", str(release), root, "--proc", "/proc", "--dev", "/dev",
            "--tmpfs", "/tmp", "--dir", "/bin", "--ro-bind", str(args.busybox.resolve()),
            "/bin/sh", "--clearenv", "--setenv", "PATH", "/bin",
            "--setenv", "TERM", "xterm-256color", "--chdir", "/tmp",
        ]

        def run(command):
            return subprocess.run(sandbox + command, capture_output=True, timeout=20)

        result = run([launcher, "doctor", "--json"])
        check("launcher works in relocated empty filesystem", result.returncode == 0)
        check("static Python and curses available",
              json.loads(result.stdout)["data"]["curses_available"])
        check("help noninteractive", run([launcher, "--help"]).returncode == 0)
        check("unknown command refuses", run([launcher, "not-a-command"]).returncode == 2)
        check("no arguments without TTY refuses", run([launcher]).returncode == 2)
        result = run([launcher, "layout", "--json"])
        check("missing state refuses, no installer fallback", result.returncode != 0)
        check("no host Python or shared libraries",
              run([interpreter, "-I", "-c",
                   "import pathlib; assert not pathlib.Path('/usr').exists(); "
                   "assert not pathlib.Path('/lib').exists(); "
                   "assert not pathlib.Path('/bin/python3').exists()"]).returncode == 0)
        modules = (
            "import curses,locale,ssl,zlib,bz2,lzma,sqlite3,ctypes,json,tarfile,fcntl,pty;"
            "locale.setlocale(locale.LC_ALL,'C.UTF-8');"
            "assert zlib.decompress(zlib.compress(b'hello'))==b'hello';"
            "assert bz2.decompress(bz2.compress(b'hello'))==b'hello';"
            "assert lzma.decompress(lzma.compress(b'hello'))==b'hello';"
            "import sys;sys.path.insert(0," + repr(root + "/manage.pyz") + ");"
            "from managebase.config_io import decode;"
            "assert decode(b'services: {}')['services']=={}"
        )
        check("stdlib compression and vendored YAML", run([interpreter, "-I", "-c", modules]).returncode == 0)
        result = run(["/bin/sh", "-c", 'PATH="$1:$PATH"; export PATH; manage.sh doctor --json',
                      "test", root])
        check("PATH invocation", result.returncode == 0)
        result = run(["/bin/sh", "-c", 'cd "$1"; PATH=.:/bin; export PATH; manage.sh doctor',
                      "test", root])
        check("relative PATH invocation", result.returncode == 0)
        fixture = (
            "from pathlib import Path; import json,subprocess;"
            "r=Path('/tmp/instance');r.mkdir();"
            "paths=['bundle.yaml','deploy/docker/compose.yaml',"
            "'config/compose.override.yaml','config/compose.env','state/installation.json'];"
            "[(r/p).parent.mkdir(parents=True,exist_ok=True) for p in paths];"
            "[(r/p).write_text('services: {}\\n') for p in paths[:-1]];"
            "s={'layout_version':1,'bundle_name':'example','bundle_version':'1',"
            "'instance_id':'example-one','install_root':str(r),'deploy_targets':['docker'],"
            "'storage':[],'compose':{'project_name':'example-one','docker_binary':'/bin/docker',"
            "'files':paths[1:3],'env_files':[paths[3]],'profiles':[]}};"
            "(r/paths[-1]).write_text(json.dumps(s));"
            f"p=subprocess.run([{launcher!r},'layout','--root',str(r),'--json']);"
            "assert p.returncode==0;"
            "s['install_root']='/wrong';(r/paths[-1]).write_text(json.dumps(s));"
            f"p=subprocess.run([{launcher!r},'layout','--root',str(r),'--json']);"
            "assert p.returncode!=0"
        )
        check("fixed installed contract and root mismatch",
              run([interpreter, "-I", "-c", fixture]).returncode == 0)

        def tui(small=False):
            master, slave = pty.openpty()
            before = termios.tcgetattr(slave)
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 8 if small else 24,
                                                            30 if small else 100, 0, 0))
            def start():
                return subprocess.Popen(
                    sandbox + [launcher], stdin=slave, stdout=slave, stderr=slave,
                    start_new_session=True,
                    preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0))

            proc = start()
            output = bytearray()

            def wait(text):
                expected = text.encode()
                data = bytearray()
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    if select.select([master], [], [], .1)[0]:
                        chunk = os.read(master, 65536)
                        output.extend(chunk)
                        data.extend(chunk)
                        if expected in data:
                            return
                raise AssertionError(f"TUI missing {text!r}: {bytes(output[-1200:])!r}")

            try:
                if small:
                    wait("终端至少需要")
                else:
                    wait("部署管理基座")
                    os.write(master, b"\x1bOB\x1bOC\x1bOB\x1bOB\n")
                    wait("python_supported")
                    os.write(master, b"\x1b")
                    wait("部署管理基座")
                    # Start a fresh menu to test Chinese editing from its first entry.
                    os.write(master, b"\x1b")
                    check("TUI arrow navigation and Esc", proc.wait(timeout=5) == 0)
                    check("TUI restores termios", termios.tcgetattr(slave) == before)
                    proc = start()
                    wait("部署管理基座")
                    os.write(master, b"\n")
                    wait("取消")
                    os.write(master, b"\x15" + "/tmp/中文目录".encode() + b"\n")
                    wait("已切换检查目录")
                    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 8, 30, 0, 0))
                    # bwrap's PID-namespace supervisor may not forward terminal signals.
                    pending = [proc.pid]
                    while pending:
                        pid = pending.pop()
                        children = Path(f"/proc/{pid}/task/{pid}/children").read_text().split()
                        pending.extend(map(int, children))
                        if not children:
                            os.kill(pid, signal.SIGWINCH)
                    # Wake a get_wch read restarted by the namespace's signal delivery.
                    os.write(master, b"\x1bOB")
                    wait("终端至少需要")
                os.write(master, b"\x1b")
                check("small TUI exit" if small else "Chinese edit and resize", proc.wait(timeout=5) == 0)
                check("terminal restored after exit", termios.tcgetattr(slave) == before)
                check("no TUI traceback", b"Traceback" not in output)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
                os.close(master)
                os.close(slave)

        tui()
        tui(small=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({
        "artifact_sha256": hashlib.sha256(args.artifact.read_bytes()).hexdigest(),
        "passed": checks, "success": True,
        "scope": "Linux x86_64 scratch rootfs, network isolated, bundled static runtime",
        "not_tested": ["remote deployment of this artifact", "ARM64", "minimum kernel version",
                       "real Docker/firewall mutations by this test"],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(checks)} checks; {args.report}")


if __name__ == "__main__":
    main()
