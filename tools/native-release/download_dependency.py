"""Download a release dependency with bounded retries and atomic installation."""

import argparse
from http.client import IncompleteRead
from pathlib import Path
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile


def download(url, destination, *, attempts=6, delay=5, timeout=600, validate_zip=False):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(1, attempts + 1):
        partial = None
        retryable = True
        try:
            request = Request(url, headers={"User-Agent": "MAA-Native-release"})
            with urlopen(request, timeout=timeout) as response:
                expected = response.headers.get("Content-Length")
                size = 0
                with tempfile.NamedTemporaryFile(
                    dir=destination.parent,
                    prefix=destination.name + ".",
                    suffix=".part",
                    delete=False,
                ) as output:
                    partial = Path(output.name)
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                        size += len(chunk)
                if expected is not None and size != int(expected):
                    raise OSError(
                        f"Incomplete download: expected {expected} bytes, got {size}"
                    )
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--zip", action="store_true", dest="validate_zip")
    args = parser.parse_args()
    download(args.url, args.destination, validate_zip=args.validate_zip)
