import hashlib,importlib.util,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location("publish",Path(__file__).parents[1]/"scripts/publish.py")
publish=importlib.util.module_from_spec(spec);spec.loader.exec_module(publish)
class PublishTests(unittest.TestCase):
    def test_existing_drafts_without_git_tags(self):
        releases=[{"tag_name":tag,"assets":[]} for tag in ("immortalwrt-node22","nxhack-node24")]
        calls=[]
        def gh(*args):
            calls.append(args)
            if args==("api",f"repos/{publish.REPO}/releases"):return json.dumps(releases)
            if len(args)==2 and "/git/ref/tags/" in args[1]:raise subprocess.CalledProcessError(1,args)
            return "{}"
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for provider,tag in [("immortalwrt","immortalwrt-node22"),("nxhack","nxhack-node24")]:
                directory=root/f"mirror-{provider}";directory.mkdir()
                (directory/"node.tar.gz").write_bytes(b"original payload")
                (directory/"manifest.json").write_text(json.dumps({"provider":provider,"tag":tag,"architectures":{str(i):{} for i in range(15)}}))
                (directory/"SHA256SUMS").write_text("".join(hashlib.sha256(f.read_bytes()).hexdigest()+"  "+f.name+"\n" for f in [directory/"node.tar.gz",directory/"manifest.json"]))
            with patch.object(publish,"gh",side_effect=gh),patch.dict(os.environ,{"GITHUB_SHA":"a"*40}):publish.publish(root)
        creates=[c for c in calls if c[:3]==("api","--method","POST")]
        self.assertEqual(len(creates),2)
        self.assertFalse(any(c[:2]==("release","create") for c in calls))
        self.assertEqual(len([c for c in calls if c[:2]==("release","edit")]),2)
