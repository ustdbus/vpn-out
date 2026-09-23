#!/usr/bin/env python3
"""
VPN 订阅与节点全量自动化提取器
一键调用各个 VPN 提取模块，并将所有提取出的节点聚合导出：

产物列表：
1. all-proxies.txt: 聚合所有 VPN 节点的单行通用代理链接（包含 WireGuard / SOCKS5 / HTTP）
2. clash-subscription.yaml: 聚合的完整 mihomo / Clash 订阅配置（包含各 VPN 策略组）
3. 单独提取文件：
   - warp-wireguard.json / warp-wireguard.conf / warp-links.txt
   - windscribe.yaml / windscribe-links.txt
   - opera.yaml / opera-links.txt
"""
import argparse
import asyncio
import json
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from extract_warp import generate_warp
from extract_windscribe import generate_windscribe
from extract_opera import generate_opera
from extract_proton import extract_proton_async


def build_aggregated_clash(outdir: str):
    """读取所有提取出的 yaml/json，合成一个全量订阅"""
    proxies_lines = []
    proxy_names = []

    # 1. 尝试读 Windscribe
    ws_yaml = os.path.join(outdir, "windscribe.yaml")
    if os.path.exists(ws_yaml):
        with open(ws_yaml, "r", encoding="utf-8") as f:
            content = f.read()
            if "proxies:" in content:
                p_part = content.split("proxies:")[1].split("proxy-groups:")[0]
                proxies_lines.append(p_part.strip())
                for line in p_part.strip().splitlines():
                    if "name:" in line:
                        n = line.split("name:")[1].split(",")[0].strip().strip("\"'")
                        proxy_names.append(n)

    # 2. 尝试读 Opera
    op_yaml = os.path.join(outdir, "opera.yaml")
    if os.path.exists(op_yaml):
        with open(op_yaml, "r", encoding="utf-8") as f:
            content = f.read()
            if "proxies:" in content:
                p_part = content.split("proxies:")[1].split("proxy-groups:")[0]
                proxies_lines.append(p_part.strip())
                for line in p_part.strip().splitlines():
                    if "name:" in line:
                        n = line.split("name:")[1].split(",")[0].strip().strip("\"'")
                        proxy_names.append(n)

    # 3. 尝试读 WARP WireGuard 出站并转换为 Clash / Mihomo 格式
    warp_json = os.path.join(outdir, "warp-wireguard.json")
    if os.path.exists(warp_json):
        try:
            with open(warp_json, "r", encoding="utf-8") as f:
                wcfg = json.load(f)
            v4 = ""
            v6 = ""
            for addr in wcfg.get("local_address", []):
                ip_part = addr.split("/")[0]
                if ":" in ip_part:
                    v6 = ip_part
                else:
                    v4 = ip_part
            priv = wcfg.get("private_key", "")
            pub = wcfg.get("peer_public_key", "")
            srv = wcfg.get("server", "engage.cloudflareclient.com")
            port = wcfg.get("server_port", 2408)
            name = "WARP-WireGuard"

            clash_wg = f"""  - name: {name}
    type: wireguard
    server: {srv}
    port: {port}
    ip: {v4}
    ipv6: {v6}
    public-key: {pub}
    private-key: {priv}
    udp: true
    remote-dns-resolve: true
    dns: [1.1.1.1, 2606:4700:4700::1111]
    mtu: 1280
    reserved: [0, 0, 0]"""
            proxies_lines.append(clash_wg)
            proxy_names.append(name)
        except Exception as e:
            print(f"[WARP Clash 转换] 忽略错误: {e}", file=sys.stderr)

    if not proxies_lines:
        return

    ind = lambda lst, n=6: "\n".join(" " * n + f"- {x}" for x in lst)

    ws_names = [x for x in proxy_names if x.startswith("WS-")]
    op_names = [x for x in proxy_names if x.startswith("Opera-")]
    warp_names = [x for x in proxy_names if x.startswith("WARP")]

    main_proxies = ["♻️ 自动选择"]
    if ws_names:
        main_proxies.append("🛡️ Windscribe节点")
    if op_names:
        main_proxies.append("🎭 Opera节点")
    if warp_names:
        main_proxies.append("⚡ WARP直连")
    main_proxies.append("DIRECT")

    sections = [
        """mixed-port: 7890
allow-lan: false
mode: rule
log-level: info
ipv6: true

proxies:
"""
        + "\n".join(proxies_lines),
        f"""
proxy-groups:
  - name: 🚀 节点选择
    type: select
    proxies:
{ind(main_proxies)}

  - name: ♻️ 自动选择
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    proxies:
{ind(proxy_names)}""",
    ]

    if ws_names:
        sections.append(
            f"""  - name: 🛡️ Windscribe节点
    type: select
    proxies:
{ind(ws_names)}"""
        )

    if op_names:
        sections.append(
            f"""  - name: 🎭 Opera节点
    type: select
    proxies:
{ind(op_names)}"""
        )

    if warp_names:
        sections.append(
            f"""  - name: ⚡ WARP直连
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    proxies:
{ind(warp_names)}"""
        )

    sections.append(
        """rules:
  - MATCH,🚀 节点选择
"""
    )

    full_yaml = "\n".join(sections)
    out_file = os.path.join(outdir, "clash-subscription.yaml")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(full_yaml)
    print(f"[聚合订阅] 已生成 mihomo 聚合配置文件: {out_file} (共 {len(proxy_names)} 个节点)")


