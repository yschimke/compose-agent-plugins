#!/usr/bin/env python3
"""Vendor the plugins' generic skills from yschimke/skills at one commit.

    python3 scripts/update-skills.py main
    python3 scripts/update-skills.py 156983dce2608d2d766628e838c6d6c0e8135ce9
    python3 scripts/update-skills.py --from-local ../skills HEAD    # offline, from a clone

The skills to vendor are every skill a plugin (or the OpenCode bundle) in src/plugins.json names
that has no directory under src/skills/. Each one's whole directory (SKILL.md, references/,
scripts/, executable bits kept) is copied from `skills/<name>/` at the resolved commit into
src/vendor/skills/<name>/, which is replaced wholesale. src/vendor/skills/provenance.json records
the repository, the ref asked for, the full commit it resolved to, the skills, and every file's
sha256 and mode; scripts/check_generated.py rejects vendored files that disagree with it. The
plugins are then regenerated.

Vendored skills are never edited here: change them in yschimke/skills and vendor again.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "plugins.json"
LOCAL_SKILLS = ROOT / "src" / "skills"
VENDOR = ROOT / "src" / "vendor" / "skills"
PROVENANCE = VENDOR / "provenance.json"
REPOSITORY = "https://github.com/yschimke/skills"
ARCHIVE = "https://codeload.github.com/yschimke/skills/tar.gz/{ref}"
COMMIT_API = "https://api.github.com/repos/yschimke/skills/commits/{ref}"
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
SHA = re.compile(r"^[0-9a-f]{40}$")
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def fetch(url: str, accept: str | None = None) -> bytes:
    headers = {"User-Agent": "compose-agent-plugins"}
    if accept:
        headers["Accept"] = accept
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as response:
        return response.read()


def wanted_skills() -> list[str]:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    names = {skill for plugin in source["plugins"] for skill in plugin.get("skills", [])}
    names.update(source.get("opencode", {}).get("skills", []))
    return sorted(name for name in names if not (LOCAL_SKILLS / name).is_dir())


def remote_archive(ref: str) -> tuple[tarfile.TarFile, str, int]:
    """The repository at `ref` from codeload, the commit it resolved to, and its path prefix depth."""
    archive = tarfile.open(fileobj=io.BytesIO(fetch(ARCHIVE.format(ref=ref))), mode="r:gz")
    # git archive writes the commit into the pax global header.
    commit = archive.pax_headers.get("comment", "")
    if not SHA.fullmatch(commit):
        commit = fetch(COMMIT_API.format(ref=ref), "application/vnd.github.sha").decode().strip()
    return archive, commit, 1


def local_archive(path: Path, ref: str, skills: list[str]) -> tuple[tarfile.TarFile, str, int]:
    def git(*args: str) -> bytes:
        result = subprocess.run(["git", "-C", str(path), *args], capture_output=True)
        if result.returncode:
            sys.exit(f"git {args[0]} in {path} failed for {', '.join(skills)}: "
                     f"{result.stderr.decode(errors='replace').strip()}")
        return result.stdout

    commit = git("rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    data = git("archive", "--format=tar", commit, "--", *(f"skills/{skill}" for skill in skills))
    return tarfile.open(fileobj=io.BytesIO(data), mode="r:"), commit, 0


def extract(archive: tarfile.TarFile, depth: int, skills: list[str], target: Path) -> None:
    for member in archive.getmembers():
        parts = member.name.split("/")[depth:]
        if len(parts) < 3 or parts[0] != "skills" or parts[1] not in skills:
            continue
        if member.isdir():
            continue
        relative = Path(*parts[1:])
        if not member.isfile() or ".." in relative.parts or relative.is_absolute():
            sys.exit(f"refusing to vendor {member.name}: only plain files inside the skill")
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(archive.extractfile(member).read())
        output.chmod(0o755 if member.mode & 0o111 else 0o644)
    missing = [skill for skill in skills if not (target / skill / "SKILL.md").is_file()]
    if missing:
        sys.exit(f"yschimke/skills has no skills/<name>/SKILL.md for: {', '.join(missing)}")


def provenance(ref: str, commit: str, skills: list[str], root: Path) -> dict[str, object]:
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[path.relative_to(root).as_posix()] = {
                "mode": "100755" if path.stat().st_mode & 0o111 else "100644",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
    return {
        "$comment": "Written by scripts/update-skills.py. Do not edit the vendored skills; "
        "scripts/check_generated.py checks them against this file.",
        "commit": commit,
        "files": files,
        "ref": ref,
        "repository": REPOSITORY,
        "skills": skills,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("ref", help="branch, tag or commit of yschimke/skills")
    parser.add_argument("--from-local", type=Path, metavar="PATH",
                        help="read the commit from a local git clone of yschimke/skills instead")
    parser.add_argument("--no-generate", action="store_true", help="skip scripts/generate.py")
    args = parser.parse_args()
    if not REF.fullmatch(args.ref) or ".." in args.ref:
        sys.exit(f"invalid ref: {args.ref}")
    skills = wanted_skills()
    if not skills or not all(NAME.fullmatch(skill) for skill in skills):
        sys.exit(f"no valid skills to vendor: {skills}")
    if args.from_local:
        archive, commit, depth = local_archive(args.from_local, args.ref, skills)
    else:
        archive, commit, depth = remote_archive(args.ref)
    if not SHA.fullmatch(commit):
        sys.exit(f"could not resolve {args.ref} to a commit")
    previous = json.loads(PROVENANCE.read_text(encoding="utf-8")) if PROVENANCE.is_file() else {}
    with tempfile.TemporaryDirectory() as directory:
        staging = Path(directory) / "skills"
        staging.mkdir()
        with archive:
            extract(archive, depth, skills, staging)
        record = provenance(args.ref, commit, skills, staging)
        if VENDOR.exists():
            shutil.rmtree(VENDOR)
        shutil.copytree(staging, VENDOR)
    PROVENANCE.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not args.no_generate:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "generate.py")], check=True)
    before = str(previous.get("commit", "none"))[:12]
    print(f"yschimke/skills {before} -> {commit[:12]} ({args.ref}): {', '.join(skills)}")


if __name__ == "__main__":
    main()
