#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, urllib.parse, urllib.request, sys
from opencc import OpenCC
t2s = OpenCC('t2s'); s2t = OpenCC('s2t')

def fetch(url, timeout=180):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8', 'ignore')

# 1. 拉台标文件名清单
d = json_load = __import__('json').loads(fetch('https://api.github.com/repos/fanmingming/live/git/trees/main'))
logos = [x['path'][3:] for x in d['tree'] if x['path'].startswith('tv/')]

alias = {'港台电视31':'RTHK31','港台电视32':'RTHK32','港台电视33':'RTHK33','港台电视34':'RTHK34',
 '港台电视35':'RTHK35','ViuTV':'viutv','ViuTVsix':'viutv6','TVB Plus':'TVB+','翡翠台':'TVB翡翠台',
 '明珠台':'TVB明珠台','黃金翡翠台':'翡翠台','鳳凰衛視中文台':'凤凰卫视中文台','鳳凰衛視資訊台':'凤凰卫视资讯台',
 '無綫財經·資訊台':'tvbfinanceinformationchannel'}
def norm(s):
    s = t2s.convert(s); s = re.sub(r'[\s（）()\u3000·]','',s); s = re.sub(r'^(TVB|tvb)','',s)
    return s.lower()
lmap = {}
for l in logos:
    lmap.setdefault(norm(l[:-4]), l[:-4])
def find(name):
    c = [name] + ([alias[name]] if name in alias else []) + [s2t.convert(name), t2s.convert(name)]
    for x in c:
        n = norm(x)
        if n in lmap: return lmap[n]
        n2 = re.sub(r'[台頻频道]$','',n)
        if n2 and n2 in lmap: return lmap[n2]
    return None

BASE = 'https://cdn.jsdelivr.net/gh/fanmingming/live@main/tv/'
hk = fetch('https://epg.pw/xmltv/epg_HK.xml')
try:
    tw = fetch('https://epg.pw/xmltv/epg_TW.xml')
except Exception as e:
    print('TW fail:', e); tw = ''

st = [0,0]
def repl(m):
    cid, name = m.group(1), m.group(2)
    logo = find(name); st[0 if logo else 1] += 1
    icon = '    <icon src="%s%s.png" />\n' % (BASE, urllib.parse.quote(logo)) if logo else '    <icon src="" />\n'
    return '<channel id="%s">\n    <display-name lang="zh">%s</display-name>\n%s  </channel>' % (cid, name, icon)
# 保留 epg.pw 台湾段原有高清台标（不覆盖空 icon）
PAT = re.compile(r'<channel id="(\d+)">\s*<display-name lang="[^"]*">([^<]*)</display-name>\s*<icon src="" />\s*</channel>')
def body_of(src):
    i = src.find('>', src.find('<tv')) + 1
    j = src.rfind('</tv>')
    return src[i:j].strip('\n')
hk2 = PAT.sub(repl, body_of(hk))
print('HK icons:', st[0], 'miss', st[1])

merged = '<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="merged-epg">\n' \
         + hk2 + ('\n\n' + body_of(tw) if tw else '') + '\n</tv>\n'
# epg.pw 的时间数值本身是港台本地时间,只是时区标记错写成 +0000
# 只改标记为 +0800,时间数字保持不变(不能加8小时,否则偏8小时)
merged, _n = re.subn(r'(\d{14}) \+0000', r'\1 +0800', merged)
print('时区标记修正:', _n)
# 给每个频道追加 display-name 马甲(简体/繁体/去HD/去尾注/去空格),
# 这样其他源的 m3u 无论用哪种写法都能按名字匹配到 EPG
from opencc import OpenCC as _CC
_t2s, _s2t = _CC('t2s'), _CC('s2t')
def _variants(name):
    out=set(); seed={name}
    for s in list(seed):
        seed.add(_t2s.convert(s)); seed.add(_s2t.convert(s))
    for b in seed:
        b=b.strip()
        # 去尾注 (普)/[Geo-blocked]/(1080p)
        core=re.sub(r'\s*[（(][^)）]{1,10}[)）]\s*$','',b)
        core=re.sub(r'\s*\[[^\]]{1,15}\]\s*$','',core)
        group={b,core}
        for c in list(group):
            group.add(re.sub(r'\s*(HD|高清|4K|SD|FHD|UHD|1080p|720p)$','',c,flags=re.I))
        for c in group:
            c=c.strip()
            if not c: continue
            out.add(c); out.add(c.replace(' ',''))
    for v in list(out):
        for suf in ['電視台','电视台','頻道','频道','衛視','卫视']:
            if v.endswith(suf) and len(v)-len(suf)>=2:
                out.add(v[:-len(suf)])
    # HD / 高清 变体
    for n in list(out):
        if re.search(r'(HD|高清)$',n,re.I): continue
        out.add(n+' HD'); out.add(n+'HD'); out.add(n+' 高清')
    return sorted(v for v in out if v)
def _addnames(m):
    blk=m.group(0)
    dn=[x.strip() for x in re.findall(r'<display-name[^>]*>([^<]*)</display-name>',blk)]
    if not dn: return blk
    have=set(dn); allv=set()
    for d in dn: allv|=set(_variants(d))
    # 中英组合 "English (中文)" 形式,匹配 iptv-org 命名
    cn=[d for d in dn if re.search(r'[\u4e00-\u9fff]',d)]
    en=[d for d in dn if re.search(r'[A-Za-z]{2,}',d) and not re.search(r'[\u4e00-\u9fff]',d)]
    if cn and en:
        for e in en[:2]:
            for c in cn[:2]:
                allv.add(f'{e} ({c})'); allv.add(f'{e}({c})')
    extra=''.join('    <display-name lang="zh">%s</display-name>\n'%v for v in sorted(allv-have))
    return blk.replace('</channel>', extra+'  </channel>') if extra else blk
