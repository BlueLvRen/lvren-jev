from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..runtime import JevRuntime
from .git import GitRepository
from .publisher import (
    PyPIClient,
    ReleaseExecutor,
    ReleasePlanner,
    SubprocessReleaseActions,
)
from .decision import ReleaseDecisionEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lvren-jev-release",
        description="基于完整 Git 提交正文和实际 diff 的本地发布程序",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("preview", "publish"):
        sub = subparsers.add_parser(command, help="preview 只判断，publish 执行完整发布")
        sub.add_argument("--repo", type=Path, default=Path("."))
        sub.add_argument("--target", default="HEAD", help="锁定的目标 commit 或 revision")
        sub.add_argument("--runtime-config", type=Path, required=True)
        sub.add_argument("--max-diff-bytes", type=int, default=2_000_000)
        sub.add_argument("--pypi-index", default="https://pypi.org")
        sub.add_argument("--package", default="lvren-jev")
        if command == "publish":
            sub.add_argument("--token-file", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = GitRepository(args.repo)
    pypi = PyPIClient(args.package, args.pypi_index)
    with JevRuntime.from_config(args.runtime_config) as runtime:
        planner = ReleasePlanner(
            repository,
            ReleaseDecisionEngine(runtime=runtime),
            pypi=pypi,
        )
        result = planner.plan(target=args.target, max_diff_bytes=args.max_diff_bytes)
        if args.command == "publish" and result.status == "ready":
            result = ReleaseExecutor(
                SubprocessReleaseActions(
                    repository,
                    token_file=args.token_file,
                    package=args.package,
                    pypi=pypi,
                )
            ).execute(result)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    if result.status == "failed":
        return 1
    if result.status == "rejected":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
