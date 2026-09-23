#!/usr/bin/env python3
"""
Opera VPN (SurfEasy) 匿名注册与落地节点提取器
纯 Python 标准库实现 Digest 鉴权与匿名开户，无需任何外部依赖。

输出产物：
- opera-links.txt: 单行通用 HTTPS/HTTP 代理链接（可直接导入 sout）
- opera-account.json: 凭据与落地详情
"""
import hashlib
import json
import os
import re
import secrets
import ssl
import sys
import urllib.parse
import urllib.request
import urllib.error

SSL_CTX = ssl._create_unverified_context()

EP = "https://api2.sec-tunnel.com/v4"
API_USER = "se0316"
API_PASS = "SILrMEPBmJuhomxWkfm3JalqHX2Eheg1YhlEZiMh8II"
CLIENT_TYPE = "se0316"

REGIONS = {"AS": "亚洲", "EU": "欧洲", "AM": "美洲"}

HDR = {
    "SE-Client-Version": "Stable 114.0.5282.21",
    "SE-Operating-System": "Windows",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 OPR/114.0.0.0",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
}


def rand_hex(n: int) -> str:
    return secrets.token_hex(n)


def sha1_upper(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest().upper()


def digest_hash(algo: str, data: str) -> str:
    algo_lower = algo.lower()
    if "sha-256" in algo_lower or "sha256" in algo_lower:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
    if "sha-512" in algo_lower or "sha512" in algo_lower:
        return hashlib.sha512(data.encode("utf-8")).hexdigest()
    return hashlib.md5(data.encode("utf-8")).hexdigest()


class OperaSession:
    def __init__(self):
        self.cookie_jar = ""

    def _absorb_cookies(self, headers):
        cookies = headers.get_all("Set-Cookie") or []
        if cookies:
            cookie_parts = [c.split(";")[0] for c in cookies]
            self.cookie_jar = "; ".join(cookie_parts)

    def rpc(self, path: str, params: dict) -> dict:
        url = f"{EP}/{path}"
        body = urllib.parse.urlencode(params).encode("utf-8")

        req_headers = dict(HDR)
        if self.cookie_jar:
            req_headers["Cookie"] = self.cookie_jar

        req = urllib.request.Request(url, data=body, headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
                self._absorb_cookies(r.headers)
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self._absorb_cookies(e.headers)
                wa = e.headers.get("Www-Authenticate", "")
                auth_header = self._make_digest_auth(wa, url, path, params)
                req_headers["Authorization"] = auth_header
                retry_req = urllib.request.Request(url, data=body, headers=req_headers)
                with urllib.request.urlopen(retry_req, timeout=30, context=SSL_CTX) as r2:
                    self._absorb_cookies(r2.headers)
                    j = json.loads(r2.read())
                    if j.get("status", {}).get("code", 0) != 0:
                        raise RuntimeError(f"{path} 业务错误: {j.get('status')}")
                    return j
            raise

    def _make_digest_auth(self, wa: str, url: str, path: str, params: dict) -> str:
        def get_val(key):
            m = re.search(rf'{key}="([^"]*)"', wa)
            return m.group(1) if m else ""

        realm = get_val("realm")
        nonce = get_val("nonce")
        qop = get_val("qop")
        opaque = get_val("opaque")

        algo_m = re.search(r'algorithm=([^\s,]+)', wa)
        algo = algo_m.group(1).replace('"', '') if algo_m else "MD5"

        uri = urllib.parse.urlparse(url).path
        cnonce = rand_hex(4)
        nc = "00000001"

        h1 = digest_hash(algo, f"{API_USER}:{realm}:{API_PASS}")
        h2 = digest_hash(algo, f"POST:{uri}")

        q = qop.split(",")[0].strip() if qop else ""
        if q:
            resp = digest_hash(algo, f"{h1}:{nonce}:{nc}:{cnonce}:{q}:{h2}")
        else:
            resp = digest_hash(algo, f"{h1}:{nonce}:{h2}")

        parts = [
            f'Digest username="{API_USER}"',
            f'realm="{realm}"',
            f'nonce="{nonce}"',
            f'uri="{uri}"',
            f'response="{resp}"',
            f'algorithm={algo}',
        ]
        if q:
            parts.extend([f'qop={q}', f'nc={nc}', f'cnonce="{cnonce}"'])
        if opaque:
            parts.append(f'opaque="{opaque}"')

        return ", ".join(parts)


def generate_opera(outdir: str = "dist"):
    os.makedirs(outdir, exist_ok=True)
    print("[Opera] 开始匿名注册 Opera VPN 账号...")
    s = OperaSession()

    email = f"{rand_hex(5)}@{CLIENT_TYPE}.best.vpn"
    s.rpc("register_subscriber", {"email": email, "password": sha1_upper(email)})

    dev = s.rpc("register_device", {
        "client_type": CLIENT_TYPE,
        "device_hash": rand_hex(10).upper(),
        "device_name": "Opera-Browser-Client",
    })
    device_id = dev["data"]["device_id"]
    id_hash = sha1_upper(device_id)

    gp = s.rpc("device_generate_password", {"device_id": device_id})
    password = gp["data"]["device_password"]
    print(f"[Opera] 账号凭据生成成功 (用户名 ID: {id_hash[:8]}...)")

    print("[Opera] 正在探测各区域落地服务器...")
    landings = []
    for code, loc in REGIONS.items():
        try:
            disc = s.rpc("discover", {"serial_no": id_hash, "requested_geo": code})
            ips = disc.get("data", {}).get("ips", [])
            seq = 0
            for x in ips:
                seq += 1
                landings.append({
                    "tag": f"Opera-{loc}{seq}",
                    "loc": loc,
                    "ip": x["ip"],
                    "port": (x.get("port") and x["port"][0]) or 443,
                    "host": f"{code.lower()}{seq-1}.sec-tunnel.com",
                })
        except Exception as e:
            print(f"  - 跳过区域 {code}: {e}")

    print(f"[Opera] 共获取到 {len(landings)} 个落地节点")

    # 1. 生成单行代理链接列表（直接支持导入 sout 与各种客户端）
    links = []
    for land in landings:
        # Opera 是标准 HTTPS 代理 (RFC 2817 CONNECT 代理)
        link = f"https://{urllib.parse.quote(id_hash)}:{urllib.parse.quote(password)}@{land['ip']}:{land['port']}#{urllib.parse.quote(land['tag'])}"
        links.append(link)

    links_path = os.path.join(outdir, "opera-links.txt")
    acc_path = os.path.join(outdir, "opera-account.json")

    with open(links_path, "w", encoding="utf-8") as f:
        f.write("\n".join(links) + "\n")

    acc_data = {
        "username": id_hash,
        "password": password,
        "landings": landings,
    }
    with open(acc_path, "w", encoding="utf-8") as f:
        json.dump(acc_data, f, indent=2, ensure_ascii=False)

    print(f"[Opera] 产物已保存：")
    print(f"  - 链接列表: {links_path} ({len(links)} 个节点)")
    print(f"  - 账号信息: {acc_path}")

    return {
        "links": links_path,
        "username": id_hash,
        "password": password,
        "landings": landings,
        "node_links": links,
    }


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "dist"
    generate_opera(outdir)


if __name__ == "__main__":
    main()
