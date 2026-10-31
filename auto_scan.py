#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动测源机器人:扫描sources.txt所有源池,提取港澳台,实测,合并进hmt.m3u"""
import re, subprocess, concurrent.futures, sys

HMT_ID = re.compile(r'tvg-id="[^"]*\.(tw|hk|mo)(@[^"]*)?"')
KW = re.compile(r'台湾|台灣|Taiwan|香港|Hong Kong|澳门|澳門|Macau|Macao|港台|翡翠|明珠|TVB|ViuTV|RTHK|HOY|凤凰|鳳凰|中天|中視|中视|民視|民视|三立|東森|东森|台視|台视|華視|华视|TVBS|八大|緯來|纬来|公視|公视|大愛|大爱|非凡|MOMO|龍華|龙华|人间衛視|人间卫视', re.I)

def fetch(u, t=45):
    r = subprocess.run(['curl','-sL','-m',str(t),u], capture_output=True, text=True, errors='ignore')
    return r.stdout or ''

def parse(txt):
    items=[]; cur=None
    for l in txt.split('\n'):
        l=l.strip()
        if l.startswith('#EXTINF'): cur=l
        elif l and not l.startswith('#') and cur:
            items.append((cur,l)); cur=None
    return items

def is_hmt(info):
    if HMT_ID.search(info): return True
    return bool(KW.search(info))

def check(p):
    """真解码检测:用 ffprobe 读视频流,能读出 h264/hevc/mpeg2 才算活"""
    info,u=p
    try:
        r=subprocess.run(['ffprobe','-v','error','-rw_timeout','8000000',
            '-analyzeduration','4000000','-probesize','2000000',
            '-select_streams','v:0','-show_entries','stream=codec_name,width,height',
            '-of','csv=p=0',u],capture_output=True,text=True,timeout=25)
        info_out=(r.stdout or '').strip()
        ok = any(c in info_out for c in ('h264','hevc','mpeg2','h265','av1','vp9'))
        return {'info':info,'url':u,'name':info.rsplit(',',1)[-1].strip(),'ok':ok,'detail':info_out[:40]}
    except subprocess.TimeoutExpired:
        return {'info':info,'url':u,'name':info.rsplit(',',1)[-1].strip(),'ok':False,'detail':'超时'}
    except Exception as e:
        return {'info':info,'url':u,'name':info.rsplit(',',1)[-1].strip(),'ok':False,'detail':str(e)[:30]}

def region(r):
    s=(r['info']+' '+r['url']).lower()
    if re.search(r'\.mo@|macau|macao|tdm|lotus|澳门|澳門',s): return '澳门'
    if re.search(r'\.hk@|hong kong|rthk|tvb|hoy|viutv|jade|pearl|bstv|phoenix|鳳凰|美亚|mei ah|asian drama|kix|tvbs|香港',s): return '香港'
    return '台湾'

CN={'Beautiful Life TV':'人间卫视','CGNTV Chinese':'CGNTV中文台','EBC Foreign Movie':'东森洋片台','Jade':'翡翠台',
'Lotus TV':'莲花卫视','Mei Ah Movie Channel':'美亚电影台','PTS 3':'公视三台','SJTV':'世界卫视',
'Taiwan Indigenous TV':'原住民族电视台','TTV News':'台视新闻','TVBS-Asia':'TVBS Asia','TVBS Asia':'TVBS Asia',
'WXTV':'唯心电视台','唯心電視':'唯心电视台','Dali TV':'大立电视台','Discovery Asia Taiwan':'Discovery亚洲台',
'RTHK TV 31':'港台电视31','Asian Drama':'亚洲剧台','Golden Jade':'黄金翡翠台','LIVE三立':'三立新闻',
'鳳凰中文臺':'凤凰中文台','鳳凰資訊臺':'凤凰资讯台','鳳凰香港臺':'凤凰香港台','中天新闻':'中天新闻',
'TITV':'原住民族电视台','Pet Club':'宠物频道','CGN中文台':'CGNTV中文台','民视新闻':'民视新闻'}
def cnname(raw):
    for k,v in CN.items():
        if k in raw: return v
    return re.sub(r'\s*[\(\（].*?[\)\）]|\s*\[.*?\]','',raw).strip()

def main():
    # 1) 扫描源池
    pool=[]; seen=set()
    for src in [l.strip() for l in open('sources.txt',encoding='utf-8') if l.strip() and not l.startswith('#')]:
        try:
            for it in parse(fetch(src)):
                if is_hmt(it[0]) and it[1] not in seen:
                    seen.add(it[1]); pool.append(it)
        except Exception as e:
            print('skip',src,e)
    print('候选:',len(pool))
    # 2) 并发实测
    with concurrent.futures.ThreadPoolExecutor(16) as ex:
        res=list(ex.map(check,pool))
    alive=[r for r in res if r['ok']]
    print('实测可用:',len(alive))
    # 3) 读现有hmt.m3u,保留原有条目
    existing_urls=set(); head=[]
    lines=open('hmt.m3u',encoding='utf-8').read().split('\n')
    out=[l for l in lines if l.strip()]
    for l in out:
        if l.startswith('http'): existing_urls.add(l.strip())
    # 4) 追加新发现的
    added=0
    for r in alive:
        if r['url'] in existing_urls: continue
        nm=cnname(r['name']); g=region(r)
        m=re.search(r'tvg-id="([^"]+)"',r['info']); tid=m.group(1) if m else nm
        m2=re.search(r'tvg-logo="([^"]+)"',r['info']); logo=m2.group(1) if m2 else ''
        out.append(f'#EXTINF:-1 tvg-id="{tid}" tvg-name="{nm}" tvg-logo="{logo}" group-title="{g}",{nm}')
        out.append(r['url'])
        existing_urls.add(r['url']); added+=1
        print('  +新增',g,nm)
    open('hmt.m3u','w',encoding='utf-8').write('\n'.join(out)+'\n')
    total=len([l for l in out if l.startswith('#EXTINF')])
    print(f'新增{added}条,总计{total}个频道条目')

if __name__=='__main__':
    main()
