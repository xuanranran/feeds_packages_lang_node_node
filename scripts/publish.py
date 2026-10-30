#!/usr/bin/env python3
"""Publish two fixed releases only after both providers passed verification."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
REPO="xuanranran/feeds_packages_lang_node_node"
def gh(*args):
    return subprocess.check_output(["gh",*args],text=True,encoding="utf-8").strip()
def publish(root):
    for provider,tag in [("immortalwrt","immortalwrt-node22"),("nxhack","nxhack-node24")]:
        directory=root/f"mirror-{provider}"
        manifest=json.loads((directory/"manifest.json").read_text())
        if manifest["provider"]!=provider or manifest["tag"]!=tag or len(manifest["architectures"])!=15:
            raise ValueError("Unexpected release metadata")
        for line in (directory/"SHA256SUMS").read_text().splitlines():
            digest,name=line.split("  ")
            if Path(name).name!=name or hashlib.sha256((directory/name).read_bytes()).hexdigest()!=digest:
                raise ValueError("Asset checksum mismatch")
    for provider,tag in [("immortalwrt","immortalwrt-node22"),("nxhack","nxhack-node24")]:
        directory=root/f"mirror-{provider}"
        notes="15 architectures: metadata, SHA256, Node/npm and ABI runtime checks passed. "
        notes+=("Upstream APK signatures verified." if provider=="immortalwrt" else "nxhack APKs are unsigned; repository signature not verified. HTTPS provenance and checksums recorded.")
        releases=json.loads(gh("api",f"repos/{REPO}/releases"))
        release=next((r for r in releases if r["tag_name"]==tag),None)
        if release is None:
            release=json.loads(gh("api","--method","POST",f"repos/{REPO}/releases","-f",f"tag_name={tag}","-f",f"target_commitish={os.environ['GITHUB_SHA']}","-F","draft=true","-f",f"name={tag}","-f",f"body={notes}"))
        # Draft releases may not create a Git tag until publication.
        try:
            gh("api",f"repos/{REPO}/git/ref/tags/{tag}")
        except subprocess.CalledProcessError:
            gh("api","--method","POST",f"repos/{REPO}/git/refs","-f",f"ref=refs/tags/{tag}","-f",f"sha={os.environ['GITHUB_SHA']}")
        else:
            gh("api","--method","PATCH",f"repos/{REPO}/git/refs/tags/{tag}","-f",f"sha={os.environ['GITHUB_SHA']}","-F","force=true")
        files=sorted(directory.glob("*.tar.gz"))+[directory/"manifest.json",directory/"SHA256SUMS"]
        gh("release","upload",tag,"--repo",REPO,*map(str,files),"--clobber")
        expected={p.name for p in files}
        for asset in release["assets"]:
            if asset["name"] not in expected:
                gh("api","--method","DELETE",f"repos/{REPO}/releases/assets/{asset['id']}")
        gh("release","edit",tag,"--repo",REPO,"--draft=false","--latest="+("true" if provider=="nxhack" else "false"),"--notes",notes)
if __name__=="__main__":publish(Path(sys.argv[1]))
