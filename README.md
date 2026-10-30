## OpenWrt - Node.js 预编译包

使用预编译 Node.js，减少依赖 Node.js 的软件包构建时间。默认优先使用 nxhack Node 24，缺少对应架构时回退到 ImmortalWrt Node 22；支持 `NODE_MAJOR=22` 手动指定。

在 OpenWrt 源码根目录执行：

```bash
# 替换默认 Node.js 包
rm -rf customfeeds/packages/lang/node/node
mkdir -p customfeeds/packages/lang/node/node/scripts

node_mirror="https://raw.githubusercontent.com/xuanranran/feeds_packages_lang_node_node/refs/heads/main"
curl -fsSL "$node_mirror/Makefile" > customfeeds/packages/lang/node/node/Makefile
curl -fsSL "$node_mirror/scripts/resolve.py" > customfeeds/packages/lang/node/node/scripts/resolve.py
```

每天北京时间 04:23 检查更新，验证通过后更新 [ImmortalWrt Node 22](https://github.com/xuanranran/feeds_packages_lang_node_node/releases/tag/immortalwrt-node22) 和 [nxhack Node 24](https://github.com/xuanranran/feeds_packages_lang_node_node/releases/tag/nxhack-node24) 两个固定发布。
