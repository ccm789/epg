#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步 adg-cloud/astro 的马来西亚 Astro 列表，把自带的 EPG 声明
改成指向本仓库（gh-proxy 加速，国内可直连），生成 astro.m3u。"""
import urllib.request

SRC = 'https://raw.githubusercontent.com/adg-cloud/astro/refs/heads/main/astro.m3u'
EPG = 'https://gh-proxy.com/raw.githubusercontent.com/ccm789/epg/main/epg_sgmy.xml'

req = urllib.request.Request(SRC, headers={'User-Agent': 'Mozilla/5.0'})
raw = urllib.request.urlopen(req, timeout=90).read().decode('utf-8', 'ignore')

if len(raw) < 20000 or '#EXTINF' not in raw:
    raise SystemExit('源内容异常，保持旧文件不动')

lines = raw.splitlines()
body = [l for l in lines if not l.strip().startswith('#EXTM3U')]
out = '\n'.join([f'#EXTM3U url-tvg="{EPG}"'] + body) + '\n'

# 频道数骤降时也不覆盖，防止上游改坏
old = 0
try:
    old = open('astro.m3u', encoding='utf-8').read().count('#EXTINF')
except Exception:
    pass
new = out.count('#EXTINF')
if old and new < old * 0.8:
    raise SystemExit(f'频道数 {old} -> {new} 降幅过大，保持旧文件')

open('astro.m3u', 'w', encoding='utf-8').write(out)
print(f'astro.m3u 更新完成: {new} 个频道')
