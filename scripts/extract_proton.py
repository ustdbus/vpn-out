#!/usr/bin/env python3
"""
Proton VPN 凭据与 WireGuard 节点提取器
若配置了 PROTON_USER 和 PROTON_PASS 环境变量，则自动申请 7 天证书并拉取各国家免费节点。
若未配置，则优雅跳过。
"""
import asyncio
import base64
import hashlib
import json
import os
import sys
import time
import urllib.parse

WANT = {
    "JP": "日本", "SG": "新加坡", "US": "美国", "NL": "荷兰",
    "CH": "瑞士", "CA": "加拿大", "PL": "波兰", "RO": "罗马尼亚",
    "NO": "挪威", "MX": "墨西哥"
}
PER_COUNTRY = 3


def ed25519_to_wg(raw_sk: bytes) -> str:
    h = bytearray(hashlib.sha512(raw_sk).digest()[:32])
    h[0] &= 248
    h[31] &= 127
    h[31] |= 64
    return base64.b64encode(bytes(h)).decode()


async def extract_proton_async(outdir: str = "dist", strict: bool = False):
    user = os.environ.get("PROTON_USER")
    pwd = os.environ.get("PROTON_PASS")
    if not user or not pwd:
        msg = (
            "[Proton 提示] 未检测到 PROTON_USER 或 PROTON_PASS 环境变量！\n"
            "  -> Proton 提取需要您自己的已有账号（免费账号即可）。\n"
            "  -> 请前往 GitHub 仓库: Settings -> Secrets and variables -> Actions\n"
            "  -> 新增两个 Secret: PROTON_USER 和 PROTON_PASS。"
        )
        print(msg, file=sys.stderr)
        if strict:
            raise RuntimeError("缺少 PROTON_USER 或 PROTON_PASS Secrets 配置，已中止。")
        return None

    try:
        from proton.session import Session
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives import serialization
    except ImportError as e:
        msg = f"[Proton 错误] 缺少运行依赖 ({e})，请安装: pip install git+https://github.com/ProtonVPN/python-proton-core.git cryptography"
        print(msg, file=sys.stderr)
        if strict:
            raise RuntimeError(msg)
        return None

    os.makedirs(outdir, exist_ok=True)
    print("[Proton] 正在登录 Proton 账户...")
    s = Session(appversion="linux-vpn@4.8.2", user_agent="ProtonVPN/4.8.2 (Linux; Ubuntu/24.04)")
    if not await s.async_authenticate(user, pwd):
        print("[Proton] 登录失败：账号密码错误或触发风控", file=sys.stderr)
        return None

    sk = ed25519.Ed25519PrivateKey.generate()
    pem = sk.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    raw = sk.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption()
    )

    cert = await s.async_api_request("/vpn/v1/certificate", jsondata={
        "ClientPublicKey": pem,
        "Mode": "session",
        "Duration": "10080 min",
        "DeviceName": "vpn-out",
    })
    exp = cert["ExpirationTime"]
    wg_sk = ed25519_to_wg(raw)

    lg = await s.async_api_request("/vpn/logicals")
    free = [x for x in lg.get("LogicalServers", []) if x.get("Tier") == 0]

    picked, by_cc = [], {}
    for srv in sorted(free, key=lambda x: x.get("Score", 99)):
        cc = srv["ExitCountry"]
        if cc not in WANT or by_cc.get(cc, 0) >= PER_COUNTRY:
            continue
        phys = (srv.get("Servers") or [{}])[0]
        pub = phys.get("X25519PublicKey")
        ip = phys.get("EntryIP")
        if not (pub and ip):
            continue
        by_cc[cc] = by_cc.get(cc, 0) + 1
        picked.append({
            "name": f"Proton-{WANT[cc]}{by_cc[cc]}",
            "cc": cc,
            "ip": ip,
            "port": 51820,
            "pub": pub,
        })

    links = []
    for srv in picked:
        # WireGuard 通用链接标准格式: wireguard://private_key@ip:port?publickey=pub#name
        link = f"wireguard://{urllib.parse.quote(wg_sk)}@{srv['ip']}:{srv['port']}?publickey={urllib.parse.quote(srv['pub'])}&address=10.2.0.2/32#{urllib.parse.quote(srv['name'])}"
        links.append(link)

    links_path = os.path.join(outdir, "proton-links.txt")
    if links:
        with open(links_path, "w", encoding="utf-8") as f:
            f.write("\n".join(links) + "\n")

    payload = {
        "privateKey": wg_sk,
        "expiresAt": exp,
        "servers": picked,
        "node_links": links,
        "links": links_path,
    }

    acc_path = os.path.join(outdir, "proton-account.json")
    with open(acc_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"[Proton] 成功获取 {len(picked)} 个节点，保存至 {acc_path} 与 {links_path}")
    return payload


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "dist"
    asyncio.run(extract_proton_async(outdir))


if __name__ == "__main__":
    main()
