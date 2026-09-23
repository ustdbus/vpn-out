# vpn-out: 全自动 VPN 订阅与节点提取器

专为 GitHub Actions 打造的极简 VPN 节点提取器。无需服务器、无需配置复杂的 Cloudflare Worker，一键自动注册、提取多国家/地区的 VPN 代理节点并生成标准订阅。

完美兼容 **sout** 代理面板与各大代理客户端（Mihomo / Clash Verge / ClashMi / Shadowrocket 等）。

---

## 🌟 支持的 VPN 节点类型

| VPN 服务 | 注册方式 | 节点类型 | 覆盖地区 | 特点 |
| :--- | :--- | :--- | :--- | :--- |
| **Windscribe** | Actions 自动开户 | HTTP / HTTPS 代理 | 13 个国家/地区（香港、美国、加拿大、法国、德国、英国、荷兰、挪威、瑞士、罗马尼亚等） | 官方免费 2GB/月，60+ 落地服务器 |
| **Opera VPN** | 匿名协议自动开户 | HTTPS 代理 | 亚洲、欧洲、美洲 | 不限流量，匿名开户 |
| **Cloudflare WARP** | MASQUE 协议注册 | MASQUE / WireGuard | 全球任播 Anycast | 57 个优选端点，极低握手延迟与抗封锁 |
| **Proton VPN** | 凭证自动提取 | WireGuard | 日本、新加坡、美国、荷兰等 | 免费机房节点 |

---

## 🚀 产物与在线订阅链接

工作流执行完成后，会自动将最新的可用节点发布到本仓库的 `sub` 分支，您可以直接使用 RAW 直链作为**永远在线、自动更新的订阅源**：

- **单行代理节点聚合列表 (sout 推荐)**:
  `https://raw.githubusercontent.com/ustdbus/vpn-out/sub/all-proxies.txt`
- **Mihomo / Clash 聚合订阅**:
  `https://raw.githubusercontent.com/ustdbus/vpn-out/sub/clash-subscription.yaml`
- **Windscribe 独立节点列表**:
  `https://raw.githubusercontent.com/ustdbus/vpn-out/sub/windscribe-links.txt`
- **Opera 独立节点列表**:
  `https://raw.githubusercontent.com/ustdbus/vpn-out/sub/opera-links.txt`
- **WARP MASQUE 独立链接列表**:
  `https://raw.githubusercontent.com/ustdbus/vpn-out/sub/warp-masque-links.txt`

---

## 📖 在 sout 面板中使用

1. 打开 **sout** 控制面板。
2. 方式 A（一键批量添加）：
   - 点击 **「添加自定义出口」**。
   - 在弹出的窗口中，将从上面链接复制的节点链接（或直接输入订阅链接）粘贴进去，点击 **「批量解析并导入」** 即可一键加入出口隧道池！
3. 方式 B（自动定时订阅）：
   - 点击 **「SOCKS5 订阅源」**。
   - 添加源名称（如 `VPN-OUT 订阅源`）以及上面的 `all-proxies.txt` 或 `clash-subscription.yaml` 链接。
   - sout 会自动同步节点并按家宽/机房进行识别，之后在下方节点列表中绑定分流即可。

---

## ⚙️ 如何在 GitHub Actions 运行

1. 进入仓库的 **Actions** 标签页。
2. 点击左侧 **`VPN 订阅自动化提取与更新`**。
3. 点击右侧 **`Run workflow`**，选择需要提取的 VPN 类型（默认 `all` 全部提取），点击启动。
4. 运行完成后，可在 **Summary** 查看节点统计，在 **Artifacts** 下载打包文件，同时 `sub` 分支中的订阅直链已自动同步更新。
