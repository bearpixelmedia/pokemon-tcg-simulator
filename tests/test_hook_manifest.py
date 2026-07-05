import unittest

from core.hook_manifest import hook_signature, is_registered_hook


class HookManifestTests(unittest.TestCase):
    def test_hook_signature_is_stable(self) -> None:
        first = hook_signature("generic-hook", "Some clause.")
        second = hook_signature("generic-hook", "Some clause.")
        self.assertEqual(first, second)

    def test_is_registered_hook_matches_manifest_entries(self) -> None:
        hook_id = "sample-hook"
        clause = "Do something."
        signature = hook_signature(hook_id, clause)
        manifest = {"entries": [{"signature": signature, "hook_id": hook_id, "clause": clause}]}
        self.assertTrue(is_registered_hook(hook_id, clause, manifest))
        self.assertFalse(is_registered_hook("other-hook", clause, manifest))


if __name__ == "__main__":
    unittest.main()
