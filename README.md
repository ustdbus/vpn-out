# vpn-out: 全自动 VPN 订阅与节点提取器

专为 GitHub Actions 打造的极简 VPN 节点提取器。无需服务器、无需配置复杂的 Cloudflare Worker，一键自动注册、提取多国家/地区的 VPN 代理节点并生成标准订阅。

完美兼容 **sout** 代理面板与各大代理客户端（sing-box / Shadowrocket / WireGuard 客户端等）。

---

## 🌟 支持的 VPN 节点类型

| VPN 服务 | 注册方式 | 节点类型 | 覆盖地区 | 特点 |
| :--- | :--- | :--- | :--- | :--- |
| **Windscribe** | Actions 自动开户 | HTTP / HTTPS 代理 | 13 个国家/地区（香港、美国、加拿大、法国、德国、英国、荷兰、挪威、瑞士、罗马尼亚等） | 官方免费 2GB/月，60+ 落地服务器 |
| **Opera VPN** | 匿名协议自动开户 | HTTPS 代理 | 亚洲、欧洲、美洲 | 不限流量，匿名开户 |
| **Proton VPN** | 凭证自动提取 | WireGuard | 日本、新加坡、美国、荷兰等 | 免费机房节点 |


---

## 🚀 产物与在线订阅链接

工作流执行完成后，会自动将最新的可用节点发布到本仓库的 `sub` 分支，您可以直接使用 RAW 直链作为**永远在线、自动更新的订阅源**：

- **单行代理节点聚合列表 (sout 推荐首选)**:
  `https://raw.githubusercontent.com/ustdbus/vpn-out/sub/all-proxies.txt`
- **Windscribe 独立节点列表 (HTTP/HTTPS 代理)**:
  `https://raw.githubusercontent.com/ustdbus/vpn-out/sub/windscribe-links.txt`
- **Opera 独立节点列表 (HTTPS 代理)**:
  `https://raw.githubusercontent.com/ustdbus/vpn-out/sub/opera-links.txt`
- **Proton 独立节点列表 (WireGuard)**:
  `https://raw.githubusercontent.com/ustdbus/vpn-out/sub/proton-links.txt`

> **提示**：Cloudflare WARP 推荐直接在 **sout** 面板中「申请并创建 WARP 出口」，由本机直接调用 Cloudflare 官方 API 注册独立专属账户，无需再通过外部订阅导入。


---

## 📖 在 sout 面板中使用

1. 打开 **sout** 控制面板。
2. 方式 A（一键批量添加）：
   - 点击 **「添加自定义出口」**。
   - 在弹出的窗口中，将从上面链接复制的节点链接（或直接输入订阅链接）粘贴进去，点击 **「批量解析并导入」** 即可一键加入出口隧道池！
3. 方式 B（自动定时订阅）：
   - 点击 **「SOCKS5 订阅源」**。
   - 添加源名称（如 `VPN-OUT 订阅源`）以及上面的 `all-proxies.txt` 链接。
   - sout 会自动同步节点并按家宽/机房进行识别，之后在下方节点列表中绑定分流即可。

---

## ⚙️ 如何在 GitHub Actions 运行

1. **自动定时更新（每隔 3 天凌晨 3 点）**：
   - 仓库已配置全量工作流 **`全量 VPN 订阅自动化提取与更新 (All)`**，每隔 3 天（北京时间凌晨 03:00）自动全量运行一次，三个服务一起自动更新，聚合发布到 `sub` 分支。
2. **手动按需单独更新（选项全部保留）**：
   - 进入 **Actions** 标签页，左侧保留了各独立服务的 Action 入口，可随时按需单独点击 `Run workflow`：
     - **`Windscribe 订阅自动化更新`**：单独开户并刷新 Windscribe 节点与订阅。
     - **`Opera VPN 订阅自动化更新`**：单独探测并刷新 Opera 落地节点。
     - **`Proton VPN 订阅自动化更新`**：单独申请证书并刷新 Proton WireGuard 节点（需配置 `PROTON_USER`/`PROTON_PASS` Secrets）。
     - **`全量 VPN 订阅自动化提取与更新 (All)`**：随时手动全量刷新全部节点。
3. 运行完成后，各工作流均会自动将结果同步至 `sub` 分支，更新对应的独立订阅直链及 `all-proxies.txt` 聚合列表。
