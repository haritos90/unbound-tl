import unittest

from gen3tl.profile import profile
from gen3tl.project import Manifest, registry_scope

from project_fixture import UNBOUND, needs_unbound

@needs_unbound
class GameProjectProfileTest(unittest.TestCase):
    def test_project_profile_uses_manifest_identity_and_unique_default(self):
        manifest = Manifest.read(UNBOUND / "project.toml")
        path = UNBOUND / "profile"
        with registry_scope(UNBOUND):
            paths = profile.profile_paths()
            self.assertIn(path, paths)
            self.assertEqual(profile.name_of(path), manifest.profile)
            self.assertEqual(profile.locate(manifest.profile), path)
            self.assertEqual(profile.Profile.by_name(manifest.profile).path, path)
            self.assertEqual(profile.Profile.by_name(None).path, path)
            self.assertEqual(sum(profile.name_of(p) == manifest.profile for p in paths), 1)
