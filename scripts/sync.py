#!/usr/bin/env python3
"""Mirror ImmortalWrt Node 22 and nxhack Node 24 prebuilt APKs."""

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import tarfile
import time
import urllib.request
import zlib

ROOT = Path(__file__).resolve().parents[1]
ARCHES = (
    "aarch64_cortex-a53", "aarch64_cortex-a72", "aarch64_cortex-a76", "aarch64_generic",
    "arm_arm1176jzf-s_vfp", "arm_cortex-a15_neon-vfpv4", "arm_cortex-a5_vfpv4",
    "arm_cortex-a7_neon-vfpv4", "arm_cortex-a7_vfpv4", "arm_cortex-a8_vfpv3",
    "arm_cortex-a9_neon", "arm_cortex-a9_vfpv3-d16", "i386_pentium-mmx",
    "i386_pentium4", "x86_64",
)
PROVIDERS = {
    "immortalwrt": {"major": 22, "abi": 127, "base": "https://downloads.immortalwrt.org/snapshots/packages", "feed": "packages", "tag": "immortalwrt-node22"},
    "nxhack": {"major": 24, "abi": 137, "base": "https://downloads.nxhack.com/releases/25.12.6/packages", "feed": "node", "tag": "nxhack-node24"},
}
SOURCE = "nxhack"
BASE = PROVIDERS[SOURCE]["base"]
ABI = 137
MAJOR = 24
FEED = "node"


def configure(source, nxhack_release=None):
    global SOURCE, BASE, ABI, MAJOR, FEED
    SOURCE = source
    p = PROVIDERS[source]
    BASE, ABI, MAJOR, FEED = p["base"], p["abi"], p["major"], p["feed"]
    if source == "nxhack" and nxhack_release:
        if not re.fullmatch(r"\d+\.\d+\.\d+", nxhack_release):
            raise ValueError("Expected stable OpenWrt release (major.minor.patch)")
        BASE = f"https://downloads.nxhack.com/releases/{nxhack_release}/packages"


def fetch(url, target=None):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "node-nxhack-mirror/1"})
            with urllib.request.urlopen(request, timeout=60) as response:
                if target is None:
                    return response.read()
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix(target.suffix + ".part")
                with temporary.open("wb") as output:
                    shutil.copyfileobj(response, output)
                if not temporary.stat().st_size:
                    raise ValueError(f"Empty download: {url}")
                temporary.replace(target)
                return target
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def adb_decode(data, schema):
    """Read APK v3 package metadata; apk verify separately checks signatures/data.

    Format: https://github.com/alpinelinux/apk-tools/blob/master/src/adb.h
    Schema: https://github.com/alpinelinux/apk-tools/blob/master/src/apk_adb.h
    """
    path = "ADB input"
    if data[:4] != b"ADBd":
        raise ValueError(f"Expected a deflate-compressed APK v3: {path}")
    raw = zlib.decompress(data[4:], -15)
    if raw[:8] != schema:
        raise ValueError(f"Invalid APK package schema: {path}")
    block = struct.unpack_from("<I", raw, 8)[0]
    if block >> 30 or (block & 0x3fffffff) > len(raw) - 8:
        raise ValueError(f"Invalid APK metadata block: {path}")
    metadata = raw[12:8 + (block & 0x3fffffff)]

    def decode(value, depth=0):
        if depth > 16:
            raise ValueError("APK metadata nesting limit exceeded")
        kind, offset = value >> 28, value & 0x0fffffff
        if kind == 0:
            return None
        if kind == 1:
            return offset
        if kind in (2, 3):
            size = 4 if kind == 2 else 8
            if offset + size > len(metadata):
                raise ValueError("Invalid integer offset")
            return int.from_bytes(metadata[offset:offset + size], "little")
        if kind in (8, 9, 10):
            size = {8: 1, 9: 2, 10: 4}[kind]
            length = int.from_bytes(metadata[offset:offset + size], "little")
            if offset + size + length > len(metadata):
                raise ValueError("Invalid blob offset")
            return metadata[offset + size:offset + size + length]
        if kind in (13, 14):
            count = struct.unpack_from("<I", metadata, offset)[0]
            if not 1 <= count <= 1000000 or offset + count * 4 > len(metadata):
                raise ValueError("Invalid array offset")
            return [decode(struct.unpack_from("<I", metadata, offset + i * 4)[0], depth + 1)
                    for i in range(1, count)]
        raise ValueError(f"Unsupported ADB value type {kind}")

    return decode(struct.unpack_from("<I", metadata, 4)[0])


def package_info(info):
    text = lambda value: value.decode("utf-8") if value else ""
    return {"name": text(info[0]), "version": text(info[1]), "architecture": text(info[4]),
            "depends": [text(dep[0]) for dep in (info[14] or [])]}


def apk_info(path):
    return package_info(adb_decode(path.read_bytes(), b"ADB.pckg")[0])


def repository_info(data):
    root = adb_decode(data, b"ADB.indx")
    packages = [package_info(info) for info in root[1]]
    return {p["name"]: p for p in packages}


def archive(directory, target):
    """Stable checksums across syncs of the same original APKs and key."""
    with target.open("wb") as output, gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT) as tar:
            for path in sorted(directory.rglob("*")):
                if not path.is_file() or path.name == "verified.json":
                    continue
                info = tar.gettarinfo(str(path), path.relative_to(directory).as_posix())
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                info.mode = 0o644
                with path.open("rb") as source:
                    tar.addfile(info, source)


