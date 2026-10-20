"""Make sure frontend files contain only authorized changes."""

import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class FrontendAssetsTests(unittest.TestCase):
    def test_fixed_assets_equal_original_snapshot(self):
        baseline = json.loads((FIXTURES / "frontend-baseline.json").read_text(encoding="utf-8"))
        assets = ROOT / "src/amlens/components/dashboard"
        for name, digest in baseline["files"].items():
            if name not in baseline["integration_changes"]:
                content = (assets / name).read_bytes()
                for replacement in baseline.get("authorized_content_replacements", {}).get(
                    name, []
                ):
                    before, after = replacement["before"].encode(), replacement["after"].encode()
                    self.assertEqual(content.count(after), 1, name)
                    content = content.replace(after, before)
                self.assertEqual(hashlib.sha256(content).hexdigest(), digest, name)

    def test_embedded_streamlit_css_remains_original(self):
        app = (ROOT / "src/amlens/app.py").read_text(encoding="utf-8")
        css = re.search(r"<style>(.*?)</style>", app, re.S).group(1)
        self.assertEqual(
            css,
            """
[data-testid="stAppViewContainer"],[data-testid="stApp"]{background:#F7F2EB}
[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stStatusWidget"]{display:none}
.stMainBlockContainer{padding:0 24px 0!important;max-width:1600px!important}
[data-testid="stVerticalBlock"]{gap:0}footer{display:none}
""",
        )


if __name__ == "__main__":
    unittest.main()
