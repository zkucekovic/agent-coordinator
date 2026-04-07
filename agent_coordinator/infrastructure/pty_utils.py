"""PTY-based subprocess runner for interactive agent backends.

All agent CLIs (copilot, claude, opencode …) need to believe they are
running in a real terminal so they can:
  - show permission-request dialogs
  - perform isatty() checks and enable colour / interactive features
  - receive user responses to those dialogs

When stdout is a pipe (the default with subprocess.PIPE), the child
detects "not a TTY" and silently falls back to "Permission denied –
could not request permission from user".

run_with_pty() solves this by:
  1. Creating a PTY pair (master_fd / slave_fd).
  2. Giving slave_fd as the subprocess's stdin + stdout (it sees a TTY).
  3. Using a separate OS-level pipe for stderr (so session IDs / error
     text are captured cleanly without PTY noise).
  4. Reading from master_fd in a thread → strip ANSI → on_output() for
     streaming, or collect for final return.
  5. Forwarding real terminal input → master_fd in another thread so the
     user can type 'y / n' responses to permission dialogs.

Falls back to subprocess.run(capture_output=True) on platforms without
the `pty` module (e.g. Windows).
"""

from __future__ import annotations

import os
import re
import select
import sys
import threading
from pathlib import Path
from typing import Callable

# ── ANSI stripping ────────────────────────────────────────────────────────────

_ANSI_RE = re.compile(
    r"\033(?:"
    r"\[[0-?]*[ -/]*[@-~]"            # CSI sequences (colours, cursor)
    r"|\][^\x07]*(?:\x07|\033\\)"      # OSC sequences (must precede two-char)
    r"|\([A-Z]"                        # character set designation
    r"|[@-Z\\-_]"                      # two-char ESC sequences
    r")"
)

def _strip(text: str) -> str:
    return _ANSI_RE.sub("", text)


# ── Platform guard ────────────────────────────────────────────────────────────

try:
    import pty as _pty
    import fcntl
    import termios
    _HAS_PTY = True
except ImportError:
    _HAS_PTY = False


# ── Public API ────────────────────────────────────────────────────────────────

class PtyResult:
    __slots__ = ("returncode", "stdout", "stderr")

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout     = stdout
        self.stderr     = stderr


def run_with_pty(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    on_output: Callable[[str], None] | None = None,
) -> PtyResult:
    """
    Run *cmd* in a PTY and return (returncode, stdout, stderr).

    stdout/stderr of the child are captured; stdout is streamed via
    on_output if provided.  stdin is forwarded from the real terminal so
    the user can respond to permission dialogs.

    Falls back to a plain pipe-based run when PTY is unavailable.
    """
    if _HAS_PTY and sys.stdin.isatty():
        return _run_pty(cmd, cwd, env, on_output)
    return _run_pipe(cmd, cwd, env, on_output)


# ── PTY implementation ────────────────────────────────────────────────────────

_MAX_CHUNKS_BYTES = 10_000_000  # 10 MB safety cap for captured output


