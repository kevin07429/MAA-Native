"""Download a release dependency with bounded retries and atomic installation."""

import argparse
from http.client import IncompleteRead
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

GITHUB_RELEASE_URL = re.compile(
    r"^https://github\.com/(?P<repository>[^/]+/[^/]+)/releases/download/"
    r"(?P<tag>[^/]+)/(?P<asset>[^/]+)$"
)


def run_with_retries(command, *, attempts=6, delay=5):
    for attempt in range(1, attempts + 1):
        result = subprocess.run(command, check=False)
        if result.returncode == 0:
            return
        if attempt == attempts:
            raise RuntimeError(
                f"Dependency command failed after {attempt} attempts: {command}"
            )
        wait = min(delay * 2 ** (attempt - 1), 60)
        print(
            f"Dependency command attempt {attempt}/{attempts} failed; retrying in {wait}s",
            flush=True,
        )
        time.sleep(wait)
    raise ValueError("attempts must be positive")


def download(url, destination, *, attempts=6, delay=5, timeout=600, validate_zip=False):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    release_asset = None
    match = GITHUB_RELEASE_URL.fullmatch(url)
    if match:
        release_asset = github_release_asset(
            match["repository"], match["tag"], match["asset"]
        )
    last_error = None
    for attempt in range(1, attempts + 1):
        partial = None
        retryable = True
        try:
            partial, size, expected = download_once(
                url, destination, release_asset, timeout
            )
            if expected is not None and size != expected:
                raise OSError(
                    f"Incomplete download: expected {expected} bytes, got {size}"
                )
            if release_asset is not None:
                verify_digest(partial, release_asset.get("digest"))
            if validate_zip:
                with zipfile.ZipFile(partial) as archive:
                    corrupt = archive.testzip()
                    if corrupt is not None:
                        raise zipfile.BadZipFile("Corrupt ZIP member: " + corrupt)
            partial.replace(destination)
            print(
                f"Downloaded {destination.name} ({size} bytes), attempt {attempt}",
                flush=True,
            )
            return
        except HTTPError as error:
            last_error = error
            retryable = error.code in (408, 429) or error.code >= 500
            error.close()
        except (
            OSError,
            RuntimeError,
            URLError,
            IncompleteRead,
            zipfile.BadZipFile,
            EOFError,
        ) as error:
            last_error = error
        finally:
            if partial is not None:
                partial.unlink(missing_ok=True)
        if not retryable or attempt == attempts:
            raise RuntimeError(
                f"Dependency download failed after {attempt} attempts: {url}: {last_error}"
            ) from last_error
        wait = min(delay * 2 ** (attempt - 1), 60)
        print(
            f"Download attempt {attempt}/{attempts} failed: {last_error}; retrying in {wait}s",
            flush=True,
        )
        time.sleep(wait)
    raise ValueError("attempts must be positive")


def github_release_asset(repository, tag, name):
    result = subprocess.run(
        ["gh", "api", f"repos/{repository}/releases/tags/{tag}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        details = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"GitHub release lookup failed: {details}")
    assets = json.loads(result.stdout)["assets"]
    asset = next((item for item in assets if item["name"] == name), None)
    if asset is None:
        raise RuntimeError(f"GitHub release asset not found: {name}")
    return asset


def download_once(url, destination, release_asset, timeout):
    descriptor, partial_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=destination.name + ".",
        suffix=".part",
    )
    os.close(descriptor)
    partial = Path(partial_name)
    try:
        with partial.open("wb") as output:
            if release_asset is not None:
                result = subprocess.run(
                    [
                        "gh",
                        "api",
                        "-H",
                        "Accept: application/octet-stream",
                        release_asset["url"],
                    ],
                    stdout=output,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if result.returncode:
                    details = result.stderr.decode("utf-8", errors="replace").strip()
                    raise RuntimeError(f"GitHub asset download failed: {details}")
                size = output.tell()
                expected = release_asset.get("size")
            else:
                request = Request(url, headers={"User-Agent": "MAA-Native-release"})
                with urlopen(request, timeout=timeout) as response:
                    content_length = response.headers.get("Content-Length")
                    expected = (
                        int(content_length) if content_length is not None else None
                    )
                    size = 0
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                        size += len(chunk)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return partial, size, expected


def verify_digest(path, digest):
    if not digest:
        raise RuntimeError("GitHub release asset has no digest")
    algorithm, expected = digest.split(":", 1)
    if algorithm != "sha256":
        raise RuntimeError(f"Unsupported release asset digest: {algorithm}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError("GitHub release asset digest mismatch")


def prefetch_maadeps(triplet, *, root=Path(".")):
    root = Path(root)
    config = runpy.run_path(str(root / "tools/maadeps-download.py"))
    release = subprocess.run(
        ["gh", "api", f"repos/{config['REPO']}/releases/tags/{config['VERSION']}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if release.returncode:
        details = release.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"MaaDeps release lookup failed: {details}")
    name = f"MaaDeps-{triplet}.tar.xz"
    assets = json.loads(release.stdout)["assets"]
    asset = next((item for item in assets if item["name"] == name), None)
    if asset is None:
        raise RuntimeError(f"MaaDeps release asset not found: {name}")
    download(
        asset["browser_download_url"],
        root / "src/MaaUtils/MaaDeps/tarball" / name,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?")
    parser.add_argument("destination", nargs="?", type=Path)
    parser.add_argument("--zip", action="store_true", dest="validate_zip")
    parser.add_argument("--run", nargs=argparse.REMAINDER)
    parser.add_argument("--prefetch-maadeps", metavar="TRIPLET")
    args = parser.parse_args()
    if args.prefetch_maadeps:
        prefetch_maadeps(args.prefetch_maadeps)
    elif args.run:
        run_with_retries(args.run)
    elif args.url and args.destination:
        download(args.url, args.destination, validate_zip=args.validate_zip)
    else:
        parser.error("provide URL and destination, or --run followed by a command")
