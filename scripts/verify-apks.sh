#!/bin/bash
set -euo pipefail

provider=${2:?provider required}
dist=$(realpath "${1:-dist}")

abi=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["abi"])' "$dist/manifest.json")
mapfile -t arches < <(python3 -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["architectures"]))' "$dist/manifest.json")
for arch in "${arches[@]}"; do
    version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["architectures"][sys.argv[2]]["version"])' "$dist/manifest.json" "$arch")
    release=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["architectures"][sys.argv[2]]["release"])' "$dist/manifest.json" "$arch")
    case "$arch" in
        x86_64) platform=linux/amd64 ;;
        i386_*) platform=linux/386 ;;
        aarch64_*) platform=linux/arm64 ;;
        arm_arm1176*) platform=linux/arm/v6 ;;
        arm_*) platform=linux/arm/v7 ;;
        riscv64*) platform=linux/riscv64 ;;
        *) echo "No runtime validation platform for $arch" >&2; exit 1 ;;
    esac
    # Refresh the multi-platform tag so a prior ARM/i386 image is not reused.
    docker run --pull=always --rm --platform "$platform" \
        -v "$dist:/mirror:ro" -e NODE_ARCH="$arch" -e NODE_VERSION="$version" -e NODE_ABI="$abi" -e PROVIDER="$provider" \
        alpine:edge sh -eu -c '
            apk add --no-cache libstdc++ openssl zlib nghttp2-libs c-ares libatomic
            mkdir -p /tmp/node
            if [ "$PROVIDER" = immortalwrt ]; then
                apk --keys-dir "/mirror/$NODE_ARCH/keys" verify /mirror/"$NODE_ARCH"/*.apk
                apk --keys-dir "/mirror/$NODE_ARCH/keys" extract --destination /tmp/node /mirror/"$NODE_ARCH"/*.apk
            else
                # nxhack APKs are unsigned; never claim upstream signature validation.
                apk --allow-untrusted extract --destination /tmp/node /mirror/"$NODE_ARCH"/*.apk
            fi
            node=/tmp/node/usr/bin/node
            test "$($node --version)" = "v$NODE_VERSION"
            test "$($node -p process.versions.modules)" = "$NODE_ABI"
            $node /tmp/node/usr/lib/node_modules/npm/bin/npm-cli.js --version
            echo "$NODE_ARCH: original payload, Node, npm and ABI $NODE_ABI verified"
        '
    python3 - "$dist" "$arch" "$version" "$abi" <<'PYVERIFY'
import hashlib,json,sys
from pathlib import Path
root,arch,version,abi=sys.argv[1:]
p=Path(root)/arch
hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.glob('*.apk')}
(p/'verified.json').write_text(json.dumps({'version':version,'abi':int(abi),'sha256':hashes}))
PYVERIFY
done

python3 "$(dirname "$0")/sync.py" --provider "$provider" --output "$dist" --finalize