def sync(output, requested="", cache=None, arches=ARCHES):
    output.mkdir(parents=True, exist_ok=True)
    if not arches or len(set(arches)) != len(arches) or any(not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", arch) for arch in arches):
        raise ValueError("Invalid or duplicate architecture names")
    indexes = {arch: repository_info(fetch(f"{BASE}/{arch}/{FEED}/packages.adb")) for arch in arches}
    versions = {}
    for arch in arches:
        packages = indexes[arch]
        node, npm = packages.get(f"node{ABI}"), packages.get("node-npm")
        if not node or not re.fullmatch(rf"{MAJOR}\.\d+\.\d+-r\d+", node["version"]):
            raise ValueError(f"No matching Node / ABI package in {arch}")
        version = node["version"]
        if not npm or npm["version"] != version or node["architecture"] != arch or npm["architecture"] != arch:
            raise ValueError(f"Node/npm version or architecture mismatch in {arch}")
        if requested and requested not in (version, version.rsplit("-r", 1)[0]):
            raise ValueError(f"Requested {requested}, {arch} provides {version}")
        versions[arch] = version
    manifest = {"abi": ABI, "major": MAJOR, "provider": SOURCE, "upstream": BASE,
                "authentication": "upstream APK signatures verified" if SOURCE == "immortalwrt" else "HTTPS source; upstream APKs unsigned; repository signature not verified", "architectures": {}}

    def prepare_arch(arch):
        package_version = versions[arch]
        version, release = package_version.rsplit("-r", 1)
        directory = output / arch
        directory.mkdir(exist_ok=True)
        expected_files = {f"{name}-{package_version}.apk" for name in (f"node{ABI}", "node-npm")}
        if any(path.name not in expected_files for path in directory.glob("*.apk")):
            raise ValueError(f"Old APKs in {directory}; use an empty output directory")
        shutil.copytree(ROOT / "keys" / SOURCE, directory / "keys", dirs_exist_ok=True)
        packages = []
        for name in (f"node{ABI}", "node-npm"):
            filename = f"{name}-{package_version}.apk"
            target = directory / filename
            cached = cache / arch / filename if cache else None
            if cached and cached.is_file() and cached.stat().st_size:
                shutil.copyfile(cached, target)
            else:
                fetch(f"{BASE}/{arch}/{FEED}/{filename}", target)
            info = apk_info(target)
            if (info["name"], info["version"], info["architecture"]) != (name, package_version, arch):
                raise ValueError(f"APK metadata does not match index: {target}")
            expected = {"libatomic1", "libc", "libcares", "libnghttp2-14", "libopenssl3", "libstdcpp6", "zlib"}
            if name == f"node{ABI}" and set(info["depends"]) != expected:
                raise ValueError(f"Node dependencies changed; update the adapter before publishing: {info}")
            if name == "node-npm" and set(info["depends"]) != {"libc", f"node{ABI}"}:
                raise ValueError(f"npm dependencies changed: {info}")
            packages.append({**info, "file": filename, "sha256": sha256(target),
                             "source": f"{BASE}/{arch}/{FEED}/{filename}"})
        target = output / f"node-{SOURCE}-{package_version}-{arch}.tar.gz"
        archive(directory, target)
        return arch, {"version": version, "release": release, "file": target.name, "sha256": sha256(target), "packages": packages}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for arch, info in executor.map(prepare_arch, arches):
            manifest["architectures"][arch] = info
            print(arch, versions[arch], info["sha256"], flush=True)

    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def finalize(output):
    manifest = json.loads((output / "manifest.json").read_text())
    for arch, entry in manifest["architectures"].items():
        proof = json.loads((output / arch / "verified.json").read_text())
        hashes = {p["file"]: sha256(output / arch / p["file"]) for p in entry["packages"]}
        if proof != {"version": entry["version"], "abi": ABI, "sha256": hashes}:
            raise ValueError(f"Missing or stale runtime verification: {arch}")
        if any(hashes[p["file"]] != p["sha256"] for p in entry["packages"]):
            raise ValueError(f"APK changed after download: {arch}")
        if sha256(output / entry["file"]) != entry["sha256"]:
            raise ValueError(f"Archive changed after download: {arch}")
    identity = json.dumps(manifest["architectures"], sort_keys=True).encode()
    manifest["tag"] = PROVIDERS[SOURCE]["tag"]
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    assets = sorted(output.glob("*.tar.gz")) + [output / "manifest.json"]
    (output / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in assets), encoding="utf-8")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"tag={manifest['tag']}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=PROVIDERS, required=True)
    parser.add_argument("--nxhack-release", default="")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--version", default="")
    parser.add_argument("--cache", type=Path, help="Optional local download cache; APK signatures are still verified by the workflow")
    parser.add_argument("--architectures", default=",".join(ARCHES), help="Comma-separated official package architectures")
    parser.add_argument("--finalize", action="store_true", help="Finalize release metadata after APK/runtime verification")
    args = parser.parse_args()
    if args.provider == "nxhack" and not args.nxhack_release and not args.finalize:
        from discover import latest_nxhack
        args.nxhack_release, _ = latest_nxhack()
    configure(args.provider, args.nxhack_release)
    if args.finalize:
        finalize(args.output)
    else:
        sync(args.output, args.version, args.cache, tuple(args.architectures.split(",")))
