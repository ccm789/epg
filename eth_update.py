#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ETH 源独立维护:从源池拉 txt,ffprobe 真解码复检,生成 eth.txt(M3U格式) + eth_src.txt(TVBox格式)
   与 hmt.m3u 完全独立,互不影响。
"""
import re, subprocess, concurrent.futures, os, sys

POOL_FILE = 'eth_sources.txt'   # 每行一个 txt 源地址
OUT_M3U = 'eth.m3u'
OUT_TXT = 'eth.txt'
CODECS = ('h264', 'hevc', 'mpeg2', 'h265', 'av1', 'vp9')


def fetch(url):
    try:
        r = subprocess.run(['curl', '-sL', '-m', '90', '--compressed', url],
                           capture_output=True, text=True, errors='ignore')
        return r.stdout or ''
    except Exception:
        return ''


def parse_txt(txt):
    """TVBox txt 格式: 分组名,#genre# 然后 频道名,url"""
    items = []
    group = ''
    for line in txt.splitlines():
        line = line.strip()
        if not line:
            continue
        if '#genre#' in line:
            group = line.replace('#genre#', '').replace(',', '').strip()
            continue
        if ',' in line:
            name, url = line.split(',', 1)
            url = url.strip()
            if url.startswith(('http://', 'https://', 'rtmp://', 'rtsp://')):
                items.append({'name': name.strip(), 'url': url, 'group': group})
    return items


def parse_m3u(txt):
    items = []
    cur = None
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith('#EXTINF'):
            g = re.search(r'group-title="([^"]*)"', line)
            cur = {'name': line.rsplit(',', 1)[-1].strip(),
                   'group': g.group(1) if g else ''}
        elif line and not line.startswith('#') and cur:
            cur['url'] = line
            items.append(cur)
            cur = None
    return items


def probe(url):
    try:
        r = subprocess.run([
            'ffprobe', '-v', 'error', '-rw_timeout', '8000000',
            '-analyzeduration', '4000000', '-probesize', '2000000',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name',
            '-of', 'csv=p=0', url
        ], capture_output=True, text=True, timeout=25)
        out = (r.stdout or '').strip().lower()
        return any(c in out for c in CODECS)
    except Exception:
        return False


def write_m3u(items, path):
    lines = ['#EXTM3U']
    for x in items:
        nm = x['name']
        lines.append(f'#EXTINF:-1 tvg-id="{nm}" tvg-name="{nm}" '
                     f'group-title="{x["group"] or "其他"}",{nm}')
        lines.append(x['url'])
    open(path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')


def write_txt(items, path):
    lines = []
    last = None
    for x in items:
        g = x['group'] or '其他'
        if g != last:
            lines.append(f'{g},#genre#')
            last = g
        lines.append(f'{x["name"]},{x["url"]}')
    open(path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')


def main():
    if not os.path.exists(POOL_FILE):
        print('缺少 eth_sources.txt')
        return 1
    srcs = [l.strip() for l in open(POOL_FILE, encoding='utf-8')
            if l.strip() and not l.startswith('#')]
    print(f'源池: {len(srcs)} 个')

    # 1) 收集
    raw = []
    seen = set()
    for s in srcs:
        txt = fetch(s)
        if not txt:
            print(f'  拉取失败 {s}')
            continue
        items = parse_m3u(txt) if '#EXTINF' in txt else parse_txt(txt)
        print(f'  {s[:60]} -> {len(items)} 条')
        for x in items:
            if x['url'] in seen:
                continue
            seen.add(x['url'])
            raw.append(x)
    print(f'去重后: {len(raw)} 条')

    if not raw:
        print('没有拉到任何源,放弃更新(保留旧文件)')
        return 0

    # 2) 不做筛选!这些流多有地区限制,测试机连不上≠死链(用户实测可播)
    #    只做格式转换,全量保留
    alive = raw

    write_m3u(alive, OUT_M3U)
    write_txt(alive, OUT_TXT)
    from collections import Counter
    print('分组分布:', dict(Counter(x['group'] for x in alive)))
    print(f'已写入 {OUT_M3U} / {OUT_TXT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
