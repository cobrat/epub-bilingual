# EPUB Bilingual Converter

把 EPUB 转成“原文段落 + 译文段落”的双语 EPUB。默认使用 OpenAI-compatible `/chat/completions` 接口，也支持本地 Ollama。

## Quick Start

```bash
uv sync
cp .env.example .env
```

把 API Key 填进 `.env` 后，最简单的使用方式是交互向导：

```bash
uv run ebook-bilingual --interactive
```

向导首页是纯文本状态摘要：

```text
EPUB 双语转换器
状态: 可以开始, 开始转换会先 dry-run

书籍: books/tiny.epub
输出: books/tiny.bilingual.epub（自动）
模型: SiliconFlow 中国站 / Qwen/... / API Key: 已配置
选项: 布局: preserve | 批大小: 8 | 并发: 1

1. 开始
2. 电子书
3. 翻译
4. 选项
5. 界面语言 / Language: 中文
0. 退出
```

直接命令行转换：

```bash
uv run ebook-bilingual books/input.epub
```

先检查段落数、缓存和费用估算：

```bash
uv run ebook-bilingual books/input.epub --dry-run
```

不调用模型，只生成测试 EPUB：

```bash
uv run ebook-bilingual books/tiny.epub --mock
```

## Providers

`.env.example` 默认使用 SiliconFlow 中国站。交互向导内置 OpenAI、SiliconFlow、DeepSeek、DashScope、Kimi、Gemini、OpenRouter、Groq、Mistral、Together AI、Perplexity、Azure OpenAI 和 Ollama 模板。

也可以手动指定任何兼容 OpenAI Chat Completions 的服务：

```bash
uv run ebook-bilingual books/input.epub \
  --base-url "https://api.example.com/v1" \
  --model "your-model"
```

Azure OpenAI 使用自己的资源地址和部署名，例如：

```bash
uv run ebook-bilingual books/input.epub \
  --base-url "https://<resource>.openai.azure.com/openai/v1" \
  --model "<deployment-name>"
```

Ollama 默认使用 `http://localhost:11434/v1`，不需要 API Key。

## Common Options

- `--layout preserve|clean`：保留原书样式，或使用工具内置的 clean 双语排版。
- `--style-css path.css`：给 `--layout clean` 使用自定义 CSS。
- `--batch-size N`、`--concurrency N`：控制批量大小和并发数。
- `--cache path.json`：指定翻译缓存；默认写到输出文件旁边。
- `--limit N`：只翻译前 N 个片段，适合试跑。
- `--terminology path.csv`：术语表，格式为 `source,target[,note]`。
- `--fail-on-skipped`：有跳过文档时返回非零退出码。
- `--verbose`：输出 skipped 的详细异常堆栈，不打印 API Key。
- `--profile`：输出主要阶段耗时。

更多参数见：

```bash
uv run ebook-bilingual --help
```

## Development

```bash
uv run ruff check .
uv run mypy
uv run python -m unittest discover -s tests
uv build
```

仓库内置 `books/tiny.epub` 作为 smoke fixture。重建它：

```bash
uv run python scripts/create_tiny_epub.py
```
