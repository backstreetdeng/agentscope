"""Import side effects must not change a Skill version or invalidate resume."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from skill_runtime import SkillRegistry

class PackageHashTest(unittest.TestCase):
    def test_bytecode_does_not_change_version_but_source_does(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)/"test-skill";root.mkdir()
            (root/"SKILL.md").write_text("---\nname: test-skill\ndescription: test package\n---\nInstructions\n",encoding="utf-8")
            before=SkillRegistry._load(root).package_hash
            cache=root/"__pycache__";cache.mkdir()
            (cache/"thing.cpython.pyc").write_bytes(b"execution-side-effect")
            self.assertEqual(before,SkillRegistry._load(root).package_hash)
            (root/"script.py").write_text("print('version2')",encoding="utf-8")
            self.assertNotEqual(before,SkillRegistry._load(root).package_hash)

if __name__=="__main__": unittest.main()
