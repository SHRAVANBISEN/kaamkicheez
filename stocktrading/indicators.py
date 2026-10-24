"""Compatibility entry points for the completed-bar intraday engine."""

from stocktrading.intraday_engine import calculate_features


def calculate_indicators(df, now=None, rules=None):
    try:
        return calculate_features(df, now=now, rules=rules)
    except (ValueError, KeyError, TypeError) as exc:
        print(f"Indicator calculation rejected: {exc}")
        return None


def calculate_all(watchlist_data):
    results = {}
    for symbol, frame in watchlist_data.items():
        indicators = calculate_indicators(frame)
        if indicators:
            results[symbol] = indicators
    return results


if __name__ == "__main__":
    from stocktrading.auth import get_access_token
    from stocktrading.data_fetcher import fetch_watchlist, init_watchlist_db

    init_watchlist_db()
    token = get_access_token()
    if token:
        for symbol, indicators in calculate_all(fetch_watchlist(token)).items():
            print(symbol, indicators)
