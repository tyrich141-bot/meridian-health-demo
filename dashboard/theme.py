"""
Единый визуальный язык дашборда клиники: палитра, шаблон графиков plotly,
глобальный CSS и небольшие хелперы разметки. ТОЛЬКО для тестовой страницы
_style_preview.py — в боевой app.py не подключается, пока не согласовано.

Ничего из бизнес-логики/расчётов здесь нет — только внешний вид.
"""
from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st


# ─────────────────────────────── Палитра ───────────────────────────────
# Нейтральная сине-графитовая гамма — не привязана к чужому бренду, подобрана
# отдельно для портфолио-версии (см. references/color-formula.md).

# Основной тон (глубокий сланцево-синий графит)
BRAND          = "#33566F"   # основной сине-графитовый
BRAND_DEEP     = "#21374A"   # темнее — крупные заголовки/акценты
SAGE           = "#6E8A97"   # приглушённый серо-голубой — вторичные ряды
MIST           = "#B9C7CE"   # светлый серо-голубой — фон/третичные ряды

# Акценты
PINK           = "#C98188"   # пыльная роза — «план не выполнен», внимание
PURPLE         = "#83699E"   # приглушённый сливовый — вторая категория (напр. косметология)
PURPLE_VIVID   = "#7C5CA8"   # более яркий сливовый (справочно, в графиках не используем)
ESPRESSO       = "#A98B6E"   # тёплый песочно-коричневый (запасной акцент)
STEEL          = "#5E8583"   # приглушённый тёмно-бирюзовый — доп. категория
CLAY           = "#BC7C56"   # тёплая терракота — негатив/«не выполнен»

# Подпись для карточек. GREEN_VALUE = BRAND_DEEP (тот же тёмный тон, что у
# заголовков секций) — раньше был отдельным чуть более светлым оттенком,
# из-за чего "Выручка" (label) и заголовок секции визуально не совпадали.
GREEN_LABEL    = "#3F6B85"
GREEN_VALUE    = BRAND_DEEP

# Серо-голубой ряд — нейтральные ряды на графиках (лучше «мешаются» с основным тоном)
NEUTRAL_SAGE = ["#E4E9EC", "#C3CBCE", "#93A0A6", "#748893", "#546069", "#38434A"]

# Тёплые «чернила» для текста
INK_MUTED      = "#6E6A63"   # приглушённый — подписи, оси, подзаголовки
INK_SOFT       = "#9A938A"   # мягкий — пояснения/капшены

# ── Нейтральная база. Тёплый кремовый (текущий дашборд, config.toml #FBF6F0).
NEUTRAL_BASE = "warm"
_WARM = dict(BG="#FBF6F0", SURFACE="#FFFFFF", SURFACE_ALT="#F3ECE1",
             BORDER="#E7DBC9", GRID="#EADFCD", TEXT="#33322F", TEXT_MUTED="#6E6A63")
_COOL = dict(BG="#F7F8FA", SURFACE="#FFFFFF", SURFACE_ALT="#F2F4F7",
             BORDER="#D8D9DC", GRID="#E7E9EE", TEXT="#1E1E1E", TEXT_MUTED="#7D7C7F")
_BASE = _COOL if NEUTRAL_BASE == "cool" else _WARM

CREAM          = _BASE["BG"]
SURFACE        = _BASE["SURFACE"]
SURFACE_ALT    = _BASE["SURFACE_ALT"]
BORDER         = _BASE["BORDER"]
GRID           = _BASE["GRID"]

TEXT           = _BASE["TEXT"]
TEXT_MUTED     = _BASE["TEXT_MUTED"]
TEXT_ON_BRAND  = "#FFFFFF"

# Семантика значений. Негатив/«план не выполнен» — розовый (не терракота):
# терракота (CLAY) читалась слишком «тревожно», розовый мягче и уже был задуман
# для этой роли изначально. NEGATIVE — для заливок/линий/колец (пастельный
# читается на белом/прозрачном); NEGATIVE_DEEP — для текста поверх светлого
# розового фона, где самому PINK не хватает контраста.
POSITIVE       = BRAND
NEGATIVE       = PINK
NEGATIVE_DEEP  = "#7A3F46"
NEUTRAL        = MIST

