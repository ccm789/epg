#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成韩国/新加坡/马来西亚独立 EPG：epg_kr.xml / epg_sg.xml / epg_my.xml
数据源 epg.pw/xmltv/epg_XX.xml（+0000 实为当地时间数值，改标真实时区）
清过期节目、补台标(fanmingming live 库)、只保留主流频道(按节目量)。"""
import re, os, json, gzip, urllib.request, datetime

NOW = datetime.datetime.utcnow()
CACHE = '/tmp/epgsgmy'
os.makedirs(CACHE, exist_ok=True)

def fetch(url, timeout=300, binary=False):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    data = urllib.request.urlopen(req, timeout=timeout).read()
    return data if binary else data.decode('utf-8', 'ignore')

# ---------- 台标库 ----------
logos = []  # 统一存不带 .png 的名字
try:
    d = json.loads(fetch('https://api.github.com/repos/fanmingming/live/git/trees/main'))
    logos = [x['path'][3:-4] for x in d['tree'] if x['path'].startswith('tv/') and x['path'].endswith('.png')]
except Exception as e:
    print('logo list api fail, try local cache:', e)
    for cand in (os.path.join(CACHE, 'tvlist.json'), '/tmp/epgwork/tvlist.json'):
        try:
            with open(cand) as f:
                d = json.load(f)
            if isinstance(d, dict):
                d = d.get('tree', [])
            logos = [x['name'][:-4] for x in d if x['name'].endswith('.png')]
            print('local cache ok:', cand, len(logos))
            break
        except Exception as e2:
            print('local cache fail:', cand, e2)

def norm(s):
    s = re.sub(r'[\s（）()\u3000·|｜]', '', s).lower()
    return re.sub(r'(hd|fhd|uhd|4k|高清|超高清|頻道|频道|台|channel)$', '', s)

lmap = {}
for l in logos:
    lmap.setdefault(norm(l), l)

def find_logo(names):
    for name in names:
        for x in (name, name.replace(' HD', ''), re.sub(r'\s*HD$', '', name, flags=re.I)):
            n = norm(x)
            if n in lmap:
                return 'https://gh-proxy.com/raw.githubusercontent.com/fanmingming/live/main/tv/' + lmap[n] + '.png'
    return None

# ---------- 抓源 ----------
COUNTRIES = [
    ('SG', 'epg_sg.xml', '+0800', 120),   # 新加坡 UTC+8
    ('MY', 'epg_my.xml', '+0800', 120),   # 马来西亚 UTC+8
    ('KR', 'epg_kr.xml', '+0900', 120),   # 韩国 UTC+9（源暂空则跳过）
]
KEEP = 150  # 只保留节目量前 N 的主流频道

for cc, out, tz, keep in COUNTRIES:
    try:
        raw = fetch(f'https://epg.pw/xmltv/epg_{cc}.xml')
    except Exception as e:
        print(f'{cc}: fetch fail {e}'); continue
    if raw.count('<programme') < 100:
        print(f'{cc}: no data ({raw.count("<programme")} programmes), skip'); continue

    # 频道定义
    chans = {}
    for m in re.finditer(r'<channel id="([^"]+)">(.*?)</channel>', raw, re.S):
        cid, body = m.group(1), m.group(2)
        names = re.findall(r'<display-name[^>]*>([^<]+)</display-name>', body)
        chans[cid] = names

    # 节目计数 → 主流过滤
    counts = {}
    for m in re.finditer(r'<programme channel="([^"]+)"', raw):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    keep_ids = {c for c, n in sorted(counts.items(), key=lambda x: -x[1])[:keep] if n >= 5}
    print(f'{cc}: {len(chans)} channels, keep {len(keep_ids)}')

    # 清过期 + 改时区
    kept_progs, dropped = [], 0
    for m in re.finditer(r'<programme channel="([^"]+)" start="(\d{14}) \+\d{4}" stop="(\d{14}) \+\d{4}">(.*?)</programme>', raw, re.S):
        cid, st, sp, body = m.groups()
        if cid not in keep_ids:
            continue
        if datetime.datetime.strptime(sp[:14], '%Y%m%d%H%M%S') <= NOW:
            dropped += 1
            continue
        kept_progs.append(f'<programme channel="{cid}" start="{st} {tz}" stop="{sp} {tz}">{body}</programme>')

    # 输出
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<tv generator-info-name="epgsgmy" source-info-url="https://epg.pw">']
    logo_n = 0
    for cid in sorted(keep_ids, key=lambda c: -counts[c]):
        names = chans.get(cid, ['?'])
        logo = find_logo(names)
        if logo:
            logo_n += 1
        lines.append(f'  <channel id="{cid}">')
        for n in names:
            lines.append(f'    <display-name lang="zh">{n}</display-name>')
        if logo:
            lines.append(f'    <icon src="{logo}" />')
        lines.append('  </channel>')
    lines += kept_progs
    lines.append('</tv>')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'{out}: {len(keep_ids)} channels, {len(kept_progs)} programmes (dropped expired {dropped}), logos {logo_n}, {os.path.getsize(out)//1024}KB')

# ---------- 合并为单文件 epg_sgmy.xml ----------
def body_of(path):
    x = open(path, encoding='utf-8').read()
    rest = x.split('<tv ', 1)[1].split('>', 1)[1]
    return rest.rsplit('</tv>', 1)[0].strip()

merged, nch, nprog = [], 0, 0
for cc, out, tz, keep in COUNTRIES:
    if os.path.exists(out):
        b = body_of(out)
        nch += b.count('<channel id=')
        nprog += b.count('<programme')
        merged.append(b)
if merged:
    with open('epg_sgmy.xml', 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="epgsgmy" source-info-url="https://epg.pw">\n'
                + '\n'.join(merged) + '\n</tv>\n')
    print(f'epg_sgmy.xml: {nch} channels, {nprog} programmes, {os.path.getsize("epg_sgmy.xml")//1024}KB')
print('done')
