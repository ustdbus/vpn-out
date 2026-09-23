#!/usr/bin/env python3
"""
Cloudflare WARP (WireGuard) 官方接口直连提取器
完全纯 Python 实现：标准 API 注册 + 密钥对生成，直接获取 WireGuard 凭据。
无需 MASQUE、无需 usque 二进制、无需任何 IP 优选，直连 engage.cloudflareclient.com。

输出产物：
- warp-wireguard.json: 标准 sing-box 1.10+ 的 WireGuard outbound 配置片段
- warp-wireguard.conf: 标准 WireGuard 客户端配置文件 (可直接导入官方客户端)
- warp-links.txt: 单行 WireGuard 节点通用链接
- warp-account.json: 账户凭据元数据
"""
import os
import sys
import json
import base64
import datetime
import urllib.parse
import urllib.request
import urllib.error

CLOUDFLARE_PEER_PUBKEY = "bmXOC+F1FxEMF9dyiK2H5/1SUtzHZsVoW++jnWgmtEs="
WARP_ENDPOINT_HOST = "engage.cloudflareclient.com"
WARP_ENDPOINT_IP = "162.159.192.1"
WARP_ENDPOINT_PORT = 2408
WARP_API_URL = "https://api.cloudflareclient.com/v0a2158/reg"

# RFC 7748 X25519 纯 Python 曲线乘法回退支持
P = 2**255 - 19
A24 = 121665


def _cswap(swap, x_2, x_3):
    dummy = swap * ((x_2 - x_3) % P)
    x_2 = (x_2 - dummy) % P
    x_3 = (x_3 + dummy) % P
    return x_2, x_3


def _x25519_base(scalar_bytes: bytes) -> bytes:
    k = bytearray(scalar_bytes)
    k[0] &= 248
    k[31] &= 127
    k[31] |= 64
    k_int = int.from_bytes(k, "little")
    x1 = 9
    x2, z2 = 1, 0
    x3, z3 = x1, 1
    swap = 0
    for t in reversed(range(255)):
        k_t = (k_int >> t) & 1
        swap ^= k_t
        x2, x3 = _cswap(swap, x2, x3)
        z2, z3 = _cswap(swap, z2, z3)
        swap = k_t
        A = (x2 + z2) % P
        AA = (A * A) % P
        B = (x2 - z2) % P
        BB = (B * B) % P
        E = (AA - BB) % P
        C = (x3 + z3) % P
        D = (x3 - z3) % P
        DA = (D * A) % P
        CB = (C * B) % P
        x3 = pow(DA + CB, 2, P)
        z3 = (x1 * pow(DA - CB, 2, P)) % P
        x2 = (AA * BB) % P
        z2 = (E * (AA + A24 * E)) % P
    x2, x3 = _cswap(swap, x2, x3)
    z2, z3 = _cswap(swap, z2, z3)
    res_int = (x2 * pow(z2, P - 2, P)) % P
    return res_int.to_bytes(32, "little")


def generate_keypair():
    """生成 WireGuard 客户端 X25519 密钥对 (base64 字符串)"""
    try:
        from cryptography.hazmat.primitives.asymmetric import x25519
        from cryptography.hazmat.primitives import serialization

        priv = x25519.X25519PrivateKey.generate()
        pub = priv.public_key()
        priv_bytes = priv.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        pub_bytes = pub.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    except Exception:
        priv_bytes = os.urandom(32)
        pub_bytes = _x25519_base(priv_bytes)

    priv_b64 = base64.b64encode(priv_bytes).decode("utf-8")
    pub_b64 = base64.b64encode(pub_bytes).decode("utf-8")
    return priv_b64, pub_b64


