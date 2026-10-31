#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理 hmt.m3u 中已失效的频道:逐条 ffprobe 真解码,解不出的剔除。
   保护机制:单次最多删除 30% 条目,防止网络抖动误删一片。
"""
import re, subprocess, concurrent.futures, sys

M3U = 'hmt.m3u'
CODECS = ('h264', 'hevc', 'mpeg2', 'h265', 'av1', 'vp9')


def probe(url):
    """能读出视频编码返回 True"""
    try:
        r = subprocess.run([
            'ffprobe', '-v', 'error',
            '-rw_timeout', '8000000',
            '-analyzeduration', '4000000',
            '-probesize', '2000000',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name',
            '-of', 'csv=p=0', url
        ], capture_output=True, text=True, timeout=25)
        out = (r.stdout or '').strip().lower()
        return any(c in out for c in CODECS)
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def main():
    lines = [l.rstrip('\n') for l in open(M3U, encoding='utf-8') if l.strip()]
    pairs = []
    i = 0
    while i < len(lines):
        if lines[i].startswith('#EXTINF'):
            url = lines[i + 1] if i + 1 < len(lines) else ''
            pairs.append((lines[i], url))
            i += 2
        else:
            i += 1

    total = len(pairs)
    if total == 0:
        print('文件为空,退出')
        return 0
    print(f'复检 {total} 条...')

    with concurrent.futures.ThreadPoolExecutor(16) as ex:
        results = list(ex.map(lambda p: probe(p[1]), pairs))

    alive = [p for p, ok in zip(pairs, results) if ok]
    dead = [p for p, ok in zip(pairs, results) if not ok]
    print(f'存活 {len(alive)} / 失效 {len(dead)}')

    # 保护:一次删太多说明是网络问题,放弃本次清理
    if total and len(dead) / total > 0.30:
        print(f'失效比例 {len(dead)/total:.0%} 超过 30%,疑似网络异常,本次不删除')
        return 0

    if not dead:
        print('无需清理')
        return 0

    for ext, url in dead:
        name = ext.rsplit(',', 1)[-1].strip()
        print(f'  - 剔除 {name} | {url[:60]}')

    out = ['#EXTM3U']
    for ext, url in alive:
        out.append(ext)
        out.append(url)
    open(M3U, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    print(f'清理完成: {total} -> {len(alive)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
