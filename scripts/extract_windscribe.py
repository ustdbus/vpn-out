#!/usr/bin/env python3
"""
Windscribe 账号注册与节点订阅提取器
在 GitHub Actions 或干净 IP 环境下自动开出有效账号（2GB/月流量），
直接提取出 13 个国家/地区的全部官方代理节点，并导出为通用订阅与链接。

输出产物：
- windscribe-links.txt: 单行通用代理链接列表（直接支持导入 sout 与各种客户端）
- windscribe.yaml: mihomo / Clash 代理配置（支持各国家/地区分组）
- windscribe-account.json: 账号信息与剩余额度
"""
import base64
import hashlib
import json
import os
import secrets
import ssl
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SSL_CTX = ssl._create_unverified_context()

CLIENT_AUTH_SECRET = "952b4412f002315aa50751032fcaab03"
API = "https://api.windscribe.com"
ASSETS = "https://assets.windscribe.com/serverlist"
PROXY_PORT = 443

HDR = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.53 Safari/537.36",
    "Origin": "chrome-extension://hnmpcagpplmpfojmgmnngilcnanddlhb",
    "Accept": "application/json",
}

# 官方免费 13 个地区对应的中文标签
REGIONS = {
    "HK": "香港",
    "US": "美国东部",
    "US-C": "美国中部",
    "US-W": "美国西部",
    "CA": "加拿大东部",
    "CA-W": "加拿大西部",
    "FR": "法国",
    "DE": "德国",
    "NL": "荷兰",
    "NO": "挪威",
    "RO": "罗马尼亚",
    "CH": "瑞士",
    "GB": "英国",
}


def auth_hash():
    t = int(time.time())
    return hashlib.md5((CLIENT_AUTH_SECRET + str(t)).encode()).hexdigest(), t


