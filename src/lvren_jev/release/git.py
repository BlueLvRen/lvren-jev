from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import CommitEvidence, ReleaseEvidence, make_diff_digest


class GitError(RuntimeError):
    pass


@dataclass(frozen=True, order=True)
class VersionTag:
    major: int
    minor: int
    patch: int
    name: str
    commit: str


_VERSION_TAG = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class GitRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()

    def run(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise GitError(f"git {' '.join(args)} failed: {detail}")
        return completed.stdout

    def resolve_commit(self, revision: str = "HEAD") -> str:
        return self.run("rev-parse", "--verify", f"{revision}^{{commit}}").strip()

    def status_porcelain(self) -> str:
        return self.run("status", "--porcelain=v1", "--untracked-files=all")

    def version_tags(self, target_commit: str) -> list[VersionTag]:
        names = self.run("tag", "--merged", target_commit).splitlines()
        return self._parse_version_tags(names)

    def all_version_tags(self) -> list[VersionTag]:
        return self._parse_version_tags(self.run("tag").splitlines())

    def _parse_version_tags(self, names: list[str]) -> list[VersionTag]:
        result: list[VersionTag] = []
        for name in names:
            match = _VERSION_TAG.fullmatch(name.strip())
            if match is None:
                continue
            commit = self.resolve_commit(name.strip())
            result.append(
                VersionTag(
                    major=int(match.group(1)),
                    minor=int(match.group(2)),
                    patch=int(match.group(3)),
                    name=name.strip(),
                    commit=commit,
                )
            )
        return sorted(result, reverse=True)

    def commits_between(self, baseline: str, target: str) -> list[str]:
        return [
            item.strip()
            for item in self.run("rev-list", "--reverse", f"{baseline}..{target}").splitlines()
            if item.strip()
        ]

    def commit_subject(self, commit: str) -> str:
        return self.run("show", "-s", "--format=%s", commit).strip()

    def commit_body(self, commit: str) -> str:
        return self.run("show", "-s", "--format=%B", commit).strip()

    def cumulative_diff(self, baseline: str, target: str) -> str:
        return self.run("diff", "--no-ext-diff", "--binary", baseline, target)

    def commit_diff(self, commit: str) -> str:
        return self.run("diff", "--no-ext-diff", "--binary", f"{commit}^", commit)

    def remote_url(self) -> str | None:
        value = self.run("remote", "get-url", "origin").strip()
        return value or None


def collect_release_evidence(
    repository: GitRepository,
    *,
    target: str = "HEAD",
    max_diff_bytes: int = 2_000_000,
) -> ReleaseEvidence:
    """Lock a target commit and collect complete, non-truncated release evidence."""

    target_commit = repository.resolve_commit(target)
    if repository.status_porcelain().strip():
        return ReleaseEvidence.rejected(
            "DIRTY_WORKTREE",
            "工作区不干净，发布前不得把未提交内容混入判断或版本提交",
            target_commit=target_commit,
        )

    tags = repository.version_tags(target_commit)
    if not tags:
        return ReleaseEvidence.rejected(
            "NO_RELEASE_TAG",
            "目标提交可达范围内没有可识别的 SemVer 发布 tag",
            target_commit=target_commit,
        )
    baseline = tags[0]
    if baseline.commit == target_commit:
        return ReleaseEvidence.rejected(
            "NO_CHANGES",
            "目标提交就是上一次发布提交，没有待发布变更",
            target_commit=target_commit,
        )

    diff = repository.cumulative_diff(baseline.commit, target_commit)
    diff_bytes = len(diff.encode("utf-8"))
    if diff_bytes == 0:
        return ReleaseEvidence.rejected(
            "NO_CHANGES",
            "发布基线到目标提交之间没有实际 diff",
            target_commit=target_commit,
        )
    if diff_bytes > max_diff_bytes:
        return ReleaseEvidence.rejected(
            "EVIDENCE_TOO_LARGE",
            f"实际 diff 为 {diff_bytes} 字节，超过安全上限 {max_diff_bytes}；未截断后继续判断",
            target_commit=target_commit,
        )

    commits = tuple(
        CommitEvidence(
            sha=commit,
            subject=repository.commit_subject(commit),
            body=repository.commit_body(commit),
            diff=repository.commit_diff(commit),
        )
        for commit in repository.commits_between(baseline.commit, target_commit)
    )
    return ReleaseEvidence(
        ready=True,
        target_commit=target_commit,
        baseline_tag=baseline.name,
        baseline_commit=baseline.commit,
        commits=commits,
        diff=diff,
        diff_sha256=make_diff_digest(diff),
    )