def build_aggregated_links(outdir: str, current_links: list = None) -> list:
    """读取 outdir 下所有的独立节点文件，并与当前生成的 links 智能合并去重"""
    merged = []
    seen = set()

    def add_link(link: str):
        link = link.strip()
        if not link or link.startswith("#"):
            return
        if link not in seen:
            seen.add(link)
            merged.append(link)

    # 1. 优先加入当前提取轮次产生的链接
    if current_links:
        for lk in current_links:
            add_link(lk)

    # 2. 依次扫描并合并各个 VPN 独立的 links.txt 文件（确保历史有效节点不丢失）
    known_link_files = [
        "windscribe-links.txt",
        "opera-links.txt",
        "warp-links.txt",
        "proton-links.txt",
    ]
    for fn in known_link_files:
        fp = os.path.join(outdir, fn)
        if os.path.exists(fp):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    for line in f:
                        add_link(line)
            except Exception as e:
                print(f"[聚合警告] 读取 {fn} 失败: {e}", file=sys.stderr)

    out_file = os.path.join(outdir, "all-proxies.txt")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(merged) + "\n")
    print(f"\n[聚合单行列表] 已汇总保存到 {out_file} (共 {len(merged)} 条可用连接)")
    return merged


def main():
    parser = argparse.ArgumentParser(description="VPN 订阅全量提取工具")
    parser.add_argument(
        "--vpn",
        choices=["all", "warp", "windscribe", "opera", "proton"],
        default="all",
        help="选择提取的 VPN 类型 (默认: all)",
    )
    parser.add_argument("--warp-config", default="", help="WARP 账户配置文件路径 (可选)")
    parser.add_argument("--outdir", default="dist", help="输出目录")
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="仅根据 outdir 中的各独立产物重新生成全量 all-proxies.txt 与 clash-subscription.yaml",
    )
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    if args.aggregate_only:
        print(f"[聚合模式] 仅重新聚合 {args.outdir} 下的产物...")
        build_aggregated_links(args.outdir, [])
        build_aggregated_clash(args.outdir)
        print("[OK] 重新聚合完成！")
        return

    all_links = []

    # 1. Windscribe
    if args.vpn in ("all", "windscribe"):
        try:
            res = generate_windscribe(args.outdir)
            if res and res.get("node_links"):
                all_links.extend(res["node_links"])
        except Exception as e:
            print(f"[Windscribe] 提取遇到错误 (如 IP 风控): {e}", file=sys.stderr)

    # 2. Opera
    if args.vpn in ("all", "opera"):
        try:
            res = generate_opera(args.outdir)
            if res and res.get("node_links"):
                all_links.extend(res["node_links"])
        except Exception as e:
            print(f"[Opera] 提取遇到错误: {e}", file=sys.stderr)

    # 3. WARP (WireGuard 直连，纯 Python 官方 API 注册，无需外部依赖)
    if args.vpn in ("all", "warp"):
        try:
            cfg_path = args.warp_config if args.warp_config and os.path.exists(args.warp_config) else None
            res = generate_warp(cfg_path, args.outdir)
            if res and res.get("links"):
                all_links.extend(res["links"])
        except Exception as e:
            print(f"[WARP] 提取遇到错误: {e}", file=sys.stderr)

    # 4. Proton
    if args.vpn in ("all", "proton"):
        try:
            asyncio.run(extract_proton_async(args.outdir))
        except Exception as e:
            print(f"[Proton] 提取遇到错误: {e}", file=sys.stderr)

    # 智能增量合并写入聚合单行链接文件
    build_aggregated_links(args.outdir, all_links)

    # 组装聚合 Clash 订阅
    build_aggregated_clash(args.outdir)

    print("\n[OK] 所有任务完成！")


if __name__ == "__main__":
    main()
