#!/usr/bin/env python3
"""
VPN 订阅与节点全量自动化提取器
一键调用各个 VPN 提取模块，并将所有提取出的节点聚合导出：

产物列表：
1. all-proxies.txt: 聚合所有 VPN 节点的单行通用代理链接（sout 面板可直接一键全量导入）
2. clash-subscription.yaml: 聚合的完整 mihomo / Clash 订阅配置（包含各 VPN 策略组）
3. 单独提取文件：
   - warp-masque.yaml / warp-masque-links.txt
   - windscribe.yaml / windscribe-links.txt
   - opera.yaml / opera-links.txt
"""
import argparse
import asyncio
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from extract_warp import generate_warp
from extract_windscribe import generate_windscribe
from extract_opera import generate_opera
from extract_proton import extract_proton_async


def build_aggregated_clash(outdir: str):
    """读取所有提取出的 yaml，合成一个全量订阅"""
    proxies_lines = []
    proxy_names = []
    group_defs = []

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
                        # 提取名字
                        n = line.split("name:")[1].split(",")[0].strip().strip('"\'')
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
                        n = line.split("name:")[1].split(",")[0].strip().strip('"\'')
                        proxy_names.append(n)

    # 3. 尝试读 WARP
    warp_yaml = os.path.join(outdir, "warp-masque.yaml")
    if os.path.exists(warp_yaml):
        with open(warp_yaml, "r", encoding="utf-8") as f:
            content = f.read()
            if "proxies:" in content:
                p_part = content.split("proxies:")[1].split("proxy-groups:")[0]
                proxies_lines.append(p_part.strip())
                for line in p_part.strip().splitlines():
                    if "name:" in line:
                        n = line.split("name:")[1].split(",")[0].strip().strip('"\'')
                        proxy_names.append(n)

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
""" + "\n".join(proxies_lines),
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
{ind(proxy_names)}"""
    ]

    if ws_names:
        sections.append(f"""  - name: 🛡️ Windscribe节点
    type: select
    proxies:
{ind(ws_names)}""")

    if op_names:
        sections.append(f"""  - name: 🎭 Opera节点
    type: select
    proxies:
{ind(op_names)}""")

    if warp_names:
        sections.append(f"""  - name: ⚡ WARP直连
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    proxies:
{ind(warp_names)}""")

    sections.append("""rules:
  - MATCH,🚀 节点选择
""")

    full_yaml = "\n".join(sections)
    out_file = os.path.join(outdir, "clash-subscription.yaml")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(full_yaml)
    print(f"[聚合订阅] 已生成 mihomo 聚合配置文件: {out_file} (共 {len(proxy_names)} 个节点)")


def main():
    parser = argparse.ArgumentParser(description="VPN 订阅全量提取工具")
    parser.add_argument("--vpn", choices=["all", "warp", "windscribe", "opera", "proton"], default="all",
                        help="选择提取的 VPN 类型 (默认: all)")
    parser.add_argument("--warp-config", default="config.json", help="WARP usque 配置文件路径")
    parser.add_argument("--outdir", default="dist", help="输出目录")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
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

    # 3. WARP
    if args.vpn in ("all", "warp"):
        if os.path.exists(args.warp_config):
            try:
                res = generate_warp(args.warp_config, args.outdir)
                links_file = os.path.join(args.outdir, "warp-masque-links.txt")
                if os.path.exists(links_file):
                    with open(links_file, "r", encoding="utf-8") as f:
                        warp_links = [line.strip() for line in f if line.strip()]
                        all_links.extend(warp_links)
            except Exception as e:
                print(f"[WARP] 提取遇到错误: {e}", file=sys.stderr)
        else:
            print(f"[WARP] 未找到 {args.warp_config}，跳过 WARP 提取（可使用 usque register 提前生成）。")

    # 4. Proton
    if args.vpn in ("all", "proton"):
        try:
            asyncio.run(extract_proton_async(args.outdir))
        except Exception as e:
            print(f"[Proton] 提取遇到错误: {e}", file=sys.stderr)

    # 写入聚合单行链接文件
    all_links_file = os.path.join(args.outdir, "all-proxies.txt")
    with open(all_links_file, "w", encoding="utf-8") as f:
        f.write("\n".join(all_links) + "\n")
    print(f"\n[聚合单行列表] 已汇总保存到 {all_links_file} (共 {len(all_links)} 条可用连接)")

    # 组装聚合 Clash 订阅
    build_aggregated_clash(args.outdir)

    print("\n[OK] 所有任务完成！")


if __name__ == "__main__":
    main()
