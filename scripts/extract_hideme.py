#!/usr/bin/env python3
"""
Hide.me 免费代理节点提取器 (基于官方 Chrome 扩展协议)
无需账号注册与登录，直接拉取 Hide.me 官方实时分配的免密 SOCKS5 代理落地节点，
并进行连通性检测，导出为通用订阅与链接。

注意：Hide.me 仅作为独立订阅源，不合并进全量 all-proxies.txt。

输出产物：
- hideme-links.txt: 单行标准 SOCKS5 代理链接列表 (可直接导入 sout 与各大代理客户端)
- hideme-account.json: 节点列表详情与探测状态
"""

import json
import os
import socket
import ssl
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SSL_CTX = ssl._create_unverified_context()

# 官方 API 端点与备用源
PRIMARY_API = "https://188.166.142.39/servers/list"
FALLBACK_API = "https://raw.githubusercontent.com/hidemevpn/proxy/master/config.json"

STATIC_FALLBACKS = [
    {"name": "hide.me SOCKS", "host": "socks.hide.me", "port": 1080},
    {"name": "Netherlands", "host": "213.111.146.36", "port": 18080},
    {"name": "Automatic", "host": "185.195.71.217", "port": 18080},
]

HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

COUNTRY_MAP = {
    "Switzerland": "瑞士",
    "Netherlands": "荷兰",
    "USA": "美国",
    "United States": "美国",
    "Canada": "加拿大",
    "Germany": "德国",
    "United Kingdom": "英国",
    "Singapore": "新加坡",
    "Automatic": "自动优选",
    "hide.me SOCKS": "SOCKS官方",
}


def fetch_json(url: str, timeout: int = 8, retries: int = 2):
    req = urllib.request.Request(url, headers=HDR)
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            time.sleep(1)
    raise last_err


def test_socks5_connectivity(host: str, port: int, timeout: float = 5.0) -> bool:
    """快速测试 SOCKS5 免密代理连通性 (通过探测 Cloudflare CDN)"""
    try:
        s = socket.create_connection((host, int(port)), timeout=timeout)
        # SOCKS5 握手: VER=5, NMETHODS=1, METHOD=0 (无需认证)
        s.sendall(b"\x05\x01\x00")
        resp = s.recv(2)
        if len(resp) < 2 or resp[0] != 5 or resp[1] != 0:
            s.close()
            return False

        # 尝试建立连接到 1.1.1.1:80
        target = b"1.1.1.1"
        req = b"\x05\x01\x00\x03" + bytes([len(target)]) + target + struct.pack("!H", 80)
        s.sendall(req)
        conn_resp = s.recv(10)
        if len(conn_resp) < 4 or conn_resp[1] != 0:
            s.close()
            return False

        s.close()
        return True
    except Exception:
        return False


def get_server_candidates() -> list:
    """从主 API 与备用源获取服务器列表"""
    servers = []
    seen = set()

    # 1. 尝试主 API
    try:
        print(f"[Hide.me] 正在从主接口拉取节点列表: {PRIMARY_API}...")
        data = fetch_json(PRIMARY_API)
        if isinstance(data, list):
            for item in data:
                host = item.get("host", "").strip()
                port = int(item.get("port", 0))
                if host and port and (host, port) not in seen:
                    seen.add((host, port))
                    servers.append({
                        "name": item.get("name", "Unknown"),
                        "host": host,
                        "port": port,
                        "ttl": item.get("ttl", -1),
                    })
    except Exception as e:
        print(f"[Hide.me] 主接口请求失败 ({e})，将尝试备用源")

    # 2. 尝试 GitHub 备用源
    try:
        print(f"[Hide.me] 正在从备用接口拉取节点列表: {FALLBACK_API}...")
        data = fetch_json(FALLBACK_API)
        if isinstance(data, list):
            for item in data:
                host = item.get("host", "").strip()
                port = int(item.get("port", 0))
                if host and port and (host, port) not in seen:
                    seen.add((host, port))
                    servers.append({
                        "name": item.get("name", "Unknown"),
                        "host": host,
                        "port": port,
                        "ttl": item.get("ttl", -1),
                    })
    except Exception as e:
        print(f"[Hide.me] 备用接口拉取失败: {e}")

    # 3. 补充内置静态备用节点
    for item in STATIC_FALLBACKS:
        key = (item["host"], item["port"])
        if key not in seen:
            seen.add(key)
            servers.append(dict(item))

    return servers


def generate_hideme(outdir: str = "dist", verify: bool = True):
    os.makedirs(outdir, exist_ok=True)
    print("[Hide.me] 开始提取 Hide.me 官方免密 SOCKS5 代理节点...")

    candidates = get_server_candidates()
    print(f"[Hide.me] 共获取到 {len(candidates)} 个候选节点，开始连通性测试...")

    valid_servers = []

    if verify:
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_server = {
                executor.submit(test_socks5_connectivity, s["host"], s["port"]): s
                for s in candidates
            }
            for future in as_completed(future_to_server):
                server = future_to_server[future]
                is_ok = future.result()
                status_str = "可用" if is_ok else "不可达"
                name_cn = COUNTRY_MAP.get(server["name"], server["name"])
                print(f"  - [{status_str}] {name_cn} ({server['host']}:{server['port']})")
                if is_ok:
                    valid_servers.append(server)
    else:
        valid_servers = candidates

    # 如果验证后没有可用节点，降级使用全部候选
    if not valid_servers:
        print("[Hide.me] 警告：所有节点连通探测均未响应，将保留候选节点列表。")
        valid_servers = candidates

    # 生成单行通用 SOCKS5 代理链接
    # 格式: socks5://host:port#HideMe-地区
    links = []
    by_country = {}
    for s in valid_servers:
        raw_name = s["name"]
        name_cn = COUNTRY_MAP.get(raw_name, raw_name)
        by_country[name_cn] = by_country.get(name_cn, 0) + 1
        seq = by_country[name_cn]
        tag = f"HideMe-{name_cn}{seq if seq > 1 else ''}"

        # SOCKS5 无密码直接连接格式
        link = f"socks5://{s['host']}:{s['port']}#{urllib.parse.quote(tag)}"
        links.append(link)

    links_path = os.path.join(outdir, "hideme-links.txt")
    acc_path = os.path.join(outdir, "hideme-account.json")

    with open(links_path, "w", encoding="utf-8") as f:
        f.write("\n".join(links) + "\n")

    info = {
        "service": "hide.me",
        "type": "socks5",
        "server_count": len(valid_servers),
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "servers": valid_servers,
        "node_links": links,
    }
    with open(acc_path, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)

    print(f"[Hide.me] 产物保存成功：")
    print(f"  - 节点列表: {links_path} ({len(links)} 个节点)")
    print(f"  - 节点详情: {acc_path}")

    return {
        "links": links_path,
        "servers": valid_servers,
        "node_links": links,
    }


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "dist"
    generate_hideme(outdir)


if __name__ == "__main__":
    main()
