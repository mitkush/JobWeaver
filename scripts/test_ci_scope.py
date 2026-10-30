import unittest
from ci_scope import scope


class ScopeTest(unittest.TestCase):
    def test_main_always_full(self):
        self.assertTrue(all(scope([], full=True).values()))

    def test_backend_checks_generated_types_and_image(self):
        self.assertEqual(scope(["backend/app/schemas/drafts.py"]), dict(backend=True, frontend=True, extension=False, docker=True))

    def test_extension_only(self):
        self.assertEqual(scope(["extension/src/popup.ts"]), dict(backend=False, frontend=False, extension=True, docker=False))

    def test_unknown_and_workflow_are_full(self):
        for path in [".github/workflows/ci.yml", "Dockerfile", "scripts/deploy-oracle.sh", "new-config"]:
            self.assertTrue(all(scope([path]).values()))

    def test_docs_only(self):
        self.assertFalse(any(scope(["jobweaver-docs/PRD.md"]).values()))

    def test_mixed_frontend_extension(self):
        self.assertEqual(scope(["frontend/src/pages/FeedPage.tsx", "extension/src/popup.ts"]), dict(backend=False, frontend=True, extension=True, docker=True))


if __name__ == "__main__":
    unittest.main()
