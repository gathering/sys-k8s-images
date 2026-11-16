#!/usr/bin/env python3
"""Image versions, for the Makefile and CI (README, Versions).

  images.py list                    every image
  images.py changed BASE            images changed since BASE, as a JSON list
  images.py bump [IMAGE...]         raise version where CI should
  images.py check                   fail on a version Kargo or CI cannot use
  images.py ref IMAGE               the full image reference to push
  images.py published IMAGE         exit 0 when that tag is pushed from
                                    this content, 1 when it is not pushed,
                                    2 when the registry does not say, 3
                                    when it is pushed from other content

An image needs a new version when its directory changed after the commit
that last changed its version file. That needs only git history, so a run
that failed, was cancelled or was re-run cannot lose or lower a version.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = "ghcr.io/gathering/sys-k8s-images"
# A change here builds and tests every image on a branch.
SHARED_PATHS = [".github/workflows", "scripts", "Makefile", "requirements.txt", ".python-version"]
# last_set() for a version file that is not committed yet.
WORKTREE = "working tree"

# Strict SemVer, as Kargo's Warehouse reads it (strictSemvers: true).
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?$"
)
GATHERING = re.compile(r"^(?P<upstream>.+)-gathering\.(?P<n>[1-9]\d*)$")


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def images() -> list[str]:
    return sorted(p.parent.name for p in (ROOT / "images").glob("*/Dockerfile"))


def settings(name: str) -> dict:
    path = ROOT / "images" / name / "image.yaml"
    data = yaml.safe_load(path.read_text()) if path.exists() else None
    return {"version_scheme": "gathering", **(data or {})}


def at(ref: str, path: str) -> str | None:
    result = git("show", f"{ref}:{path}")
    return result.stdout.strip() if result.returncode == 0 else None


def version(name: str) -> str | None:
    path = ROOT / "images" / name / "version"
    return path.read_text().strip() if path.exists() else None


def upstream(name: str) -> str | None:
    """The tag of the last FROM, without its digest."""
    froms = re.findall(
        r"^FROM\s+(?:--\S+\s+)*(\S+)", (ROOT / "images" / name / "Dockerfile").read_text(), re.M
    )
    if not froms:
        return None
    ref = froms[-1].split("@")[0]
    repo, _, tag = ref.rpartition(":")
    return tag if repo and "/" not in tag else None


def changed_files(base: str, *paths: str) -> list[str]:
    """Files changed since base, uncommitted and untracked ones included."""
    result = git("diff", "--name-only", base, "--", *paths)
    if result.returncode != 0:
        sys.exit(f"git diff against {base} failed: {result.stderr.strip()}")
    untracked = git("ls-files", "--others", "--exclude-standard", "--", *paths)
    return result.stdout.split() + untracked.stdout.split()


def last_set(name: str) -> str | None:
    """The commit that last changed the version file."""
    path = f"images/{name}/version"
    if git("ls-files", "--error-unmatch", path).returncode != 0:
        return WORKTREE if version(name) else None
    if git("diff", "--quiet", "HEAD", "--", path).returncode != 0:
        return WORKTREE
    return git("log", "-1", "--format=%H", "HEAD", "--", path).stdout.strip() or None


def changed_since_set(name: str) -> bool:
    rev = last_set(name)
    if rev in (None, WORKTREE):
        return False
    return bool(changed_files(rev, f"images/{name}", f":!images/{name}/version"))


def history(name: str) -> list[str]:
    """Every version the file has had, on every side of a merge, and now."""
    path = f"images/{name}/version"
    revs = git("log", "--full-history", "--format=%H", "HEAD", "--", path).stdout.split()
    values = [at(rev, path) for rev in revs] + [version(name)]
    return [v for v in values if v and SEMVER.match(v)]


def highest(name: str) -> str | None:
    return max(history(name), key=sort_key, default=None)


def sort_key(v: str) -> tuple:
    """SemVer order, with a numeric last part compared as a number."""
    m = SEMVER.match(v)
    if not m:
        return ()
    pre = m.group(4)
    parts = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split(".")) if pre else ()
    # A release sorts after its prereleases.
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), 0 if pre else 1, parts)


def expected(name: str) -> str | None:
    """The version CI sets, or None when CI leaves it alone."""
    up = upstream(name)
    if settings(name)["version_scheme"] != "gathering" or up is None:
        return None
    if version(name) is not None and not changed_since_set(name):
        return None
    # One more than any build of this upstream version so far, also one
    # from the other side of a merge.
    ns = [int(m["n"]) for m in map(GATHERING.match, history(name)) if m and m["upstream"] == up]
    new = f"{up}-gathering.{max(ns, default=0) + 1}"
    top = highest(name)
    if top and sort_key(new) <= sort_key(top):
        return None  # an older FROM tag, which check reports
    return new


def cmd_list() -> None:
    print("\n".join(images()))


def cmd_changed(base: str) -> None:
    if git("cat-file", "-e", f"{base}^{{commit}}").returncode != 0 or changed_files(base, *SHARED_PATHS):
        print(json.dumps(images()))
    else:
        print(json.dumps([n for n in images() if changed_files(base, f"images/{n}")]))


def cmd_bump(names: list[str]) -> None:
    for name in names or images():
        new = expected(name)
        if new and new != version(name):
            (ROOT / "images" / name / "version").write_text(new + "\n")
            print(f"{name}: {version(name)}")


def cmd_check() -> None:
    errors = []
    for name in images():
        v, scheme = version(name), settings(name)["version_scheme"]
        where = f"images/{name}/version"
        changed = changed_since_set(name)
        top = highest(name)
        if scheme not in ("gathering", "free"):
            errors.append(f"images/{name}/image.yaml: version_scheme is {scheme!r}. Set gathering or free")
            continue
        if not v:
            errors.append(f"{where} is missing. Run make bump")
            continue
        if not SEMVER.match(v):
            fix = "Pin the last FROM to an x.y.z tag, or set version_scheme: free" if scheme == "gathering" else "Set one such as 1.4.2"
            errors.append(f"{where}: {v} is not SemVer, which Kargo needs. {fix}")
            continue
        if scheme == "gathering":
            up = upstream(name)
            if up is None:
                errors.append(f"images/{name}/Dockerfile: the last FROM has no tag. Pin it as <tag>@sha256:<digest>, or set version_scheme: free")
                continue
            if top and sort_key(f"{up}-gathering.999999") <= sort_key(top):
                errors.append(f"images/{name}/Dockerfile: FROM tag {up} is older than {top}, and Kargo only promotes a higher tag. Keep the newer FROM, and promote an older tag in the Kargo UI")
                continue
            m = GATHERING.match(v)
            if not m or m["upstream"] != up:
                fix = "Run make bump" if changed else "Fix it"
                errors.append(f"{where}: {v} is not {up}-gathering.<n>, from the last FROM. {fix}")
                continue
        if changed:
            fix = "Run make bump" if scheme == "gathering" else "Raise it"
            errors.append(f"{where}: the image changed after {v} was set. {fix}")
        elif top and sort_key(v) < sort_key(top):
            errors.append(f"{where}: {v} is lower than {top}, the highest so far, and Kargo only promotes a higher tag. Raise it")
    if errors:
        sys.exit("\n".join(errors))


def cmd_ref(name: str) -> None:
    print(f"{REGISTRY}/{name}:{version(name)}")


def cmd_published(name: str) -> None:
    ref = f"{REGISTRY}/{name}:{version(name)}"
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", ref, "--format", "{{json .Image}}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        if result.stderr.strip() == f"ERROR: {ref}: not found":
            sys.exit(1)
        # Not 1: any other answer must never lead to a push.
        print(f"cannot tell whether {ref} exists: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    # One image's config, or a config per platform.
    image = json.loads(result.stdout)
    if "config" not in image:
        image = image.get("linux/amd64") or next(iter(image.values()))
    rev = ((image.get("config") or {}).get("Labels") or {}).get("org.opencontainers.image.revision", "")
    paths = (f"images/{name}", f":!images/{name}/version")
    if rev and git("cat-file", "-e", f"{rev}^{{commit}}").returncode == 0 \
            and git("diff", "--quiet", rev, "HEAD", "--", *paths).returncode == 0:
        sys.exit(0)
    print(f"{ref} is pushed from {rev or 'an unknown commit'}, which differs from this commit in images/{name}", file=sys.stderr)
    sys.exit(3)


def main() -> None:
    cmd, *args = sys.argv[1:] or ["help"]
    unknown = [a for a in args if cmd in ("bump", "ref", "published") and a not in images()]
    if unknown:
        sys.exit(f"No image named {', '.join(unknown)}. Images: {', '.join(images())}")
    commands = {
        "list": (cmd_list, 0),
        "changed": (cmd_changed, 1),
        "check": (cmd_check, 0),
        "ref": (cmd_ref, 1),
        "published": (cmd_published, 1),
    }
    if cmd == "bump":
        cmd_bump(args)
    elif cmd in commands and len(args) == commands[cmd][1]:
        commands[cmd][0](*args)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