def _run_pty(
    cmd: list[str],
    cwd: Path | None,
    env: dict | None,
    on_output: Callable[[str], None] | None,
) -> PtyResult:
    import subprocess

    master_fd, slave_fd = _pty.openpty()

    # Match the real terminal window size so TUI-style agents render correctly
    try:
        ws = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\x00" * 8)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, ws)
    except Exception:
        pass

    # Separate pipe for stderr (no PTY noise, needed for session-ID extraction)
    stderr_r, stderr_w = os.pipe()

    # Track FDs that still need closing on error
    open_fds = {master_fd, slave_fd, stderr_r, stderr_w}

    def _close_fd(fd: int) -> None:
        if fd in open_fds:
            try:
                os.close(fd)
            except OSError:
                pass
            open_fds.discard(fd)

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=stderr_w,
            cwd=cwd,
            env=env,
            close_fds=True,
        )
    except Exception:
        # Clean up all FDs if Popen fails
        for fd in list(open_fds):
            _close_fd(fd)
        raise

    _close_fd(slave_fd)
    _close_fd(stderr_w)

    # ── Save current terminal state ───────────────────────────────────────────
    # Our TUI runs with ICANON+ECHO disabled.  We do NOT change the real
    # terminal here — the PTY slave starts with its own default settings
    # (ICANON+ECHO enabled) so the subprocess gets normal line-editing.
    # We forward raw bytes from our real stdin → PTY master; the slave's
    # ICANON assembles them into lines for the subprocess.

    chunks: list[str]   = []
    chunks_bytes: int   = 0
    done = threading.Event()

    # ── Output reader ─────────────────────────────────────────────────────────
    def _read_output() -> None:
        nonlocal chunks_bytes
        buf = b""
        while not done.is_set():
            try:
                r, _, _ = select.select([master_fd], [], [], 0.05)
            except (select.error, ValueError, OSError):
                break
            if not r:
                continue
            try:
                data = os.read(master_fd, 4096)
            except OSError:
                break
            if not data:
                break
            buf += data
            # Emit complete lines immediately; hold back incomplete lines
            while b"\n" in buf:
                line_b, buf = buf.split(b"\n", 1)
                line = _strip(line_b.decode("utf-8", errors="replace")) + "\n"
                if chunks_bytes < _MAX_CHUNKS_BYTES:
                    chunks.append(line)
                    chunks_bytes += len(line)
                if on_output:
                    on_output(line)
        # Flush any remaining partial line
        if buf:
            line = _strip(buf.decode("utf-8", errors="replace"))
            if line.strip():
                if chunks_bytes < _MAX_CHUNKS_BYTES:
                    chunks.append(line)
                    chunks_bytes += len(line)
                if on_output:
                    on_output(line)

    # ── Stdin forwarder ───────────────────────────────────────────────────────
    def _forward_stdin() -> None:
        """
        Forward real terminal keystrokes → PTY master so the subprocess
        can receive user input for permission prompts.

        Ctrl+C (0x03) is NOT forwarded — Python's SIGINT handler deals
        with it; forwarding it would double-kill the subprocess.
        """
        while not done.is_set():
            try:
                r, _, _ = select.select([sys.stdin], [], [], 0.1)
            except (select.error, ValueError, OSError):
                break
            if not r:
                continue
            try:
                data = os.read(sys.stdin.fileno(), 256)
            except OSError:
                break
            if not data:
                break
            # Drop Ctrl+C byte — handled via SIGINT
            data = data.replace(b"\x03", b"")
            if data:
                try:
                    os.write(master_fd, data)
                except OSError:
                    break

    out_thread = threading.Thread(target=_read_output,   daemon=True, name="pty-out")
    in_thread  = threading.Thread(target=_forward_stdin, daemon=True, name="pty-in")
    out_thread.start()
    in_thread.start()

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        raise

    done.set()
    out_thread.join(timeout=2)
    in_thread.join(timeout=0.5)

    # Drain stderr
    stderr_data = b""
    try:
        os.set_blocking(stderr_r, False)
        while True:
            try:
                chunk = os.read(stderr_r, 4096)
                if not chunk:
                    break
                stderr_data += chunk
            except BlockingIOError:
                break
    except Exception:
        pass

    _close_fd(master_fd)
    _close_fd(stderr_r)

    return PtyResult(
        returncode=proc.returncode,
        stdout="".join(chunks).strip(),
        stderr=stderr_data.decode("utf-8", errors="replace").strip(),
    )


# ── Pipe fallback (Windows / non-TTY) ────────────────────────────────────────

def _run_pipe(
    cmd: list[str],
    cwd: Path | None,
    env: dict | None,
    on_output: Callable[[str], None] | None,
) -> PtyResult:
    import subprocess

    if on_output:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=env,
        )
        assert proc.stdout
        lines: list[str] = []
        try:
            for line in proc.stdout:
                lines.append(line)
                on_output(line)
        finally:
            proc.stdout.close()
        assert proc.stderr
        try:
            stderr_text = proc.stderr.read()
        finally:
            proc.stderr.close()
        proc.wait()
        return PtyResult(proc.returncode, "".join(lines).strip(), stderr_text.strip())

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )
    if on_output and result.stdout:
        for line in result.stdout.splitlines(keepends=True):
            on_output(line)
    return PtyResult(result.returncode, result.stdout.strip(), result.stderr.strip())
