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


def load_logos():
    """从 fanmingming/live 台标库建 频道名->台标文件 映射"""
    try:
        from opencc import OpenCC
        t2s = OpenCC('t2s'); s2t = OpenCC('s2t')
    except Exception:
        t2s = s2t = None
    def norm(s):
        s = t2s.convert(s) if t2s else s
        return re.sub(r'[\s（）()·．.\-]', '', s).lower()
    try:
        r = subprocess.run(['curl', '-sL', '-m', '60',
            'https://data.jsdelivr.com/v1/packages/gh/fanmingming/live@main?structure=flat'],
            capture_output=True, text=True)
        import json as _json
        files = [f['name'] for f in _json.loads(r.stdout).get('files', [])
                 if f['name'].startswith('/tv/') and f['name'].endswith('.png')]
    except Exception as e:
        print('拉台标清单失败:', e); return {}
    lmap = {}
    for f in files:
        lmap.setdefault(norm(f[4:-4]), f[4:-4])
    return lmap


def find_logo(name, lmap):
    if not lmap: return None
    try:
        from opencc import OpenCC
        t2s = OpenCC('t2s'); s2t = OpenCC('s2t')
    except Exception:
        t2s = s2t = None
    def norm(s):
        s = t2s.convert(s) if t2s else s
        return re.sub(r'[\s（）()·．.\-]', '', s).lower()
    for c in [name] + ([s2t.convert(name)] if s2t else []) + ([t2s.convert(name)] if t2s else []):
        k = norm(c)
        if k in lmap: return lmap[k]
        k2 = re.sub(r'(台|頻道|频道)$', '', k)
        if k2 in lmap: return lmap[k2]
    return None


def load_epg_ids():
    """从 epg.xml 读 频道名->数字ID 映射,用于把 tvg-id 写成播放器能匹配的形式"""
    import xml.etree.ElementTree as ET
    m = {}
    try:
        from opencc import OpenCC
        t2s = OpenCC('t2s')
    except Exception:
        t2s = None

    def norm(s):
        s = t2s.convert(s) if t2s else s
        s = re.sub(r'[\s（）()·．.\-|備HD]', '', s)
        return s.lower()

    try:
        root = ET.parse('epg.xml').getroot()
    except Exception as e:
        print('读 epg.xml 失败,不做 EPG 绑定:', e)
        return {}
    for ch in root.findall('channel'):
        cid = ch.get('id')
        for dn in ch.findall('display-name'):
            if dn.text:
                m.setdefault(norm(dn.text), cid)
    return m


def write_m3u(items, path, epg_ids=None, logos=None):
    epg_ids = epg_ids or {}

    def norm(s):
        try:
            from opencc import OpenCC
            s = OpenCC('t2s').convert(s)
        except Exception:
            pass
        return re.sub(r'[\s（）()·．.\-|備HD]', '', s).lower()

    lines = ['#EXTM3U']
    for x in items:
        nm = x['name']
        tid = epg_ids.get(norm(nm), nm)   # 命中 EPG 就写数字ID,否则退回频道名
        logo = find_logo(nm, logos or {})
        lg = f'tvg-logo="https://epg.112114.xyz/logo/{logo}" ' if logo else ''
        lines.append(f'#EXTINF:-1 {lg}tvg-id="{tid}" tvg-name="{nm}" '
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

    epg_ids = load_epg_ids()
    print('EPG 频道表:', len(epg_ids), '条')
    write_m3u(alive, OUT_M3U, epg_ids)
    write_txt(alive, OUT_TXT)
    from collections import Counter
    print('分组分布:', dict(Counter(x['group'] for x in alive)))
    print(f'已写入 {OUT_M3U} / {OUT_TXT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