def register_warp_account():
    """直接调用 Cloudflare 官方 API 注册 WARP 账号并获取 WireGuard 配置"""
    priv_b64, pub_b64 = generate_keypair()
    now_iso = (
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        + "Z"
    )

    payload = {
        "key": pub_b64,
        "install_id": "",
        "fcm_token": "",
        "tos": now_iso,
        "model": "PC",
        "type": "Android",
        "locale": "en_US",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        WARP_API_URL,
        data=data,
        headers={
            "User-Agent": "okhttp/3.12.1",
            "Content-Type": "application/json; charset=UTF-8",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        res = json.loads(resp.read().decode("utf-8"))

    raw_cfg = res.get("result", res)
    peer_pub = CLOUDFLARE_PEER_PUBKEY
    peers = raw_cfg.get("config", {}).get("peers", [])
    if peers and peers[0].get("public_key"):
        peer_pub = peers[0]["public_key"]

    addresses = raw_cfg.get("config", {}).get("interface", {}).get("addresses", {})
    v4 = addresses.get("v4", "172.16.0.2")
    v6 = addresses.get("v6", "")

    account_info = {
        "id": raw_cfg.get("id", ""),
        "token": raw_cfg.get("token", ""),
        "private_key": priv_b64,
        "public_key": pub_b64,
        "peer_public_key": peer_pub,
        "ipv4": v4,
        "ipv6": v6,
        "account_type": raw_cfg.get("account", {}).get("account_type", "free"),
    }
    return account_info


def build_wireguard_conf(acc: dict, endpoint: str = f"{WARP_ENDPOINT_HOST}:{WARP_ENDPOINT_PORT}") -> str:
    """生成标准 WireGuard 客户端配置文件 (.conf)"""
    v4 = acc.get("ipv4", "172.16.0.2")
    v6 = acc.get("ipv6", "")
    addrs = []
    if v4:
        addrs.append(f"{v4}/32" if "/" not in v4 else v4)
    if v6:
        addrs.append(f"{v6}/128" if "/" not in v6 else v6)
    addr_str = ", ".join(addrs)

    peer_pub = acc.get("peer_public_key") or CLOUDFLARE_PEER_PUBKEY
    priv = acc.get("private_key", "")

    return f"""[Interface]
PrivateKey = {priv}
Address = {addr_str}
DNS = 1.1.1.1, 2606:4700:4700::1111
MTU = 1280

[Peer]
PublicKey = {peer_pub}
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = {endpoint}
PersistentKeepalive = 25
"""


def build_singbox_wireguard_json(acc: dict, server: str = WARP_ENDPOINT_HOST, port: int = WARP_ENDPOINT_PORT, tag: str = "WARP-WireGuard") -> dict:
    """生成标准 sing-box 1.10+ 的 WireGuard outbound 配置字典"""
    v4 = acc.get("ipv4", "172.16.0.2")
    v6 = acc.get("ipv6", "")
    local_addrs = []
    if v4:
        local_addrs.append(f"{v4}/32" if "/" not in v4 else v4)
    if v6:
        local_addrs.append(f"{v6}/128" if "/" not in v6 else v6)

    peer_pub = acc.get("peer_public_key") or CLOUDFLARE_PEER_PUBKEY
    priv = acc.get("private_key", "")

    return {
        "type": "wireguard",
        "tag": tag,
        "server": server,
        "server_port": port,
        "local_address": local_addrs,
        "private_key": priv,
        "peer_public_key": peer_pub,
        "reserved": [0, 0, 0],
        "mtu": 1280,
    }


def build_wireguard_links(acc: dict) -> list[str]:
    """生成单行 WireGuard 节点通用链接"""
    priv = acc.get("private_key", "")
    peer_pub = acc.get("peer_public_key") or CLOUDFLARE_PEER_PUBKEY
    v4 = acc.get("ipv4", "172.16.0.2")
    v6 = acc.get("ipv6", "")

    addrs = []
    if v4:
        addrs.append(f"{v4}/32" if "/" not in v4 else v4)
    if v6:
        addrs.append(f"{v6}/128" if "/" not in v6 else v6)
    addr_val = ",".join(addrs)

    def enc(s):
        return urllib.parse.quote(str(s), safe="")

    # 1. 官方直连域名节点
    params1 = "&".join([
        f"publickey={enc(peer_pub)}",
        f"address={enc(addr_val)}",
        "reserved=0,0,0",
        "mtu=1280",
    ])
    link1 = f"wireguard://{enc(priv)}@{WARP_ENDPOINT_HOST}:{WARP_ENDPOINT_PORT}?{params1}#{enc('WARP-WireGuard')}"

    # 2. 官方直连 IP 节点
    link2 = f"wireguard://{enc(priv)}@{WARP_ENDPOINT_IP}:{WARP_ENDPOINT_PORT}?{params1}#{enc('WARP-WireGuard-IP')}"

    return [link1, link2]


def generate_warp(acc_or_path=None, outdir: str = "dist"):
    """
    统一生成 WARP WireGuard 相关所有产物：
    - warp-wireguard.json
    - warp-wireguard.conf
    - warp-links.txt
    - warp-account.json
    """
    os.makedirs(outdir, exist_ok=True)

    if acc_or_path and isinstance(acc_or_path, str) and os.path.exists(acc_or_path):
        print(f"[WARP] 读取本地已有账户配置文件: {acc_or_path}")
        with open(acc_or_path, "r", encoding="utf-8") as f:
            acc = json.load(f)
    elif isinstance(acc_or_path, dict) and acc_or_path.get("private_key"):
        acc = acc_or_path
    else:
        print("[WARP] 正在通过 Cloudflare 官方 API 自动注册新 WireGuard 账户...")
        acc = register_warp_account()
        print(f"[WARP] 注册成功！分配内网 IPv4: {acc.get('ipv4')}, IPv6: {acc.get('ipv6')}")

    conf_content = build_wireguard_conf(acc)
    singbox_outbound = build_singbox_wireguard_json(acc)
    links = build_wireguard_links(acc)

    conf_file = os.path.join(outdir, "warp-wireguard.conf")
    json_file = os.path.join(outdir, "warp-wireguard.json")
    links_file = os.path.join(outdir, "warp-links.txt")
    acc_file = os.path.join(outdir, "warp-account.json")

    with open(conf_file, "w", encoding="utf-8") as f:
        f.write(conf_content)

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(singbox_outbound, f, indent=2, ensure_ascii=False)

    with open(links_file, "w", encoding="utf-8") as f:
        f.write("\n".join(links) + "\n")

    with open(acc_file, "w", encoding="utf-8") as f:
        json.dump(acc, f, indent=2, ensure_ascii=False)

    print("[WARP] WireGuard 产物生成完毕：")
    print(f"  - WireGuard 客户端配置: {conf_file}")
    print(f"  - sing-box 出站配置: {json_file}")
    print(f"  - 单行节点链接: {links_file} ({len(links)} 条)")
    print(f"  - 账户凭据元数据: {acc_file}")

    return {
        "conf": conf_file,
        "json": json_file,
        "links_file": links_file,
        "links": links,
        "account": acc,
    }


def main():
    cfg_file = sys.argv[1] if len(sys.argv) > 1 else None
    outdir = sys.argv[2] if len(sys.argv) > 2 else "dist"
    generate_warp(cfg_file, outdir)


if __name__ == "__main__":
    main()
