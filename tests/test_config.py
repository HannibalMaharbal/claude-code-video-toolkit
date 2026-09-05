import sys
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from config import get_default_voice_provider  # noqa: E402


class RegistryConfigTests(unittest.TestCase):
    def test_default_voice_provider_comes_from_registry(self):
        self.assertEqual(get_default_voice_provider(), "kokoro")


if __name__ == "__main__":
    unittest.main()