# Категориальная последовательность: 3 акцента (сине-графитовый/розовый/сливовый),
# дальше — серо-голубые нейтрали (лучше «мешаются» с основным тоном).
SEQUENCE = [BRAND, PINK, PURPLE, SAGE, "#93A0A6", "#C3CBCE", "#546069"]

# Фиксированные цвета по специальностям (удержание/отток) — косметология фиолетовым.
SPEC_COLORS = {"Стоматология": BRAND, "Косметология": PURPLE}

DATA_LABEL_SIZE = 15
FONT_FAMILY = ('"Inter", "Segoe UI", -apple-system, BlinkMacSystemFont, '
               '"Helvetica Neue", Arial, sans-serif')


# ────────────────────────── Шаблон графиков ──────────────────────────
def _register_template() -> None:
    tpl = pio.templates["plotly_white"]
    tpl.layout.update(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT, size=13, family=FONT_FAMILY),
        # Заголовок сверху (стандартная позиция), легенда — ПОД графиком, а не
        # над ним: раньше обе делили узкую полосу над plot-областью и наезжали
        # друг на друга при длинных легендах. Разнесение по разным краям
        # снимает коллизию при любой высоте графика.
        title=dict(
            font=dict(color=BRAND_DEEP, size=16, family=FONT_FAMILY),
            x=0.01, xanchor="left", y=1, yanchor="bottom", pad=dict(b=14),
        ),
        colorway=SEQUENCE,
        separators=", ",
        margin=dict(t=54, r=24, b=68, l=56),
        legend=dict(
            font=dict(color=TEXT_MUTED, size=12), bgcolor="rgba(0,0,0,0)",
            orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5,
        ),
        hoverlabel=dict(
            bgcolor=SURFACE, bordercolor=BORDER,
            font=dict(color=TEXT, size=12, family=FONT_FAMILY),
        ),
        # tickformat=",.0f" — НЕ на xaxis: большинство X здесь — категории или
        # месяцы-строки ("2026-01"), и числовой tickformat заставляет plotly
        # трактовать их как даты/числа, ломая подписи ("_,0f" вместо "янв 2026").
        # Разряды тысяч нужны только на Y (реальные числовые величины).
        xaxis=dict(
            showgrid=False, zeroline=False, linecolor=BORDER, tickcolor=BORDER,
            title=dict(font=dict(color=TEXT_MUTED, size=12)),
            tickfont=dict(color=TEXT_MUTED, size=12),
        ),
        yaxis=dict(
            showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False,
            linecolor="rgba(0,0,0,0)", tickcolor=BORDER,
            title=dict(font=dict(color=TEXT_MUTED, size=12)),
            tickfont=dict(color=TEXT_MUTED, size=12), tickformat=",.0f",
        ),
    )
    label = dict(color=TEXT, size=DATA_LABEL_SIZE, family=FONT_FAMILY)
    tpl.data.bar = [go.Bar(textfont=label)]
    tpl.data.waterfall = [go.Waterfall(textfont=label)]
    tpl.data.pie = [go.Pie(textfont=label)]
    # shape="spline" — скруглённые плавные линии вместо острых углов на ВСЕХ
    # line-графиках дашборда (задаётся один раз в шаблоне, а не в каждой фигуре).
    tpl.data.scatter = [go.Scatter(textfont=label, line=dict(shape="spline", smoothing=1.3))]
    tpl.data.funnel = [go.Funnel(textfont=dict(color=TEXT_ON_BRAND, size=DATA_LABEL_SIZE, family=FONT_FAMILY))]

    pio.templates["clinic"] = tpl
    pio.templates.default = "clinic"
    px.defaults.color_discrete_sequence = SEQUENCE
    px.defaults.template = "clinic"


def set_number_lang(lang: str) -> None:
    """Разделитель разрядов в шаблоне графиков (влияет на все tickformat/text_auto):
    'ru' — пробел тысяч + запятая дробной части, 'en' — запятая тысяч + точка (стандарт plotly)."""
    pio.templates["clinic"].layout.separators = ", " if lang == "ru" else ".,"


