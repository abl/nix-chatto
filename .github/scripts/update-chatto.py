#!/usr/bin/env python3
"""Point package.nix at the latest stable chattocorp/chatto release.

Stable means the highest release, by X.Y.Z, that is not a draft, not a
pre-release, and has a tag matching vX.Y.Z. Releases are paged from
/releases rather than /releases/latest, because upstream is a monorepo and
"latest" can be a sub-package tag such as pkg/events/v0.1.0. Other tags are
ignored. The 0.5 beta line is ignored until upstream marks a release stable.

Rewrites `version` and the x86_64-linux / aarch64-linux fetchurl hashes in
package.nix. Each hash is the sha256 SRI of that release tarball, and
it must match chatto_<version>_checksums.txt.

Prints `updated <from> <to>` or `current <version>`. When GITHUB_OUTPUT is
set, also writes updated, from, to, and release_url. Exit 0 when the pin is
already current or newer. Exit non-zero when a newer release cannot be
applied safely.
"""

import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.request

REPO = "chattocorp/chatto"
NIX_PATH = "package.nix"
ARCHES = {
    "x86_64-linux": "x86_64",
    "aarch64-linux": "arm64",
}
VERSION_RE = re.compile(r'^(\s*)version = "([^"]+)";$', re.M)
HASH_RES = {
    system: re.compile(rf'^(\s*){system} = "(sha256-[^"]+)";$', re.M)
    for system in ARCHES
}


def parse_version(value):
    """Return a comparable tuple. Reject pre-release and non-X.Y.Z tags."""
    text = value[1:] if value.startswith("v") else value
    if not re.fullmatch(r"\d+\.\d+\.\d+", text):
        raise SystemExit(f"version {value!r} is not a stable X.Y.Z release")
    return tuple(int(part) for part in text.split("."))


def fetch(url, timeout):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "abl-nix-chatto-update"}
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github+json"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:500]
        raise SystemExit(f"GET {url} failed: HTTP {exc.code} {body}") from exc


def github_json(url):
    return json.loads(fetch(url, 60).decode("utf-8"))


STABLE_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
MAX_PAGES = 5


def latest_stable_release():
    """Highest non-draft, non-prerelease release tagged vX.Y.Z."""
    best = None
    for page in range(1, MAX_PAGES + 1):
        releases = github_json(
            f"https://api.github.com/repos/{REPO}/releases?per_page=100&page={page}"
        )
        for release in releases:
            if release.get("draft") or release.get("prerelease"):
                continue
            match = STABLE_TAG_RE.match(release.get("tag_name") or "")
            if not match:
                continue
            key = tuple(int(part) for part in match.groups())
            if best is None or key > best[0]:
                best = (key, release)
        if len(releases) < 100:
            break
    if best is None:
        raise SystemExit(f"no stable vX.Y.Z release found for {REPO}")
    return best[1]


def checksum_for(text, filename):
    found = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2 or parts[-1] != filename:
            continue
        digest = parts[0]
        if digest.startswith("sha256:"):
            digest = digest.split(":", 1)[1]
        if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise SystemExit(f"bad checksum for {filename}: {parts[0]!r}")
        if found is not None:
            raise SystemExit(f"duplicate checksum for {filename}")
        found = digest.lower()
    if found is None:
        raise SystemExit(f"checksums file has no entry for {filename}")
    return found


def sri(data):
    return "sha256-" + base64.b64encode(hashlib.sha256(data).digest()).decode()


def read_pin(text):
    versions = VERSION_RE.findall(text)
    if len(versions) != 1:
        raise SystemExit(
            f"expected one version assignment in {NIX_PATH}, found {len(versions)}"
        )
    hashes = {}
    for system, pattern in HASH_RES.items():
        matches = pattern.findall(text)
        if len(matches) != 1:
            raise SystemExit(
                f"expected one {system} hash in {NIX_PATH}, found {len(matches)}"
            )
        hashes[system] = matches[0][1]
    return versions[0][1], hashes


def write_pin(text, version, hashes):
    def replace(pattern, repl, label):
        updated, count = pattern.subn(repl, text, count=1)
        if count != 1:
            raise SystemExit(f"failed to rewrite {label}")
        return updated

    text = replace(VERSION_RE, rf'\1version = "{version}";', "version")
    for system, digest in hashes.items():
        text = replace(
            HASH_RES[system], rf'\1{system} = "{digest}";', system
        )
    written, written_hashes = read_pin(text)
    if written != version or written_hashes != hashes:
        raise SystemExit("rewrite of package.nix did not stick")
    return text


def set_output(values):
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def hashes_for(release, version):
    by_name = {asset["name"]: asset for asset in release.get("assets", [])}
    checksum_name = f"chatto_{version}_checksums.txt"
    if checksum_name not in by_name:
        names = ", ".join(sorted(by_name)) or "(none)"
        raise SystemExit(f"{release['tag_name']} has no {checksum_name}; assets: {names}")
    checksums = fetch(
        by_name[checksum_name]["browser_download_url"], 60
    ).decode("utf-8")

    hashes = {}
    for system, suffix in ARCHES.items():
        filename = f"chatto_Linux_{suffix}.tar.gz"
        asset = by_name.get(filename)
        if asset is None:
            raise SystemExit(f"{release['tag_name']} has no {filename}")
        expected = checksum_for(checksums, filename)
        data = fetch(asset["browser_download_url"], 180)
        if len(data) < 2 or data[:2] != b"\x1f\x8b":
            raise SystemExit(f"{filename} is not a gzip archive ({len(data)} bytes)")
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise SystemExit(
                f"{filename} sha256 {actual} does not match checksums ({expected})"
            )
        published = (asset.get("digest") or "").removeprefix("sha256:")
        if published and published != actual:
            raise SystemExit(
                f"{filename} sha256 {actual} does not match the GitHub asset digest"
            )
        size = asset.get("size")
        if isinstance(size, int) and size != len(data):
            raise SystemExit(
                f"{filename} is {len(data)} bytes, GitHub reports {size}"
            )
        hashes[system] = sri(data)
    return hashes


def main():
    with open(NIX_PATH, encoding="utf-8") as handle:
        original = handle.read()
    pinned, _ = read_pin(original)
    pinned_tuple = parse_version(pinned)

    release = latest_stable_release()
    tag = release["tag_name"]
    version = tag[1:] if tag.startswith("v") else tag
    latest = parse_version(version)
    release_url = release["html_url"]

    if latest < pinned_tuple:
        print(f"current {pinned} (ahead of {tag})")
        set_output({
            "updated": "false",
            "from": pinned,
            "to": pinned,
            "release_url": release_url,
        })
        return
    if latest == pinned_tuple:
        print(f"current {pinned}")
        set_output({
            "updated": "false",
            "from": pinned,
            "to": pinned,
            "release_url": release_url,
        })
        return

    hashes = hashes_for(release, version)
    updated = write_pin(original, version, hashes)
    with open(NIX_PATH, "w", encoding="utf-8") as handle:
        handle.write(updated)
    print(f"updated {pinned} {version}")
    set_output({
        "updated": "true",
        "from": pinned,
        "to": version,
        "release_url": release_url,
    })


if __name__ == "__main__":
    main()
