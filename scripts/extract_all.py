#!/usr/bin/env python3
"""
VPN 订阅与节点全量自动化提取器
一键调用各个 VPN 提取模块，并将所有提取出的节点聚合导出：

产物列表：
1. all-proxies.txt: 聚合所有 VPN 节点的单行通用代理链接（包含 SOCKS5 / HTTP / HTTPS / WireGuard）
2. 单独提取文件：
   - windscribe-links.txt
   - opera-links.txt
   - proton-links.txt
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

from extract_windscribe import generate_windscribe
from extract_opera import generate_opera
from extract_proton import extract_proton_async






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
        choices=["all", "windscribe", "opera", "proton"],
        default="all",
        help="选择提取的 VPN 类型 (默认: all)",
    )
    parser.add_argument("--outdir", default="dist", help="输出目录")
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="仅根据 outdir 中的各独立产物重新生成全量 all-proxies.txt",
    )
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    if args.aggregate_only:
        print(f"[聚合模式] 仅重新聚合 {args.outdir} 下的产物...")
        build_aggregated_links(args.outdir, [])
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


    # 3. Proton
    if args.vpn in ("all", "proton"):
        try:
            is_strict = (args.vpn == "proton")
            res = asyncio.run(extract_proton_async(args.outdir, strict=is_strict))
            if res and res.get("node_links"):
                all_links.extend(res["node_links"])
        except Exception as e:
            print(f"[Proton] 提取遇到错误: {e}", file=sys.stderr)
            if args.vpn == "proton":
                raise

    # 智能增量合并写入聚合单行链接文件
    build_aggregated_links(args.outdir, all_links)

    print("\n[OK] 所有任务完成！")


if __name__ == "__main__":
    main()
