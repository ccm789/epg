#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精简 epg.xml：删除大陆台，只保留港澳台；并给保留频道补全/统一 fanmingming 台标。"""
import re, json, os
from opencc import OpenCC
t2s = OpenCC('t2s'); s2t = OpenCC('s2t')

# ---------- fanmingming 台标清单 ----------
tree = json.load(open('/tmp/fm_tree.json', encoding='utf-8'))
logos = [x['path'][3:] for x in tree['tree']
         if x['path'].startswith('tv/') and x['path'].endswith('.png')]
def norm(s):
    s = t2s.convert(s); s = re.sub(r'[\s（）()·．.\-|/]', '', s); return s.lower()
lmap = {}
for l in logos:
    lmap.setdefault(norm(l[:-4]), l[:-4])

alias = {'港台电视31':'RTHK31','港台电视32':'RTHK32','港台电视33':'RTHK33','港台电视34':'RTHK34',
 '港台电视35':'RTHK35','ViuTV':'viutv','ViuTVsix':'viutv6','TVB Plus':'TVB+','翡翠台':'TVB翡翠台',
 '明珠台':'TVB明珠台','黃金翡翠台':'翡翠台','鳳凰衛視中文台':'凤凰卫视中文台','鳳凰衛視資訊台':'凤凰卫视资讯台',
 '無綫財經·資訊台':'tvbfinanceinformationchannel','民視':'民视','臺視':'台视','華視':'华视','中視':'中视',
 '公視':'公视','三立':'三立','東森':'东森','緯來':'纬来','八大':'八大','愛爾達':'爱尔达','靖天':'靖天',
 '年代':'年代','龍華':'龙华','台視新聞':'台视新闻','民視新聞':'民视新闻','華視新聞':'华视新闻'}

SUF_STRIP = re.compile(r'(台|頻道|频道|新闻|資訊|资讯|综合|综合台|体育|财经|亚洲台|台湾台|戏剧|电影|综艺|'
                       r'国际|高清|纪录|纪实|少儿|科教|戏曲|二台|一台|台[1-9])$')
def strip_suffix(n):
    for _ in range(4):
        n2 = SUF_STRIP.sub('', n)
        if n2 and n2 != n: n = n2
        else: break
    return n

def find_logo(name):
    cands = set()
    for x in [name, s2t.convert(name), t2s.convert(name)]:
        cands.add(x); cands.add(x + ' HD'); cands.add(x + ' 高清')
    for a in (alias.get(name), alias.get(t2s.convert(name)), alias.get(s2t.convert(name))):
        if a: cands.add(a)
    for x in cands:
        n = norm(x)
        if n in lmap: return lmap[n]
        n2 = norm(strip_suffix(x))
        if n2 and n2 in lmap: return lmap[n2]
    return None

BASE = 'https://gh-proxy.com/raw.githubusercontent.com/fanmingming/live/main/tv/'

# ---------- 大陆台判定 ----------
PROV = ['湖南','浙江','江苏','北京','上海','东方','安徽','广东','深圳','辽宁','山东','天津','重庆','东南',
        '甘肃','广西','贵州','河北','黑龙江','河南','湖北','江西','吉林','山西','陕西','四川','云南','福建',
        '青海','宁夏','新疆','内蒙古','西藏','海南','大连','厦门','青岛','南方','嘉佳','金鹰','卡酷','优漫',
        '哈哈','睛彩','三沙','太原','济南','沈阳','长春','哈尔滨','南京','杭州','武汉','成都','西安','广州',
        '长沙','南宁','贵阳','昆明','兰州','银川','西宁','拉萨','乌鲁木齐','呼和浩特']
SUF = re.compile(r'(卫视|体育|新闻|综艺|影视|经济|财经|纪录|纪实|少儿|科教|戏曲|电影|电视剧|生活|公共|频道|国际|购物)$')
EXTRA = ['大湾区','芒果','mangotv','五星体育','长沙政法','海峡卫视','中国环球']
def names_of(blk):
    return re.findall(r'<display-name[^>]*>([^<]*)</display-name>', blk)
def is_mainland(blk):
    for n in names_of(blk):
        s = t2s.convert(n); sl = s.lower()
        if re.search(r'(CCTV|央视|CGTN|中央电视|中国教育|ChinaGlobal|CBM幸福剧场|中国电影频道)', sl, re.I):
            return True
        for p in PROV:
            if sl.startswith(p + '卫视') or sl == p + '卫视': return True
            if sl.startswith(p) and SUF.search(sl): return True
        for kw in EXTRA:
            if kw.lower() in sl: return True
    return False

# ---------- 处理 ----------
src = open('epg.xml', encoding='utf-8', errors='ignore').read()
header = re.search(r'<tv[^>]*>', src).group(0)
chans = {}
for m in re.finditer(r'<channel id="([^"]+)">(.*?)</channel>', src, re.S):
    chans[m.group(1)] = m.group(0)

keep = {}; filled = 0; kept_mainland = []
for cid, blk in chans.items():
    if is_mainland(blk):
        kept_mainland.append(names_of(blk)[0] if names_of(blk) else cid)
        continue
    names = names_of(blk)
    logo = None
    for nm in names:
        logo = find_logo(nm)
        if logo: break
    if logo:
        newblk = re.sub(r'<icon src="[^"]*" */>', f'<icon src="{BASE}{logo}" />', blk, count=1)
        if '<icon' not in newblk:
            newblk = newblk.replace('</channel>', f'  <icon src="{BASE}{logo}" />\n</channel>')
        filled += 1
    else:
        newblk = blk
    keep[cid] = newblk

out = [header]
out.extend(keep.values())
pcnt = 0
for m in re.finditer(r'<programme\b.*?</programme>', src, re.S):
    cid = re.search(r'channel="([^"]+)"', m.group(0))
    if cid and cid.group(1) in keep:
        out.append(m.group(0)); pcnt += 1
out.append('</tv>')
open('epg.xml', 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print('总channel:', len(chans), ' 保留(港澳台):', len(keep),
      ' 删除(大陆台):', len(chans) - len(keep))
print('本次删除的大陆台样本:', kept_mainland[:30])
print('补/换台标频道:', filled)
print('保留节目:', pcnt)
print('输出大小: %.1f MB' % (os.path.getsize('epg.xml')/1048576))
