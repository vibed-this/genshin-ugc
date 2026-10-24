#!/usr/bin/env python3
"""把 raw/ 下的原神 UGC 教程 content.html 转成面向 AI/agent 的 Markdown 文档库。

产出结构:
  docs/综合指南|创作课程|常见问题/<层级目录>/<NN-标题>.md   (frontmatter + 正文)
  assets/<real_id>/<uuid>.<ext>                            (图片与 .gil/.gia 附件)
  llms.txt / README.md                                     (索引)
"""
import json, os, re, html as htmllib
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, 'raw')
DOCS = os.path.join(ROOT, 'docs')
ASSETS = os.path.join(ROOT, 'assets')

SECTION_ZH = {'knowledge': '综合指南', 'course': '创作课程', 'faq': '常见问题'}
SECTION_URL = {
    'knowledge': 'https://act.mihoyo.com/ys/ugc/tutorial',
    'course': 'https://act.mihoyo.com/ys/ugc/tutorial/course',
    'faq': 'https://act.mihoyo.com/ys/ugc/tutorial/faq',
}

manifest = json.load(open(os.path.join(RAW, 'manifest.json')))
by_pid = {d['path_id']: d for d in manifest}

# ---------- catalog 层级 (带顺序) ----------
tree = {}
for s in SECTION_ZH:
    tree[s] = json.load(open(os.path.join(RAW, f'cat_{s}.json')))

used_names = set()

def sanitize(name):
    name = re.sub(r'[\\/:*?"<>|\s]+', '-', name.strip()).strip('-')
    return name[:80] or 'untitled'

# 为每个 path_id 计算输出 md 相对路径 docs/xxx
out_paths = {}   # path_id -> 相对 docs/ 的 md 路径
doc_tree_entries = []  # (path_id, section, level, order_path)

def assign(node, section, dirpath, idx_prefix):
    pid = node['path_id']
    title = node['title']
    base = sanitize(f'{title}')
    name = base
    k = 2
    full = os.path.join(*(dirpath + [name]))
    while full.lower() in used_names:
        name = f'{base}-{pid}'
        full = os.path.join(*(dirpath + [name]))
        k += 1
        if k > 5:
            name = f'{base}-{pid}-{k}'
            full = os.path.join(*(dirpath + [name]))
            break
    used_names.add(full.lower())
    out = '/'.join(dirpath + [name]) + '.md'
    out_paths[pid] = out
    doc_tree_entries.append(pid)
    for i, ch in enumerate(node.get('children', []), 1):
        assign(ch, section, dirpath + [f'{idx_prefix}{name}'], f'{i:02d}-')

for s in SECTION_ZH:
    for i, n in enumerate(tree[s], 1):
        assign(n, s, [SECTION_ZH[s]], f'{i:02d}-')

# ---------- HTML -> Markdown ----------
BLOCK_RE = re.compile(
    r'<(h[1-6]|p|blockquote|pre|table|hr|details|video|ul|ol)\b[^>]*>.*?</\1>|<hr[^>]*/?>|<br[^>]*/?>',
    re.S | re.I)

def inline(node_html):
    """块内 HTML -> 行内 markdown 文本"""
    t = node_html
    # 图片与视频: 保持原有在线链接
    t = re.sub(r'<video[^>]*src="([^"]+)"[^>]*>.*?</video>',
               lambda m: f'[视频]({m.group(1)})', t, flags=re.S)
    t = re.sub(r'<video[^>]*src="([^"]+)"[^>]*/?>',
               lambda m: f'[视频]({m.group(1)})', t)
    t = re.sub(r'<img[^>]*?src="([^"]+)"[^>]*>', r'![图片](\1)', t)
    # 链接
    def a_repl(m):
        attrs, inner = m.group(1), m.group(2)
        hm = re.search(r'href="([^"]+)"', attrs)
        href = htmllib.unescape(hm.group(1)) if hm else ''
        text = inline(inner).strip()
        if not text:
            text = href.rsplit('/', 1)[-1] or href
        if href in asset_map:
            return f'[{text}]({asset_map[href]})'  # 本地化附件(.gil/.gia)
        if href.startswith('/ys/ugc/tutorial/'):
            target = href.rstrip('/').split('/')[-1].split('?')[0]
            if target in out_paths:
                return f'[{text}]({out_paths[target]})'
            return text
        if '://' not in href:
            return text
        return f'[{text}]({href})'
    t = re.sub(r'<a([^>]*)>(.*?)</a>', a_repl, t, flags=re.S)
    t = re.sub(r'<br[^>]*/?>', '  \n', t)
    t = re.sub(r'<(strong|b)>(.*?)</\1>', r'**\2**', t, flags=re.S)
    t = re.sub(r'<(em|i)>(.*?)</\1>', r'*\2*', t, flags=re.S)
    t = re.sub(r'<(u|ins)>(.*?)</\1>', r'**\2**', t, flags=re.S)
    t = re.sub(r'<(code|tt)>(.*?)</\1>', lambda m: '`' + m.group(2).strip() + '`', t, flags=re.S)
    t = re.sub(r'<sup>(.*?)</sup>', r'^\1', t, flags=re.S)
    t = re.sub(r'<[^>]+>', '', t)  # span/div/col 等去标签
    t = htmllib.unescape(t)
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()

