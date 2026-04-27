# EPUB Bilingual Converter

把一个 EPUB 电子书转换成“原文段落 + 译文段落”的中英双语对照 EPUB。工具会读取 EPUB 的 spine XHTML 文档，抽取段落和标题文本，调用 OpenAI-compatible `/chat/completions` 接口批量翻译，并把译文插回原段落下方。

## 使用

先用 uv 创建并同步环境：

```bash
uv sync
```

复制本地配置文件，并把你的硅基流动 API Key 填到 `.env`：

```bash
cp .env.example .env
```

默认配置使用硅基流动国内域名 `https://api.siliconflow.cn/v1`。如果你的 key 来自国际站，把 `.env` 里的 `LLM_BASE_URL` 改成 `https://api.siliconflow.com/v1`。

```bash
uv run ebook-bilingual books/input.epub \
  --source-lang English \
  --target-lang "Simplified Chinese" \
  --terminology examples/terminology.example.csv \
  --work-dir "books/input.run" \
  --layout clean \
  --style-css styles/eink-10.3.css \
  --concurrency 2
```

也可以接任何兼容 OpenAI Chat Completions 的服务：

```bash
uv run ebook-bilingual books/book.epub \
  --base-url "https://api.example.com/v1" \
  --model "your-model" \
  --target-lang "Simplified Chinese"
```

## 常用参数

- 未指定输出文件时：自动输出到输入文件同目录，命名为 `<原名>.bilingual.epub`。
- `--work-dir path`：为本次转换创建独立目录。输入 EPUB、术语表和样式 CSS 会复制进去，默认输出 EPUB 和 cache 也会写到这个目录。
- `--layout preserve`：默认模式，在原 EPUB 的 XHTML 里插入译文，尽量保留原书样式。
- `--layout clean`：保留正文内容、图片、代码块和表格，但移除原书 CSS/行内样式，改用工具控制的样式，更适合墨水屏阅读。
- `--style-css path.css`：给 `--layout clean` 使用自定义 CSS。示例样式见 `styles/eink-10.3.css`。
- `--dry-run`：只分析 EPUB，输出段落数、估算 token 和费用，不调用大模型。
- `--concurrency 2`：并发翻译 batch 数。长书可从 2 或 3 开始，过高可能触发限速。
- `--batch-size 8`：每次请求翻译的段落数，太大可能触发上下文或响应格式问题。
- `--cache path.json`：翻译缓存，默认写到 `<output>.translation-cache.json`，中断后重跑不会重复翻译已缓存段落。
- `--limit N`：只翻译前 N 个段落，适合先检查排版。
- `--mock`：不调用大模型，插入占位译文，用来测试 EPUB 结构。
- `--min-chars N`：跳过过短文本。
- `--terminology path.csv`：读取术语表，格式为 `source,target[,note]`，翻译提示词会要求模型按术语表统一译名。
- `.env`：本地 API Key 和默认模型配置文件，不会被 git 提交；`.env.example` 是可提交模板。

## 目录结构

```text
books/                 # 本地 EPUB 和每本书的运行目录；除 tiny.epub 外不提交
examples/              # 可复用的术语表示例配置
scripts/               # 本地辅助脚本
src/ebook_bilingual/   # CLI、EPUB 处理、HTML 处理、LLM 客户端等源码
styles/                # 可复用或自定义的 EPUB 阅读 CSS
tests/                 # 单元测试
```

## 本地结构测试

```bash
uv run python -m unittest discover -s tests
```

仓库根目录有 `books/` 文件夹，可以把自己的 EPUB 放在这里。仓库里也包含一个最小 EPUB 样例：`books/tiny.epub`。可以用 mock 模式生成双语测试书，不会调用大模型：

```bash
uv run ebook-bilingual books/tiny.epub --mock
```

如果 `.env` 已填好 API Key，也可以用真实模型只翻译前 2 个片段：

```bash
uv run ebook-bilingual books/tiny.epub --limit 2 --batch-size 1
```

长书翻译前建议先 dry-run：

```bash
uv run ebook-bilingual books/tiny.epub --dry-run
```

如果需要重建样例 EPUB：

```bash
uv run python scripts/create_tiny_epub.py
```

## 说明

- `--layout preserve` 只修改 spine 中的 XHTML/HTML 文档，图片、CSS、字体、目录等资源会原样复制。
- `--layout clean` 会保留正文、图片、代码块和表格，移除原书 CSS/行内样式并注入自定义 CSS。
- 译文以 `<p class="bilingual-translation">...</p>` 插入原文段落后方，并在文档 `<head>` 注入少量 CSS。
- EPUB 内部 XHTML 如果不是有效 XML，会被跳过并在命令输出里列出。
- Project Gutenberg 的头尾版权样板和常见站点说明会在抽取翻译段落时跳过，避免 `--limit` 先消耗在非正文内容上。
- 输出 EPUB 会为 manifest 中的 XHTML/HTML 文件补 `<!DOCTYPE html>`，便于 Sigil 这类编辑器打开。
