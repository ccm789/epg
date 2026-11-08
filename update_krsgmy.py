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

# ---------- 韩国：从 filegear 源提取 KR 频道 ----------
KR_WHITELIST = re.compile(r'^(KBSWORLD(\(HD\))?|KBSWORLDHD|KBSW|TVN|TVNHD|TVNMOVIES|TVNHD\(MANDARIN\)|TVNHD\(MALAY\)|JTBC.*|MBN.*|OCN.*)$', re.I)
try:
    fg_path = os.path.join(CACHE, 'fg.xml')
    if not os.path.exists(fg_path):
        gz = fetch('https://epg.946985.filegear-sg.me/t.xml.gz', binary=True)
        with gzip.open(fg_path, 'wb') as f:
            f.write(gz)
    data = open(fg_path, encoding='utf-8', errors='ignore').read()
    kr_chans, kr_progs = {}, []
    for m in re.finditer(r'<channel id="([^"]+)">(.*?)</channel>', data, re.S):
        cid, body = m.group(1), m.group(2)
        names = re.findall(r'<display-name[^>]*>([^<]+)</display-name>', body)
        if names and KR_WHITELIST.match(' '.join(names)):
            kr_chans[cid] = names
    for m in re.finditer(r'<programme channel="([^"]+)" start="(\d{14}) \+0800" stop="(\d{14}) \+0800">(.*?)</programme>', data, re.S):
        if m.group(1) in kr_chans:
            st, sp, body = m.group(2), m.group(3), m.group(4)
            if datetime.datetime.strptime(sp[:14], '%Y%m%d%H%M%S') > NOW:
                kr_progs.append(f'<programme channel="{m.group(1)}" start="{st} +0800" stop="{sp} +0800">{body}</programme>')
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<tv generator-info-name="epgsgmy" source-info-url="https://epg.946985.filegear-sg.me">']
    logo_n = 0
    for cid, names in sorted(kr_chans.items(), key=lambda x: -len(x[1][0])):
        logo = find_logo(names)
        if logo:
            logo_n += 1
        lines.append(f'  <channel id="{cid}">')
        for n in names:
            lines.append(f'    <display-name lang="zh">{n}</display-name>')
        if logo:
            lines.append(f'    <icon src="{logo}" />')
        lines.append('  </channel>')
    lines += kr_progs
    lines.append('</tv>')
    with open('epg_kr.xml', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'epg_kr.xml: {len(kr_chans)} channels, {len(kr_progs)} programmes, logos {logo_n}, {os.path.getsize("epg_kr.xml")//1024}KB')
except Exception as e:
    print('KR extract fail:', e)

# ---------- 马来西亚：从 filegear 源提取直名频道（与播放列表同名，自动适配） ----------
FG_MY = {'TV1': ['TV1'], 'TV2': ['TV2'], 'TVS': ['TVS'],
         'BERITARTM': ['BERITA rtm', 'Berita RTM'],
         'BERNAMATV': ['Bernama News', 'BERNAMATV'],
         'SUKAN+': ['SUKAN rtm', 'Sukan RTM', 'SUKAN+'],
         'TVALHIJRAH': ['TV ALHIJRAH', 'Al-Hijrah'],
         'TVOKEY': ['TV OKEY', 'Okey'],
         'AWANI': ['Astro AWANI', 'AWANI']}
try:
    extra_ch, extra_prog = {}, []
    for m in re.finditer(r'<programme channel="([^"]+)" start="(\d{14}) \+0800" stop="(\d{14}) \+0800">(.*?)</programme>', data, re.S):
        if m.group(1) in FG_MY:
            st, sp, body = m.group(2), m.group(3), m.group(4)
            if datetime.datetime.strptime(sp[:14], '%Y%m%d%H%M%S') > NOW:
                extra_prog.append(f'<programme channel="{m.group(1)}" start="{st} +0800" stop="{sp} +0800">{body}</programme>')
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<tv generator-info-name="epgsgmy" source-info-url="https://epg.946985.filegear-sg.me">']
    for cid, names in FG_MY.items():
        if not any(p.split('"')[2] == cid for p in []): pass
        lines.append(f'  <channel id="{cid}">')
        for n in names:
            lines.append(f'    <display-name lang="zh">{n}</display-name>')
        lines.append('  </channel>')
    lines += extra_prog
    lines.append('</tv>')
    with open('epg_my_fg.xml', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'epg_my_fg.xml: {len(FG_MY)} channels, {len(extra_prog)} programmes, {os.path.getsize("epg_my_fg.xml")//1024}KB')
except Exception as e:
    print('FG MY extract fail:', e)

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
for extra in ('epg_kr.xml', 'epg_my_fg.xml'):
    if os.path.exists(extra):
        b = body_of(extra)
        nch += b.count('<channel id=')
        nprog += b.count('<programme')
        merged.append(b)
# ---------- Singtel CAST 官方台标源（用户提供的订阅，含新加坡/马来西亚大量官方台标） ----------
SINGTEL_M3U = 'http://38.134.40.167:9100/sub/xzpsOpfumRG6/playlist.m3u'
def _snorm(x):
    return re.sub(r'[\s\(\)\-\.]+', '', x.strip().lower())
