#!/usr/bin/env python3
"""每日测活 mod_live.m3u：串行+多次重试+二次复查，剔除失效源，保持分组结构不变"""
import ssl, time, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (SmartTV) VLC/3.0"}
SRC = "mod_live.m3u"
READ_SECS = 3.0
TIMEOUT = 12

def _fetch(u, ctx=None):
    req = urllib.request.Request(u, headers=UA)
    return urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx).read()

def test_udp_once(url):
    total = 0
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=TIMEOUT)
    deadline = time.time() + READ_SECS
    while time.time() < deadline:
        chunk = r.read(65536)
        if not chunk:
            break
        total += len(chunk)
    r.close()
    return total >= 100 * 1024

def test_udp(url):
    """udpxy 裸TS：读3秒>=100KB即活。最多3次尝试，间隔4秒（udpxy连接过频会偶发拒绝）"""
    for attempt in range(3):
        try:
            if test_udp_once(url):
                return True
        except Exception:
            pass
        time.sleep(4)
    return False

def _get_media(url, ctx):
    """返回 media playlist 地址。master/media 两种都支持"""
    body = _fetch(url, ctx).decode("utf-8", "ignore")
    if "#EXTM3U" not in body:
        return None
    if "#EXT-X-STREAM-INF" in body:
        lines = body.splitlines()
        for i, l in enumerate(lines):
            if l.startswith("#EXT-X-STREAM-INF"):
                uri = lines[i + 1].strip() if i + 1 < len(lines) else None
                if uri:
                    from urllib.parse import urljoin
                    return urljoin(url, uri)
        return None
    return url

def test_hls_once(url, ctx):
    media = _get_media(url, ctx)
    if not media:
        return False
    from urllib.parse import urljoin
    mbody = _fetch(media, ctx).decode("utf-8", "ignore")
    segs = [urljoin(media, l.strip()) for l in mbody.splitlines()
            if l.strip() and not l.startswith("#")]
    if not segs:
        return False
    for seg in segs[-3:]:
        try:
            if len(_fetch(seg, ctx)) >= 30 * 1024:
                return True
        except Exception:
            continue
    return False

def test_hls(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for attempt in range(2):
        try:
            if test_hls_once(url, ctx):
                return True
        except Exception:
            pass
        time.sleep(3)
    return False

def parse(path):
    """解析 m3u：返回头部注释行列表 + [(inf行, url)]"""
    header, entries, cur = [], [], None
    for line in open(path, encoding="utf-8").read().splitlines():
        if line.startswith("#EXTM3U") or line.startswith("# 注意") or line.startswith("url-tvg="):
            header.append(line)
        elif line.startswith("# 台湾"):
            header.append(line)
        elif line.startswith("#EXTINF"):
            cur = line
        elif line.startswith("http"):
            entries.append((cur, line))
            cur = None
    return header, entries

def main():
    header, entries = parse(SRC)
    results = {}
    for i, (inf, url) in enumerate(entries):
        fn = test_udp if "/udp/" in url else test_hls
        results[url] = fn(url)
        mark = "OK  " if results[url] else "DEAD"
        print(f"[{mark}] {i+1}/{len(entries)} {url[:70]}", flush=True)
    # 二次复查：第一轮死的串口再单独验一次（网络抖动兜底）
    dead1 = [u for u, ok in results.items() if not ok]
    for u in dead1:
        fn = test_udp if "/udp/" in u else test_hls
        time.sleep(2)
        if fn(u):
            results[u] = True
            print(f"[复活] {u[:70]}", flush=True)
    # 按组重建，保留原顺序；空组跳过
    groups, order = {}, []
    for inf, url in entries:
        g = inf.split('group-title="')[1].split('"')[0]
        if g not in groups:
            groups[g] = []
            order.append(g)
        if results.get(url):
            groups[g].append((inf, url))
    out = list(header[:4])  # EXTM3U + 3行注释说明
    total = 0
    for g in order:
        items = groups[g]
        if not items:
            continue
        out.append(f'#EXTINF:-1 group-title="{g}",==== {g.split("·")[1]} ====')
        for inf, url in items:
            out.append(inf)
            out.append(url)
            total += 1
    open(SRC, "w", encoding="utf-8").write("\n".join(out) + "\n")
    dead = [u for u, ok in results.items() if not ok]
    print(f"== 测活完成：{total} 台存活，剔除 {len(dead)} 台")
    for u in dead:
        print("  剔除:", u)

if __name__ == "__main__":
    main()
