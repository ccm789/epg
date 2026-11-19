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
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=TIMEOUT)
    except urllib.error.HTTPError as e:
        if e.code == 503:
            return -1  # udpxy 忙（客户端槽位满/组播被占），不算死
        raise
    deadline = time.time() + READ_SECS
    while time.time() < deadline:
        chunk = r.read(65536)
        if not chunk:
            break
        total += len(chunk)
    r.close()
    return total if total >= 100 * 1024 else 0

def test_udp(url):
    """udpxy 裸TS：读3秒>=100KB即活。最多5次尝试（503=被别人占用，多重试挤位）"""
    saw_busy = False
    for attempt in range(5):
        try:
            ret = test_udp_once(url)
            if ret == -1:
                saw_busy = True
            elif ret > 0:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False if saw_busy else False

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

def probe_udp(url):
    """探针：返回 ok / busy(503被占) / dead"""
    for attempt in range(3):
        try:
            try:
                r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=TIMEOUT)
            except urllib.error.HTTPError as e:
                if e.code == 503:
                    return "busy"
                raise
            total = 0
            deadline = time.time() + 2.0
            while time.time() < deadline:
                chunk = r.read(65536)
                if not chunk:
                    break
                total += len(chunk)
            r.close()
            if total >= 50 * 1024:
                return "ok"
        except Exception:
            pass
        time.sleep(3)
    return "dead"

def main():
    header, entries = parse(SRC)
    udp_entries = [(inf, u) for inf, u in entries if "/udp/" in u]
    hls_entries = [(inf, u) for inf, u in entries if "/udp/" not in u]

    # 探针：Actions 等海外机房无法访问台湾家宽 udpxy；503=被其他用户占用(仍可达)
    state = probe_udp(udp_entries[0][1]) if udp_entries else "dead"
    udp_reachable = state in ("ok", "busy")
    print(f"[探针] udpxy 状态: {state}", flush=True)

    results = {}
    if udp_reachable:
        for i, (inf, url) in enumerate(entries):
            if "/udp/" in url:
                results[url] = test_udp(url)
            else:
                results[url] = test_hls(url)
            mark = "OK  " if results[url] else "DEAD"
            print(f"[{mark}] {i+1}/{len(entries)} {url[:70]}", flush=True)
    else:
        print("!! udpxy 不可达（海外机房探针失败），本轮跳过组播测活，仅测公网HLS源", flush=True)
        for i, (inf, url) in enumerate(hls_entries):
            results[url] = test_hls(url)
            mark = "OK  " if results[url] else "DEAD"
            print(f"[{mark}] {i+1}/{len(hls_entries)} {url[:70]}", flush=True)

    # 护栏：死条目超过30%视为测试环境异常，本轮不修改文件
    total_n = len(results)
    dead_n = sum(1 for ok in results.values() if not ok)
    if total_n and dead_n / total_n > 0.3:
        print(f"!! 死亡比例 {dead_n}/{total_n} 超过30%，疑似测试环境异常，本轮跳过清理", flush=True)
        return
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
        if results.get(url) or ("/udp/" in url and not udp_reachable):
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
