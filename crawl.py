#!/usr/bin/env python3
"""爬取原神「千星奇域」UGC 教程站 (act.mihoyo.com/ys/ugc/tutorial) 的原始数据。

产出:
  raw/cat_<section>.json   三个板块的目录树 (knowledge/course/faq)
  raw/manifest.json        全部文档清单 (含层级路径与更新时间)
  raw/<section>_<path_id>.html  每篇文档的原始正文 HTML

之后运行 build_docs.py 即可转换为 Markdown 文档库。
"""
import json, os, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, 'raw')
SECTIONS = ['knowledge', 'course', 'faq']
V = '1016'          # content.html 的版本参数 (站点当前值)
GAME_BIZ = 'hk4eugc_cn'
LANG = 'zh-cn'

os.makedirs(RAW, exist_ok=True)

for s in SECTIONS:
    url = f'https://act-webstatic.mihoyo.com/ugc-tutorial/{s}/cn/{LANG}/catalog.json'
    data = urllib.request.urlopen(url, timeout=30).read()
    open(f'{RAW}/cat_{s}.json', 'wb').write(data)

docs = []
for s in SECTIONS:
    cat = json.load(open(f'{RAW}/cat_{s}.json'))
    def walk(node, path):
        p = path + [node['title']]
        docs.append({'section': s, 'path_id': node['path_id'], 'real_id': node.get('real_id'),
                     'title': node['title'], 'path': p, 'updated_at': node.get('updated_at', '')})
        for c in node.get('children', []):
            walk(c, p)
    for n in cat:
        walk(n, [])

json.dump(docs, open(f'{RAW}/manifest.json', 'w'), ensure_ascii=False, indent=1)
print('文档总数:', len(docs))

def fetch(d):
    url = (f"https://act-webstatic.mihoyo.com/ugc-tutorial/{d['section']}/cn/{LANG}/"
           f"{d['real_id']}/content.html?v={V}&game_biz={GAME_BIZ}&lang={LANG}")
    out = f"{RAW}/{d['section']}_{d['path_id']}.html"
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return None
    try:
        open(out, 'wb').write(urllib.request.urlopen(url, timeout=30).read())
        return None
    except Exception as e:
        return (d['path_id'], str(e))

with ThreadPoolExecutor(16) as ex:
    errs = [e for e in ex.map(fetch, docs) if e]
print('失败:', len(errs))
for e in errs:
    print(' ', e)
