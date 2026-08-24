def apply_discount(price, percent_off):
    """Return price after applying a percent-off discount."""
    if percent_off < 0 or percent_off > 100:
        raise ValueError("percent_off must be between 0 and 100")
    return round(price * (1 - percent_off / 100), 2)
