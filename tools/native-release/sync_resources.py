"""Apply only official resource changes; commit them only after the build gate passes."""

import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess

STATE = ".github/native-resource-sync.json"
REPORT = "RESOURCE_UPDATES.md"
PLAN = ".git/native-resource-sync-plan.json"
RESOURCE_PATHS = ["resource/", "tools/OptimizeTemplates/optimize_templates.json"]


def git(*args, input=None):
    return subprocess.run(
        ["git", *args],
        input=input,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def resource_path(name):
    return name.startswith("resource/") or name == RESOURCE_PATHS[1]


def changed_paths(*revisions):
    return [
        p
        for p in git("diff", "--name-only", "-z", *revisions)
        .decode("utf-8")
        .split("\0")
        if p
    ]


def pending_program_commits(target):
    entries = []
    for sha in git("rev-list", "--reverse", "HEAD.." + target).decode().splitlines():
        names = (
            git(
                "diff-tree",
                "--root",
                "--no-commit-id",
                "--name-only",
                "-z",
                "-r",
                "-m",
                sha,
            )
            .decode()
            .split("\0")
        )
        if any(p and not resource_path(p) for p in names):
            entries.append(
                {
                    "sha": sha,
                    "title": git("show", "-s", "--format=%s", sha)
                    .decode("utf-8")
                    .strip(),
                }
            )
    return entries


def validate():
    paths = changed_paths("--cached")
    for name in paths:
        if not resource_path(name) and name not in (STATE, REPORT):
            raise RuntimeError("Non-resource change is staged: " + name)
        path = Path(name)
        if path.is_symlink():
            raise RuntimeError("Resource symlinks are not accepted: " + name)
        if path.is_file() and path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8-sig"))
    return paths


def prepare(upstream):
    if git("status", "--porcelain", "--untracked-files=no").strip():
        raise RuntimeError("Prepare requires a clean tracked working tree")
    target = git("rev-parse", "--verify", upstream + "^{commit}").decode().strip()
    head = git("rev-parse", "HEAD").decode().strip()
    state = (
        json.loads(Path(STATE).read_text(encoding="utf-8"))
        if Path(STATE).exists()
        else {}
    )
    base = (
        state.get("upstream_commit")
        or git("merge-base", "HEAD", target).decode().strip()
    )
    git("merge-base", "--is-ancestor", base, target)
    program = pending_program_commits(target)
    # Avoid reapplying changes already included by a later manual upstream merge.
    pending = [p for p in changed_paths("HEAD", target) if resource_path(p)]
    if not pending:
        summary = "Official resources are already synchronized. Program commits are not merged automatically.\n"
        summary += "\n".join(
            f"- Pending program commit `{c['sha'][:12]}`: {c['title']}" for c in program
        )
        return False, summary + "\n"
    patch = git("diff", "--binary", "--full-index", base, target, "--", *RESOURCE_PATHS)
    if not patch:
        raise RuntimeError(
            "Resource state differs without a new upstream patch; manual review is required"
        )
    if program:
        git("apply", "--3way", "--index", "--whitespace=nowarn", "-", input=patch)
        merge_mode = "resource_patch_with_program_commits_excluded"
    else:
        # A pure resource interval can retain upstream ancestry as a normal merge.
        git("merge", "--no-commit", "--no-ff", target)
        merge_mode = "resource_history_merge"
    if git("ls-files", "--unmerged").strip():
        raise RuntimeError("Resource merge conflict; no commit or push was performed")
    paths = validate()
    if not paths:
        return False, "No resource changes to commit.\n"
    commits = []
    for sha in git("rev-list", "--reverse", base + ".." + target).decode().splitlines():
        names = (
            git(
                "diff-tree",
                "--root",
                "--no-commit-id",
                "--name-only",
                "-z",
                "-r",
                "-m",
                sha,
            )
            .decode()
            .split("\0")
        )
        entry = {
            "sha": sha,
            "title": git("show", "-s", "--format=%s", sha).decode("utf-8").strip(),
        }
        if any(resource_path(p) for p in names):
            commits.append(entry)
    version = json.loads(Path("resource/version.json").read_text(encoding="utf-8-sig"))
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )
    result = {
        "merge_mode": merge_mode,
        "upstream_commit": target,
        "previous_upstream_commit": base,
        "updated_utc": timestamp,
        "resource_version": version,
        "resource_files": paths,
        "resource_commits": commits,
        "program_commits_not_merged": program,
    }
    Path(STATE).parent.mkdir(parents=True, exist_ok=True)
    Path(STATE).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Official resource update / 官方资源更新",
        "",
        f"Updated (UTC): {timestamp}",
        "",
        f"Upstream: MaaAssistantArknights/MaaAssistantArknights dev-v2 `{target}`",
        "",
        f"Resource version: {version.get('last_updated', 'unknown')}",
        "",
        "## Resource changes / 资源变更",
        "",
    ]
    lines.extend(f"- `{c['sha'][:12]}` {c['title']}" for c in commits)
    lines.extend(["", "## Changed files / 变更文件", ""])
    lines.extend(f"- `{p}`" for p in paths)
    lines.extend(
        [
            "",
            "## Program changes pending review / 待检查的程序变更",
            "",
            "These program commits were not merged by the resource workflow. / 以下程序提交未由资源流程合入。",
            "",
        ]
    )
    lines.extend(f"- `{c['sha'][:12]}` {c['title']}" for c in program)
    if not program:
        lines.append("None in this interval. / 本次区间没有程序变更。")
    summary = "\n".join(lines) + "\n"
    Path(REPORT).write_text(summary, encoding="utf-8")
    git("add", "--", STATE, REPORT)
    validate()
    Path(PLAN).write_text(
        json.dumps({"head": head, "target": target}), encoding="utf-8"
    )
    return True, summary