def table_md(tbl_html):
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl_html, re.S)
    parsed = []
    for r in rows:
        cells = re.findall(r'<(t[dh])[^>]*>(.*?)</\1>', r, re.S)
        parsed.append([inline(c[1]).replace('|', '\\|').replace('\n', ' ') for c in cells])
    if not parsed:
        return ''
    ncol = max(len(r) for r in parsed)
    for r in parsed:
        while len(r) < ncol:
            r.append('')
        r[:] = [c.replace('\n', '<br>') if len(c) > 1 else c for c in [x if x.strip() else ' ' for x in r]]
    # 用第二行做分隔行（首行若为 th 自动成为表头）
    out = ['| ' + ' | '.join(parsed[0]) + ' |',
           '| ' + ' | '.join(['---'] * ncol) + ' |']
    for r in parsed[1:]:
        out.append('| ' + ' | '.join(r) + ' |')
    return '\n'.join(out)

def convert(html_text):
    out = []
    pos = 0
    for m in BLOCK_RE.finditer(html_text):
        if m.start() > pos:
            seg = html_text[pos:m.start()]
            txt = inline(seg)
            if txt:
                out.append(txt)
        tag = m.group(1) or 'hr'
        seg = m.group(0)
        if len(tag) == 2 and tag[0] == 'h' and tag[1].isdigit():
            level = int(tag[1])
            txt = inline(re.sub(rf'^<{tag}[^>]*>|</{tag}>$', '', seg))
            if txt:
                out.append('#' * level + ' ' + txt)
        elif tag == 'p':
            txt = inline(re.sub(r'^<p[^>]*>|</p>$', '', seg))
            if txt:
                out.append(txt)
        elif tag == 'blockquote':
            inner = re.sub(r'^<blockquote[^>]*>|</blockquote>$', '', seg)
            txt = inline(inner)
            if txt:
                out.append('\n'.join('> ' + l for l in txt.split('\n')))
        elif tag == 'pre':
            inner = htmllib.unescape(re.sub(r'<[^>]+>', '', re.sub(r'^<pre[^>]*>|</pre>$', '', seg)))
            out.append('```\n' + inner.strip('\n') + '\n```')
        elif tag == 'table':
            out.append(table_md(seg))
        elif tag == 'hr':
            out.append('---')
        elif tag == 'br':
            pass  # 段间的 br 忽略
        elif tag == 'video':
            txt = inline(seg)
            if txt:
                out.append(txt)
        elif tag == 'details':
            inner = re.sub(r'^<details[^>]*>|</details>$', '', seg)
            out.append(inline(inner))
        elif tag in ('ul', 'ol'):
            items = re.findall(r'<li[^>]*>(.*?)</li>', seg, re.S)
            lines = []
            for i, it in enumerate(items, 1):
                pre = f'{i}. ' if tag == 'ol' else '- '
                lines.append(pre + inline(it).replace('\n', ' '))
            if lines:
                out.append('\n'.join(lines))
        pos = m.end()
    tail = inline(html_text[pos:])
    if tail:
        out.append(tail)
    return '\n\n'.join(x for x in out if x.strip())

# ---------- 收集资源 URL ----------
asset_map = {}   # 原始 URL -> 相对 assets 的路径
to_download = [] # (url, 本地绝对路径)

for d in manifest:
    f = os.path.join(RAW, f"{d['section']}_{d['path_id']}.html")
    h = open(f, encoding='utf-8', errors='replace').read()
    # 仅本地化存档类附件 (.gil/.gia); 图片与视频保持在线链接
    for url in set(re.findall(r'<a[^>]*?href="([^"]+\.(?:gil|gia))"', h)):
        url = htmllib.unescape(url)
        if '://' not in url:
            continue
        fname = os.path.basename(urlparse(url).path)
        if not fname:
            continue
        rel = os.path.join('assets', d['real_id'], fname)
        if url not in asset_map:
            asset_map[url] = rel
            to_download.append((url, os.path.join(ROOT, rel)))

