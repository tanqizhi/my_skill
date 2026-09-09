"""Bounded subprocess execution. No shell and no inherited Docker context."""

import os
from pathlib import Path
import selectors
import signal
import subprocess
import time

from .model import ManagementError


def run_readonly(argv: list[str], cwd: Path, *, timeout: float = 15,
                 max_output: int = 1024 * 1024) -> bytes:
    return run_command(argv, cwd, timeout=timeout, max_output=max_output)


def run_command(argv: list[str], cwd: Path, *, timeout: float = 15,
                max_output: int = 1024 * 1024, tick=None) -> bytes:
    # Compose interpolation must not inherit unrelated caller variables.
    env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
           "HOME": str(cwd),
           "LC_ALL": "C.UTF-8", "COMPOSE_DISABLE_ENV_FILE": "1",
           "COMPOSE_ANSI": "never"}
    try:
        proc = subprocess.Popen(
            argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True, shell=False,
        )
    except OSError:
        raise ManagementError("无法执行已登记的 Docker 程序，请检查路径、权限和运行时安装。", 4) from None
    assert proc.stdout is not None and proc.stderr is not None
    output = bytearray()
    total = 0
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ, True)
            selector.register(proc.stderr, selectors.EVENT_READ, False)
            while selector.get_map():
                if tick:
                    tick()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ManagementError("Docker 命令超时；已终止客户端，容器实际状态需重新查询。", 5)
                for key, _ in selector.select(min(remaining, 0.2)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if total > max_output:
                        raise ManagementError("运行时输出超过安全上限，检查已终止。", 5)
                    if key.data:
                        output.extend(chunk)
            try:
                code = proc.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise ManagementError("Docker 命令超时；已终止客户端，容器实际状态需重新查询。", 5) from None
        if code:
            # Runtime diagnostics can contain interpolated secrets.
            raise ManagementError(f"Docker 命令失败，退出码 {code}；原始输出未显示，以免泄露配置。", 5)
        return bytes(output)
    finally:
        # Terminate descendants too, including ones retaining an output pipe.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        proc.stdout.close()
        proc.stderr.close()
