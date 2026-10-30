import importlib.util,unittest
from pathlib import Path
def module(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).parents[1]/"scripts"/(name+".py"));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
sync=module("sync");resolve=module("resolve")
class MirrorTests(unittest.TestCase):
    def manifest(self,version,abi,arch="x86_64"):
        return {"abi":abi,"architectures":{arch:{"version":version,"release":"1","file":"node.tar.gz","sha256":"abc"}}}
    def test_prefers_24(self):
        self.assertEqual(resolve.select("x86_64",24,lambda tag:self.manifest("24.22.1",137))[-1],"nxhack-node24")
    def test_fallback_missing_arch(self):
        def load(tag):return self.manifest("24.22.1",137,"other") if tag.startswith("nxhack") else self.manifest("22.23.3",127)
        self.assertEqual(resolve.select("x86_64",24,load)[0],"22.23.3")
    def test_explicit_22(self):
        self.assertEqual(resolve.select("x86_64",22,lambda tag:self.manifest("22.23.3",127))[-1],"immortalwrt-node22")
    def test_reject_abi(self):
        with self.assertRaises(ValueError):resolve.select("x86_64",24,lambda tag:self.manifest("24.22.1",127))
    def test_provider_configuration(self):
        for source,abi in [("immortalwrt",127),("nxhack",137)]:
            sync.configure(source);self.assertEqual(sync.ABI,abi)
        self.assertEqual(len(sync.ARCHES),15)