def build_singtel_logos():
    try:
        src = fetch(SINGTEL_M3U).decode('utf-8', errors='ignore') if isinstance(fetch(SINGTEL_M3U), bytes) else fetch(SINGTEL_M3U)
    except Exception as e:
        print('singtel logo fetch fail:', e)
        return {}
    logos = {}
    for m in re.finditer(r'#EXTINF:-1[^\n]*?tvg-name="([^"]*)"[^\n]*?tvg-logo="([^"]*)"', src):
        k = _snorm(m.group(1)); v = m.group(2)
        logos[k] = v
        if k.endswith('hd'):
            logos[k[:-2]] = v
        if 'ch' in k:
            logos[k.replace('ch', 'channel', 1)] = v
        if 'channel' in k:
            logos[k.replace('channel', 'ch', 1)] = v
    print('singtel logos:', len(logos))
    return logos

def inject_icons(text, logos):
    if not logos:
        return text
    n = [0]
    def repl(m):
        cid, body = m.group(1), m.group(2)
        if '<icon' in body:
            return m.group(0)
        names = re.findall(r'<display-name[^>]*>([^<]*)</display-name>', body)
        logo = None
        for name in names:
            cands = {_snorm(name), _snorm(re.sub(r'\s*HD$', '', name, flags=re.I))}
            for c in list(cands):
                for v in (c, c + 'hd', c.replace('channel', 'ch', 1), c.replace('ch', 'channel', 1)):
                    if v in logos:
                        logo = logos[v]; break
                if logo: break
            if logo: break
        if not logo:
            return m.group(0)
        n[0] += 1
        lines = body.rstrip().splitlines()
        idx = max(i for i, l in enumerate(lines) if l.strip().startswith('<display-name'))
        lines.insert(idx + 1, f'    <icon src="{logo}" />')
        return f'<channel id="{cid}">' + '\n'.join(lines) + '\n  </channel>'
    text = re.sub(r'<channel id="([^"]+)">(.*?)</channel>', repl, text, flags=re.S)
    print('icons injected:', n[0])
    return text

# ---------- 别名：兼容播放列表里的常见叫法（TiviMate 名称匹配用） ----------
ALIAS = {
    '492816': ['CH-5', 'CH5', '5 CH-5', '新传媒5频道'],           # Channel 5
    '492894': ['CH-8', 'CH8', '8 CH-8', '新传媒8频道'],           # Channel 8
    '492864': ['CH-U', 'CHU', 'U频道'],                            # Channel U
    '492817': ['Vasantha HD'],                                     # Vasantham
    '492874': ['CNA HD', 'Channel NewsAsia'],                      # CNA
    '492898': ['Hub 如意台', 'Hub如意台', 'HUB RUYI'],             # Hub Ruyi
    '492903': ['Hub Premier 1 HD', 'HUB PREMIER 1'],               # Hub Premier 1
    '492895': ['Hub E-City HD', 'Hub E City'],                     # Hub E City HD
    '492851': ['Hub VVDrama HD', 'Hub VV Drama', 'HUB VVDRAMA'],   # Hub VV Drama HD
    '492834': ['Hub Sports 1', 'HUB SPORTS 1 HD'],
    '492827': ['Hub Sports 2', 'HUB SPORTS 2 HD'],
    '492882': ['天映頻道', '天映频道', 'Celestial Movies'],        # Celestial Movies HD
    '492899': ['天映經典', '天映经典', 'Celestial Classic Movies'],# CCM
}
def add_aliases(text):
    for cid, extras in ALIAS.items():
        pat = re.compile(r'(<channel id="%s">\s*)((?:\s*<display-name[^>]*>[^<]*</display-name>)+)' % re.escape(cid))
        m = pat.search(text)
        if not m:
            continue
        have = set(re.findall(r'<display-name[^>]*>([^<]*)</display-name>', m.group(2)))
        add = ''.join(f'<display-name lang="zh">{a}</display-name>\n    ' for a in extras if a not in have)
        if add:
            text = text[:m.end(2)] + '\n    ' + add.rstrip() + text[m.end(2):]
    return text

def merge_my_celestial(text):
    """补马来西亚版天映频道(Celestial Movies HD, epg.pw MY 源 id 1298)"""
    if 'channel id="1298"' in text:
        return text
    try:
        src = fetch('https://epg.pw/xmltv/epg_MY.xml')
    except Exception as e:
        print('马来EPG拉取失败:', e); return text
    m = re.search(r'<channel id="1298">.*?</channel>', src, re.S)
    if not m:
        print('马来EPG无1298'); return text
    progs = re.findall(r'<programme[^>]*channel="1298"[^>]*>.*?</programme>', src, re.S)
    print(f'补马来版天映: {len(progs)} 条节目')
    return text.replace('</tv>', m.group(0) + ''.join(progs) + '</tv>', 1)

if merged:
    final = ('<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="epgsgmy" source-info-url="https://epg.pw">\n'
             + '\n'.join(merged) + '\n</tv>\n')
    final = add_aliases(final)
    final = merge_my_celestial(final)
    final = inject_icons(final, build_singtel_logos())
    with open('epg_sgmy.xml', 'w', encoding='utf-8') as f:
        f.write(final)
    print(f'epg_sgmy.xml: {nch} channels, {nprog} programmes, {os.path.getsize("epg_sgmy.xml")//1024}KB')
print('done')
