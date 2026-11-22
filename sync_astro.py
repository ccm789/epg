#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步 adg-cloud/astro 列表 → 生成两份：
   astro.m3u       全量（改写 EPG 声明指向本仓库，国内可拉）
   astro_live.m3u  只保留实测有响应的源（每天自动更新）"""
import urllib.request
import subprocess
from concurrent.futures import ThreadPoolExecutor

SRC = 'https://raw.githubusercontent.com/adg-cloud/astro/refs/heads/main/astro.m3u'
EPG = 'https://ghproxy.net/https://raw.githubusercontent.com/ccm789/epg/main/epg_sgmy.xml'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'

req = urllib.request.Request(SRC, headers={'User-Agent': UA})
raw = None
for attempt in (SRC, 'https://ghproxy.net/https://' + SRC):
    try:
        raw = urllib.request.urlopen(
            urllib.request.Request(attempt, headers={'User-Agent': UA}), timeout=60
        ).read().decode('utf-8', 'ignore')
        if len(raw) > 20000:
            break
    except Exception as e:
        print('拉取失败:', attempt, e)
        raw = None
if not raw:
    raise SystemExit('源拉取失败，保持旧文件不动')

if len(raw) < 20000 or '#EXTINF' not in raw:
    raise SystemExit('源内容异常，保持旧文件不动')

lines = raw.splitlines()
head = f'#EXTM3U url-tvg="{EPG}"'

# 解析成 (EXTINF 行, URL) 对，跳过被 ### 注释掉的条目
items = []
i = 0
while i < len(lines):
    s = lines[i].strip()
    if s.startswith('#EXTINF'):
        commented = s.startswith('###')
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith('#')):
            j += 1
        if j < len(lines):
            url = lines[j].strip()
            if '://' in url:
                items.append((s, url, commented))
            i = j + 1
            continue
    i += 1

# ---------- 全量版 ----------
full = [head] + [f'{a}\n{b}' for a, b, c in items if not c]
open('astro.m3u', 'w', encoding='utf-8').write('\n'.join(full) + '\n')
print(f'astro.m3u: {len(full) - 1} 个频道')

# ---------- 测活 ----------
def alive(url):
    if url.startswith('rtmp'):
        return False
    try:
        r = subprocess.run(
            ['curl', '-4', '-s', '-o', '/dev/null', '-L', '--max-redirs', '2',
             '-r', '0-2000', '--max-time', '8', '-A', UA,
             '-w', '%{http_code} %{size_download}', url],
            capture_output=True, text=True, timeout=20)
        p = r.stdout.split()
        return len(p) > 1 and p[0] in ('200', '206') and int(p[1]) > 0
    except Exception:
        return False

with ThreadPoolExecutor(max_workers=24) as ex:
    flags = list(ex.map(lambda x: alive(x[1]), items))

live = [f'{a}\n{b}' for (a, b, c), ok in zip(items, flags) if ok and not c]
if live:
    open('astro_live.m3u', 'w', encoding='utf-8').write('\n'.join([head] + live) + '\n')
print(f'astro_live.m3u: {len(live)} 个可用频道 / {len(items)} 个实测')
