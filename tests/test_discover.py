import sys,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/"scripts"))
import discover
class DiscoveryTests(unittest.TestCase):
    def snapshot(self,base="source",version="24.22.1-r1"):
        return {"upstream":base,"versions":{"x86_64":version}}
    def manifest(self):
        return {"upstream":"source","architectures":{"x86_64":{"version":"24.22.1","release":"1"}}}
    def test_numeric_sort_and_stable_series(self):
        html=''.join(f'<a href="{v}/">x</a>' for v in ["25.12.9","25.12.10","25.12.11-rc1","26.1.0","25.12.9"])
        self.assertEqual(discover.candidates(html),["26.1.0","25.12.10","25.12.9"])
    def test_bad_release_listing_fails(self):
        with self.assertRaises(ValueError):discover.candidates('<html>error</html>')
    def test_incomplete_new_release_falls_back(self):
        def probe(v):
            if v=="25.12.7":raise discover.NotReady("one architecture missing")
            return self.snapshot()
        self.assertEqual(discover.select_latest(["25.12.7","25.12.6"],probe)[0],"25.12.6")
    def test_complete_new_release_selected(self):
        self.assertEqual(discover.select_latest(["25.12.7","25.12.6"],lambda v:self.snapshot())[0],"25.12.7")
    def test_network_errors_do_not_become_no_update(self):
        with self.assertRaises(TimeoutError):discover.select_latest(["25.12.7"],lambda v:(_ for _ in ()).throw(TimeoutError()))
    def test_no_change(self):self.assertFalse(discover.changed(self.snapshot(),self.manifest()))
    def test_node_update(self):self.assertTrue(discover.changed(self.snapshot(version="24.22.2-r1"),self.manifest()))
    def test_release_update_same_node(self):self.assertTrue(discover.changed(self.snapshot(base="new-source"),self.manifest()))
    def test_downgrade_rejected(self):
        with self.assertRaises(ValueError):discover.changed(self.snapshot(version="24.21.0-r1"),self.manifest())
    def test_first_publication(self):self.assertTrue(discover.changed(self.snapshot(),None))
    def test_explicit_release_validation(self):
        discover.mirror.configure("nxhack","25.12.7")
        self.assertIn("/25.12.7/",discover.mirror.BASE)
        with self.assertRaises(ValueError):discover.mirror.configure("nxhack","../outside")
        discover.mirror.configure("nxhack")

    def test_future_openwrt_releases(self):
        html=''.join(f'<a href="{v}/">x</a>' for v in ["27.12.0","26.12.1","25.12.6","26.12.2-rc1","24.10.8"])
        self.assertEqual(discover.candidates(html),["27.12.0","26.12.1","25.12.6"])
        discover.mirror.configure("nxhack","27.12.0")
        self.assertIn("/27.12.0/",discover.mirror.BASE)
        discover.mirror.configure("nxhack")
    def test_immortalwrt_patch_update(self):
        old={"upstream":"immortalwrt","architectures":{"x86_64":{"version":"22.23.3","release":"1"},"aarch64_generic":{"version":"22.23.3","release":"1"}}}
        snapshot={"upstream":"immortalwrt","versions":{"x86_64":"22.23.4-r1","aarch64_generic":"22.23.3-r1"}}
        self.assertTrue(discover.changed(snapshot,old))
    def test_immortalwrt_revision_update(self):
        old={"upstream":"immortalwrt","architectures":{"x86_64":{"version":"22.23.3","release":"1"}}}
        self.assertTrue(discover.changed({"upstream":"immortalwrt","versions":{"x86_64":"22.23.3-r2"}},old))
    def test_either_provider_triggers_sync(self):
        for nx_update,imm_update in [(False,True),(True,False),(True,True),(False,False)]:
            with self.subTest(nxhack=nx_update,immortalwrt=imm_update):
                with patch.object(discover,"latest_nxhack",return_value=("26.12.0",{})),patch.object(discover,"published",return_value={}),patch.object(discover,"inspect",return_value={"versions":{}}),patch.object(discover.version_record,"read",return_value={}),patch.object(discover,"changed",return_value=nx_update),patch.object(discover,"versions_changed",return_value=imm_update):
                    release,updates=discover.check()
                    self.assertEqual(release,"26.12.0")
                    self.assertEqual(any(updates.values()),nx_update or imm_update)
