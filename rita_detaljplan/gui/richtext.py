"""Text som sätts in i dialogrutor som tolkar Qts rika text (HTML-delmängd) ska först kodas, så att text från Boverkets
katalog, planens namn och inställningarna inte kan ändra hur dialogrutan ser ut."""
from html import escape


def esc(value) -> str:
    return escape(str(value), quote=False)
