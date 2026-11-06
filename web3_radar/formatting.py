from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .models import EarnOffer, ProviderResult, RateTier


STATUS_LABELS = {
    "available": "可申购",
    "sold_out": "售罄",
    "not_started": "未开始",
}


def format_report(observed_at: datetime, results: list[ProviderResult]) -> list[str]:
    header = (
        "📡 Web3 Radar\n"
        f"{observed_at.strftime('%Y-%m-%d %H:%M')}（Asia/Shanghai）\n"
        "美元稳定币 Earn 利率快照（APR）"
    )
    chunks: list[str] = []
    for result in results:
        lines = [header, "", f"【{result.exchange}】"]
        offers = sorted(
            result.offers,
            key=lambda offer: (
                offer.asset,
                0 if offer.is_bonus else 1,
                0 if offer.product_type == "flexible" else 1,
                -offer.apr_percent,
            ),
        )
        if not offers:
            lines.append("暂无可展示产品")
        for offer in offers:
            lines.extend(_format_offer(offer))
        if result.error:
            lines.extend(("", f"⚠️ 数据提示：{_shorten(result.error, 800)}"))
        lines.extend(("", "高 APR 常有额度、地区、新用户或 VIP 限制；以申购页最终条款为准。"))
        chunks.extend(_split_message("\n".join(lines)))
    return chunks or [header + "\n\n本次没有获得任何交易所数据。"]


def _format_offer(offer: EarnOffer) -> list[str]:
    kind = "活期" if offer.product_type == "flexible" else "定期"
    duration = ""
    if offer.duration_days is not None:
        duration = f" {_number(offer.duration_days)}天"
    flags: list[str] = []
    if offer.is_bonus:
        flags.append("⚡Bonus/限定")
    flags.append(STATUS_LABELS.get(offer.status, offer.status))
    line = (
        f"• {offer.asset} {kind}{duration} {_number(offer.apr_percent)}% "
        f"[{' · '.join(flags)}]"
    )
    lines = [line]
    for tier in offer.tiers:
        lines.append(f"  └ {_format_tier(tier)}")
    details: list[str] = []
    if offer.min_amount is not None:
        details.append(f"起投 {_number(offer.min_amount)} {offer.asset}")
    if offer.max_amount is not None:
        details.append(f"个人上限 {_number(offer.max_amount)} {offer.asset}")
    if details:
        lines.append("  " + "；".join(details))
    if offer.eligibility:
        lines.append("  条件：" + _shorten(offer.eligibility, 180))
    return lines


def _format_tier(tier: RateTier) -> str:
    upper = "∞" if tier.max_amount is None else _number(tier.max_amount)
    label = f"{_number(tier.min_amount)}–{upper}: {_number(tier.apr_percent)}%"
    if tier.note:
        label += f"（{tier.note}）"
    return label


def _number(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _shorten(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


def _split_message(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines():
        addition = len(line) + (1 if current else 0)
        if current and size + addition > limit:
            chunks.append("\n".join(current))
            current = []
            size = 0
        current.append(line)
        size += len(line) + (1 if size else 0)
    if current:
        chunks.append("\n".join(current))
    return chunks
