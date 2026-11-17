#!/usr/bin/env python3
"""allinone.m3u 每日测活：并发实测每个播放地址，剔除失效源后回写文件。
配合 GitHub Actions (allinone.yml) 使用：checkout 后运行本脚本，有变化则自动 commit。"""
import re, subprocess, concurrent.futures, sys

FILE = 'allinone.m3u'
UA = 'okhttp/3.12'

def alive(u):
    """取流前 20KB，200/206 且有数据 = 可用"""
    try:
        r = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-m', '8', '-L', '-A', UA,
             '-w', '%{http_code} %{size_download}', '-r', '0-20000', u],
            capture_output=True, text=True, timeout=10)
        c, s = r.stdout.split()
        return c in ('200', '206') and int(s) > 100
    except Exception:
        return False

entries, cur = [], None
for line in open(FILE, encoding='utf-8'):
    line = line.rstrip('\n')
    if line.startswith('#EXTINF'):
        cur = line
    elif line.strip() and not line.startswith('#') and cur:
        entries.append((cur, line.strip()))
        cur = None

print(f'共 {len(entries)} 条待测')
with concurrent.futures.ThreadPoolExecutor(20) as ex:
    flags = list(ex.map(lambda e: alive(e[1]), entries))

live = [e for e, ok in zip(entries, flags) if ok]
dead = len(entries) - len(live)
# 按分组统计
import collections
cnt = collections.Counter(re.search(r'group-title="([^"]*)"', m).group(1)
                          for m, _ in live if 'group-title' in m)
print(f'可用 {len(live)}，剔除 {dead}，剩余分布 {dict(cnt)}')

if not live:
    sys.exit('⚠️ 全部失效，保留原文件不覆盖，请人工检查')

new = '\n'.join(['#EXTM3U'] + [f'{m}\n{u}' for m, u in live]) + '\n'
old = open(FILE, encoding='utf-8').read()
if new != old:
    open(FILE, 'w', encoding='utf-8').write(new)
    print('✅ 文件已更新，等待 commit')
else:
    print('✅ 无变化')
