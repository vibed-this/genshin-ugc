# 爬取与构建方法

本库由米哈游官方「千星奇域」UGC 教程站爬取转换而来，站点入口：
<https://act.mihoyo.com/ys/ugc/tutorial>（含 综合指南 / 创作课程 / FAQ 三个板块）。

## 站点结构分析

1. **前端是 Vue SPA**（`act.mihoyo.com/ys/ugc/tutorial/...`），HTML 壳为空，正文靠 JS 渲染，直接抓页面拿不到内容。
2. 分析其 JS bundle（`/ys/ugc/tutorial/static/js/index.*.js`）发现三类数据源：
   - **目录树**（静态 JSON，可直接 GET）：
     `https://act-webstatic.mihoyo.com/ugc-tutorial/{section}/cn/zh-cn/catalog.json`
     `section` ∈ `knowledge`（综合指南）/ `course`（创作课程）/ `faq`（FAQ）。
     树节点含 `path_id`、`real_id`、`title`、`updated_at`、`children`。
   - **正文 HTML**（静态托管，每篇一个文件）：
     `https://act-webstatic.mihoyo.com/ugc-tutorial/{section}/cn/zh-cn/{real_id}/content.html?v=1016&game_biz=hk4eugc_cn&lang=zh-cn`
     这是不依赖 API 的关键入口。发现方式：在浏览器内劫持 `XMLHttpRequest` 后于 SPA 内部路由跳转，捕获到应用实际请求的就是这个静态 URL。
   - **辅助索引**：同目录下 `textMap.json`（全文纯文本，用于站内搜索）、`headingsMap.json`（标题锚点），可选用。
   - `api-ugc.mihoyo.com/v1/tutorial/get_tutorial_data?path_id=...` 也存在，但静态 `content.html` 已覆盖全部需求且无鉴权/限流问题。
3. **图片与附件**与正文同目录：`.../{section}/cn/zh-cn/{real_id}/{uuid}.{png|gif|...}`；
   附件为 `.gil`（蓝图/控件）/`.gia` 文件；视频为 `.mp4`（本库未收录，仅在原位保留占位链接）。

## 复现步骤

```bash
python3 crawl.py      # 下载目录树 + manifest + 317 篇正文 HTML 到 raw/
python3 build_docs.py # 转换为 docs/ Markdown、下载 assets/、生成 llms.txt 与 README
```

- 仅需更新时重跑两个脚本即可（`crawl.py` 与 `build_docs.py` 均跳过已存在文件，增量友好）。
- 若站点 `v=` 版本参数变化，改 `crawl.py` 中的 `V`。

## 转换规则（build_docs.py）

- 按官网目录树镜像分层：`docs/综合指南|创作课程|常见问题/NN-章节/NN-标题.md`。
- 每篇 frontmatter：`title / section / breadcrumb / doc_id / source / updated_at`，方便 agent 做检索与切块时保留上下文。
- HTML → Markdown：h1–h6、段落、GFM 表格、行内样式（strong/em/u/code/tt）、blockquote、hr、图片、链接。
- 站内跳转（`/ys/ugc/tutorial[...]//detail/<id>`）全部改写为对应 Markdown 文件的相对路径；外链保留绝对 URL。
- 图片与视频不下载，保留原站在线链接（`![图片](url)` / `[视频](url)`）；仅 `.gil/.gia` 存档附件下载到 `assets/<real_id>/` 并本地化。
- 生成 `llms.txt`（全站分层清单）作为 agent 的站点级索引入口。

## 仓库内容说明

- 本仓库**只收录文本（docs/、llms.txt）与存档附件（.gil/.gia）**；图片/视频以在线链接形式写在文档里，不占用仓库体积。
- `raw/` 保留原始 HTML，便于校对转换质量。
