"""模拟新闻原文。"""

def simulate(tick, event_time, *, params):
    if tick % params.every_n_ticks:
        return []
    number = tick // params.every_n_ticks
    variant = number % 3
    symbols = params.known_symbols
    value = symbols[0] if variant == 0 else ", ".join((*symbols, symbols[0]))
    symbol_line = f"{params.symbols_field}: {value}\n" if variant != 2 else ""
    return [
        f"News-ID: sim-news-{tick:08d}\nPublished-At: {event_time.isoformat()}\n"
        f"Title: 模拟市场简报 {number + 1}\n{symbol_line}\n"
        'Body: 这是一条教学新闻，不代表真实消息。\n发言人表示："下一期将公布更多信息。"\n'
    ]
