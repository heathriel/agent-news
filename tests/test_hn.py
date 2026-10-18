"""Offline regression tests for Hacker News JSON serialization.

Run with: python3 -m unittest discover -s tests -v
Requires bash and jq. No network calls or existing user state are used.
"""
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "monitor.sh"


class HackerNewsTests(unittest.TestCase):
    def fetch(self, stories, limit=30):
        # Load function definitions only, never the live CLI dispatcher.
        definitions, separator, _ = SCRIPT.read_text().partition("# Main\n")
        self.assertTrue(separator, "Missing CLI boundary")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = {"topstories": list(range(1, len(stories) + 1))}
            fixtures.update({str(i): story for i, story in enumerate(stories, 1)})
            cases = []
            for name, value in fixtures.items():
                fixture = root / (name + ".json")
                fixture.write_text(json.dumps(value))
                suffix = "topstories" if name == "topstories" else "item/" + name
                url = "https://hacker-news.firebaseio.com/v0/" + suffix + ".json"
                cases.append(f"{shlex.quote(url)}) cat {shlex.quote(str(fixture))} ;;")
            # A shell function shadows curl; every unexpected URL fails closed.
            mock = '\ncurl() {\ncase "${@: -1}" in\n' + "\n".join(cases)
            mock += '\n*) echo "Unexpected URL" >&2; return 99 ;;\nesac\n}\n'
            harness = root / "fetch_hn.sh"
            harness.write_text(definitions + mock + f"fetch_hn {limit}\n")
            result = subprocess.run(
                ["bash", str(harness)],
                env={"HOME": temporary, "PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"},
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def test_no_stories(self):
        self.assertEqual(self.fetch([]), [])

    def test_no_matching_stories(self):
        self.assertEqual(self.fetch([{"title": "Ordinary technology news"}, None]), [])

    def test_single_match_and_defaults(self):
        self.assertEqual(self.fetch([{"title": "AI agent news"}]), [
            {"source": "hn", "title": "AI agent news", "url": "", "score": 0}
        ])

    def test_multiple_matches_form_one_array(self):
        stories = [
            {"title": "AI agent one", "url": "https://example.invalid/1", "score": 5},
            {"title": "Agentic two", "url": "https://example.invalid/2", "score": 10},
        ]
        self.assertEqual(self.fetch(stories), [dict(source="hn", **s) for s in stories])

    def test_json_special_characters_round_trip(self):
        story = {
            "title": 'AI agent "quoted" \\ path\nnext\tline — café',
            "url": 'https://example.invalid/"quoted"/\\path',
            "score": 42,
        }
        self.assertEqual(self.fetch([story]), [dict(source="hn", **story)])

    def test_limit_and_case_insensitive_matching(self):
        stories = [{"title": "LANGCHAIN update"}, {"title": "AI agent outside limit"}]
        results = self.fetch(stories, limit=1)
        self.assertEqual([item["title"] for item in results], ["LANGCHAIN update"])


if __name__ == "__main__":
    unittest.main()
