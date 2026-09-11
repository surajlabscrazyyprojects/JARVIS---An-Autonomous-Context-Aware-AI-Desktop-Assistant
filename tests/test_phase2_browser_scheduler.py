from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from jarvis.runtime import EventStore, TaskStore
from jarvis.scheduler import TaskScheduler
from jarvis.tools import BrowserTool


class SchedulerTests(unittest.TestCase):
    def test_priority_dependencies_and_retry_are_persistent(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = TaskStore(root / "tasks.json")
            scheduler = TaskScheduler(store, EventStore(root / "events.jsonl"))
            first = store.create("first", total_steps=1)
            second = store.create("second", total_steps=1)
            scheduler.submit(second["task_id"], priority="background", dependencies=[first["task_id"]])
            scheduler.submit(first["task_id"], priority="voice")
            self.assertEqual(first["task_id"], scheduler.acquire_next())
            scheduler.complete(first["task_id"], success=True)
            self.assertEqual(second["task_id"], scheduler.acquire_next())
            self.assertGreater(scheduler.retry(second["task_id"], "transient failure"), 0)
            self.assertEqual("QUEUED", scheduler.status()["tasks"][second["task_id"]]["state"])


class BrowserAcceptanceTests(unittest.TestCase):
    def test_local_website_navigation_and_structured_verification(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text(
                "<html><head><title>Moonlight Coffee</title><style>body{background:#111}</style></head>"
                "<body><nav>Menu</nav><main><h1>Moonlight Coffee</h1></main><script>console.log('ready')</script></body></html>",
                encoding="utf-8",
            )

            class Handler(SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory=str(root), **kwargs)
                def log_message(self, *_args):
                    pass

            httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            Thread(target=httpd.serve_forever, daemon=True).start()
            browser = BrowserTool(headless=True)
            try:
                url = f"http://127.0.0.1:{httpd.server_port}/"
                navigation = browser.navigate(url)
                self.assertTrue(navigation.verified, navigation.error)
                self.assertEqual("Moonlight Coffee", navigation.output["title"])
                verification = browser.verify_website()
                self.assertTrue(verification.verified, verification.output)
                self.assertTrue(verification.output["checks"]["responsive_viewport"])
            finally:
                browser.stop()
                httpd.shutdown()
                httpd.server_close()
