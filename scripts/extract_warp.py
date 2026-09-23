#!/usr/bin/env python3
"""
Cloudflare WARP (MASQUE) 连接提取器
支持直接解析 usque config.json 或自动生成 MASQUE 节点配置。

输出产物：
- warp-masque.yaml: 57 个优选端点的 mihomo 完整配置
- warp-masque-links.txt: Shadowrocket 适用的 masque:// 链接列表（每行一个）
- warp-outbounds.json: sing-box 出站格式
- warp-account.json: 账户凭据元数据
"""
import os
import sys
import json
import urllib.parse

V4 = ["162.159.198.1", "162.159.198.2", "162.159.199.1", "162.159.199.2"]
V6 = ["2606:4700:103::1", "2606:4700:103::2", "2606:4700:104::1", "2606:4700:104::2"]
PORTS = (443, 500, 1701, 4500, 4443, 8443, 8095)
OFFICIAL_SNI = "zt-masque.cloudflareclient.com"
SNI_NODE = ("162.159.198.1", 443)


def pem_to_b64der(pem: str) -> str:
    return "".join(
        ln.strip()
        for ln in pem.strip().splitlines()
        if ln.strip() and not ln.startswith("-----")
    )


def node_name(ip: str, port: int) -> str:
    if ":" in ip:
        seg = ip.split(":")[2]
        tail = ip.rsplit(":", 1)[-1]
        return f"WARP6-{seg}-{tail}-{port}"
    return f"WARP-{'.'.join(ip.split('.')[2:])}-{port}"


def masque_clash_node(name: str, ip: str, port: int, priv: str, pub: str, v4: str, v6: str, sni: str = None) -> str:
    srv = f'"{ip}"' if ":" in ip else ip
    extra = f"\n    sni: {sni}" if sni else ""
    return f"""  - name: {name}
    type: masque
    server: {srv}
    port: {port}{extra}
    private-key: {priv}
    public-key: {pub}
    ip: {v4}
    ipv6: {v6}
    mtu: 1280
    udp: true
    remote-dns-resolve: true
    dns: [1.1.1.1, 2606:4700:4700::1111]"""


def masque_links(cfg: dict, priv: str, pub: str):
    def enc(v):
        return urllib.parse.quote(str(v), safe="").replace("%2C", ",")

    lines = []
    for ip in V4 + V6:
        for port in PORTS:
            params = "&".join([
                "publicKey=" + enc(pub),
                "privateKey=" + enc(priv),
                "ip=" + enc(cfg.get("ipv4", "172.16.0.2")),
                "dns=" + enc("1.1.1.1, 8.8.8.8"),
                "udp=1",
                "cc=" + enc(""),
                "flag=" + enc("CDN"),
            ])
            host = f"[{ip}]" if ":" in ip else ip
            name = node_name(ip, port)
            lines.append(f"masque://{host}:{port}?{params}#{enc(name)}")
    return lines


def build_singbox_outbounds(cfg: dict, priv: str, pub: str):
    outbounds = []
    v4 = cfg.get("ipv4", "172.16.0.2")
    v6 = cfg.get("ipv6", "")
    for ip in V4 + V6:
        for port in PORTS:
            name = node_name(ip, port)
            ob = {
                "type": "masque",
                "tag": name,
                "server": ip,
                "server_port": port,
                "private_key": priv,
                "public_key": pub,
                "local_address": [v4 + "/32"] if v4 else [],
                "udp": True,
            }
            if v6:
                ob["local_address"].append(v6 + "/128")
            outbounds.append(ob)
    return outbounds


def generate_warp(cfg_or_path, outdir: str = "dist"):
    os.makedirs(outdir, exist_ok=True)
    if isinstance(cfg_or_path, str):
        with open(cfg_or_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        cfg = cfg_or_path

    priv = cfg.get("private_key", "").strip()
    if priv.startswith("-----"):
        priv = pem_to_b64der(priv)
    pub = cfg.get("endpoint_pub_key", "")
    if pub.startswith("-----"):
        pub = pem_to_b64der(pub)
    v4 = cfg.get("ipv4", "")
    v6 = cfg.get("ipv6", "")

    names = []
    proxies = []
    for ip in V4 + V6:
        for port in PORTS:
            name = node_name(ip, port)
            names.append(name)
            proxies.append(masque_clash_node(name, ip, port, priv, pub, v4, v6))

    names.append("WARP-官方域名")
    proxies.append(masque_clash_node("WARP-官方域名", SNI_NODE[0], SNI_NODE[1], priv, pub, v4, v6, OFFICIAL_SNI))

    links = masque_links(cfg, priv, pub)
    sb_outbounds = build_singbox_outbounds(cfg, priv, pub)

    ind = lambda lst, n=6: "\n".join(" " * n + f"- {x}" for x in lst)

    clash_yaml = f"""# Cloudflare WARP over MASQUE 订阅配置
# 生成时间: 自动生成
mixed-port: 7890
allow-lan: false
mode: rule
log-level: info
ipv6: true

proxies:
{chr(10).join(proxies)}

proxy-groups:
  - name: 🚀 节点选择
    type: select
    proxies:
      - ♻️ 自动选择
      - 🔄 故障转移
      - ☑️ 手动切换
      - DIRECT

  - name: ♻️ 自动选择
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    proxies:
{ind(names)}

  - name: 🔄 故障转移
    type: fallback
    url: http://www.gstatic.com/generate_204
    interval: 180
    proxies:
{ind(names)}

  - name: ☑️ 手动切换
    type: select
    proxies:
{ind(names)}

rules:
  - MATCH,🚀 节点选择
"""

    yaml_file = os.path.join(outdir, "warp-masque.yaml")
    links_file = os.path.join(outdir, "warp-masque-links.txt")
    sb_file = os.path.join(outdir, "warp-outbounds.json")
    acc_file = os.path.join(outdir, "warp-account.json")

    with open(yaml_file, "w", encoding="utf-8") as f:
        f.write(clash_yaml)

    with open(links_file, "w", encoding="utf-8") as f:
        f.write("\n".join(links) + "\n")

    with open(sb_file, "w", encoding="utf-8") as f:
        json.dump(sb_outbounds, f, indent=2, ensure_ascii=False)

    with open(acc_file, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    print(f"[WARP] 成功生成 {len(names)} 个节点配置：")
    print(f"  - YAML: {yaml_file}")
    print(f"  - 链接: {links_file} ({len(links)} 条)")
    print(f"  - Sing-box: {sb_file}")

    return {
        "yaml": yaml_file,
        "links": links_file,
        "nodes": names,
        "count": len(names)
    }


def main():
    cfg_file = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "dist"

    if not os.path.exists(cfg_file):
        print(f"未找到 {cfg_file}，请先运行 usque register 获取或传入配置路径", file=sys.stderr)
        sys.exit(1)

    generate_warp(cfg_file, outdir)


if __name__ == "__main__":
    main()
