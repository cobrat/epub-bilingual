from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .llm import OLLAMA_DEFAULT_BASE_URL


@dataclass(frozen=True)
class ProviderTemplate:
    id: str
    name: str
    base_url: str
    default_model: str
    models: tuple[str, ...] = ()
    api_key_required: bool = True
    input_price_per_1m: float | None = None
    output_price_per_1m: float | None = None
    price_currency: str = "USD"
    output_token_ratio: float | None = None
    recommended_batch_size: int | None = None
    recommended_concurrency: int | None = None


def provider(
    provider_id: str,
    name: str,
    base_url: str,
    default_model: str,
    models: tuple[str, ...] = (),
    **overrides: Any,
) -> ProviderTemplate:
    return ProviderTemplate(id=provider_id, name=name, base_url=base_url, default_model=default_model, models=models, **overrides)


PROVIDER_TEMPLATES: tuple[ProviderTemplate, ...] = (
    provider("openai", "OpenAI", "https://api.openai.com/v1", "gpt-4.1-mini", ("gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini")),
    provider(
        "siliconflow-cn",
        "SiliconFlow 中国站",
        "https://api.siliconflow.cn/v1",
        "Qwen/Qwen3-30B-A3B-Instruct-2507",
        ("Qwen/Qwen3-30B-A3B-Instruct-2507", "deepseek-ai/DeepSeek-V3"),
        input_price_per_1m=0.09,
        output_price_per_1m=0.30,
    ),
    provider(
        "siliconflow-global",
        "SiliconFlow Global",
        "https://api.siliconflow.com/v1",
        "Qwen/Qwen3-30B-A3B-Instruct-2507",
        ("Qwen/Qwen3-30B-A3B-Instruct-2507", "deepseek-ai/DeepSeek-V3"),
        input_price_per_1m=0.09,
        output_price_per_1m=0.30,
    ),
    provider("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat", ("deepseek-chat", "deepseek-reasoner"), recommended_batch_size=4),
    provider("dashscope", "DashScope 兼容模式", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus", ("qwen-plus", "qwen-max", "qwen-turbo")),
    provider("kimi", "Kimi / Moonshot", "https://api.moonshot.cn/v1", "kimi-k2.6", ("kimi-k2.6", "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"), recommended_batch_size=4),
    provider("gemini", "Google Gemini 兼容模式", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash", ("gemini-3.5-flash",)),
    provider("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "~openai/gpt-latest", ("~openai/gpt-latest", "~anthropic/claude-sonnet-latest", "openai/gpt-5.1")),
    provider(
        "groq",
        "Groq",
        "https://api.groq.com/openai/v1",
        "llama-3.3-70b-versatile",
        ("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b", "qwen/qwen3-32b"),
        input_price_per_1m=0.59,
        output_price_per_1m=0.79,
    ),
    provider("mistral", "Mistral AI", "https://api.mistral.ai/v1", "mistral-large-latest", ("mistral-large-latest", "mistral-small-latest")),
    provider("together", "Together AI", "https://api.together.ai/v1", "MiniMaxAI/MiniMax-M3", ("MiniMaxAI/MiniMax-M3", "Qwen/Qwen3-235B-A22B-Instruct-2507-tput", "meta-llama/Llama-3.3-70B-Instruct-Turbo")),
    provider("perplexity", "Perplexity Sonar", "https://api.perplexity.ai", "sonar-pro", ("sonar-pro", "sonar"), recommended_batch_size=2),
    provider("azure-openai", "Azure OpenAI", "https://YOUR-RESOURCE-NAME.openai.azure.com/openai/v1", "YOUR-DEPLOYMENT-NAME"),
    provider("ollama", "Ollama 本地", OLLAMA_DEFAULT_BASE_URL, "", api_key_required=False, recommended_batch_size=2),
)


def provider_template_by_id(provider_id: str | None) -> ProviderTemplate | None:
    return next((template for template in PROVIDER_TEMPLATES if template.id == provider_id), None)


def provider_id_for_base_url(base_url: str) -> str | None:
    normalized = normalize_base_url(base_url)
    for template in PROVIDER_TEMPLATES:
        if normalize_base_url(template.base_url) == normalized:
            return template.id
    parsed = urlparse(base_url)
    if parsed.port == 11434 or "ollama" in (parsed.hostname or "").lower():
        return "ollama"
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if hostname.endswith(".openai.azure.com") and path.startswith("/openai"):
        return "azure-openai"
    return None


def provider_template_for_base_url(base_url: str) -> ProviderTemplate | None:
    return provider_template_by_id(provider_id_for_base_url(base_url))


def resolve_prices(
    model: str | None,
    base_url: str,
    input_price: float | None,
    output_price: float | None,
) -> tuple[float | None, float | None]:
    if input_price is not None and output_price is not None:
        return input_price, output_price

    template = provider_template_for_base_url(base_url)
    if template is None or model not in template.models:
        return input_price, output_price

    return (
        input_price if input_price is not None else template.input_price_per_1m,
        output_price if output_price is not None else template.output_price_per_1m,
    )


def normalize_base_url(base_url: str) -> str:
    parsed = urlparse(base_url.rstrip("/"))
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port is not None else ""
    path = parsed.path.rstrip("/")
    return f"{scheme}://{hostname}{port}{path}"
