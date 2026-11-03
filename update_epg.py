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
    vs=[name,_t2s.convert(name),_s2t.convert(name)]
    for v in list(vs):
        v2=re.sub(r'\s*[(（](免費|普|英|粵|雙語|HD)[)）]','',v)
        if v2 and v2 not in vs: vs.append(v2)
        v3=re.sub(r'\s*HD$','',v2)
        if v3 and v3 not in vs: vs.append(v3)
    for v in list(vs):
        v4=v.replace(' ','')
        if v4 and v4 not in vs: vs.append(v4)
    return [v for v in vs if v]
def _addnames(m):
    blk=m.group(0)
    dn=re.findall(r'<display-name[^>]*>([^<]*)</display-name>',blk)
    if not dn: return blk
    have=set(dn); extra=''
    for v in _variants(dn[0]):
        if v not in have:
            extra+='    <display-name lang="zh">%s</display-name>\n'%v; have.add(v)
    return blk.replace('</channel>', extra+'  </channel>') if extra else blk
merged, _n2 = re.subn(r'<channel id="\d+">.*?</channel>', _addnames, merged, flags=re.S)
print('display-name马甲补充频道数:', _n2)
open('epg.xml','w',encoding='utf-8').write(merged)
print('written', len(merged))
