"""
Числовое форматирование в стиле операционного отчёта клиники:
разряды через пробел в русском режиме (через запятую в английском — см. set_lang()),
отрицательные значения в скобках, проценты со знаком.
"""

import pandas as pd

_LANG = "ru"


def set_lang(lang: str) -> None:
    """Переключает разделитель разрядов для всех fmt_* ниже: 'ru' — пробел, 'en' — запятая."""
    global _LANG
    _LANG = lang


def fmt_num(x, decimals: int = 0) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "n/a" if _LANG == "en" else "н/д"
    negative = x < 0
    s = f"{abs(x):,.{decimals}f}"
    if _LANG != "en":
        s = s.replace(",", " ")
    return f"({s})" if negative else s


def fmt_money(x, decimals: int = 0) -> str:
    return f"{fmt_num(x, decimals)} ₽"


def to_k(x):
    """Для значений на диаграммах — в тысячах рублей (как в операционном отчёте)."""
    if x is None:
        return None
    return x / 1000


def fmt_k(x, decimals: int = 0) -> str:
    return fmt_num(to_k(x), decimals)


def fmt_pct(x, decimals: int = 0) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "n/a" if _LANG == "en" else "н/д"
    return f"{x:+.{decimals}%}"


def fmt_pct_plain(x, decimals: int = 0) -> str:
    """Без знака +/- спереди — для абсолютных долей (конверсия, загрузка и т.п.)."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "n/a" if _LANG == "en" else "н/д"
    return f"{x:.{decimals}%}"
