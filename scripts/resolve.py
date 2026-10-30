#!/usr/bin/env python3
"""Select the newest supported major for this architecture from fixed releases."""
import argparse,json,sys,urllib.request,urllib.error
REPO="xuanranran/feeds_packages_lang_node_node"
TAGS={24:"nxhack-node24",22:"immortalwrt-node22"}
def select(arch,major,load):
    for candidate in ([24,22] if major==24 else [22]):
        tag=TAGS[candidate]
        manifest=load(tag)
        if manifest is None:
            continue
        p=manifest["architectures"].get(arch)
        if p is not None:
            if manifest["abi"] != {22:127,24:137}[candidate] or not p["version"].startswith(str(candidate)+"."):
                raise ValueError("Manifest ABI/version mismatch")
            return p["version"],p["release"],p["sha256"],p["file"],tag
    raise ValueError(f"No supported Node package for {arch}")
def load(tag):
    try:
        with urllib.request.urlopen(f"https://github.com/{REPO}/releases/download/{tag}/manifest.json",timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code==404:return None
        raise
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--arch",required=True);p.add_argument("--major",type=int,choices=[22,24],default=24);a=p.parse_args()
    print(*select(a.arch,a.major,load))
