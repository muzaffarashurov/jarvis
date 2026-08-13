"""GitResult domain model for EP-038 Git Integration.

Pure data describing the outcome of one `git` subprocess invocation --
no subprocess call happens in this module, matching the pattern already
used by `Tool` (`src/core/tool/tool.py`, EP-031): a small,
dependency-free data type owned by Core, with the one real invocation
(`subprocess.run(["git", ...])`) living exclusively in
`GitService` (`src/services/git_service.py`).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["GitResult"]


@dataclass(frozen=True)
class GitResult:
    """The outcome of one `git` subprocess invocation.

    Attributes:
        command: The git subcommand that was run (e.g. "status"), for
            logging/debugging -- not the full argv.
        success: Whether the subprocess exited with code 0.
        stdout: Decoded standard output (`errors="replace"`, so this
            never raises on unexpected byte sequences).
        stderr: Decoded standard error, same decoding policy.
        exit_code: The raw process exit code.
    """

    command: str
    success: bool
    stdout: str
    stderr: str
    exit_code: int
