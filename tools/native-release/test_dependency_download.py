"""Exercise release dependency downloads against a real local HTTP server."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile

SCRIPT = Path(__file__).with_name("download_dependency.py")


class DependencyDownloadTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("dependency_download", SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name) / "dependency.zip"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("runtime.dll", b"verified runtime")
        self.archive = buffer.getvalue()
        self.responses = []
        self.requests = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.requests += 1
                status, body, length = owner.responses.pop(0)
                self.send_response(status)
                self.send_header("Content-Length", str(length or len(body)))
                self.end_headers()
                self.wfile.write(body)
                self.close_connection = True

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.url = f"http://127.0.0.1:{server.server_port}/dependency.zip"

    def download(self, attempts=3):
        self.module.download(
            self.url,
            self.destination,
            attempts=attempts,
            delay=0,
            timeout=2,
            validate_zip=True,
        )

    def test_504_retries_then_publishes_complete_archive(self):
        self.responses = [
            (504, b"gateway timeout", None),
            (504, b"gateway timeout", None),
            (200, self.archive, None),
        ]
        self.download()
        self.assertEqual(self.requests, 3)
        self.assertEqual(self.destination.read_bytes(), self.archive)
        self.assertEqual(list(self.destination.parent.iterdir()), [self.destination])

    def test_truncated_response_and_invalid_zip_retry(self):
        self.responses = [
            (200, self.archive[:10], 999),
            (200, b"not a ZIP", None),
            (200, self.archive, None),
        ]
        self.download()
        self.assertEqual(self.requests, 3)
        self.assertEqual(self.destination.read_bytes(), self.archive)

    def test_exhausted_retries_preserve_existing_file_and_remove_partials(self):
        self.destination.write_bytes(b"existing download")
        self.responses = [(504, b"timeout", None)] * 3
        with self.assertRaisesRegex(RuntimeError, "3 attempts"):
            self.download()
        self.assertEqual(self.destination.read_bytes(), b"existing download")
        self.assertEqual(list(self.destination.parent.iterdir()), [self.destination])

    def test_permanent_404_fails_without_retry(self):
        self.responses = [(404, b"not found", None)]
        with self.assertRaisesRegex(RuntimeError, "404"):
            self.download()
        self.assertEqual(self.requests, 1)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.destination.parent.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
