import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/"scripts"))
import versions,discover
class VersionRecordTests(unittest.TestCase):
    def manifest(self):
        return {"provider":"immortalwrt","abi":127,"tag":"immortalwrt-node22","architectures":{a:{"version":"22.23.3","release":"1"} for a in versions.mirror.ARCHES}}
    def test_record_round_trip_and_single_arch_update(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"imm.txt"
            versions.record(self.manifest(),path);old=versions.read(path)
            self.assertEqual(len(old),15)
            self.assertFalse(discover.versions_changed(old.copy(),old))
            new=old.copy();new["x86_64"]="22.23.4-r1"
            self.assertTrue(discover.versions_changed(new,old))
            self.assertEqual(versions.read(path)["x86_64"],"22.23.3-r1")
    def test_revision_update_and_downgrade(self):
        self.assertTrue(discover.versions_changed({"x86_64":"22.23.3-r2"},{"x86_64":"22.23.3-r1"}))
        with self.assertRaises(ValueError):discover.versions_changed({"x86_64":"22.23.2-r1"},{"x86_64":"22.23.3-r1"})
    def test_missing_record_triggers_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(discover.versions_changed({"x86_64":"22.23.3-r1"},versions.read(Path(directory)/"absent")))
    def test_bad_record_fails_without_replacing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"imm.txt";versions.record(self.manifest(),path);original=path.read_bytes()
            manifest=self.manifest();manifest["architectures"]["x86_64"]["version"]="24.22.1"
            with self.assertRaises(ValueError):versions.record(manifest,path)
            self.assertEqual(path.read_bytes(),original)
            path.write_text("x86_64 22.23.3-r1\nx86_64 22.23.4-r1\n")
            with self.assertRaises(ValueError):versions.read(path)
    def test_incomplete_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"imm.txt";path.write_text("x86_64 22.23.3-r1\n")
            with self.assertRaises(ValueError):versions.read(path)
    def test_wrong_provider_rejected(self):
        manifest=self.manifest();manifest["provider"]="nxhack"
        with self.assertRaises(ValueError):versions.record(manifest)