print(f'待下载资源: {len(to_download)}')
done = 0
def dl(job):
    url, path = job
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return None
    try:
        data = urllib.request.urlopen(url, timeout=60).read()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, 'wb').write(data)
        return None
    except Exception as e:
        return (url, str(e))
with ThreadPoolExecutor(16) as ex:
    errs = [e for e in ex.map(dl, to_download) if e]
print('资源下载失败:', len(errs))
for e in errs[:10]:
    print(' ', e[0][:120], e[1])

# ---------- 写出 markdown ----------
index_lines = []  # llms.txt

for d in manifest:
    pid = d['path_id']
    f = os.path.join(RAW, f"{d['section']}_{pid}.html")
    h = open(f, encoding='utf-8', errors='replace').read()
    body = convert(h)
    out_rel = out_paths[pid]           # 相对 docs/
    out_abs = os.path.join(DOCS, out_rel)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    # 文档位于 docs/ 下 depth+1 层目录内, assets 在仓库根
    ups = '../' * (out_rel.count('/') + 1)
    body = re.sub(r'(\[[^\]]*\])\((assets/[^)]+)\)',
                  lambda m: f'{m.group(1)}({ups}{m.group(2)})', body)
    # 重写文档互链为相对路径
    def fix_doc(m):
        text, target = m.group(1), m.group(2)
        t_rel = target
        if t_rel not in out_paths.values():
            return m.group(0)
        this_dir = os.path.dirname(out_rel)
        common = os.path.relpath(os.path.join(DOCS, t_rel), os.path.join(DOCS, this_dir))
        return f'{text}({common})'
    body = re.sub(r'(\[[^\]]+\])\(([^)]+\.md)\)', fix_doc, body)
    # 附件链接在 inline 中已转为 assets/... 形式? gil 链接文本为空, 这里再补一次
    breadcrumb = ' / '.join(d['path'])
    fm = ['---',
          f'title: "{d["title"]}"',
          f'section: "{SECTION_ZH[d["section"]]}"',
          f'breadcrumb: "{breadcrumb}"',
          f'doc_id: "{pid}"',
          f'source: "{SECTION_URL[d["section"]]}/detail/{pid}"',
          f'updated_at: "{d.get("updated_at", "")}"',
          '---', '']
    open(out_abs, 'w', encoding='utf-8').write('\n'.join(fm) + body + '\n')

# ---------- llms.txt / README ----------
def write_index(nodes, section, depth, lines):
    for n in nodes:
        pid = n['path_id']
        title = n['title']
        rel = out_paths[pid]
        lines.append('  ' * depth + f'- [{title}]({rel})')
        write_index(n.get('children', []), section, depth + 1, lines)

ll = ['# 原神「千星奇域」UGC 创作教程文档库', '',
      '本库由米游社原神 UGC 官方教程站 (act.mihoyo.com/ys/ugc/tutorial) 爬取转换而来，',
      '内容为 Markdown，图片与蓝图附件已本地化。frontmatter 含 title/section/breadcrumb/doc_id/source/updated_at。',
      '']
for s, zh in SECTION_ZH.items():
    ll.append(f'## {zh}')
    write_index(tree[s], s, 0, ll)
    ll.append('')
open(os.path.join(ROOT, 'llms.txt'), 'w', encoding='utf-8').write('\n'.join(ll))

# README
readme = ['# 原神千星奇域 UGC 创作教程（AI 文档库）', '',
          '来源: https://act.mihoyo.com/ys/ugc/tutorial （米哈游官方教程站，爬取于 2026-10-24）', '',
          '- `docs/综合指南/` — 游戏内编辑器综合指南（节点、控件、脚本等，219 篇）',
          '- `docs/创作课程/` — 官方创作课程（86 篇）',
          '- `docs/常见问题/` — FAQ（12 篇）',
          '- `assets/` — 文中图片与 .gil/.gia 蓝图附件，按文档 ID 分目录',
          '- `llms.txt` — 全站文档清单（供 agent 定位文档）', '',
          '每篇文档 frontmatter: title / section / breadcrumb / doc_id / source / updated_at。',
          '文档间互链为相对路径；站内跳转已映射到对应文档。视频内容仅保留占位链接（按要求未下载）。']
open(os.path.join(ROOT, 'README.md'), 'w', encoding='utf-8').write('\n'.join(readme) + '\n')
print('完成: docs=%d' % len(manifest))
