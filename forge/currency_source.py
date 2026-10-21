"""The sole allowed source of real currency market data."""
from urllib.parse import parse_qs, urlsplit

from .model import require

EXCHANGE_CATEGORIES = frozenset({"Currency", "Fragments", "Abyss", "UncutGems", "LineageSupportGems",
                                "Essences", "SoulCores", "Idols", "Runes", "Ritual", "Expedition",
                                "Delirium", "Breach", "Verisium"})


def validate_currency_source(reference, league):
    url = urlsplit(reference)
    require(url.scheme == "https" and url.netloc == "poe.ninja"
            and url.path == "/poe2/api/economy/exchange/current/overview"
            and not url.fragment,
            "CURRENCY_SOURCE_REQUIRED", "Real currency data requires the poe.ninja PoE2 exchange API")
    query = parse_qs(url.query, keep_blank_values=True)
    require(set(query) == {"league", "type"} and query["league"] == [league]
            and len(query["type"]) == 1 and query["type"][0] in EXCHANGE_CATEGORIES,
            "PRICE_SCOPE_MISMATCH", "Expected exact league and a documented PoE2 exchange category")
    return query["type"][0]
