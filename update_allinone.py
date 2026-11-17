#!/usr/bin/env python3
"""allinone.m3u 每日测活 v2：HLS 跟进到最后切片实测流量，剔除失效与空壳源。
配合 GitHub Actions (allinone.yml)：checkout 后运行本脚本，有变化自动 commit。"""
import re, subprocess, concurrent.futures, sys, collections, urllib.parse

FILE = 'allinone.m3u'
UA = 'okhttp/3.12'
MIN_KBPS = 15   # 低于此速度视为不可用（约 120kbps，SD 底线）

def measure(u):
    """返回 KB/s，失败返回 0"""
    try:
        if '.m3u8' in u.lower():
            r = subprocess.run(['curl','-s','-m','6','-A',UA,u],capture_output=True,text=True,timeout=8)
            body = r.stdout
            if '#EXTM3U' not in body: return 0.0
            seg = None
            for l in body.split('\n'):
                l = l.strip()
                if l and not l.startswith('#'): seg = l   # 最后一个切片 = 最新
            if not seg: return 0.0
            seg_url = seg if seg.startswith('http') else urllib.parse.urljoin(u, seg)
            r2 = subprocess.run(['curl','-s','-o','/dev/null','-m','4','-A',UA,
                                 '-w','%{size_download} %{time_total}',seg_url],
                                capture_output=True,text=True,timeout=6)
            s,tt = r2.stdout.split()
            return int(s)/max(float(tt),0.3)/1024
        else:
            r = subprocess.run(['curl','-s','-o','/dev/null','-m','4','-L','-A',UA,
                                '-w','%{size_download} %{time_total}','-r','0-1500000',u],
                               capture_output=True,text=True,timeout=6)
            s,tt = r.stdout.split()
            return int(s)/max(float(tt),0.3)/1024
    except Exception:
        return 0.0

entries, cur = [], None
for line in open(FILE, encoding='utf-8'):
    line = line.rstrip('\n')
    if line.startswith('#EXTINF'):
        cur = line
    elif line.strip() and not line.startswith('#') and cur:
        entries.append((cur, line.strip()))
        cur = None

print(f'共 {len(entries)} 条待测')
with concurrent.futures.ThreadPoolExecutor(12) as ex:
    speeds = list(ex.map(lambda e: measure(e[1]), entries))

live = [(m,u) for (m,u),s in zip(entries,speeds) if s >= MIN_KBPS]
dead = len(entries) - len(live)
cnt = collections.Counter(re.search(r'group-title="([^"]*)"',m).group(1) for m,_ in live if 'group-title' in m)
print(f'可用 {len(live)}，剔除 {dead}，剩余分布 {dict(cnt)}')

if not live:
    sys.exit('⚠️ 全部失效，保留原文件不覆盖，请人工检查')

new = '\n'.join(['#EXTM3U'] + [f'{m}\n{u}' for m,u in live]) + '\n'
old = open(FILE, encoding='utf-8').read()
if new != old:
    open(FILE,'w',encoding='utf-8').write(new)
    print('✅ 文件已更新，等待 commit')
else:
    print('✅ 无变化')
