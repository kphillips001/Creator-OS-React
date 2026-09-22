"""Presentation-only copy policy; never a source of commercial price authority."""
import re

_AMOUNT = r"\d+(?:[.,]\d+)*"
_CURRENCY = r"(?:USD|EUR|GBP|CAD|AUD|NZD|JPY|CHF|INR|dollars?|euros?|pounds?|bucks?|cents?)"
_PRICE = re.compile(
    rf"(?<!\w)(?:(?:US|CA|AU|NZ)?[$€£¥₹]\s*{_AMOUNT}|"
    rf"{_CURRENCY}\s*{_AMOUNT}|{_AMOUNT}\s*(?:{_CURRENCY}\b|[$\u20ac\u00a3\u00a5\u20b9])|\d+[.,]\d{{2}}(?!\d))",
    re.IGNORECASE,
)


def telegram_offer_caption(text):
    """Remove monetary display spans while preserving non-price sales copy."""
    lines=[]
    for line in str(text or '').strip().splitlines():
        clean=_PRICE.sub('',line)
        if clean!=line:
            clean=re.sub(r'\b(?:price|cost|only|just|for)\s*[:=-]?\s*(?=[.!?]*$)', '', clean, flags=re.I)
            clean=re.sub(r'[ \t]+',' ',clean).strip(' \t:-')
            if not clean.strip('.!?'):continue
        lines.append(clean)
    return re.sub(r'\n{3,}','\n\n','\n'.join(lines)).strip() or 'Take a look when you are ready.'