merged, _n2 = re.subn(r'<channel id="\d+">.*?</channel>', _addnames, merged, flags=re.S)
print('display-name马甲补充频道数:', _n2)

# ============ 合并第三方EPG源(时光轨车/宿命/老张) ============
# 只并入与我们频道名匹配得上的频道及其节目,外部频道id加前缀防冲突
import gzip as _gzip, subprocess as _sp
def _norm(s): return re.sub(r'[\s（）()·．.\-|]', '', _t2s.convert(s)).lower()
def _fetch_merge(url, prefix, merged, ours):
    gz = f'/tmp/{prefix}src.xml.gz'
    for u in [url, 'https://gh-proxy.com/'+url]:
        try:
            _sp.run(['curl','-sL','-m','150','-o',gz,u],timeout=160)
            if open(gz,'rb').read(2)==b'\x1f\x8b':
                xml=_gzip.open(gz,'rt',encoding='utf-8',errors='ignore').read()
                break
            xml=''
        except Exception: xml=''
    if not xml: print(prefix,'拉取失败'); return merged,0,0
    have_ids=set(re.findall(r'<channel id="([^"]+)"',merged))
    chs=[];keep=[]
    for m in re.finditer(r'<channel id="([^"]+)">.*?</channel>',xml,re.S):
        blk=m.group(0)
        names=[_norm(d) for d in re.findall(r'<display-name[^>]*>([^<]*)<',blk)]
        if any(n in ours for n in names):
            newid=prefix+'_'+re.search(r'id="([^"]+)"',blk).group(1)
            if newid in have_ids: continue
            chs.append(re.sub(r'<channel id="[^"]+">',f'<channel id="{newid}">',blk,count=1))
            keep.append(newid)
    pgs=[]
    if keep:
        for m in re.finditer(r'<programme [^>]*?channel="([^"]+)"[^>]*>.*?</programme>',xml,re.S):
            cid=m.group(1)
            for k in keep:
                if cid==k[2:] or cid==k:
                    pgs.append(re.sub(r'channel="[^"]+"',f'channel="{k}"',m.group(0),count=1))
                    break
    print(prefix, f'并入频道 {len(chs)} 节目 {len(pgs)}')
    if chs or pgs:
        merged=merged.replace('</tv>','\n'+'\n'.join(chs)+'\n'+'\n'.join(pgs)+'\n</tv>')
    return merged,len(chs),len(pgs)

# 我们全部频道名(从两条m3u收集)
import os as _os
ours=set()
for _f in ['hmt.m3u','eth.m3u']:
    if _os.path.exists(_f):
        for _l in open(_f,encoding='utf-8'):
            if _l.startswith('#EXTINF'):
                ours.add(_norm(_l.rsplit(',',1)[-1].strip()))
EXT_SOURCES=[
 ('https://raw.githubusercontent.com/sggc/SD-EPG/main/EPG/sggc-desc.xml.gz','g'),
 ('https://raw.githubusercontent.com/sumingyd/xml/main/epg.xml.gz','s'),
 ('http://epg.51zmt.top:8000/e1.xml.gz','z'),
]
_tch=_tpg=0
for _u,_p in EXT_SOURCES:
    merged,c,p=_fetch_merge(_u,_p,merged,ours)
    _tch+=c; _tpg+=p
print(f'第三方合并合计: 频道+{_tch} 节目+{_tpg}')

open('epg.xml','w',encoding='utf-8').write(merged)
print('written', len(merged))

# ============ 收口：统一格式 + 清过期 ============
from datetime import datetime as _dt, timezone as _tz, timedelta as _td
from collections import defaultdict as _dd
_src = open('epg.xml', encoding='utf-8').read()
_h = re.search(r'<tv[^>]*>', _src).group(0)
_chans, _order = {}, []
for _m in re.finditer(r'<channel id="([^"]+)">(.*?)</channel>', _src, re.S):
    _chans[_m.group(1)] = _m.group(0); _order.append(_m.group(1))
_now = _dt.now(_tz(_td(hours=8))).strftime('%Y%m%d%H%M%S')
_pg = _dd(list); _fmt_fix = 0
for _m in re.finditer(r'<programme\b([^>]*)>(.*?)</programme>', _src, re.S):
    _a, _b = _m.group(1), _m.group(2)
    _c = re.search(r'channel="([^"]+)"', _a)
    _s = re.search(r'start="(\d{14})', _a)
    _e = re.search(r'stop="(\d{14})', _a)
    if not (_c and _s and _e): continue
    if _e.group(1) <= _now: continue          # 丢过期
    if not _a.lstrip().startswith('channel'): _fmt_fix += 1
    _pg[_c.group(1)].append(
        '<programme channel="%s" start="%s +0800" stop="%s +0800">%s</programme>'
        % (_c.group(1), _s.group(1), _e.group(1), _b))
_out = [_h]
for _c in _order:
    if not _pg.get(_c): continue              # 丢无节目频道
    _out.append(_chans[_c]); _out.extend(_pg[_c])
_out.append('</tv>')
open('epg.xml', 'w', encoding='utf-8').write('\n'.join(_out) + '\n')
print('收口: 频道', sum(1 for _c in _order if _pg.get(_c)),
      '节目', sum(len(v) for v in _pg.values()), '格式修正', _fmt_fix)
