from __future__ import annotations

from .providers import resolve_prices as resolve_provider_prices


def resolve_prices(
    model: str | None,
    base_url: str,
    input_price: float | None,
    output_price: float | None,
) -> tuple[float | None, float | None]:
    return resolve_provider_prices(model, base_url, input_price, output_price)