def commit():
    plan = json.loads(Path(PLAN).read_text(encoding="utf-8"))
    if git("rev-parse", "HEAD").decode().strip() != plan["head"]:
        raise RuntimeError("Branch moved after preparation; refusing to commit")
    paths = validate()
    if not any(resource_path(p) for p in paths):
        raise RuntimeError("No resource payload is staged")
    # Reject build tools changing tracked source or unstaged resource files.
    if git("diff", "--name-only").strip():
        raise RuntimeError("Unstaged tracked changes appeared during validation")
    git("commit", "-m", "chore: sync official resources through " + plan["target"][:12])
    plan["validated_commit"] = git("rev-parse", "HEAD").decode().strip()
    Path(PLAN).write_text(json.dumps(plan), encoding="utf-8")


def publish():
    plan = json.loads(Path(PLAN).read_text(encoding="utf-8"))
    if git("rev-parse", "HEAD").decode().strip() != plan["validated_commit"]:
        raise RuntimeError("Validated commit changed before publication")
    if git("status", "--porcelain", "--untracked-files=no").strip():
        raise RuntimeError("Tracked files changed after validation")
    for _ in range(3):
        result = subprocess.run(
            ["git", "push", "origin", "HEAD:native"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0:
            print(result.stderr.decode("utf-8", errors="replace"))
            return
        git("fetch", "--no-tags", "origin", "native:refs/remotes/origin/native")
        remote = git("rev-parse", "origin/native").decode().strip()
        git("merge-base", "--is-ancestor", plan["head"], remote)
        remote_paths = changed_paths(plan["head"], remote)
        if any(p != "README.md" and not p.startswith("docs/") for p in remote_paths):
            raise RuntimeError(
                "Concurrent program or resource changes require fresh validation; nothing was overwritten"
            )
        git(
            "merge",
            "--no-edit",
            "-m",
            "Merge concurrent documentation before resource sync",
            remote,
        )
        if any(
            not resource_path(p) and p not in (STATE, REPORT)
            for p in changed_paths(remote, "HEAD")
        ):
            raise RuntimeError("Unexpected changes after documentation merge")
    raise RuntimeError("Normal push failed repeatedly; no force push was attempted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "validate", "commit", "publish"])
    parser.add_argument("--upstream", default="upstream/dev-v2")
    args = parser.parse_args()
    if args.phase == "prepare":
        changed, summary = prepare(args.upstream)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
                out.write("changed=" + str(changed).lower() + "\n")
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
                out.write(summary)
        print(summary)
    elif args.phase == "validate":
        print("Validated resource files:", len(validate()))
    elif args.phase == "commit":
        commit()
    else:
        publish()


if __name__ == "__main__":
    main()
