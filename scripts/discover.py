#!/usr/bin/env python3
"""Find complete Node mirrors and compare them with the two published releases."""
import argparse,concurrent.futures,json,os,re,urllib.error,urllib.request
import sync as mirror
import versions as version_record
REPO="xuanranran/feeds_packages_lang_node_node"
RELEASE_LIST="https://downloads.openwrt.org/releases/"
class NotReady(ValueError):pass

def read(url,head=False):
    request=urllib.request.Request(url,method="HEAD" if head else "GET",headers={"User-Agent":"openwrt-node-update-check/1"})
    with urllib.request.urlopen(request,timeout=30) as response:
        return b"" if head else response.read()

def candidates(html):
    versions=set(re.findall(r'href=[\'"](\d+\.\d+\.\d+)/[\'"]',html))
    versions={v for v in versions if tuple(map(int,v.split("."))) >= (25,12,0)}
    if not versions:raise ValueError("No stable APK-era OpenWrt releases in official listing")
    return sorted(versions,key=lambda v:tuple(map(int,v.split("."))),reverse=True)

def inspect(provider,release=None):
    config=mirror.PROVIDERS[provider]
    base=(f"https://downloads.nxhack.com/releases/{release}/packages" if provider=="nxhack" else config["base"])
    def one(arch):
        url=f"{base}/{arch}/{config['feed']}"
        packages=mirror.repository_info(read(url+"/packages.adb"))
        node,npm=packages.get(f"node{config['abi']}"),packages.get("node-npm")
        if not node or not re.fullmatch(rf"{config['major']}\.\d+\.\d+-r\d+",node["version"]):
            raise NotReady(f"Wrong or missing Node in {arch}")
        if not npm or npm["version"]!=node["version"] or node["architecture"]!=arch or npm["architecture"]!=arch:
            raise NotReady(f"Node/npm mismatch in {arch}")
        for package in (node,npm):
            read(f"{url}/{package['name']}-{package['version']}.apk",head=True)
        return arch,node["version"]
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:versions=dict(pool.map(one,mirror.ARCHES))
    except urllib.error.HTTPError as error:
        if error.code==404:raise NotReady(f"Incomplete source {base}") from error
        raise
    return {"upstream":base,"versions":versions}

def select_latest(versions,probe):
    for version in versions:
        try:return version,probe(version)
        except NotReady:continue
    raise NotReady("No complete nxhack Node 24 release for all 15 architectures")

def latest_nxhack():
    return select_latest(candidates(read(RELEASE_LIST).decode()),lambda v:inspect("nxhack",v))

def published(provider):
    tag=mirror.PROVIDERS[provider]["tag"]
    try:return json.loads(read(f"https://github.com/{REPO}/releases/download/{tag}/manifest.json"))
    except urllib.error.HTTPError as error:
        if error.code==404:return None
        raise

def version_key(version):return tuple(map(int,re.findall(r"\d+",version)))

def versions_changed(current,old):
    if any(a in old and version_key(v)<version_key(old[a]) for a,v in current.items()):
        raise ValueError("Upstream would downgrade an architecture; refusing automatic sync")
    return current!=old

def changed(snapshot,manifest):
    if manifest is None:return True
    old={a:p["version"]+"-r"+p["release"] for a,p in manifest["architectures"].items()}
    different=versions_changed(snapshot["versions"],old)
    return snapshot["upstream"]!=manifest["upstream"] or different

def check():
    release,nxhack=latest_nxhack()
    updates={"nxhack":changed(nxhack,published("nxhack")),
             "immortalwrt":versions_changed(inspect("immortalwrt")["versions"],version_record.read())}
    return release,updates

def outputs(values):
    print(json.dumps(values),flush=True)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as output:
            for key,value in values.items():output.write(f"{key}={value}\n")

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--select-only",action="store_true");parser.add_argument("--release",default="");args=parser.parse_args()
    if args.select_only:
        if args.release:
            if not re.fullmatch(r"\d+\.\d+\.\d+",args.release):raise ValueError("Expected stable OpenWrt release (major.minor.patch)")
            inspect("nxhack",args.release);release=args.release
        else:release,_=latest_nxhack()
        outputs({"nxhack_release":release})
    else:
        release,updates=check()
        outputs({"nxhack_release":release,"changed":str(any(updates.values())).lower(),**updates})
