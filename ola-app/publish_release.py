#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 build_package.py 的产物发布成 GitHub Release。

Release 约定（仓库公开，消费方按 releases/latest 取最新）：
    tag      = 国服客户端 build 号，标题「国服客户端 build <build>」
    资产     = ola-app-jsonl-cn<build>.tar.gz、同名 .sha256、manifest.json
    正式发布  不是草稿、不是预发布，否则不会出现在 releases/latest 里

该 build 的 Release 不存在 → 创建；已存在（同一 build 重新生成）→ 覆盖同名资产并更新说明，
版本号不变。消费方每次比较资产摘要，摘要变了就当作有更新。

用法:
    python3 publish_release.py --build 3736091 --assets-dir DIR \\
        [--repo MaerdDaed/eve_local_sde] [--target main] [--dry-run]

凭据来自本机已登录的 gh（机器人账号），令牌不写进本脚本，也不进仓库。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile


QUERY_TIMEOUT = 60  # 查询类调用（秒）
PUBLISH_TIMEOUT = 900  # 创建 Release、上传资产（秒）


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], check=check, text=True, capture_output=True,
                          timeout=QUERY_TIMEOUT)


def run(cmd: list[str], dry_run: bool) -> None:
    if dry_run:
        print("  [dry-run] " + " ".join(cmd))
        return
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=PUBLISH_TIMEOUT)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode != 0:
        raise SystemExit(f"gh 命令失败: {' '.join(cmd[:4])}…\n{result.stderr.strip()}")


def release_notes(build: str, manifest: dict) -> str:
    lines = [
        f"国服客户端 build {build} 的 ola-app SDE jsonl 数据包。",
        "",
        f"- 生成时间：{manifest['generatedAt']}",
        f"- 工具链：{manifest['toolchain']}",
        "",
        "`ola-app-jsonl-cn%s.tar.gz` 内含 `manifest.json` 与 `jsonl/`（13 个数据文件）；"
        "`.sha256` 是整包摘要（sha256sum -c 格式）；`manifest.json` 是包内清单的副本。" % build,
        "同一 build 重新生成时覆盖本 Release 的资产，版本号不变，以资产摘要区分。",
        "",
        "| 文件 | 行数 | sha256 |",
        "|---|---:|---|",
    ]
    for path, entry in manifest["files"].items():
        lines.append(f"| `{path}` | {entry['lines']} | `{entry['sha256']}` |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="发布 ola-app SDE 数据包的 GitHub Release")
    parser.add_argument("--build", required=True)
    parser.add_argument("--assets-dir", required=True)
    parser.add_argument("--repo", default="MaerdDaed/eve_local_sde")
    parser.add_argument("--target", default="main", help="新建 tag 指向的分支")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要执行的命令")
    args = parser.parse_args()

    stem = f"ola-app-jsonl-cn{args.build}"
    assets = [os.path.join(args.assets_dir, name)
              for name in (f"{stem}.tar.gz", f"{stem}.tar.gz.sha256", "manifest.json")]
    missing = [path for path in assets if not os.path.isfile(path)]
    if missing:
        raise SystemExit(f"缺少发布资产: {missing}（先运行 build_package.py）")
    with open(assets[2], encoding="utf-8") as fh:
        manifest = json.load(fh)
    if manifest.get("clientBuild") != args.build:
        raise SystemExit(
            f"manifest.json 的 clientBuild={manifest.get('clientBuild')!r} 与 --build={args.build} 不一致")

    repo = ["--repo", args.repo]
    existing = gh("release", "view", args.build, *repo, "--json", "tagName", "--jq", ".tagName",
                  check=False)
    if existing.returncode == 0:
        action = "overwrite"
    elif "release not found" in existing.stderr + existing.stdout:
        action = "create"
    else:
        raise SystemExit(f"查询 Release 失败:\n{(existing.stderr or existing.stdout).strip()}")

    notes = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False)
    notes.write(release_notes(args.build, manifest))
    notes.close()
    try:
        if action == "create":
            print(f"创建 Release {args.build}")
            run(["gh", "release", "create", args.build, *repo, "--target", args.target,
                 "--title", f"国服客户端 build {args.build}", "--notes-file", notes.name,
                 *assets], args.dry_run)
        else:
            print(f"Release {args.build} 已存在，覆盖资产")
            run(["gh", "release", "upload", args.build, *repo, "--clobber", *assets], args.dry_run)
            run(["gh", "release", "edit", args.build, *repo, "--notes-file", notes.name],
                args.dry_run)
    finally:
        os.unlink(notes.name)

    if args.dry_run:
        return 0
    latest = gh("api", f"repos/{args.repo}/releases/latest",
                "--jq", '.tag_name + "  " + ([.assets[] | .name + "=" + (.digest // "no-digest")] | join("  "))')
    print(f"releases/latest → {latest.stdout.strip()}")
    if not latest.stdout.startswith(args.build + " "):
        raise SystemExit("发布后 releases/latest 不是本次的 build，请人工检查")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
