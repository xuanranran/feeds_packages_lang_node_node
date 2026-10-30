#!/usr/bin/env python3
"""Read and record successfully published ImmortalWrt Node 22 versions."""
import argparse,json,re
from pathlib import Path
import sync as mirror
VERSION_FILE=Path(__file__).resolve().parents[1]/"versions/immortalwrt-node22.txt"

def validate(versions):
    if set(versions)!=set(mirror.ARCHES):raise ValueError("Version record must contain all 15 supported architectures")
    if any(not re.fullmatch(r"22\.\d+\.\d+-r\d+",v) for v in versions.values()):
        raise ValueError("Expected full Node 22 package versions including revision")
    return versions

def read(path=VERSION_FILE):
    if not path.exists():return {}
    versions={}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):continue
        fields=line.split()
        if len(fields)!=2 or fields[0] in versions:raise ValueError("Malformed or duplicate version record")
        versions[fields[0]]=fields[1]
    return validate(versions)

def record(manifest,path=VERSION_FILE):
    if manifest["provider"]!="immortalwrt" or manifest["abi"]!=127 or manifest["tag"]!="immortalwrt-node22":
        raise ValueError("Expected published ImmortalWrt Node 22 manifest")
    versions=validate({a:p["version"]+"-r"+p["release"] for a,p in manifest["architectures"].items()})
    text="# Successfully published ImmortalWrt Node 22 package versions\n# architecture version\n"
    text+="".join(f"{arch} {versions[arch]}\n" for arch in mirror.ARCHES)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(".tmp");temporary.write_text(text,encoding="utf-8",newline="\n");temporary.replace(path)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--manifest",type=Path,required=True);args=parser.parse_args()
    record(json.loads(args.manifest.read_text(encoding="utf-8")))
