#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 Yang-1989 EPG (epg.php 代理) 生成 epg_yang.xml（全量436台带台标），
并把新马韩相关频道合并进 epg_sgmy.xml"""
import json, os, re, urllib.request, datetime, gzip

CACHE = '/tmp/epgsgmy'
os.makedirs(CACHE, exist_ok=True)
NOW = datetime.datetime(2026, 11, 5, 14, 0)

def fetch(url, timeout=300):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120',
        'Referer': 'https://epg.yang-1989.xyz/'})
    return urllib.request.urlopen(req, timeout=timeout).read()

def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

def conv(s):
    return datetime.datetime.strptime(s[:14], '%Y%m%d%H%M%S')

# 拉取（缓存）
cache = os.path.join(CACHE, 'yang.json')
if os.path.exists(cache):
    d = json.load(open(cache))
else:
    d = json.loads(fetch('https://epg.yang-1989.xyz/epg.php?url=https%3A%2F%2Fiptv.yang-1989.xyz%2Fepg.xml.gz'))
    json.dump(d, open(cache, 'w'))

chans, progs = d['channels'], d['programs']
print('source:', len(chans), 'channels,', len(progs), 'programs')

# 全量 epg_yang.xml
lines = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<tv generator-info-name="yang-epg" source-info-url="https://iptv.yang-1989.xyz">']
nlogo = 0
for c in chans:
    lines.append(f'  <channel id="{esc(c["id"])}">')
    lines.append(f'    <display-name lang="zh">{esc(c["name"])}</display-name>')
    if c.get('logo'):
        lines.append(f'    <icon src="{esc(c["logo"])}" />')
        nlogo += 1
    lines.append('  </channel>')
kept = 0
for p in progs:
    if conv(p['stop']) <= NOW:
        continue
    kept += 1
    lines.append(f'  <programme channel="{esc(p["channel"])}" start="{p["start"]}" stop="{p["stop"]}">')
    lines.append(f'    <title lang="zh">{esc(p["title"])}</title>')
    if p.get('desc'):
        lines.append(f'    <desc lang="zh">{esc(p["desc"])}</desc>')
    lines.append('  </programme>')
lines.append('</tv>')
open('epg_yang.xml', 'w', encoding='utf-8').write('\n'.join(lines))
print(f'epg_yang.xml: {len(chans)} channels, {kept} programmes, logos {nlogo}, {os.path.getsize("epg_yang.xml")//1024}KB')

# 新马韩相关频道 → epg_sgmy 补充文件
SGMY_PAT = re.compile(
    r'Channel [578U]|CNA|天映(頻道|經典)(新加坡|馬來西亞)|SPOTV|Astro (AOD|歡喜台)|八度空間|'
    r'that.s tvN|tvN$|ARIRANG|KMTV|Hub |myTV SUPER|SUPER |The Indonesia Channel|'
    r'KBS|MBC|SBS|JTBC|韩|韓|BBC World|Fox News', re.I)
sel = [c for c in chans if SGMYPAT.search(c['name'])] if (SGMYPAT := SGMY_PAT) else []
REPO_ICON = {'天映頻道新加坡': 'https://raw.githubusercontent.com/ccm789/epg/main/logos/CM.png',
             '天映頻道馬來西亞': 'https://raw.githubusercontent.com/ccm789/epg/main/logos/CM.png',
             '天映經典新加坡': 'https://raw.githubusercontent.com/ccm789/epg/main/logos/CCM.png',
             '天映經典馬來西亞': 'https://raw.githubusercontent.com/ccm789/epg/main/logos/CCM.png'}
ALIAS = {'天映頻道新加坡': ['CELESTIAL HD', 'Celestial Movies HD', '天映頻道'],
         '天映頻道馬來西亞': ['Celestial Movies (1080p)', '天映頻道'],
         '天映經典新加坡': ['天映經典', 's_天映经典'],
         '天映經典馬來西亞': ['天映經典頻道']}
sel_ids = {c['id'] for c in sel}
lines = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<tv generator-info-name="yang-epg" source-info-url="https://iptv.yang-1989.xyz">']
for c in sel:
    lines.append(f'  <channel id="{esc(c["id"])}">')
    lines.append(f'    <display-name lang="zh">{esc(c["name"])}</display-name>')
    for a in ALIAS.get(c['id'], []):
        lines.append(f'    <display-name lang="zh">{esc(a)}</display-name>')
    icon = REPO_ICON.get(c['id'])
    if icon:
        lines.append(f'    <icon src="{icon}" />')
    lines.append('  </channel>')
n = 0
for p in progs:
    if p['channel'] in sel_ids and conv(p['stop']) > NOW:
        n += 1
        lines.append(f'  <programme channel="{esc(p["channel"])}" start="{p["start"]}" stop="{p["stop"]}">')
        lines.append(f'    <title lang="zh">{esc(p["title"])}</title>')
        if p.get('desc'):
            lines.append(f'    <desc lang="zh">{esc(p["desc"])}</desc>')
        lines.append('  </programme>')
lines.append('</tv>')
open('epg_sgmy_yang.xml', 'w', encoding='utf-8').write('\n'.join(lines))
print(f'epg_sgmy_yang.xml: {len(sel)} channels, {n} programmes, {os.path.getsize("epg_sgmy_yang.xml")//1024}KB')
print('done')
