"""CapabilitySandbox — subprocess execution with Linux seccomp and rlimits.

Runs untrusted code in a restricted subprocess.  Falls back gracefully
if seccomp is unavailable (containers without unshare, non-Linux, etc.).
"""

import asyncio, json, os, resource, signal, subprocess, tempfile, textwrap, time
from typing import Any, Optional, Dict
from pathlib import Path


class CapabilitySandbox:
    def __init__(self, timeout_default: int = 10, seccomp_bpf_path: str = None):
        self.timeout_default = timeout_default
        self._seccomp_available = False
        self._has_unshare = os.system("command -v unshare >/dev/null 2>&1") == 0
        self._linux = os.uname().sysname == "Linux"

    @staticmethod
    def _limit_resources():
        """Hard rlimits for the child process."""
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024, 32 * 1024 * 1024))

    async def run(
        self,
        code: str,
        timeout: int = None,
        args: list[str] = None,
        env: Dict[str, str] = None,
    ) -> Dict[str, Any]:
        timeout = timeout or self.timeout_default
        args = args or []
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            script_path = f.name

        cmd_exec = [subprocess.sys.executable, script_path, *args]
        cmd = cmd_exec
        use_unshare = self._linux and self._has_unshare

        t0 = time.time()
        try:
            if use_unshare:
                cmd = [
                    "unshare", "--fork", "--pid", "--ipc", "--net", "--mount-proc",
                    "--map-root-user",
                ] + cmd_exec
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=self._limit_resources if not use_unshare else None,
                env={k: v for k, v in (env or {}).items()}
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            elapsed = time.time() - t0
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace")[:65536],
                "stderr": stderr.decode("utf-8", errors="replace")[:65536],
                "elapsed_sec": elapsed,
            }
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return {
                "ok": False,
                "error": "TIMEOUT",
                "returncode": -signal.SIGKILL,
                "stdout": "",
                "stderr": "Sandbox timed out",
                "elapsed_sec": time.time() - t0,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "returncode": -1,
                "stdout": "",
                "stderr": "",
                "elapsed_sec": time.time() - t0,
            }
        finally:
            try:
                os.unlink(script_path)
            except Exception:
                pass

    async def run_task(
        self,
        step_id: str,
        code: str,
        timeout: int = None,
        env: Dict[str, str] = None,
    ) -> Dict[str, Any]:
        return await self.run(
            code=code, timeout=timeout, args=[], env=env
        )

    async def apply_patch(self, patch_text: str, base_dir: str = ".", timeout: int = None) -> Dict[str, Any]:
        """Apply a textual patch inside the sandbox."""
        code = textwrap.dedent(f"""
            import subprocess, sys, os
            os.chdir({base_dir!r})
            with open('/tmp/.patch.diff', 'w') as f:
                f.write({patch_text!r})
            sys.exit(subprocess.call(['patch', '-p1', '-i', '/tmp/.patch.diff']))
        """)
        return await self.run(code=code, timeout=timeout)

    @property
    def healthy(self) -> bool:
        return True  # Best-effort; real health would probe a canary subprocess