def post_api(url: str, data: dict):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={**HDR, "Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
        return r.status, json.loads(r.read())


def register_account():
    h, t = auth_hash()
    user = "u" + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(9))
    pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16)) + "!aA9"
    st, body = post_api(f"{API}/Users", {
        "client_auth_hash": h,
        "time": str(t),
        "session_type_id": "2",
        "username": user,
        "password": pw,
    })
    d = body.get("data")
    if not d:
        raise RuntimeError(f"Windscribe 开户失败: {body.get('errorMessage', body)}")
    if d.get("status") != 1:
        raise RuntimeError(
            f"拿到降额账号 status={d['status']} traffic_max={d.get('traffic_max')}，"
            f"当前 IP 被风控，请重试以更换 runner IP。"
        )
    return {
        "username": user,
        "password": pw,
        "userId": d["user_id"],
        "sessionAuthHash": d["session_auth_hash"],
        "locHash": d["loc_hash"],
        "trafficMax": d["traffic_max"],
        "status": d["status"],
        "registeredAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def fetch_credentials(acc: dict):
    h, t = auth_hash()
    q = urllib.parse.urlencode({
        "client_auth_hash": h,
        "session_auth_hash": acc["sessionAuthHash"],
        "time": str(t),
    })
    req = urllib.request.Request(f"{API}/ServerCredentials?{q}", headers=HDR)
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
        d = json.loads(r.read()).get("data")
    if not d:
        raise RuntimeError("获取 Windscribe 代理凭据失败")
    return {
        "proxyUser": base64.b64decode(d["username"]).decode("utf-8"),
        "proxyPass": base64.b64decode(d["password"]).decode("utf-8"),
    }


def fetch_server_list(loc_hash: str):
    url = f"{ASSETS}/chrome/0/{loc_hash}"
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
        j = json.loads(r.read())
    servers = []
    for c in j.get("data", []):
        if c.get("premium_only"):
            continue
        short_name = c.get("short_name", "")
        loc = REGIONS.get(short_name)
        if not loc:
            continue
        seq = 0
        for g in c.get("groups", []):
            for h in g.get("hosts", []):
                hostname = h.get("hostname")
                if not hostname:
                    continue
                seq += 1
                servers.append({
                    "tag": f"{loc}{seq}",
                    "loc": loc,
                    "short_name": short_name,
                    "host": hostname,
                    "port": PROXY_PORT,
                })
    return servers


def generate_windscribe(outdir: str = "dist", existing_acc: dict = None):
    os.makedirs(outdir, exist_ok=True)

    if existing_acc:
        acc = existing_acc
        print(f"[Windscribe] 使用已有账号: {acc.get('userId')}")
    else:
        print("[Windscribe] 正在注册新账号...")
        acc = register_account()
        gb = acc["trafficMax"] / (1024 * 1024 * 1024)
        print(f"[Windscribe] 开户成功! 用户 ID: {acc['userId']}, 额度: {gb:.2f} GB")

    print("[Windscribe] 正在获取代理连接凭据与服务器列表...")
    cred = fetch_credentials(acc)
    servers = fetch_server_list(acc["locHash"])
    print(f"[Windscribe] 共获取到 {len(servers)} 个可用节点，覆盖 13 个国家/地区")

    user = cred["proxyUser"]
    pwd = cred["proxyPass"]

    # 1. 生成单行代理链接列表（可直接导入 sout 和其它客户端）
    # 格式: https://user:pass@host:443#WS-地区
    links = []
    for s in servers:
        tag = f"WS-{s['tag']}"
        link = f"https://{urllib.parse.quote(user)}:{urllib.parse.quote(pwd)}@{s['host']}:{s['port']}#{urllib.parse.quote(tag)}"
        links.append(link)

    # 2. 生成 Clash / mihomo 格式
    proxies = []
    by_loc = {}
    names = []
    for s in servers:
        name = f"WS-{s['tag']}"
        names.append(name)
        by_loc.setdefault(s["loc"], []).append(name)
        proxies.append(
            f'  - {{name: "{name}", type: http, server: {s["host"]}, port: {s["port"]}, '
            f'username: "{user}", password: "{pwd}", tls: true, sni: "{s["host"]}", '
            f'skip-cert-verify: false}}'
        )

    def q(items, n=6):
        return "\n".join(" " * n + f'- "{x}"' for x in items)

    def p(items, n=6):
        return "\n".join(" " * n + f"- {x}" for x in items)

    loc_groups = []
    loc_group_names = []
    for loc, tags in by_loc.items():
        gname = f"WS-{loc}"
        loc_group_names.append(gname)
        loc_groups.append(f"""  - name: {gname}
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    tolerance: 100
    proxies:
{q(tags)}""")

    clash_yaml = f"""# Windscribe 官方节点订阅
# 账号: {acc['userId']} (2GB/月)
# 地区覆盖: 13 个地区，共 {len(servers)} 个节点
mixed-port: 7890
allow-lan: false
mode: rule

proxies:
{chr(10).join(proxies)}

proxy-groups:
  - name: 🚀 节点选择
    type: select
    proxies:
      - ♻️ 自动选择
{p(loc_group_names)}
      - ☑️ 手动选择
      - DIRECT

  - name: ♻️ 自动选择
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    proxies:
{q(names)}

  - name: ☑️ 手动选择
    type: select
    proxies:
{q(names)}

{chr(10).join(loc_groups)}

rules:
  - MATCH,🚀 节点选择
"""

    links_path = os.path.join(outdir, "windscribe-links.txt")
    yaml_path = os.path.join(outdir, "windscribe.yaml")
    acc_path = os.path.join(outdir, "windscribe-account.json")

    with open(links_path, "w", encoding="utf-8") as f:
        f.write("\n".join(links) + "\n")

    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(clash_yaml)

    full_acc = {**acc, **cred, "server_count": len(servers)}
    with open(acc_path, "w", encoding="utf-8") as f:
        json.dump(full_acc, f, indent=2, ensure_ascii=False)

    print(f"[Windscribe] 产物已保存：")
    print(f"  - 链接列表: {links_path} ({len(links)} 个节点)")
    print(f"  - YAML: {yaml_path}")
    print(f"  - 账号信息: {acc_path}")

    return {
        "links": links_path,
        "yaml": yaml_path,
        "account": full_acc,
        "servers": servers,
        "proxyUser": user,
        "proxyPass": pwd,
        "node_links": links,
    }


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "dist"
    generate_windscribe(outdir)


if __name__ == "__main__":
    main()