def dual_axis(fig: go.Figure, left_title: str = "", right_title: str = "") -> go.Figure:
    """Единая настройка второй (правой) оси: без своей сетки, мягкие подписи."""
    fig.update_layout(
        yaxis=dict(title=left_title),
        yaxis2=dict(
            title=dict(text=right_title, font=dict(color=TEXT_MUTED, size=12)),
            overlaying="y", side="right", showgrid=False, zeroline=False,
            tickfont=dict(color=TEXT_MUTED, size=12), linecolor="rgba(0,0,0,0)",
        ),
    )
    return fig


# ─────────────────────────────── CSS ───────────────────────────────
def _css() -> str:
    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {{ font-family: {FONT_FAMILY}; }}
    .stApp {{ background: {CREAM}; }}
    .block-container {{ padding-top: 2.2rem; max-width: 1360px; }}

    .stMarkdown p, .stMarkdown li, .stMarkdown span, .stMarkdown div {{ color: {TEXT}; }}
    /* Жирные/курсивные "вывод"-строки под заголовками графиков (напр. "74%
       записей доходят...", авто-тезисы курсивом типа "_С 2025-09 по..._") —
       приглушённый тёмно-серый вместо почти-чёрного TEXT, чтобы не читались
       как чужеродный чёрный текст на фоне мягкой палитры. */
    .stMarkdown strong, .stMarkdown em {{ color: {INK_MUTED} !important; }}

    /* Виджеты Streamlit (радио/селект/подписи) сами задают Source Sans на своих
       обёртках, ломая наследование шрифта — форсируем Inter везде в приложении. */
    [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] span,
    [data-testid="stRadio"] label, [data-testid="stRadio"] p,
    [data-testid="stSelectbox"] *, [data-testid="stCaptionContainer"] p {{
        font-family: {FONT_FAMILY} !important;
    }}
    [data-testid="stWidgetLabel"] p {{
        color: {TEXT_MUTED} !important; font-size: 0.86rem !important; font-weight: 600 !important;
    }}

    h1, h2, h3, h4,
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4,
    .stMarkdown h1 span, .stMarkdown h2 span, .stMarkdown h3 span {{
        color: {BRAND_DEEP} !important; font-weight: 700; letter-spacing: -0.01em;
    }}

    .ds-section {{
        margin: 0.4rem 0 0.9rem; padding-left: 0.7rem;
        border-left: 4px solid {BRAND}; line-height: 1.25;
    }}
    .ds-section .ds-title {{ font-size: 1.48rem !important; font-weight: 700; color: {BRAND_DEEP} !important; }}
    .ds-section .ds-subtitle {{ font-size: 0.9rem !important; color: {TEXT_MUTED} !important; margin-top: 0.15rem; font-weight: 400 !important; }}

    /* !important — иначе общее ".stMarkdown p {{ color: TEXT }}" перебивает
       приглушённый серый обратно на тёмный/почти чёрный. */
    .ds-caption {{ font-size: 0.83rem !important; color: {INK_SOFT} !important; font-style: italic; line-height: 1.4; }}

    /* Карточки — контур без заливки: прозрачный фон, только тонкая рамка, без тени */
    [data-testid="stMetric"] {{
        background: transparent; border: 1px solid {BORDER}; border-radius: 16px;
        padding: 1rem 1.15rem 0.9rem; box-shadow: none;
        transition: border-color .18s ease;
    }}
    [data-testid="stMetric"]:hover {{ border-color: {SAGE}; }}
    [data-testid="stMetricLabel"] {{ color: {GREEN_LABEL} !important; }}
    [data-testid="stMetricLabel"] p {{
        color: {GREEN_LABEL} !important; font-weight: 600; font-size: 0.82rem !important;
        text-transform: uppercase; letter-spacing: 0.03em;
    }}
    [data-testid="stMetricValue"] {{ color: {BRAND_DEEP} !important; font-weight: 700; font-size: 1.75rem; }}

    /* Вкладки — ещё легче: без фоновой капсулы и без рамки вокруг всей группы,
       только тонкая нижняя линия-подложка и лёгкая заливка активной вкладки. */
    [role="tablist"] {{
        gap: 0.1rem; background: transparent; padding: 0 0 0.35rem;
        border: none !important;
        border-bottom: 1px solid {BORDER} !important;
    }}
    [data-testid="stTab"] {{
        border-radius: 8px; padding: 0.3rem 0.75rem; color: {TEXT_MUTED} !important;
        font-weight: 600; font-size: 0.86rem; border-bottom: none !important;
    }}
    [data-testid="stTab"] * {{ color: {TEXT_MUTED} !important; }}
    [data-testid="stTab"]:hover {{ background: rgba(51,86,111,0.08); }}
    [data-testid="stTab"][aria-selected="true"] {{ background: {BRAND}; }}
    [data-testid="stTab"][aria-selected="true"] * {{ color: {TEXT_ON_BRAND} !important; }}
    [role="tablist"] [data-baseweb="tab-highlight"],
    [role="tablist"]::after {{ background: transparent !important; height: 0 !important; }}

    [data-baseweb="tag"] {{ background-color: {BRAND} !important; border-radius: 7px; }}
    [data-baseweb="tag"] span {{ color: {TEXT_ON_BRAND} !important; }}

    hr {{ border-color: {BORDER} !important; margin: 1.1rem 0; }}

    .ds-period-label {{
        font-family: {FONT_FAMILY} !important; font-weight: 700 !important;
        font-size: 1.3rem !important; color: {BRAND_DEEP} !important; margin: 0.4rem 0 0.2rem;
    }}

    .stButton button, .stDownloadButton button {{
        border-radius: 24px; border: 1px solid {BRAND}; color: {BRAND};
        font-weight: 600; background: {SURFACE}; padding: 0.4rem 1.3rem;
    }}
    .stButton button:hover, .stDownloadButton button:hover {{
        background: {BRAND}; color: {TEXT_ON_BRAND}; border-color: {BRAND};
    }}

    /* Воздушные карточки со спарклайном (metric_grid). Цвета с !important —
       иначе глобальное «.stMarkdown div {{ color }}» перебивает зелёный на серый. */
    .hx-row {{ display:grid; gap:26px; margin:8px 0 4px; }}
    .hx-card {{ padding:4px 2px 6px; position:relative; }}
    .hx-card:not(:first-child)::before {{ content:""; position:absolute; left:-13px; top:6px;
        bottom:6px; width:1px; background:{BORDER}; }}
    .hx-lbl {{ font-size:0.74rem !important; font-weight:600; text-transform:uppercase;
        letter-spacing:0.04em; color:{GREEN_VALUE} !important; opacity:0.82; }}
    .hx-val {{ font-size:1.85rem !important; font-weight:700; color:{GREEN_VALUE} !important;
        line-height:1.1; margin:7px 0 8px; }}
    .hx-foot {{ display:flex; align-items:center; justify-content:space-between; gap:8px; min-height:22px; }}
    .hx-pill {{ display:inline-flex !important; align-items:center; gap:3px; font-size:0.78rem;
        font-weight:600; padding:2px 9px; border-radius:20px;
        background:rgba(51,86,111,0.12); color:{GREEN_VALUE} !important; }}
    .hx-pill-dn {{ background:rgba(201,129,136,0.35); color:{NEGATIVE_DEEP} !important; }}
    </style>
    """


# ─────────────────────────── Публичные хелперы ───────────────────────────
def apply(page_title: str = "Клиника — дашборд", layout: str = "wide") -> None:
    st.set_page_config(page_title=page_title, layout=layout, initial_sidebar_state="collapsed")
    _register_template()
    st.markdown(_css(), unsafe_allow_html=True)
    st.markdown(spotlight_css(), unsafe_allow_html=True)


def section(title: str, subtitle: str | None = None) -> None:
    sub = f'<div class="ds-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(f'<div class="ds-section"><div class="ds-title">{title}</div>{sub}</div>',
                unsafe_allow_html=True)


def caption(text: str) -> None:
    st.markdown(f'<p class="ds-caption">{text}</p>', unsafe_allow_html=True)


def _spark_svg(values, color, w: int = 64, h: int = 20) -> str:
    """Мини-график тренда из списка чисел, нормированный в бокс w×h."""
    vals = [v for v in (values or []) if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    n = len(vals)
    pts = [f"{round(i * (w - 4) / (n - 1) + 2, 1)},{round(h - 2 - (v - lo) / rng * (h - 4), 1)}"
           for i, v in enumerate(vals)]
    lx, ly = pts[-1].split(",")
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{lx}" cy="{ly}" r="2" fill="{color}"/></svg>')


def metric_card(label: str, value: str, delta: str | None = None,
                positive: bool = True, trend=None) -> str:
    """HTML одной воздушной карточки со спарклайном. Возвращает строку для metric_grid."""
    color = GREEN_VALUE if positive else NEGATIVE_DEEP
    spark = _spark_svg(trend, color) if trend else "<span></span>"
    pill = ""
    if delta is not None:
        cls = "hx-pill" if positive else "hx-pill hx-pill-dn"
        arrow = "↑" if positive else "↓"
        pill = f'<span class="{cls}">{arrow} {delta}</span>'
    foot = f'<div class="hx-foot">{pill or "<span></span>"}{spark}</div>'
    return (f'<div class="hx-card"><div class="hx-lbl">{label}</div>'
            f'<div class="hx-val">{value}</div>{foot}</div>')


# ─────────────────────── Gauge-донат («% от плана/цели») ───────────────────────
def gauge_donut(pct: float, label: str, color: str | None = None,
                size: int = 168, track: str | None = None,
                text_color: str | None = None) -> go.Figure:
    """Кольцевой индикатор доли (0..1+). pct>1 закрашивает полное кольцо тем же
    цветом (план перевыполнен), но подпись в центре показывает реальный %.
    Число в центре красится в цвет кольца (или в text_color, если задан отдельно —
    например, ring=NEGATIVE (мягкий розовый), text=NEGATIVE_DEEP для контраста) —
    чтобы негативный/невыполненный KPI не оставался зелёным текстом при розовом кольце."""
    color = color or BRAND
    track = track or BORDER
    text_color = text_color or color
    filled = min(max(pct, 0), 1)
    fig = go.Figure(go.Pie(
        values=[filled, 1 - filled], hole=0.76, sort=False, direction="clockwise",
        rotation=-90, marker=dict(colors=[color, track], line=dict(width=0)),
        textinfo="none", hoverinfo="skip",
    ))
    # Длинные подписи ("% отмен (план/факт)") переносим на 2 строки — иначе
    # текст вылезает за пределы кольца.
    label_lines = _wrap_label(label)
    label_size = size * (0.075 if "<br>" not in label_lines else 0.066)
    label_y = 0.32 if "<br>" not in label_lines else 0.30
    fig.update_layout(
        showlegend=False, width=size, height=size,
        margin=dict(t=6, b=6, l=6, r=6),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        annotations=[
            dict(text=f"<b>{pct:.0%}</b>", x=0.5, y=0.56, showarrow=False,
                 font=dict(size=size * 0.145, color=text_color, family=FONT_FAMILY)),
            dict(text=label_lines, x=0.5, y=label_y, showarrow=False,
                 font=dict(size=label_size, color=TEXT_MUTED, family=FONT_FAMILY)),
        ],
    )
    return fig


def _wrap_label(label: str, max_chars: int = 13) -> str:
    """Переносит длинный текст на несколько строк по словам (для gauge_donut)."""
    words = label.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) > max_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return "<br>".join(lines)


def area_gradient(fig: go.Figure, x, y, name: str, color: str | None = None,
                  yaxis: str = "y1", show_markers: bool = True) -> go.Figure:
    """Добавляет линию с гладкой градиентной заливкой (цвет → прозрачность)."""
    color = color or BRAND
    fig.add_scatter(
        x=x, y=y, name=name, yaxis=yaxis,
        mode="lines+markers" if show_markers else "lines",
        line=dict(color=color, width=2.4, shape="spline", smoothing=0.4),
        marker=dict(size=5, color=color),
        fill="tozeroy",
        fillgradient=dict(type="vertical", colorscale=[[0, color], [1, "rgba(255,255,255,0)"]]),
    )
    return fig


def insight_card(headline: str, big_stat: str, text: str, positive: bool = True) -> None:
    """Крупная карточка-инсайт: заголовок + большая цифра + пояснение (в духе
    «You are going to grow by 44% next year» из референсов)."""
    color = GREEN_VALUE if positive else NEGATIVE_DEEP
    st.markdown(
        f'<div class="ins-card">'
        f'<div class="ins-head">{headline}</div>'
        f'<div class="ins-stat" style="color:{color} !important;">{big_stat}</div>'
        f'<div class="ins-text">{text}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def progress_bar(label: str, pct: float, value_text: str, color: str | None = None) -> str:
    """HTML горизонтальный progress-бар (план/факт на 1 объект — врач, направление)."""
    color = color or BRAND
    fill = min(max(pct, 0), 1) * 100
    over = pct > 1
    return (
        f'<div class="pb-row">'
        f'<div class="pb-top"><span class="pb-lbl">{label}</span>'
        f'<span class="pb-val">{value_text}</span></div>'
        f'<div class="pb-track"><div class="pb-fill" style="width:{fill:.1f}%;'
        f'background:{NEGATIVE_DEEP if over else color};"></div></div>'
        f'</div>'
    )


def avatar_chip(initials: str, color: str | None = None) -> str:
    """Маленький круглый аватар-инициалы (для списков врачей/людей)."""
    color = color or BRAND
    return (f'<span class="av-chip" style="background:{color};">{initials}</span>')


def spotlight_css() -> str:
    """CSS для insight_card / progress_bar / avatar_chip — вызвать один раз после apply()."""
    return f"""
    <style>
    /* Прозрачная, без заливки/рамки — тот же лёгкий язык, что у "Главные тезисы
       периода" на Сводке (просто текст с зелёной чертой слева), а не отдельная
       закрашенная плашка. */
    .ins-card {{ background:transparent; border:none; border-left:4px solid {BRAND};
        border-radius:0; padding:2px 0 2px 18px; margin:6px 0 4px; }}
    /* Тот же тёмно-зелёный, что у заголовков секций и карточек (не отдельный
       GREEN_LABEL) — иначе метка "ЮНИТ-ЭКОНОМИКА МЕСЯЦА" выглядит чужеродным
       оттенком зелёного рядом с остальными заголовками. */
    .ins-head {{ font-size:0.8rem; font-weight:700; text-transform:uppercase;
        letter-spacing:0.04em; color:{GREEN_VALUE} !important; margin-bottom:6px; }}
    .ins-stat {{ font-size:2.4rem; font-weight:800; line-height:1.08; margin-bottom:8px; }}
    /* INK_MUTED, не TEXT — тот же приглушённый тон, что у остальных "вывод"-строк. */
    .ins-text {{ font-size:0.92rem; color:{INK_MUTED} !important; line-height:1.5; max-width:640px; }}

    .pb-row {{ margin:0 0 14px; }}
    .pb-top {{ display:flex; justify-content:space-between; margin-bottom:5px; font-size:0.84rem; }}
    .pb-lbl {{ color:{TEXT} !important; font-weight:600; }}
    .pb-val {{ color:{TEXT_MUTED} !important; }}
    .pb-track {{ height:8px; border-radius:6px; background:{BORDER}; overflow:hidden; }}
    .pb-fill {{ height:100%; border-radius:6px; transition:width .2s ease; }}

    .av-chip {{ display:inline-flex; align-items:center; justify-content:center;
        width:26px; height:26px; border-radius:50%; color:#fff; font-size:0.68rem;
        font-weight:700; margin-right:8px; vertical-align:middle; }}

    .ghost-card {{ background:{SURFACE_ALT}; border:1.5px dashed {BORDER}; border-radius:18px;
        padding:22px; text-align:center; opacity:0.75; }}
    .ghost-tag {{ display:inline-block; font-size:0.72rem; font-weight:700; color:{TEXT_MUTED} !important;
        background:{SURFACE}; border:1px solid {BORDER}; border-radius:20px; padding:3px 12px;
        margin-top:10px; text-transform:uppercase; letter-spacing:0.04em; }}
    </style>
    """


def metric_grid(cards, cols: int = 4) -> None:
    """Рендерит ряд карточек (список HTML из metric_card) сеткой в cols колонок."""
    html = (f'<div class="hx-row" style="grid-template-columns:repeat({cols},1fr)">'
            + "".join(cards) + "</div>")
    st.markdown(html, unsafe_allow_html=True)
