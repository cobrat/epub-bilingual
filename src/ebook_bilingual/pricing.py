from __future__ import annotations


KNOWN_PRICE_PER_1M = {
    "Qwen/Qwen3-30B-A3B-Instruct-2507": (0.09, 0.30),
}


def resolve_prices(
    model: str | None,
    base_url: str,
    input_price: float | None,
    output_price: float | None,
) -> tuple[float | None, float | None]:
    if input_price is not None and output_price is not None:
        return input_price, output_price
    if model in KNOWN_PRICE_PER_1M and "siliconflow" in base_url:
        known_input, known_output = KNOWN_PRICE_PER_1M[model]
        return input_price if input_price is not None else known_input, output_price if output_price is not None else known_output
    return input_price, output_price
