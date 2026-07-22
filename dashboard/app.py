"""
Дашборд клиники — 9 вкладок по темам управленческого учёта: Сводка, Финансовые
показатели, Клиенты, Операционная эффективность, Продукты/направления,
Юнит-экономика, Запас прочности, KPI, CAC. Читает CSV из ../warehouse/,
собранные пайплайном etl/*.py (источники каждой цифры — docs/data_sources.md).
Визуальный язык (палитра/шрифт/карточки/графики) — в theme.py.

Запуск:
    streamlit run dashboard/app.py
"""

import io
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import insights as ins
import theme as T
from formatting import fmt_k, fmt_money, fmt_num, fmt_pct, set_lang, to_k

WAREHOUSE_DIR = Path(__file__).resolve().parent.parent / "warehouse"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

T.apply(page_title="Meridian Health — Dashboard")

_lang_spacer, _lang_col = st.columns([6, 1])
with _lang_col:
    LANG = st.radio("Язык / Language", ["RU", "EN"], index=0, horizontal=True,
                     label_visibility="collapsed", key="lang")

set_lang(LANG.lower())
T.set_number_lang(LANG.lower())


def t(ru: str, en: str) -> str:
    """Возвращает ru или en в зависимости от переключателя языка вверху страницы."""
    return en if LANG == "EN" else ru


def _check_password() -> bool:
    """Парольный гейт перед дашбордом — нужен, когда дашборд открыт наружу через
    Tailscale Funnel (публичная ссылка), а не только локально на localhost.
    Пароль — в .streamlit/secrets.toml (не в git, см. .gitignore). Если файла
    нет (обычный локальный запуск) — доступ без пароля, как раньше.

    Спрашивается всегда, в том числе локально: Tailscale Funnel проксирует
    запросы так, что заголовки Host/Origin неотличимы от настоящего localhost
    (проверено — подмена происходит на стороне Funnel), поэтому надёжно
    различить "свой Mac" и "снаружи по ссылке" на уровне заголовков нельзя."""
    try:
        pwd = st.secrets.get("dashboard_password")
    except Exception:
        pwd = None
    if not pwd:
        return True
    if st.session_state.get("_authed"):
        return True
    st.markdown(f"<h2 style='text-align:center;'>{t('Meridian Health — операционный дашборд', 'Meridian Health — Operations Dashboard')}</h2>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1, 1])
    with mid:
        entered = st.text_input(t("Пароль", "Password"), type="password")
        if entered:
            if entered == pwd:
                st.session_state["_authed"] = True
                st.rerun()
            else:
                st.error(t("Неверный пароль.", "Incorrect password."))
    return False


if not _check_password():
    st.stop()

# Тот же CAPTION_STYLE, что использует весь код ниже (f'<p style="{CAPTION_STYLE}">'),
# но со значениями из новой палитры — правится в одном месте на весь файл.
CAPTION_STYLE = f"font-size:0.83em;color:{T.INK_SOFT};font-style:italic;"

# ───────────────────────── Палитра — алиасы на theme.py ─────────────────────────
# Старые имена сохранены (весь код ниже использует именно их), но указывают на
# новые брендовые токены из theme.py — без необходимости переписывать каждый график.
DARK_GREEN = T.BRAND
LIGHT_GREEN = T.SAGE
SAGE = T.MIST
GRAY = "#C1BEBD"
PINK = T.PINK
ESPRESSO = T.PURPLE  # приглушённый фиолетовый вместо кофейного — по фактическим правкам
CREAM = T.CREAM
TEXT_DARK = T.BRAND_DEEP
TEXT_BODY = T.TEXT
DATA_LABEL_SIZE = T.DATA_LABEL_SIZE

CORPORATE_SEQUENCE = T.SEQUENCE
px.defaults.color_discrete_sequence = CORPORATE_SEQUENCE

# фиксированные цвета по специальностям — для графиков удержания/оттока из Google-таблицы
SPEC_COLORS = T.SPEC_COLORS

# Цвет столбца scorecard удержания — по уровню достижения бенчмарка (не по специальности)
LEVEL_COLORS = {"Ниже среднего": T.NEGATIVE, "Средний": "#93A0A6", "Хороший": T.SAGE, "Отличный": T.BRAND}

# Единая палитра для направлений — одна цветовая семья (сине-графитовый→серо-голубой),
# а не пёстрая смесь бренд/розовый/фиолетовый (иначе донат не сочетается с
# остальными графиками той же гаммы рядом).
DIRECTION_COLORS = [DARK_GREEN, "#4F7484", LIGHT_GREEN, "#B9C7CE", "#C3CBCE", "#93A0A6"]
# Едва заметный фон-дорожка за строкой метрики (вместо раскраски самого бара) —
# классический светофор, приглушённый под тёплую палитру дашборда.
ZONE_COLORS = {"Ниже среднего": "#D98A7E", "Средний": "#E3C177", "Хороший": DARK_GREEN, "Отличный": DARK_GREEN}


def pct_change(new, old):
    if old in (0, None) or pd.isna(old) or pd.isna(new):
        return None
    return (new - old) / abs(old)


# ───────────────────────── Загрузка данных ─────────────────────────
@st.cache_data
def load_data():
    d = {}
    d["visits"] = pd.read_csv(WAREHOUSE_DIR / "visits_enriched.csv", parse_dates=["visit_datetime"])
    d["lines"] = pd.read_csv(WAREHOUSE_DIR / "fact_service_lines.csv", parse_dates=["visit_datetime"])
    d["monthly_client"] = pd.read_csv(WAREHOUSE_DIR / "monthly_client_summary.csv")
    d["cohort"] = pd.read_csv(WAREHOUSE_DIR / "cohort_ltv.csv")
    d["breakeven"] = pd.read_csv(WAREHOUSE_DIR / "breakeven_monthly.csv")
    d["doctors_util"] = pd.read_csv(WAREHOUSE_DIR / "doctor_monthly_utilization.csv")
    d["pnl"] = pd.read_csv(WAREHOUSE_DIR / "monthly_pnl.csv")
    d["by_direction"] = pd.read_csv(WAREHOUSE_DIR / "revenue_by_direction_monthly.csv")
    d["grade_metrics"] = pd.read_csv(WAREHOUSE_DIR / "grade_monthly_metrics.csv")
    d["format_by_grade"] = pd.read_csv(WAREHOUSE_DIR / "format_monthly_by_grade.csv")
    d["neuro"] = pd.read_csv(WAREHOUSE_DIR / "neurology_monthly_metrics.csv")
    d["neuro_top_doctor"] = pd.read_csv(WAREHOUSE_DIR / "neurology_top_doctor_share.csv")
    d["room_util"] = pd.read_csv(WAREHOUSE_DIR / "room_utilization_monthly.csv")
    d["team"] = pd.read_csv(WAREHOUSE_DIR / "doctor_team_monthly.csv")
    funnel_path = WAREHOUSE_DIR / "funnel_monthly.csv"
    d["funnel"] = pd.read_csv(funnel_path) if funnel_path.exists() else None
    kpi_plan_path = WAREHOUSE_DIR / "kpi_plan_monthly.csv"
    d["kpi_plan"] = pd.read_csv(kpi_plan_path) if kpi_plan_path.exists() else None
    doc_econ_path = WAREHOUSE_DIR / "doctor_economics_monthly.csv"
    d["doctor_economics"] = pd.read_csv(doc_econ_path) if doc_econ_path.exists() else None
    cash_path = WAREHOUSE_DIR / "cash_runway_monthly.csv"
    d["cash_runway"] = pd.read_csv(cash_path) if cash_path.exists() else None
    churn_path = WAREHOUSE_DIR / "churn_monthly.csv"
    d["churn"] = pd.read_csv(churn_path) if churn_path.exists() else None
    dir_margin_path = WAREHOUSE_DIR / "direction_margin_monthly.csv"
    d["direction_margin"] = pd.read_csv(dir_margin_path) if dir_margin_path.exists() else None
    drug_margin_path = WAREHOUSE_DIR / "drug_margin_monthly.csv"
    d["drug_margin"] = pd.read_csv(drug_margin_path) if drug_margin_path.exists() else None
    cross_sell_path = WAREHOUSE_DIR / "cross_sell_monthly.csv"
    d["cross_sell"] = pd.read_csv(cross_sell_path) if cross_sell_path.exists() else None
    doc_retention_path = WAREHOUSE_DIR / "doctor_retention_anomalies.csv"
    d["doctor_retention_anomalies"] = pd.read_csv(doc_retention_path) if doc_retention_path.exists() else None
    marketing_path = WAREHOUSE_DIR / "marketing_spend_monthly.csv"
    d["marketing_spend"] = pd.read_csv(marketing_path) if marketing_path.exists() else None
    # Аналитика удержания/оттока — из Google-таблицы пользователя (retention_report.py),
    # подтягивается через etl/load_retention_from_sheet.py (может отсутствовать офлайн).
    for key, fname in [
        ("retention_scorecard", "retention_scorecard.csv"),
        ("cohort_retention", "cohort_retention.csv"),
        ("grade_retention", "grade_retention.csv"),
        ("churn_specialty", "churn_by_specialty.csv"),
    ]:
        p = WAREHOUSE_DIR / fname
        d[key] = pd.read_csv(p) if p.exists() else None
    return d


data = load_data()
ALL_MONTHS = sorted(data["visits"]["visit_datetime"].dt.to_period("M").astype(str).unique())

# Консультации — фактические ОПЛАЧЕННЫЕ визиты из CRM (fact_visits/visits_enriched),
# включая уволившихся врачей. Раньше брали из ЗП, но файлы ЗП не содержат ушедших
# врачей за ранние месяцы (их визиты есть в CRM, но не в текущих файлах ЗП), из-за
# чего ранние месяцы недосчитывались и средний чек за них был завышен. CRM даёт
# реальный счёт.
# Технические визиты с символической выручкой (0₽ и ≤1₽) НЕ считаются консультацией
# (решение сверки данных): так «Консультации» на Сводке = «Факт визитов» на KPI =
# monthly_client, а средний чек не занижается нулевым визитом в знаменателе. Порог >1
# совпадает с фильтром amount>1 в ЗП-пайплайне (breakeven, monthly_client, ЗП).
_visits_actual = data["visits"].copy()
_visits_actual["month"] = _visits_actual["visit_datetime"].dt.to_period("M").astype(str)
_visits_actual = _visits_actual[_visits_actual["revenue"] > 1]
VISITS_BY_MONTH_ACTUAL = _visits_actual.groupby("month")["visit_id"].count()


def n_visits_actual(months):
    return VISITS_BY_MONTH_ACTUAL.reindex(months).fillna(0).sum()


# Единая помесячная сводка по врачам для топ-5 и тезисов. Сверка данных:
#   • число консультаций на врача (n_visits) — из CRM (оплаченные визиты, тот же
#     канонический счёт, что VISITS_BY_MONTH_ACTUAL) → доля «% консультаций» и её
#     знаменатель совпадают с карточкой «Консультации» на Сводке;
#   • выручка на врача (revenue) — из ЗП (doctor_economics), это точный источник
#     по врачу; фолбэк на выручку из CRM, если ЗП не загружена.
# Ушедшие врачи есть в CRM, но не в текущих файлах ЗП → у них visits>0, revenue=0
# (в топ-5 по выручке не попадут, но их консультации корректно учтены в доле).
_doc_visits = _visits_actual.groupby(["month", "doctor"]).size().rename("n_visits").reset_index()
if data["doctor_economics"] is not None:
    _doc_rev = data["doctor_economics"].groupby(["month", "doctor"])["revenue"].sum().reset_index()
else:
    _doc_rev = _visits_actual.groupby(["month", "doctor"])["revenue"].sum().reset_index()
DOCTOR_PERF = _doc_visits.merge(_doc_rev, on=["month", "doctor"], how="outer")
DOCTOR_PERF["n_visits"] = DOCTOR_PERF["n_visits"].fillna(0)
DOCTOR_PERF["revenue"] = DOCTOR_PERF["revenue"].fillna(0)

head_left, head_right = st.columns([4, 1.4])
with head_left:
    # Логотип, а под ним — заголовок. Без white-space:nowrap: на широком экране
    # фраза и так помещается в одну строку, на узком — переносится естественно.
    logo_path = ASSETS_DIR / "logo.png"
    if logo_path.exists():
        st.image(str(logo_path), width=210)
    st.markdown(
        f"<h1 style='font-size:2.2rem; margin:0; padding-top:0.2rem; color:{DARK_GREEN};'>"
        f"{t('Meridian Health — операционный дашборд', 'Meridian Health — Operations Dashboard')}</h1>",
        unsafe_allow_html=True,
    )
with head_right:
    st.write("")
    pptx_button_placeholder = st.empty()
    pptx_download_placeholder = st.empty()

# ───────────────────────── Период: выбор и агрегация (на главном экране) ─────────────────────────
# Стиль — класс .ds-period-label из theme.py (фирменный зелёный, жирный).
st.markdown(f"<div class='ds-period-label'>{t('Выберите период', 'Select period')}</div>", unsafe_allow_html=True)
period_col1, period_col2 = st.columns([1, 2])
_GRANULARITY_LABELS = {"Месяц": t("Месяц", "Month"), "Квартал": t("Квартал", "Quarter"),
                        "Полугодие": t("Полугодие", "Half-year"), "Год": t("Год", "Year")}
with period_col1:
    granularity = st.radio(t("Гранулярность", "Granularity"), ["Месяц", "Квартал", "Полугодие", "Год"],
                            index=0, horizontal=True, format_func=lambda g: _GRANULARITY_LABELS[g])


def period_of(month_str: str) -> str:
    p = pd.Period(month_str, freq="M")
    if granularity == "Месяц":
        return month_str
    if granularity == "Квартал":
        return f"{p.year}-Q{p.quarter}"
    if granularity == "Полугодие":
        return f"{p.year}-H{1 if p.month <= 6 else 2}"
    return str(p.year)


PERIOD_MONTHS = {}
for m in ALL_MONTHS:
    PERIOD_MONTHS.setdefault(period_of(m), []).append(m)
ORDERED_PERIODS = sorted(PERIOD_MONTHS, key=lambda p: PERIOD_MONTHS[p][0])

with period_col2:
    selected_period = st.selectbox(t("Период", "Period"), ORDERED_PERIODS, index=len(ORDERED_PERIODS) - 1)
cur_months = PERIOD_MONTHS[selected_period]
period_idx = ORDERED_PERIODS.index(selected_period)
prev_months = PERIOD_MONTHS[ORDERED_PERIODS[period_idx - 1]] if period_idx > 0 else []
# Все трендовые графики истории обрезаются по конец выбранного периода — чтобы при
# выборе, например, мая ни на одном графике не "утекали" более поздние месяцы
# (включая прогнозные месяцы финмодели и частично заполненные месяцы ЗП).
HIST_MONTHS = [m for m in ALL_MONTHS if m <= cur_months[-1]]

caption = t(f"Текущий период: {cur_months[0]} — {cur_months[-1]}", f"Current period: {cur_months[0]} — {cur_months[-1]}")
# Полугодие/Год могут сравнивать периоды с разным числом месяцев (например, Год
# 2026 из 7 фактических месяцев против полного Года 2025 из 12) — % изменения в
# этом случае вводят в заблуждение, поэтому явно подписываем несопоставимость.
period_incomplete = bool(prev_months) and len(cur_months) != len(prev_months)
if prev_months:
    caption += t(f" · Сравнение с: {prev_months[0]} — {prev_months[-1]}", f" · Compared to: {prev_months[0]} — {prev_months[-1]}")
    if period_incomplete:
        caption += t(
            f" · ⚠️ неполный период ({len(cur_months)} мес. против {len(prev_months)} мес.) — % изменения не сопоставимы",
            f" · ⚠️ incomplete period ({len(cur_months)} mo. vs {len(prev_months)} mo.) — % changes are not comparable",
        )
T.caption(caption)
st.divider()


def sum_col(df, month_col, months, col):
    return df[df[month_col].isin(months)][col].sum()


def metric_with_delta(col, label, cur_val, prev_val, kind="num", suffix=""):
    delta = pct_change(cur_val, prev_val) if prev_months else None
    value_str = fmt_money(cur_val) if kind == "money" else fmt_num(cur_val)
    col.metric(label, value_str + suffix, fmt_pct(delta) if delta is not None else None)


T.caption(t(f"Данные: {data['visits']['visit_datetime'].min().date()} — {data['visits']['visit_datetime'].max().date()}",
            f"Data: {data['visits']['visit_datetime'].min().date()} — {data['visits']['visit_datetime'].max().date()}"))

pptx_sections = []  # собирается по ходу рендера вкладок, используется кнопкой экспорта в PPTX внизу

tab0, tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    t("Сводка", "Summary"), t("Финансовые показатели", "Financials"), t("Клиенты", "Clients"),
    t("Операционная эффективность", "Operations"), t("Продукты/направления", "Products/Directions"),
    t("Юнит-экономика", "Unit Economics"), t("Запас прочности", "Margin of Safety"),
    "KPI", "CAC", t("Прогноз", "Forecast"),
])

# ═══════════════════════ СВОДКА ═══════════════════════
with tab0:
    T.section(t(f"Главное за период: {selected_period}", f"Highlights for {selected_period}"))

    monthly_all = data["monthly_client"]
    n_visits_cur_top = n_visits_actual(cur_months)
    if n_visits_cur_top is None:
        n_visits_cur_top = sum_col(monthly_all, "visit_month", cur_months, "n_visits_new") + sum_col(monthly_all, "visit_month", cur_months, "n_visits_repeat")
    n_visits_prev_top = n_visits_actual(prev_months) if prev_months else None
    if prev_months and n_visits_prev_top is None:
        n_visits_prev_top = sum_col(monthly_all, "visit_month", prev_months, "n_visits_new") + sum_col(monthly_all, "visit_month", prev_months, "n_visits_repeat")
    # Выручка — единый источник с Блок 1 (monthly_pnl: факт по визитам + допвыручка вне
    # CRM), чтобы цифры на Сводке и в Блок 1 больше не расходились между собой.
    rev_cur_top = sum_col(data["pnl"], "month", cur_months, "revenue")
    rev_prev_top = sum_col(data["pnl"], "month", prev_months, "revenue") if prev_months else None
    pnl_cur_top = data["pnl"][data["pnl"]["month"].isin(cur_months)][["revenue", "gross_profit", "operating_profit"]].sum()
    pnl_prev_top = data["pnl"][data["pnl"]["month"].isin(prev_months)][["revenue", "gross_profit", "operating_profit"]].sum() if prev_months else None
    repeat_cur_top = sum_col(monthly_all, "visit_month", cur_months, "n_clients_repeat")
    repeat_prev_top = sum_col(monthly_all, "visit_month", prev_months, "n_clients_repeat") if prev_months else None
    room_cur_top = data["room_util"][data["room_util"]["month"].isin(cur_months)].groupby("specialty").agg(capacity_hours=("capacity_hours", "sum"), actual_hours=("actual_hours", "sum"))
    util_cur_top = room_cur_top["actual_hours"].sum() / room_cur_top["capacity_hours"].sum() if room_cur_top["capacity_hours"].sum() else None
    # Текущий состав = последний месяц периода (снапшот), не максимум по
    # специальностям за все месяцы периода — иначе врачи, ушедшие в середине
    # периода, продолжают учитываться, и число завышается (баг, найден 2026-07:
    # Q2 показывал 24 врача при факте 19-20 на конец июня).
    doctors_cur_top = data["team"][data["team"]["month"] == cur_months[-1]]["n_doctors"].sum()
    doctors_prev_top = data["team"][data["team"]["month"] == prev_months[-1]]["n_doctors"].sum() if prev_months else None

    avg_check_top = rev_cur_top / n_visits_cur_top if n_visits_cur_top else 0
    avg_check_prev_top = (rev_prev_top / n_visits_prev_top) if prev_months and n_visits_prev_top else None

    margin_cur_top = pnl_cur_top["gross_profit"] / pnl_cur_top["revenue"] if pnl_cur_top["revenue"] else None
    margin_prev_top = (pnl_prev_top["gross_profit"] / pnl_prev_top["revenue"]) if prev_months and pnl_prev_top["revenue"] else None

    # LTV: средняя накопленная выручка на клиента, усреднённая по ВСЕМ когортам,
    # чьё наблюдение (cohort_month + month_index) попадает в выбранный период —
    # т.е. "средний LTV клиентов на момент этого периода", а не только для когорт,
    # стартовавших именно в этом периоде (иначе для свежих периодов почти всегда н/д).
    # Средневзвешенное по n_clients когорты — иначе когорта из 67 человек влияет
    # на итог наравне с когортой из 392 (см. чат 2026-07).
    cohort_df = data["cohort"].copy()
    cohort_df["calendar_month"] = (
        pd.PeriodIndex(cohort_df["cohort_month"], freq="M") + cohort_df["month_index"].astype(int)
    ).astype(str)

    def _weighted_ltv(months):
        sub = cohort_df[cohort_df["calendar_month"].isin(months)]
        total_clients = sub["n_clients"].sum()
        if not total_clients:
            return None
        return (sub["avg_cum_revenue"] * sub["n_clients"]).sum() / total_clients

    ltv_cur_top = _weighted_ltv(cur_months)
    ltv_prev_top = _weighted_ltv(prev_months) if prev_months else None

    summary_metrics_raw = [
        (t("Выручка", "Revenue"), rev_cur_top, rev_prev_top, "money"),
        (t("Консультации", "Consultations"), n_visits_cur_top, n_visits_prev_top, "num"),
        (t("Средний чек", "Average check"), avg_check_top, avg_check_prev_top, "money"),
        (t("Повторные клиенты", "Returning clients"), repeat_cur_top, repeat_prev_top, "num"),
        (t("Количество врачей", "Number of doctors"), doctors_cur_top, doctors_prev_top, "num"),
        (t("Операционный результат", "Operating result"), pnl_cur_top["operating_profit"], pnl_prev_top["operating_profit"] if prev_months else None, "money"),
    ]
    # ── Карточки со спарклайном на реальных данных: тренд — последние до 6
    # месяцев истории (HIST_MONTHS), тот же источник, что и сами цифры выше.
    trend_months = HIST_MONTHS[-6:] if len(HIST_MONTHS) >= 2 else HIST_MONTHS
    _room_by_month = data["room_util"][data["room_util"]["month"].isin(trend_months)]

    def _trend(series_fn):
        vals = [series_fn(m) for m in trend_months]
        return vals if all(v is not None for v in vals) else None

    revenue_trend = _trend(lambda m: sum_col(data["pnl"], "month", [m], "revenue"))
    consult_trend = _trend(lambda m: VISITS_BY_MONTH_ACTUAL.get(m, 0))
    avg_check_trend = None
    if revenue_trend and consult_trend:
        avg_check_trend = [r / c if c else 0 for r, c in zip(revenue_trend, consult_trend)]
    repeat_trend = _trend(lambda m: sum_col(monthly_all, "visit_month", [m], "n_clients_repeat"))
    doctors_trend = _trend(lambda m: data["team"][data["team"]["month"] == m].groupby("specialty")["n_doctors"].max().sum())
    ebitda_trend = _trend(lambda m: sum_col(data["pnl"], "month", [m], "operating_profit"))

    def _util_for_month(m):
        sub = _room_by_month[_room_by_month["month"] == m]
        cap = sub["capacity_hours"].sum()
        return (sub["actual_hours"].sum() / cap * 100) if cap else None
    util_trend = _trend(_util_for_month)

    def _margin_for_month(m):
        row = data["pnl"][data["pnl"]["month"] == m][["revenue", "gross_profit"]].sum()
        return (row["gross_profit"] / row["revenue"] * 100) if row["revenue"] else None
    margin_trend = _trend(_margin_for_month)

    def _pct_unsigned(delta):
        """Модуль в процентах без знака — стрелку ↑/↓ рисует сама карточка."""
        return f"{abs(delta):.0%}" if delta is not None else None

    def _card(label, cur_val, prev_val, kind, trend):
        delta = pct_change(cur_val, prev_val) if prev_months and cur_val is not None else None
        value_str = (fmt_money(cur_val) if kind == "money" else fmt_num(cur_val)) if cur_val is not None else t("н/д", "n/a")
        positive = delta is None or delta >= 0
        return T.metric_card(label, value_str, _pct_unsigned(delta), positive, trend)

    T.metric_grid([
        _card(t("Выручка", "Revenue"), rev_cur_top, rev_prev_top, "money", revenue_trend),
        _card(t("Консультации", "Consultations"), n_visits_cur_top, n_visits_prev_top, "num", consult_trend),
        _card(t("Средний чек", "Average check"), avg_check_top, avg_check_prev_top, "money", avg_check_trend),
        _card(t("Повторные клиенты", "Returning clients"), repeat_cur_top, repeat_prev_top, "num", repeat_trend),
    ])
    margin_delta = (margin_cur_top - margin_prev_top) if (margin_cur_top is not None and margin_prev_top is not None) else None
    T.metric_grid([
        _card(t("Операционный результат", "Operating result"), pnl_cur_top["operating_profit"], pnl_prev_top["operating_profit"] if prev_months else None, "money", ebitda_trend),
        _card(t("Количество врачей", "Number of doctors"), doctors_cur_top, doctors_prev_top, "num", doctors_trend),
        T.metric_card(t("Загрузка кабинетов", "Room utilization"), f"{util_cur_top:.0%}" if util_cur_top is not None else t("н/д", "n/a"), trend=util_trend),
        T.metric_card(t("Маржинальность", "Margin"), f"{margin_cur_top:.0%}" if margin_cur_top is not None else t("н/д", "n/a"),
                      _pct_unsigned(margin_delta), margin_delta is None or margin_delta >= 0, margin_trend),
    ])
    ltv_delta = pct_change(ltv_cur_top, ltv_prev_top) if ltv_cur_top is not None else None
    T.metric_grid([
        T.metric_card(t("LTV (среднее по периоду)", "LTV (period average)"), fmt_money(ltv_cur_top) if ltv_cur_top is not None else t("н/д", "n/a"),
                      _pct_unsigned(ltv_delta), ltv_delta is None or ltv_delta >= 0),
    ], cols=4)

    summary_metrics_for_pptx = [
        (label, fmt_money(cur_val) if kind == "money" else fmt_num(cur_val), fmt_pct(pct_change(cur_val, prev_val)) if prev_val is not None else None)
        for label, cur_val, prev_val, kind in summary_metrics_raw
    ] + [
        ("Загрузка кабинетов", f"{util_cur_top:.0%}" if util_cur_top is not None else t("н/д", "n/a"), None),
        ("Маржинальность", f"{margin_cur_top:.0%}" if margin_cur_top is not None else t("н/д", "n/a"), fmt_pct(margin_delta) if margin_delta is not None else None),
        ("LTV (среднее по периоду)", fmt_money(ltv_cur_top) if ltv_cur_top is not None else t("н/д", "n/a"), fmt_pct(ltv_delta) if ltv_delta is not None else None),
    ]

    st.divider()
    T.section(t("Главные тезисы периода", "Key takeaways for the period"))
    summary_narrative = [
        (t("Финансы.", "Financials."), ins.pnl_insight(data['pnl'], cur_months, prev_months, lang=LANG.lower())),
        (t("Клиенты и удержание.", "Clients & retention."), ins.clients_insight(data['monthly_client'], cur_months, prev_months, avg_check_cur=avg_check_top, avg_check_prev=avg_check_prev_top, lang=LANG.lower())),
        (t("Направления.", "Directions."), ins.direction_insight(data['by_direction'], cur_months, prev_months, lang=LANG.lower())),
        (t("Команда врачей.", "Doctor team."), ins.doctors_insight(data['team'], cur_months, prev_months, visits_cur=n_visits_actual(cur_months), visits_prev=n_visits_actual(prev_months) if prev_months else None, lang=LANG.lower())),
        (t("Топ-специалисты.", "Top specialists."), ins.top5_insight(DOCTOR_PERF, 'month', cur_months, lang=LANG.lower())),
        (t("Грейды стоматологии.", "Dentistry grades."), ins.grade_insight(data['grade_metrics'], cur_months, prev_months, lang=LANG.lower())),
        (t("Косметология.", "Cosmetology."), ins.neuro_insight(data['neuro'], data['neuro_top_doctor'], cur_months, prev_months, lang=LANG.lower())),
        (t("Загрузка кабинетов.", "Room utilization."), ins.rooms_insight(data['room_util'], cur_months, prev_months, lang=LANG.lower())),
    ]
    if data["funnel"] is not None:
        summary_narrative.append((t("Воронка записи.", "Booking funnel."), ins.funnel_insight(data['funnel'], cur_months, prev_months, lang=LANG.lower())))
    if data["churn_specialty"] is not None:
        conf = data["churn_specialty"][~data["churn_specialty"]["preliminary"]]
        parts = []
        for spec in SPEC_COLORS:
            last = conf[conf["specialty"] == spec].dropna(subset=["churn_rate"]).tail(1)
            if len(last):
                spec_label = ins.DIRECTION_EN.get(spec, spec).lower() if LANG == "EN" else spec.lower()
                parts.append(f"{spec_label} {last.iloc[0]['churn_rate']:.0%} ({t('посл. подтв.', 'last confirmed')} {last.iloc[0]['month']})")
        if parts:
            summary_narrative.append((t("Отток (churn, 90 дней).", "Churn (90 days)."),
                                       t("Последний подтверждённый отток: ", "Latest confirmed churn: ") + ", ".join(parts) + "."))
    if data["cross_sell"] is not None:
        cs_sub = data["cross_sell"][data["cross_sell"]["month"].isin(cur_months)]["cross_sell_rate"].mean()
        if pd.notna(cs_sub):
            summary_narrative.append(("Cross-sell.", t(
                f"У {cs_sub:.0%} пациентов за период были услуги более чем одного направления.",
                f"{cs_sub:.0%} of patients in the period received services from more than one direction.",
            )))
    summary_narrative.append(("KPI.", ins.kpi_insight(data['breakeven'], cur_months, lang=LANG.lower())))
    if data["marketing_spend"] is not None:
        summary_narrative.append(("CAC.", ins.cac_insight(data['marketing_spend'], data['monthly_client'], data['pnl'], cur_months, ltv_cur_top, lang=LANG.lower())))

    for heading, text in summary_narrative:
        st.markdown(f"**{heading}** {text}")
    st.markdown(
        f'<p style="{CAPTION_STYLE}">{t(
            "Тезисы формируются автоматически по правилам (не LLM) на основе изменения метрик к предыдущему периоду той же гранулярности. "
            "Полные графики и детализация — во вкладках Финансовые показатели, Клиенты, Операционная эффективность и Продукты/направления.",
            "Takeaways are generated automatically by rules (not an LLM), based on how metrics changed vs. the prior period of the same granularity. "
            "Full charts and detail live in the Financials, Clients, Operations and Products/Directions tabs.",
        )}</p>',
        unsafe_allow_html=True,
    )

# ═══════════════════════ БЛОК 1: Финансы и общие итоги ═══════════════════════
with tab1:
    T.section(t("Финансовый результат периода", "Financial result for the period"))
    pnl_cur = data["pnl"][data["pnl"]["month"].isin(cur_months)][
        ["revenue", "variable_costs", "gross_profit", "fixed_costs", "operating_profit"]
    ].sum()
    pnl_prev = data["pnl"][data["pnl"]["month"].isin(prev_months)][
        ["revenue", "variable_costs", "gross_profit", "fixed_costs", "operating_profit"]
    ].sum() if prev_months else None

    st.markdown(f"**{ins.pnl_insight(data['pnl'], cur_months, prev_months, lang=LANG.lower())}**")

    # Столбцы — исходная зелёная гамма (increasing/decreasing/totals не умеют
    # красить по знаку, только по типу). А вот textfont на уровне trace ПРИНИМАЕТ
    # список цветов по точкам — так подпись операционного результата красится
    # розовым при убытке, а сами столбцы остаются зелёными.
    text_colors = ["#FFFFFF", TEXT_DARK, TEXT_DARK, TEXT_DARK,
                   (TEXT_DARK if pnl_cur["operating_profit"] >= 0 else T.NEGATIVE_DEEP)]
    text_positions = ["inside", "inside", "inside", "inside", "inside"]
    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=["relative", "relative", "total", "relative", "total"],
            x=[t("Выручка", "Revenue"), t("Переменные расходы", "Variable costs"), t("Маржинальная прибыль", "Gross profit"),
               t("Постоянные расходы", "Fixed costs"), t("Операционный результат", "Operating result")],
            y=[to_k(pnl_cur["revenue"]), to_k(-pnl_cur["variable_costs"]), 0, to_k(-pnl_cur["fixed_costs"]), 0],
            text=[fmt_k(v) for v in [pnl_cur["revenue"], -pnl_cur["variable_costs"], pnl_cur["gross_profit"], -pnl_cur["fixed_costs"], pnl_cur["operating_profit"]]],
            textposition=text_positions,
            textfont=dict(color=text_colors, size=DATA_LABEL_SIZE),
            increasing=dict(marker=dict(color=DARK_GREEN)),
            decreasing=dict(marker=dict(color=GRAY)),
            totals=dict(marker=dict(color=SAGE)),
            connector=dict(line=dict(color=GRAY)),
        )
    )
    fig.update_layout(title=t(f"Финансовый результат — {selected_period}", f"Financial result — {selected_period}"), showlegend=False, yaxis_title=t("тыс. ₽", "₽ thousand"))
    st.plotly_chart(fig, use_container_width=True)
    pptx_sections.append({"tab": t("Финансовые показатели", "Financials"), "heading": ins.pnl_insight(data['pnl'], cur_months, prev_months, lang=LANG.lower()), "figs": [fig]})

    # Пороговый флаг по маржинальной прибыли (gross_profit/revenue, тот же "total"
    # что и в waterfall выше) — без новой инфраструктуры, просто условный баннер
    # поверх уже посчитанного pnl_cur. Порог 30% — задан пользователем.
    gross_margin_cur = pnl_cur["gross_profit"] / pnl_cur["revenue"] if pnl_cur["revenue"] else None
    if gross_margin_cur is not None and gross_margin_cur < 0.30:
        st.warning(t(f"Маржинальная прибыль ниже целевой: {gross_margin_cur:.0%} (порог 30%).",
                     f"Gross profit is below target: {gross_margin_cur:.0%} (threshold 30%)."))

    st.markdown(f'<p style="{CAPTION_STYLE}">{t("Постоянные/переменные расходы и маржа — из финмодели, актуализируется вместе с прогоном пайплайна.", "Fixed/variable costs and margin come from the financial model, refreshed with each pipeline run.")}</p>', unsafe_allow_html=True)

    with st.expander(t("Детализация P&L по месяцам", "P&L detail by month")):
        # Финмодель содержит плановые/прогнозные месяцы далеко вперёд (без реальных
        # визитов) — не показываем их в таблице фактических данных.
        pnl_actual = data["pnl"][data["pnl"]["month"] <= ALL_MONTHS[-1]]
        st.dataframe(pnl_actual.style.format({c: fmt_num for c in ["revenue", "variable_costs", "gross_profit", "fixed_costs", "operating_profit", "net_profit"]} | {"margin_pct": "{:.1%}"}), use_container_width=True)

    st.divider()
    T.section(t("Распределение выручки, консультаций и клиентов", "Revenue, consultations and clients over time"))
    # Показываем всю историю ТОЛЬКО до конца выбранного периода — иначе при выборе,
    # например, мая на графике всё равно "утекали" более поздние месяцы (июнь и т.д.),
    # которые пользователь ещё не выбирал.
    monthly_all_hist = data["monthly_client"].copy()
    monthly = monthly_all_hist[monthly_all_hist["visit_month"] <= cur_months[-1]].copy()
    # Выручка — тот же единый источник, что в Сводке и Блок 1 (monthly_pnl), а не
    # отдельный пересчёт из monthly_client — иначе цифры на графике снова разойдутся
    # с остальным дашбордом.
    monthly = monthly.merge(data["pnl"][["month", "revenue"]], left_on="visit_month", right_on="month", how="left")
    n_hist_months = len(monthly)

    def _space_num(x):
        return f"{x:,.0f}".replace(",", " ")

    revenue_text = [_space_num(v) for v in to_k(monthly["revenue"])]
    # Консультации — по ЗП (фактически оплаченные визиты), не по CRM-выгрузке — см.
    # комментарий у n_visits_actual() выше.
    if VISITS_BY_MONTH_ACTUAL is not None:
        consult_series = monthly["visit_month"].map(VISITS_BY_MONTH_ACTUAL).fillna(0)
    else:
        consult_series = monthly["n_visits_new"] + monthly["n_visits_repeat"]
    client_series = monthly["total_clients"]

    # Без подписей поверх столбцов/линий (даёт hover) — раньше три ряда подписей
    # одновременно делали график громоздким. Легенда/подписи осей — из шаблона.
    fig2 = go.Figure()
    fig2.add_bar(x=monthly["visit_month"], y=to_k(monthly["revenue"]), name=t("Выручка, тыс. ₽", "Revenue, ₽ thousand"), yaxis="y1", marker_color=SAGE)
    # shape/smoothing указаны явно: явный line=dict(...) не наследует форму
    # из шаблона (перебивает её целиком), поэтому дефолт "spline" тут молча
    # терялся, и линии оставались ломаными.
    fig2.add_scatter(x=monthly["visit_month"], y=consult_series, name=t("Консультации", "Consultations"), yaxis="y2",
                     mode="lines+markers", line=dict(color=DARK_GREEN, width=2.2, shape="spline", smoothing=1.3), marker=dict(size=6))
    fig2.add_scatter(x=monthly["visit_month"], y=client_series, name=t("Клиенты", "Clients"), yaxis="y2",
                     mode="lines+markers", line=dict(color=ESPRESSO, width=2.2, shape="spline", smoothing=1.3), marker=dict(size=6))
    T.dual_axis(fig2, t("Выручка, тыс. ₽", "Revenue, ₽ thousand"), t("Кол-во", "Count"))
    fig2.update_layout(title=t(f"{n_hist_months} мес. работы клиники — по {cur_months[-1]}", f"{n_hist_months} mo. of operation — through {cur_months[-1]}"))
    fig2.update_xaxes(type="category")

    col_chart, col_kpi = st.columns([2, 1])
    col_chart.plotly_chart(fig2, use_container_width=True)
    pptx_sections.append({"tab": t("Финансовые показатели", "Financials"), "heading": t("Распределение выручки, консультаций и клиентов", "Revenue, consultations and clients over time"), "figs": [fig2]})

    with col_kpi:
        # Не дублируем метрики текущего месяца (они уже на Сводке) — здесь ИТОГО
        # накопительно за весь показанный на графике период (с начала работы клиники
        # по конец выбранного периода), это отдельная, самостоятельная цифра.
        # Карточки со спарклайном — тот же тренд, что и на графике слева.
        n_visits_hist = consult_series.sum()
        rev_hist = monthly["revenue"].sum()
        new_hist = monthly["n_clients_new"].sum()
        repeat_hist = monthly["n_clients_repeat"].sum()
        avg_check_hist = rev_hist / n_visits_hist if n_visits_hist else 0
        avg_check_series = (monthly["revenue"] / consult_series.replace(0, pd.NA)).fillna(0).tolist()

        st.markdown(t(f"**Итого за {n_hist_months} мес. (по {cur_months[-1]})**", f"**Total over {n_hist_months} mo. (through {cur_months[-1]})**"))
        T.metric_grid([
            T.metric_card(t("Выручка (накопит.)", "Revenue (cumulative)"), fmt_money(rev_hist), trend=monthly["revenue"].tolist()),
            T.metric_card(t("Консультации (накопит.)", "Consultations (cumulative)"), fmt_num(n_visits_hist), trend=consult_series.tolist()),
            T.metric_card(t("Средний чек за период", "Average check for period"), fmt_money(avg_check_hist), trend=avg_check_series),
            T.metric_card(t("Новые клиенты (накопит.)", "New clients (cumulative)"), fmt_num(new_hist), trend=monthly["n_clients_new"].tolist()),
            T.metric_card(t("Повторные клиенты (накопит.)", "Returning clients (cumulative)"), fmt_num(repeat_hist), trend=monthly["n_clients_repeat"].tolist()),
        ], cols=1)


with tab4:
    def dlabel(d):
        return ins.DIRECTION_EN.get(d, d) if LANG == "EN" else d

    def splabel(s):
        """Для 'сырой' специальности врача (Стоматолог/Косметолог/Гигиенист, м.р.) —
        отдельный маппинг от dlabel (тот — для направлений выручки, ж.р.)."""
        return ins.SPECIALTY_EN.get(s, s) if LANG == "EN" else s

    def glabel(g):
        """'Грейд N' -> 'Grade N' для английских предложений (значения грейда — данные,
        не статичный текст, поэтому не покрываются обычным t())."""
        return g.replace("Грейд", "Grade") if LANG == "EN" else g

    PRODUCT_EN = {
        "Ботокс": "Botox", "Диспорт": "Disport", "Гиалуроновые филлеры": "Hyaluronic fillers",
        "Мезонити": "Mesothreads", "Биоревитализация": "Biorevitalization",
    }

    def plabel(p):
        return PRODUCT_EN.get(p, p) if LANG == "EN" else p

    def gslabel(g):
        """Для смешанной колонки 'grade', где часть значений — 'Грейд N', а часть —
        специальность-переопределение (Гигиенист/Косметолог/Инъекции): применяет
        оба маппинга, т.к. заранее неизвестно, какой из них сработает."""
        return glabel(splabel(g))

    T.section(t("Выручка по направлениям деятельности клиники", "Revenue by service direction"))
    st.markdown(f"**{ins.direction_insight(data['by_direction'], cur_months, prev_months, lang=LANG.lower())}**")
    dir_cur = data["by_direction"][data["by_direction"]["month"].isin(cur_months)].groupby("direction")["revenue"].sum()
    dir_prev = data["by_direction"][data["by_direction"]["month"].isin(prev_months)].groupby("direction")["revenue"].sum() if prev_months else pd.Series(dtype=float)

    col_a, col_b = st.columns(2)
    with col_a:
        directions = ["Стоматология", "Косметология", "Инъекции", "Гигиенист", "Прочее (доп. доход)"]
        texts = []
        for dname in directions:
            v = dir_cur.get(dname, 0)
            if v == 0:
                continue
            chg = pct_change(v, dir_prev.get(dname, 0))
            # Числа в тех же единицах, что и ось (тыс. ₽), но без суффикса в самой
            # подписи — единица измерения и так подписана на оси, дублировать её
            # на каждом столбце избыточно.
            texts.append(f"{fmt_k(v)} ({fmt_pct(chg)})" if chg is not None else f"{fmt_k(v)}")
        used_dirs = [d for d in directions if dir_cur.get(d, 0) > 0]
        total_cur_dir = sum(dir_cur.get(d, 0) for d in used_dirs)
        # Не ограничиваем сумму прошлого периода used_dirs (тот отфильтрован по
        # активности в ТЕКУЩЕМ периоде) — иначе направление, обнулившееся к
        # текущему периоду (напр. "Гигиенист" с мая 2026), выпадает из суммы
        # прошлого периода и завышает % роста "Итого".
        total_prev_dir = sum(dir_prev.get(d, 0) for d in directions) if prev_months else None
        total_chg = pct_change(total_cur_dir, total_prev_dir) if prev_months else None
        texts.append(f"{fmt_k(total_cur_dir)} ({fmt_pct(total_chg)})" if total_chg is not None else f"{fmt_k(total_cur_dir)}")
        x_labels = [dlabel(d) for d in used_dirs] + [t("Итого", "Total")]
        y_values = [to_k(dir_cur.get(d, 0)) for d in used_dirs] + [to_k(total_cur_dir)]
        bar_colors = [SAGE] * len(used_dirs) + [DARK_GREEN]
        fig3 = go.Figure(go.Bar(x=x_labels, y=y_values, text=texts, textposition="outside", marker_color=bar_colors))
        fig3.update_layout(title=t(f"Структура выручки — {selected_period}", f"Revenue breakdown — {selected_period}"), yaxis_title=t("тыс. ₽", "₽ thousand"))
        fig3.update_traces(line_shape="spline", line_smoothing=1.3, selector=dict(type="scatter"))
        st.plotly_chart(fig3, use_container_width=True)
    with col_b:
        # Donut с суммой в центре + список с точным % сбоку — вместо голого pie
        # без чисел. Цвета — та же последовательность, что и остальные графики.
        dir_vals = [dir_cur.get(d, 0) for d in used_dirs]
        dir_total = sum(dir_vals)
        dir_colors_list = DIRECTION_COLORS[:len(used_dirs)]
        fig4 = go.Figure(go.Pie(labels=[dlabel(d) for d in used_dirs], values=dir_vals, hole=0.66,
                                marker=dict(colors=dir_colors_list, line=dict(width=2, color=CREAM)),
                                textinfo="none", sort=False))
        fig4.update_layout(
            showlegend=False, height=300, margin=dict(t=10, b=10, l=10, r=10),
            annotations=[dict(text=f"<b>{fmt_money(dir_total)}</b>", x=0.5, y=0.5, showarrow=False,
                              font=dict(size=18, color=TEXT_DARK))],
        )
        st.plotly_chart(fig4, use_container_width=True)
        for name, val, color in zip(used_dirs, dir_vals, dir_colors_list):
            pct = val / dir_total if dir_total else 0
            st.markdown(
                f'<div style="display:flex;align-items:center;justify-content:space-between;'
                f'padding:6px 0;border-bottom:1px solid {T.BORDER};">'
                f'<span style="display:flex;align-items:center;gap:8px;color:{TEXT_BODY};font-size:0.9rem;">'
                f'<span style="width:10px;height:10px;border-radius:3px;background:{color};display:inline-block;"></span>'
                f'{dlabel(name)}</span>'
                f'<span style="font-weight:700;color:{TEXT_DARK};">{pct:.0%}</span></div>',
                unsafe_allow_html=True,
            )
    pptx_sections.append({"tab": t("Продукты/направления", "Products/Directions"), "heading": ins.direction_insight(data['by_direction'], cur_months, prev_months, lang=LANG.lower()), "figs": [fig3, fig4]})

    with st.expander(t("Детализация выручки по направлениям и месяцам", "Revenue detail by direction and month")):
        pivot_df = data["by_direction"].pivot(index="month", columns="direction", values="revenue").fillna(0)
        if LANG == "EN":
            pivot_df = pivot_df.rename(columns=lambda d: dlabel(d))
        st.dataframe(pivot_df.style.format(fmt_num), use_container_width=True)

    st.divider()
    T.section(t("Маржинальность направлений", "Margin by direction"))
    if data["direction_margin"] is not None:
        dm_cur = data["direction_margin"][data["direction_margin"]["month"].isin(cur_months)].groupby("direction").agg(
            revenue=("revenue", "sum"), cost=("cost", "sum")
        )
        dm_cur["margin"] = dm_cur["revenue"] - dm_cur["cost"]
        dm_cur["margin_pct"] = dm_cur["margin"] / dm_cur["revenue"]
        best_dir = dm_cur["margin_pct"].idxmax()
        st.markdown(t(f"**Самое маржинальное направление — {best_dir} ({dm_cur.loc[best_dir, 'margin_pct']:.0%}).**",
                      f"**The highest-margin direction is {dlabel(best_dir)} ({dm_cur.loc[best_dir, 'margin_pct']:.0%}).**"))
        # Комбо bar + line в одной карточке (выручка/маржа — бары, % маржи —
        # линия на второй оси) вместо двух разрозненных графиков.
        dm_display = dm_cur.reset_index()
        dm_display["revenue_k"] = to_k(dm_display["revenue"])
        dm_display["margin_k"] = to_k(dm_display["margin"])
        dm_x = [dlabel(d) for d in dm_display["direction"]]
        fig_dm = go.Figure()
        fig_dm.add_bar(x=dm_x, y=dm_display["revenue_k"], name=t("Выручка, тыс. ₽", "Revenue, ₽ thousand"), yaxis="y1", marker_color=SAGE,
                       text=[fmt_k(v) for v in dm_display["revenue"]], textposition="outside")
        fig_dm.add_bar(x=dm_x, y=dm_display["margin_k"], name=t("Маржа, тыс. ₽", "Margin, ₽ thousand"), yaxis="y1", marker_color=DARK_GREEN,
                       text=[fmt_k(v) for v in dm_display["margin"]], textposition="outside")
        fig_dm.add_scatter(x=dm_x, y=dm_display["margin_pct"], name=t("Маржинальность, %", "Margin, %"), yaxis="y2",
                           mode="lines+markers+text", line=dict(color=ESPRESSO, width=2.4, shape="spline", smoothing=1.3),
                           text=[f"{v:.0%}" for v in dm_display["margin_pct"]], textposition="top center", textfont=dict(color=ESPRESSO, size=DATA_LABEL_SIZE))
        T.dual_axis(fig_dm, t("тыс. ₽", "₽ thousand"), t("Маржинальность", "Margin"))
        fig_dm.update_layout(title=t(f"Выручка, маржа и маржинальность по направлениям — {selected_period}", f"Revenue, margin and margin % by direction — {selected_period}"))
        fig_dm.layout.yaxis2.tickformat = ".0%"
        st.plotly_chart(fig_dm, use_container_width=True)
        pptx_sections.append({"tab": t("Продукты/направления", "Products/Directions"), "heading": t(f"Маржинальность направлений — {selected_period}", f"Margin by direction — {selected_period}"), "figs": [fig_dm]})
    else:
        st.info(t("Нет данных по марже направлений — запустите etl/build_direction_margin.py", "No direction-margin data — run etl/build_direction_margin.py"))

    st.divider()
    T.section(t("Средний чек (ARPU) по направлению", "Average check (ARPU) by direction"))
    T.caption(t(
        "Выручка направления (модель) / количество услуг направления (CRM). Общий средний чек "
        "на Сводке считается иначе (вся выручка / консультации по ЗП), поэтому средневзвешенное "
        "по направлениям может не совпадать с ним на 1-2%.",
        "Direction revenue (model) / direction service count (CRM). The overall average check on the "
        "Summary tab is computed differently (total revenue / payroll consultations), so the direction-weighted "
        "average may differ from it by 1-2%.",
    ))
    arpu_cur = data["by_direction"][data["by_direction"]["month"].isin(cur_months)].groupby("direction").agg(
        revenue=("revenue", "sum"), n_services=("n_services", "sum")
    )
    arpu_cur = arpu_cur[arpu_cur["n_services"] > 0]
    arpu_cur["arpu"] = arpu_cur["revenue"] / arpu_cur["n_services"]
    arpu_plot = arpu_cur.reset_index()
    arpu_plot["direction"] = arpu_plot["direction"].map(dlabel)
    # Bubble вместо bar: X — кол-во услуг, Y — средний чек, размер = выручка
    # направления — три измерения в одном графике.
    fig_arpu = px.scatter(arpu_plot, x="n_services", y="arpu", size="revenue", color="direction",
                          size_max=54, labels={"n_services": t("Кол-во услуг", "Service count"), "arpu": t("Средний чек, ₽", "Average check, ₽"), "direction": t("Направление", "Direction")})
    fig_arpu.update_layout(title=dict(text=t(f"ARPU по направлению — {selected_period}", f"ARPU by direction — {selected_period}"), x=0.02, xanchor="left",
                                      y=0.97, yanchor="top", font=dict(size=14, color=TEXT_DARK)), margin=dict(t=60))
    # X — реальное число (кол-во услуг), а не месяц/категория, поэтому здесь
    # (в отличие от общего шаблона) нужны разряды через пробел явно — иначе при
    # зуме подписи оси показывают "1000" слитно вместо "1 000".
    fig_arpu.update_xaxes(tickformat=",.0f")
    fig_arpu.update_traces(marker=dict(line=dict(width=1, color="rgba(255,255,255,0.6)")))
    st.plotly_chart(fig_arpu, use_container_width=True)
    if len(arpu_cur):
        top_arpu_dir = arpu_cur["arpu"].idxmax()
        st.markdown(t(f"**Самый высокий средний чек — {top_arpu_dir} ({fmt_money(arpu_cur.loc[top_arpu_dir, 'arpu'])}).**",
                      f"**The highest average check is in {dlabel(top_arpu_dir)} ({fmt_money(arpu_cur.loc[top_arpu_dir, 'arpu'])}).**"))
    pptx_sections.append({"tab": t("Продукты/направления", "Products/Directions"), "heading": t(f"ARPU по направлению — {selected_period}", f"ARPU by direction — {selected_period}"), "figs": [fig_arpu]})

# ═══════════════════════ ПРОДОЛЖЕНИЕ: Продукты/направления (грейды, форматы, косметология, инъекции) ═══════════════════════
with tab2:
    T.section(t("Воронка записи", "Booking funnel"))
    if data["funnel"] is not None:
        st.markdown(f"**{ins.funnel_insight(data['funnel'], cur_months, prev_months, lang=LANG.lower())}**")
        funnel_cur = data["funnel"][data["funnel"]["month"].isin(cur_months)][
            ["n_booked", "n_completed", "n_cancelled", "n_rescheduled"]
        ].sum()
        funnel_prev = (
            data["funnel"][data["funnel"]["month"].isin(prev_months)][
                ["n_booked", "n_completed", "n_cancelled", "n_rescheduled"]
            ].sum()
            if prev_months else None
        )

        # Классический 4-уровневый funnel в стиле операционного отчёта: Запись ->
        # Состоявшиеся -> Перенос/Отмена. Отменённые и Перенесённые — не вложенные
        # подмножества друг друга, а два разных исхода незавершённой записи, поэтому
        # для чистоты формы располагаем их по убыванию значения (как в ручном отчёте).
        stage3_name, stage4_name = "Перенесённые", "Отменённые"
        stage3_val, stage4_val = funnel_cur["n_rescheduled"], funnel_cur["n_cancelled"]
        if stage4_val > stage3_val:
            stage3_name, stage4_name = stage4_name, stage3_name
            stage3_val, stage4_val = stage4_val, stage3_val

        STAGE_EN = {"Запись": "Booked", "Состоявшиеся": "Completed", "Перенесённые": "Rescheduled", "Отменённые": "Cancelled"}
        stage_names_base = ["Запись", "Состоявшиеся", stage3_name, stage4_name]
        stage_names_display = [t(n, STAGE_EN[n]) for n in stage_names_base]
        stage_values = [funnel_cur["n_booked"], funnel_cur["n_completed"], stage3_val, stage4_val]
        prev_map = None
        if funnel_prev is not None and funnel_prev["n_booked"]:
            prev_map = {
                "Запись": funnel_prev["n_booked"],
                "Состоявшиеся": funnel_prev["n_completed"],
                "Перенесённые": funnel_prev["n_rescheduled"],
                "Отменённые": funnel_prev["n_cancelled"],
            }

        # Плавная "текущая" воронка (area с градиентом и spline-сглаживанием) —
        # мягкий сужающийся силуэт вместо трапеций/плоских баров.
        fig_funnel = go.Figure()
        T.area_gradient(fig_funnel, stage_names_display, stage_values, t("Воронка", "Funnel"), color=DARK_GREEN, show_markers=True)
        n_stages = len(stage_names_base)
        funnel_baseline_y = -max(stage_values) * 0.10
        for i, (name, disp_name, val) in enumerate(zip(stage_names_base, stage_names_display, stage_values)):
            pct_of_start = val / stage_values[0] if stage_values[0] else 0
            xanchor = "left" if i == 0 else "right" if i == n_stages - 1 else "center"
            delta_html = ""
            if prev_map is not None:
                delta = pct_change(val, prev_map.get(name))
                if delta is not None:
                    # Для "Перенесённые"/"Отменённые" рост — плохо (как и в churn-
                    # карточках/burn rate ниже), поэтому цвет/стрелка инвертированы
                    # относительно "Запись"/"Состоявшиеся", где рост — хорошо.
                    bad_when_up = name in ("Перенесённые", "Отменённые")
                    is_positive = delta <= 0 if bad_when_up else delta >= 0
                    d_color = DARK_GREEN if is_positive else PINK
                    arrow = "↑" if delta >= 0 else "↓"
                    delta_html = f"  <span style='font-size:11px;color:{d_color}'>{arrow}{abs(delta):.0%}</span>"
            fig_funnel.add_annotation(
                x=disp_name, y=val, yshift=20, showarrow=False, xanchor=xanchor,
                text=f"<b>{fmt_num(val)}</b>{delta_html}",
                font=dict(size=15, color=TEXT_DARK, family=T.FONT_FAMILY),
            )
            fig_funnel.add_annotation(
                x=disp_name, y=funnel_baseline_y, showarrow=False, xanchor=xanchor,
                text=f"{pct_of_start:.0%}",
                font=dict(size=11, color=T.TEXT_MUTED, family=T.FONT_FAMILY),
            )
        fig_funnel.update_layout(
            title=t(f"Воронка записи — {selected_period}", f"Booking funnel — {selected_period}"), showlegend=False,
            yaxis_title=t("Записей", "Bookings"), margin=dict(b=64),
        )
        fig_funnel.update_yaxes(range=[funnel_baseline_y * 1.6, max(stage_values) * 1.28])
        fig_funnel.update_xaxes(automargin=True)
        st.plotly_chart(fig_funnel, use_container_width=True)
        loss_pct = (stage3_val + stage4_val) / funnel_cur["n_booked"] if funnel_cur["n_booked"] else None
        if loss_pct is not None:
            st.markdown(t(f"**{loss_pct:.0%}** записей теряются из-за переносов и отмен",
                          f"**{loss_pct:.0%}** of bookings are lost to reschedules and cancellations"))
        pptx_sections.append({"tab": t("Клиенты", "Clients"), "heading": ins.funnel_insight(data['funnel'], cur_months, prev_months, lang=LANG.lower()), "figs": [fig_funnel]})

        st.markdown(t("**Динамика конверсии, отмен и переносов по месяцам**", "**Conversion, cancellation and reschedule trend by month**"))
        funnel_trend = data["funnel"][data["funnel"]["month"].isin(HIST_MONTHS)].copy()
        fig_funnel_trend = go.Figure()
        fig_funnel_trend.add_scatter(
            x=funnel_trend["month"], y=funnel_trend["conversion_pct"], name=t("Конверсия", "Conversion"), mode="lines+markers+text",
            line=dict(color=DARK_GREEN, shape="spline", smoothing=1.3), text=[f"{v:.0%}" for v in funnel_trend["conversion_pct"]],
            textposition="top center", textfont=dict(color=DARK_GREEN, size=11),
        )
        fig_funnel_trend.add_scatter(
            x=funnel_trend["month"], y=funnel_trend["reschedule_pct"], name=t("% переносов", "% rescheduled"), mode="lines+markers+text",
            line=dict(color=ESPRESSO, shape="spline", smoothing=1.3), text=[f"{v:.0%}" for v in funnel_trend["reschedule_pct"]],
            textposition="top center", textfont=dict(color=ESPRESSO, size=11),
        )
        fig_funnel_trend.add_scatter(
            x=funnel_trend["month"], y=funnel_trend["cancellation_pct"], name=t("% отмен", "% cancelled"), mode="lines+markers+text",
            line=dict(color=PINK, shape="spline", smoothing=1.3), text=[f"{v:.0%}" for v in funnel_trend["cancellation_pct"]],
            textposition="bottom center", textfont=dict(color=PINK, size=11),
        )
        fig_funnel_trend.update_layout(title=t("Динамика конверсии и отмен", "Conversion and cancellation trend"), yaxis_tickformat=".0%")
        fig_funnel_trend.update_traces(line_shape="spline", line_smoothing=1.3, selector=dict(type="scatter"))
        st.plotly_chart(fig_funnel_trend, use_container_width=True)
        funnel_trend_text = ins.funnel_trend_insight(data["funnel"], HIST_MONTHS, lang=LANG.lower())
        st.markdown(f"_{funnel_trend_text}_")
        pptx_sections.append({"tab": t("Клиенты", "Clients"), "heading": funnel_trend_text, "figs": [fig_funnel_trend]})
    else:
        st.info(t(
            "Нет данных по записям/отменам/переносам — эта выгрузка из CRM ещё не подключена. "
            "Как только появится файл в raw_exports/, воронка появится здесь автоматически.",
            "No booking/cancellation/reschedule data — this CRM export isn't connected yet. "
            "Once a file appears in raw_exports/, the funnel will show up here automatically.",
        ))

    st.divider()
    T.section(t("Динамика среднего чека, LTV и клиентов", "Average check, LTV and client trend"))
    clients_text = ins.clients_insight(data['monthly_client'], cur_months, prev_months, avg_check_cur=avg_check_top, avg_check_prev=avg_check_prev_top, lang=LANG.lower())
    st.markdown(f"**{clients_text}**")
    fig5 = go.Figure()
    # Средний чек — та же формула, что на Сводке: выручка модели / консультации
    # по ЗП, а не пересчёт из CRM-выручки (иначе цифры на графике и в карточках
    # расходились на 1-3%).
    avg_check_by_month = monthly.copy()
    avg_check_by_month["avg_check"] = avg_check_by_month["revenue"] / consult_series.replace(0, pd.NA)
    fig5.add_bar(x=avg_check_by_month["visit_month"], y=avg_check_by_month["avg_check"], name=t("Средний чек, ₽", "Average check, ₽"), yaxis="y1", marker_color=SAGE)
    fig5.add_scatter(
        x=monthly["visit_month"], y=monthly["n_clients_new"], name=t("Новые клиенты", "New clients"), yaxis="y2", mode="lines+markers+text",
        line=dict(color=DARK_GREEN, shape="spline", smoothing=1.3), text=[f"{v:,.0f}".replace(",", " ") for v in monthly["n_clients_new"]],
        textposition="top center", textfont=dict(color=DARK_GREEN, size=11),
    )
    fig5.add_scatter(
        x=monthly["visit_month"], y=monthly["n_clients_repeat"], name=t("Повторные клиенты", "Returning clients"), yaxis="y2", mode="lines+markers+text",
        line=dict(color=ESPRESSO, shape="spline", smoothing=1.3), text=[f"{v:,.0f}".replace(",", " ") for v in monthly["n_clients_repeat"]],
        textposition="bottom center", textfont=dict(color=ESPRESSO, size=11),
    )
    fig5.update_layout(
        yaxis=dict(title=t("Средний чек, ₽", "Average check, ₽")), yaxis2=dict(title=t("Клиенты", "Clients"), overlaying="y", side="right"),
        title=dict(text=t(f"Средний чек, новые и повторные клиенты — {n_hist_months} мес. по {cur_months[-1]}",
                          f"Average check, new and returning clients — {n_hist_months} mo. through {cur_months[-1]}"),
                  x=0.02, xanchor="left", y=0.97, yanchor="top", font=dict(size=14, color=TEXT_DARK)),
        margin=dict(t=60),
    )
    st.plotly_chart(fig5, use_container_width=True)

    st.divider()
    # Не рядом с предыдущим графиком (были на разных уровнях из-за caption/
    # мультиселекта над этим) — отдельным блоком ниже.
    T.caption(t("LTV — накопленная выручка на клиента по когортам (месяц первого визита), более строгая метрика, чем разовый \"LTV месяца\"",
                "LTV — cumulative revenue per client by cohort (first-visit month), a stricter metric than the one-off \"monthly LTV\""))
    all_cohorts = sorted(data["cohort"]["cohort_month"].unique())
    selected_cohorts = st.multiselect(t("Когорты", "Cohorts"), all_cohorts, default=all_cohorts[:5], key="ltv_cohorts")
    sorted_selected_cohorts = sorted(selected_cohorts)
    filtered_cohort = data["cohort"][data["cohort"]["cohort_month"].isin(selected_cohorts)].copy()
    filtered_cohort["avg_cum_revenue_k"] = to_k(filtered_cohort["avg_cum_revenue"])
    # Набор визуально контрастных цветов темы (не плавный градиент — соседние
    # тона градиента сливались при выборе всех когорт сразу). Цвета чередуют
    # разные семейства (зелёный/розовый/синий/фиолетовый/терракота), чтобы
    # даже соседние по хронологии когорты не путались между собой.
    COHORT_COLOR_POOL = [
        TEXT_DARK, PINK, T.STEEL, ESPRESSO, T.GREEN_LABEL,
        T.NEGATIVE_DEEP, LIGHT_GREEN, T.CLAY, SAGE, DARK_GREEN,
    ]
    n_c = len(sorted_selected_cohorts)
    cohort_colors = [COHORT_COLOR_POOL[i % len(COHORT_COLOR_POOL)] for i in range(n_c)]
    fig6 = px.line(filtered_cohort, x="month_index", y="avg_cum_revenue_k", color="cohort_month", markers=True,
                    category_orders={"cohort_month": sorted_selected_cohorts},
                    color_discrete_sequence=cohort_colors,
                    labels={"month_index": t("Месяцев с первого визита", "Months since first visit"),
                            "avg_cum_revenue_k": t("Накопленная выручка на клиента, тыс. ₽", "Cumulative revenue per client, ₽ thousand"),
                            "cohort_month": t("Когорта", "Cohort")})
    fig6.update_traces(line_shape="spline", line_smoothing=1.3, selector=dict(type="scatter"))
    fig6.update_layout(title=dict(text=t("LTV (накопленная выручка на клиента) по когортам", "LTV (cumulative revenue per client) by cohort"), x=0.02, xanchor="left",
                                  y=0.97, yanchor="top", font=dict(size=14, color=TEXT_DARK)), margin=dict(t=60))
    st.plotly_chart(fig6, use_container_width=True)
    if selected_cohorts:
        st.markdown(f"_{ins.cohort_ltv_insight(data['cohort'], selected_cohorts, lang=LANG.lower())}_")
    pptx_sections.append({"tab": t("Клиенты", "Clients"), "heading": clients_text, "figs": [fig5, fig6]})

    st.divider()
    T.section(t("Отток (churn) по специальностям", "Churn by specialty"))
    T.caption(t(
        "Активные в месяце — уникальные пациенты с визитом в этом месяце. Ушло — из них "
        "те, кто не возвращался 90+ дней (на сегодня). Churn = ушло / активных. "
        "Последние месяцы, где ещё не прошло 90 дней, помечены как предварительные.",
        "Active in the month — unique patients with a visit that month. Churned — those "
        "of them who haven't returned in 90+ days (as of today). Churn = churned / active. "
        "The most recent months, where 90 days haven't passed yet, are flagged as preliminary.",
    ))
    if data["churn_specialty"] is not None:
        cs = data["churn_specialty"]
        confirmed = cs[~cs["preliminary"]]
        churn_cards = []
        churn_flags = []  # (spec, cur_v, hist_avg, delta_pp) — свои у каждой специальности исторические уровни
        for spec in SPEC_COLORS:
            spec_hist = confirmed[confirmed["specialty"] == spec].dropna(subset=["churn_rate"]).sort_values("month")
            last = spec_hist.tail(1)
            trend = spec_hist["churn_rate"].tail(6).tolist() if len(spec_hist) >= 2 else None
            if len(last):
                cur_v, prev_v = last.iloc[0]["churn_rate"], (spec_hist.iloc[-2]["churn_rate"] if len(spec_hist) >= 2 else None)
                delta = pct_change(cur_v, prev_v) if prev_v is not None else None
                # Для churn рост — это плохо: раскрашиваем по направлению по-другому,
                # чем для обычных метрик (рост = розовый, а не зелёный).
                positive = delta is None or delta <= 0
                churn_cards.append(T.metric_card(
                    t(f"Churn {spec.lower()} (посл. подтв.: {last.iloc[0]['month']})", f"Churn {dlabel(spec).lower()} (last conf.: {last.iloc[0]['month']})"), f"{cur_v:.0%}",
                    f"{abs(delta):.0%}" if delta is not None else None, positive, trend,
                ))
                # Порог — не абсолютное число (у косметологии churn исторически много выше,
                # чем у стоматологии — не сопоставимы напрямую), а отклонение от СВОЕГО
                # среднего за предыдущие подтверждённые месяцы.
                hist_prior = spec_hist.iloc[:-1]["churn_rate"]
                if len(hist_prior) >= 2:
                    hist_avg = hist_prior.mean()
                    delta_pp = cur_v - hist_avg
                    if delta_pp > 0.10:
                        churn_flags.append((spec, cur_v, hist_avg, delta_pp))
            else:
                churn_cards.append(T.metric_card(f"Churn {dlabel(spec).lower()}", t("н/д", "n/a")))
        T.metric_grid(churn_cards, cols=len(SPEC_COLORS))
        for spec, cur_v, hist_avg, delta_pp in churn_flags:
            banner = st.error if delta_pp > 0.20 else st.warning
            banner(t(f"Churn «{spec}» вырос до {cur_v:.0%} — на {delta_pp*100:.0f} п.п. выше своего среднего ({hist_avg:.0%}).",
                     f"Churn in {dlabel(spec)} grew to {cur_v:.0%} — {delta_pp*100:.0f} pp above its own average ({hist_avg:.0%})."))
        fig_churn = go.Figure()
        for spec, color in SPEC_COLORS.items():
            sub = cs[cs["specialty"] == spec].sort_values("month")
            conf = sub[~sub["preliminary"]]
            prelim = sub[sub["preliminary"]]
            fig_churn.add_scatter(
                x=conf["month"], y=conf["churn_rate"], name=dlabel(spec), mode="lines+markers+text",
                line=dict(color=color, shape="spline", smoothing=1.3), text=[f"{v:.0%}" for v in conf["churn_rate"]],
                textposition="top center", textfont=dict(color=color, size=11),
            )
            if len(prelim):
                fig_churn.add_scatter(
                    x=prelim["month"], y=prelim["churn_rate"], name=t(f"{spec} (предв.)", f"{dlabel(spec)} (prelim.)"), mode="lines+markers+text",
                    line=dict(color=color, dash="dot", shape="spline", smoothing=1.3), showlegend=True,
                    text=[f"{v:.0%}" for v in prelim["churn_rate"]],
                    textposition="top center", textfont=dict(color=color, size=11),
                )
        fig_churn.update_layout(
            title=t("Churn rate по месяцам (по специальностям)", "Churn rate by month (by specialty)"),
            yaxis_tickformat=".0%", yaxis_range=[0, 1.12],
        )
        fig_churn.update_traces(line_shape="spline", line_smoothing=1.3, selector=dict(type="scatter"))
        st.plotly_chart(fig_churn, use_container_width=True)
        churn_text = ins.churn_insight(cs, lang=LANG.lower())
        st.markdown(f"_{churn_text}_")
        pptx_sections.append({"tab": t("Клиенты", "Clients"), "heading": churn_text, "figs": [fig_churn]})
    else:
        st.info(t("Нет данных по оттоку из таблицы — запустите etl/load_retention_from_sheet.py (нужен интернет).",
                  "No churn data from the sheet — run etl/load_retention_from_sheet.py (needs internet)."))

    st.divider()
    T.section(t("Удержание пациентов и целевые уровни", "Patient retention and target levels"))
    T.caption(t(
        "Возврат на 2-й приём и удержание через 3/6 месяцев по специальностям, с целевыми "
        "ориентирами (средний/хороший/отличный). Разовая консультация — нормальный исход "
        "для медицины, не «провал». Источник — Google-таблица удержания.",
        "2nd-visit return and 3/6-month retention by specialty, with target benchmarks "
        "(average/good/excellent). A single consultation is a normal outcome in "
        "healthcare, not a \"failure\". Source — the retention Google Sheet.",
    ))
    if data["retention_scorecard"] is not None:
        sc = data["retention_scorecard"]
        sc_cols = st.columns(len(SPEC_COLORS))
        sc_figs = []
        for sc_col, spec in zip(sc_cols, SPEC_COLORS):
            spec_sc = sc[(sc["specialty"] == spec) & sc["value"].notna()].copy()
            with sc_col:
                st.markdown(f"**{dlabel(spec)}**")
                if spec_sc.empty:
                    T.caption(t("Нет данных за период.", "No data for the period."))
                    continue
                # Та же плавная area-градиент воронка, что и "Воронка записи" —
                # метрики естественно убывают (возврат 2-й > удерж. 3мес > 6мес),
                # это тоже, по сути, воронка удержания.
                # Подписи оси X — читаемые русские названия, а не сырые коды
                # метрик (return_2nd/retention_3mo/retention_6mo) из данных.
                _metric_display = {"return_2nd": t("Возврат на 2-й", "2nd-visit return"), "retention_3mo": t("Удерж. 3 мес", "3-mo. retention"), "retention_6mo": t("Удерж. 6 мес", "6-mo. retention")}
                metric_names = [_metric_display.get(m, m) for m in spec_sc["metric"]]
                metric_vals = spec_sc["value"].tolist()
                fig_sc = go.Figure()
                T.area_gradient(fig_sc, metric_names, metric_vals, dlabel(spec), color=DARK_GREEN, show_markers=True)
                n_m = len(metric_names)
                for i, (_, row) in enumerate(spec_sc.iterrows()):
                    xanchor = "left" if i == 0 else "right" if i == n_m - 1 else "center"
                    label = metric_names[i]
                    fig_sc.add_annotation(
                        x=label, y=row["value"], yshift=20, showarrow=False, xanchor=xanchor,
                        text=f"<b>{row['value']:.0%}</b>", font=dict(size=14, color=TEXT_DARK, family=T.FONT_FAMILY),
                    )
                fig_sc.update_layout(
                    title=dict(text=t(f"{spec}: воронка удержания", f"{dlabel(spec)}: retention funnel"), x=0.02, xanchor="left", y=0.97, yanchor="top",
                              font=dict(size=13, color=TEXT_DARK)),
                    showlegend=False, yaxis=dict(tickformat=".0%"), margin=dict(t=54, b=10),
                )
                fig_sc.update_yaxes(range=[0, max(metric_vals) * 1.3 if metric_vals else 1])
                st.plotly_chart(fig_sc, use_container_width=True)
                sc_figs.append(fig_sc)
                # Целевые ориентиры — текстом под графиком, не аннотациями внутри
                # него: при 3 метриках подписи бенчмарков налезали друг на друга
                # и были нечитаемы.
                def _benchmark_label(b):
                    return b.replace("хороший диапазон", "good range").replace("средний диапазон", "average range") if LANG == "EN" else b
                benchmark_line = " · ".join(
                    f"{metric_names[i]}: {t('бенчмарк', 'benchmark')} {_benchmark_label(row['benchmark'])}" + (f" (N={fmt_num(row['n'])})" if pd.notna(row["n"]) else "")
                    for i, (_, row) in enumerate(spec_sc.iterrows())
                )
                T.caption(benchmark_line)
        retention_sc_text = ins.retention_scorecard_insight(sc, lang=LANG.lower())
        st.markdown(f"_{retention_sc_text}_")
        if sc_figs:
            pptx_sections.append({"tab": t("Клиенты", "Clients"), "heading": retention_sc_text, "figs": sc_figs})

        if data["cohort_retention"] is not None:
            cr = data["cohort_retention"].dropna(subset=["cohort_month"])
            fig_ret = go.Figure()
            for spec, color in SPEC_COLORS.items():
                sub = cr[cr["specialty"] == spec].sort_values("cohort_month")
                fig_ret.add_scatter(x=sub["cohort_month"], y=sub["return_2nd"], name=t(f"{spec}: возврат 2-й", f"{dlabel(spec)}: 2nd-visit return"), mode="lines+markers", line=dict(color=color, shape="spline", smoothing=1.3))
                fig_ret.add_scatter(x=sub["cohort_month"], y=sub["retention_3mo"], name=t(f"{spec}: удерж. 3 мес", f"{dlabel(spec)}: 3-mo. retention"), mode="lines+markers", line=dict(color=color, dash="dash", shape="spline", smoothing=1.3))
            fig_ret.update_layout(
                title=dict(text=t("Удержание пациентов по когортам", "Patient retention by cohort"), x=0.02, xanchor="left", y=0.97, yanchor="top",
                          font=dict(size=14, color=TEXT_DARK)),
                yaxis_tickformat=".0%", margin=dict(t=60),
            )
            st.plotly_chart(fig_ret, use_container_width=True)
            retention_cohort_text = ins.retention_cohort_insight(cr, lang=LANG.lower())
            st.markdown(f"_{retention_cohort_text}_")
            pptx_sections.append({"tab": t("Клиенты", "Clients"), "heading": retention_cohort_text, "figs": [fig_ret]})
    else:
        st.info(t("Нет данных по удержанию из таблицы — запустите etl/load_retention_from_sheet.py (нужен интернет).",
                  "No retention data from the sheet — run etl/load_retention_from_sheet.py (needs internet)."))

    if data["cohort_retention"] is not None:
        st.divider()
        T.section(t("LTV, выручка за визит и интервал по когортам", "LTV, revenue per visit and interval by cohort"))
        T.caption(t(
            "LTV — суммарная выручка с пациента на сегодня (старые когорты естественно выше — "
            "было больше времени на визиты). Выручка за визит = LTV / число сессий. "
            "Средний интервал — сколько дней в среднем между визитами одного пациента.",
            "LTV — total revenue per patient to date (older cohorts are naturally higher — "
            "they've had more time to visit). Revenue per visit = LTV / number of sessions. "
            "Average interval — average days between one patient's visits.",
        ))
        cr = data["cohort_retention"].dropna(subset=["cohort_month"])
        col1, col2 = st.columns(2)
        with col1:
            fig_ltv_sp = go.Figure()
            for spec, color in SPEC_COLORS.items():
                sub = cr[cr["specialty"] == spec].sort_values("cohort_month")
                ltv_k = to_k(sub["ltv"])
                fig_ltv_sp.add_scatter(
                    x=sub["cohort_month"], y=ltv_k, name=dlabel(spec), mode="lines+markers+text", line=dict(color=color, shape="spline", smoothing=1.3),
                    text=[f"{v:,.0f}".replace(",", " ") if pd.notna(v) else "" for v in ltv_k],
                    textposition="top center", textfont=dict(color=color, size=11),
                )
            fig_ltv_sp.update_layout(
                title=dict(text=t("LTV по месяцам когорты, тыс. ₽", "LTV by cohort month, ₽ thousand"), x=0.02, xanchor="left", y=0.97, yanchor="top",
                          font=dict(size=13, color=TEXT_DARK)),
                yaxis_title=t("тыс. ₽", "₽ thousand"), margin=dict(t=56),
            )
            st.plotly_chart(fig_ltv_sp, use_container_width=True)
        with col2:
            fig_interval = go.Figure()
            for spec, color in SPEC_COLORS.items():
                sub = cr[cr["specialty"] == spec].dropna(subset=["avg_interval_days"]).sort_values("cohort_month")
                fig_interval.add_scatter(
                    x=sub["cohort_month"], y=sub["avg_interval_days"], name=dlabel(spec), mode="lines+markers+text", line=dict(color=color, shape="spline", smoothing=1.3),
                    text=[f"{v:.0f}" for v in sub["avg_interval_days"]],
                    textposition="top center", textfont=dict(color=color, size=11),
                )
            fig_interval.update_layout(
                title=dict(text=t("Средний интервал между визитами, дней", "Average interval between visits, days"), x=0.02, xanchor="left", y=0.97, yanchor="top",
                          font=dict(size=13, color=TEXT_DARK)),
                yaxis_title=t("дней", "days"), margin=dict(t=56),
            )
            st.plotly_chart(fig_interval, use_container_width=True)
        ltv_interval_text = ins.ltv_interval_insight(cr, lang=LANG.lower())
        st.markdown(f"_{ltv_interval_text}_")
        pptx_sections.append({"tab": t("Клиенты", "Clients"), "heading": ltv_interval_text, "figs": [fig_ltv_sp, fig_interval]})

with tab3:
    T.section(t("Загрузка кабинетов", "Room utilization"))
    st.markdown(f"**{ins.rooms_insight(data['room_util'], cur_months, prev_months, lang=LANG.lower())}**")
    room_cur = data["room_util"][data["room_util"]["month"].isin(cur_months)].groupby("specialty").agg(
        capacity_hours=("capacity_hours", "sum"), actual_hours=("actual_hours", "sum")
    )
    room_cur["utilization_pct"] = room_cur["actual_hours"] / room_cur["capacity_hours"]
    util_total = room_cur["actual_hours"].sum() / room_cur["capacity_hours"].sum() if room_cur["capacity_hours"].sum() else 0

    room_prev = data["room_util"][data["room_util"]["month"].isin(prev_months)].groupby("specialty").agg(
        capacity_hours=("capacity_hours", "sum"), actual_hours=("actual_hours", "sum")
    ) if prev_months else None
    util_total_prev = (room_prev["actual_hours"].sum() / room_prev["capacity_hours"].sum()) if (room_prev is not None and room_prev["capacity_hours"].sum()) else None

    room_gauges = [(splabel(spec), row["utilization_pct"],
                   (room_prev.loc[spec, "actual_hours"] / room_prev.loc[spec, "capacity_hours"]) if (room_prev is not None and spec in room_prev.index and room_prev.loc[spec, "capacity_hours"]) else None)
                   for spec, row in room_cur.iterrows()] + [(t("Итого", "Total"), util_total, util_total_prev)]
    gauge_cols = st.columns(len(room_gauges))
    gauge_figs = []
    for col, (label, pct, prev_pct) in zip(gauge_cols, room_gauges):
        fig_g = T.gauge_donut(pct, label, color=DARK_GREEN if pct >= 1 else T.BRAND)
        col.plotly_chart(fig_g, use_container_width=True)
        # Явная дельта в п.п. к прошлому периоду под каждым gauge.
        delta_pp = (pct - prev_pct) * 100 if prev_pct is not None else None
        if delta_pp is not None:
            d_color = T.GREEN_VALUE if delta_pp >= 0 else T.NEGATIVE_DEEP
            arrow = "↑" if delta_pp >= 0 else "↓"
            col.markdown(f"<div style='text-align:center;color:{d_color};font-size:0.85rem;font-weight:600;'>{arrow} {abs(delta_pp):.0f} {t('п.п. к пред. периоду', 'pp vs. prior period')}</div>", unsafe_allow_html=True)
    T.caption(t("Расчёт по номинальной длительности услуги (стоматология) и 60 мин/визит (косметология) — методология сверена с ручным отчётом (1 кабинет стоматологии + 1 кабинет косметологии, 12ч/день).",
                "Calculated from nominal service duration (dentistry) and 60 min/visit (cosmetology) — methodology matches the manual report (1 dentistry room + 1 cosmetology room, 12h/day)."))

    # Пороговый флаг по загрузке кабинетов (итого): <20% — критично низкая
    # загрузка, 20-35% — по-прежнему низкая. Ориентир по факту: за всю историю
    # загрузка ни разу не поднималась выше ~31% — пороги отражают именно это,
    # не абстрактный отраслевой стандарт.
    if util_total < 0.20:
        st.error(t(f"Загрузка кабинетов критически низкая: {util_total:.0%} (порог 20%).", f"Room utilization is critically low: {util_total:.0%} (threshold 20%)."))
    elif util_total < 0.35:
        st.warning(t(f"Загрузка кабинетов ниже целевой: {util_total:.0%} (порог 35%).", f"Room utilization is below target: {util_total:.0%} (threshold 35%)."))
    pptx_sections.append({"tab": t("Операционная эффективность", "Operations"), "heading": ins.rooms_insight(data['room_util'], cur_months, prev_months, lang=LANG.lower()), "figs": gauge_figs})


    st.divider()
    T.section(t("Динамика проведённых консультаций", "Consultations over time"))
    # Консультации — по ЗП (фактически оплаченные визиты), не по CRM-выгрузке,
    # для согласованности со Сводкой и Блок 1.
    cons_by_month = data["monthly_client"][["visit_month"]].drop_duplicates()
    cons_by_month = cons_by_month[cons_by_month["visit_month"].isin(HIST_MONTHS)].copy()
    if VISITS_BY_MONTH_ACTUAL is not None:
        cons_by_month["n_visits"] = cons_by_month["visit_month"].map(VISITS_BY_MONTH_ACTUAL).fillna(0)
    else:
        mc_fallback = data["monthly_client"].set_index("visit_month")
        cons_by_month["n_visits"] = cons_by_month["visit_month"].map(
            mc_fallback["n_visits_new"] + mc_fallback["n_visits_repeat"]
        )
    fig11 = px.line(cons_by_month, x="visit_month", y="n_visits", markers=True,
                     labels={"visit_month": t("Месяц", "Month"), "n_visits": t("Консультации", "Consultations")})
    fig11.update_traces(
        mode="lines+markers+text", line_shape="spline", line_smoothing=1.3,
        text=[fmt_num(v) for v in cons_by_month["n_visits"]],
        textposition="top center", textfont=dict(color=DARK_GREEN, size=11),
    )
    fig11.update_layout(title=dict(text=t("Динамика проведённых консультаций", "Consultations over time"), x=0.02, xanchor="left", y=0.97, yanchor="top",
                                   font=dict(size=14, color=TEXT_DARK)), margin=dict(t=60))
    st.plotly_chart(fig11, use_container_width=True)
    if len(cons_by_month) >= 2:
        first_v, last_v = cons_by_month.iloc[0]["n_visits"], cons_by_month.iloc[-1]["n_visits"]
        trend_delta = pct_change(last_v, first_v)
        if trend_delta is not None:
            trend_word = t("выросли", "grew") if trend_delta >= 0 else t("снизились", "declined")
            st.markdown(t(f"**Консультации {trend_word} на {abs(trend_delta):.0%} с {cons_by_month.iloc[0]['visit_month']} по {cons_by_month.iloc[-1]['visit_month']}.**",
                          f"**Consultations {trend_word} {abs(trend_delta):.0%} from {cons_by_month.iloc[0]['visit_month']} to {cons_by_month.iloc[-1]['visit_month']}.**"))
    pptx_sections.append({"tab": t("Операционная эффективность", "Operations"), "heading": t("Динамика проведённых консультаций", "Consultations over time"), "figs": [fig11]})

    st.divider()

    st.divider()
    T.section(t("Рост команды врачей", "Doctor team growth"))
    st.markdown(f"**{ins.doctors_insight(data['team'], cur_months, prev_months, visits_cur=n_visits_actual(cur_months), visits_prev=n_visits_actual(prev_months) if prev_months else None, lang=LANG.lower())}**")
    # n_doctors — снапшот последнего месяца периода (не max по всем месяцам,
    # см. комментарий у doctors_cur_top в Сводке); n_visits по-прежнему сумма
    # за весь период — это разные по природе величины (остаток vs поток).
    team_cur = data["team"][data["team"]["month"].isin(cur_months)].groupby("specialty").agg(n_visits=("n_visits", "sum"))
    team_cur["n_doctors"] = data["team"][data["team"]["month"] == cur_months[-1]].groupby("specialty")["n_doctors"].sum()
    team_cur["n_doctors"] = team_cur["n_doctors"].fillna(0)
    if prev_months:
        team_prev = data["team"][data["team"]["month"].isin(prev_months)].groupby("specialty").agg(n_visits=("n_visits", "sum"))
        team_prev["n_doctors"] = data["team"][data["team"]["month"] == prev_months[-1]].groupby("specialty")["n_doctors"].sum()
        team_prev["n_doctors"] = team_prev["n_doctors"].fillna(0)
    else:
        team_prev = None

    total_doctors_cur = team_cur["n_doctors"].sum()
    total_doctors_prev = team_prev["n_doctors"].sum() if prev_months else None
    # Визиты — по ЗП, как везде на дашборде (team.n_visits — CRM-счётчик,
    # он на несколько визитов выше и расходился со Сводкой).
    total_visits_cur = n_visits_actual(cur_months) or team_cur["n_visits"].sum()
    total_visits_prev = (n_visits_actual(prev_months) or team_prev["n_visits"].sum()) if prev_months else None
    doctors_hist_team = data["team"][data["team"]["month"].isin(HIST_MONTHS[-6:])].groupby("month")["n_doctors"].sum()
    # Визиты по тем же месяцам и тому же канону, что и total_visits_cur (n_visits_actual
    # с фолбэком на CRM-счётчик ЗП) — иначе спарклайн карточки не совпадёт с её же цифрой.
    visits_hist_team = [
        n_visits_actual([m]) or data["team"][data["team"]["month"] == m]["n_visits"].sum()
        for m in HIST_MONTHS[-6:]
    ]
    visits_delta = pct_change(total_visits_cur, total_visits_prev) if prev_months else None
    doctors_delta = pct_change(total_doctors_cur, total_doctors_prev) if prev_months else None
    # Явная дельта к прошлому периоду в карточках (раньше была видна только
    # визуально по высоте столбцов, без числа), плюс доля врачей по направлениям.
    T.metric_grid([
        T.metric_card(t("Визиты", "Visits"), fmt_num(total_visits_cur), f"{abs(visits_delta):.0%}" if visits_delta is not None else None,
                      visits_delta is None or visits_delta >= 0, visits_hist_team),
        T.metric_card(t("Врачи", "Doctors"), fmt_num(total_doctors_cur), f"{abs(doctors_delta):.0%}" if doctors_delta is not None else None,
                      doctors_delta is None or doctors_delta >= 0, doctors_hist_team.tolist()),
    ], cols=2)
    fig8 = px.pie(values=team_cur["n_doctors"], names=[splabel(s) for s in team_cur.index], hole=0.5,
                   color_discrete_sequence=[DARK_GREEN, LIGHT_GREEN, ESPRESSO, GRAY])
    fig8.update_traces(texttemplate="%{percent:.0%}")
    fig8.update_layout(
        title=dict(text=t(f"Доля врачей по направлениям — {selected_period}", f"Doctor share by specialty — {selected_period}"), x=0.02, xanchor="left",
                  y=0.97, yanchor="top", font=dict(size=13, color=TEXT_DARK)),
        margin=dict(t=56),
    )
    st.plotly_chart(fig8, use_container_width=True)
    pptx_sections.append({"tab": t("Операционная эффективность", "Operations"), "heading": ins.doctors_insight(data['team'], cur_months, prev_months, visits_cur=n_visits_actual(cur_months), visits_prev=n_visits_actual(prev_months) if prev_months else None, lang=LANG.lower()), "figs": [fig8]})

    st.divider()
    T.section(t("Загрузка врачей и выручка топ-5 специалистов", "Top-5 specialist workload and revenue"))
    # Топ-5 врачей и тезис — из единого источника (ЗП, тот же что "Консультации"
    # и Юнит-экономика). Раньше выручка бралась из файла загрузки врачей, визиты —
    # из CRM, а тезис считался по третьему набору — доли на графике и в тексте
    # не совпадали между собой.
    top5_text = ins.top5_insight(DOCTOR_PERF, 'month', cur_months, lang=LANG.lower())
    st.markdown(f"**{top5_text}**")
    doc_perf_cur = DOCTOR_PERF[DOCTOR_PERF["month"].isin(cur_months)].groupby("doctor").agg(
        n_visits=("n_visits", "sum"), revenue=("revenue", "sum")
    )
    top5_bubble = doc_perf_cur.sort_values("revenue", ascending=False).head(5).reset_index()
    top5_bubble["avg_check"] = top5_bubble["revenue"] / top5_bubble["n_visits"]
    top5_bubble["revenue_k"] = to_k(top5_bubble["revenue"])
    fig9 = px.scatter(top5_bubble, x="avg_check", y="n_visits", size="revenue", color="doctor", text="doctor",
                       title=t(f"Топ-5 врачей: чек x консультации, размер = выручка — {selected_period}", f"Top-5 doctors: check x consultations, size = revenue — {selected_period}"),
                       labels={"avg_check": t("Средний чек, ₽", "Average check, ₽"), "n_visits": t("Кол-во консультаций", "Consultation count"), "doctor": t("Врач", "Doctor")})
    fig9.update_traces(textposition="top center", textfont=dict(color=T.TEXT_MUTED, size=11, family=T.FONT_FAMILY),
                        line_shape="spline", line_smoothing=1.3, selector=dict(type="scatter"))
    # Запас по краям оси X — иначе подпись крайнего пузыря (самое длинное ФИО,
    # например "Кузьмина Анастасия Романовна") обрезается границей области графика.
    x_span = top5_bubble["avg_check"].max() - top5_bubble["avg_check"].min()
    x_pad = x_span * 0.35 if x_span else top5_bubble["avg_check"].max() * 0.2
    fig9.update_xaxes(range=[top5_bubble["avg_check"].min() - x_pad, top5_bubble["avg_check"].max() + x_pad])
    st.plotly_chart(fig9, use_container_width=True)
    pptx_sections.append({"tab": t("Операционная эффективность", "Operations"), "heading": top5_text, "figs": [fig9]})

    with st.expander(t("Все врачи за период — детализация", "All doctors for the period — detail")):
        doc_hours = data["doctors_util"][data["doctors_util"]["month"].isin(cur_months)].groupby("doctor")["closed_hours"].sum()
        doc_detail_table = doc_perf_cur.sort_values("revenue", ascending=False).copy()
        doc_detail_table["closed_hours"] = doc_hours.reindex(doc_detail_table.index)
        st.dataframe(doc_detail_table.style.format({"revenue": fmt_num, "n_visits": fmt_num, "closed_hours": "{:.1f}"}), use_container_width=True)

    st.divider()
    T.section(t("Загрузка врача в часах (план/факт)", "Doctor workload in hours (plan/actual)"))
    util_cur_ops = data["doctors_util"][data["doctors_util"]["month"].isin(cur_months)].groupby("doctor").agg(
        planned_hours=("planned_hours", "sum"), closed_hours=("closed_hours", "sum")
    ).sort_values("planned_hours", ascending=False)
    if util_cur_ops["planned_hours"].sum():
        fill_rate_avg = util_cur_ops["closed_hours"].sum() / util_cur_ops["planned_hours"].sum()
        under_filled = util_cur_ops[util_cur_ops["closed_hours"] < util_cur_ops["planned_hours"]]
        st.markdown(t(f"**Средняя загрузка по врачам — {fill_rate_avg:.0%} от плана; ниже плана — {len(under_filled)} из {len(util_cur_ops)} врачей.**",
                      f"**Average doctor fill rate — {fill_rate_avg:.0%} of plan; below plan — {len(under_filled)} of {len(util_cur_ops)} doctors.**"))
    hours_html = "".join(
        T.progress_bar(
            doctor, (row["closed_hours"] / row["planned_hours"]) if row["planned_hours"] else 0,
            t(f"{row['closed_hours']:.0f} / {row['planned_hours']:.0f} ч", f"{row['closed_hours']:.0f} / {row['planned_hours']:.0f} h"),
        )
        for doctor, row in util_cur_ops.iterrows()
    )
    st.markdown(hours_html, unsafe_allow_html=True)
    # Progress-бары не экспортируются как изображение в PPTX (нет figure) —
    # секция сюда не добавляется, как и раньше для нечисловых блоков дашборда.

    st.divider()
    T.section(t("Выручка на 1 врача в месяц", "Revenue per doctor per month"))
    # Снапшот последнего месяца периода — см. комментарий у doctors_cur_top в Сводке.
    doctors_cur_count = data["team"][data["team"]["month"] == cur_months[-1]]["n_doctors"].sum()
    revenue_cur_ops = sum_col(data["pnl"], "month", cur_months, "revenue")
    revenue_per_doctor_cur = revenue_cur_ops / doctors_cur_count if doctors_cur_count else None
    doctors_prev_count = data["team"][data["team"]["month"] == prev_months[-1]]["n_doctors"].sum() if prev_months else None
    revenue_prev_ops = sum_col(data["pnl"], "month", prev_months, "revenue") if prev_months else None
    revenue_per_doctor_prev = (revenue_prev_ops / doctors_prev_count) if (prev_months and doctors_prev_count) else None

    rpd_by_month = data["team"][data["team"]["month"].isin(HIST_MONTHS)].groupby("month")["n_doctors"].sum().reset_index().merge(
        data["pnl"][["month", "revenue"]], on="month", how="inner"
    ).sort_values("month")
    rpd_by_month["revenue_per_doctor"] = rpd_by_month["revenue"] / rpd_by_month["n_doctors"]

    rpd_trend = rpd_by_month["revenue_per_doctor"].tail(6).tolist() if len(rpd_by_month) >= 2 else None
    rpd_delta = pct_change(revenue_per_doctor_cur, revenue_per_doctor_prev) if prev_months else None
    rpd_card = T.metric_card(
        t("Выручка на 1 врача за период", "Revenue per doctor for period"), fmt_money(revenue_per_doctor_cur),
        f"{abs(rpd_delta):.0%}" if rpd_delta is not None else None,
        rpd_delta is None or rpd_delta >= 0, rpd_trend,
    )
    T.metric_grid([rpd_card], cols=2)

    fig_rpd = go.Figure()
    fig_rpd.add_scatter(
        x=rpd_by_month["month"], y=rpd_by_month["revenue_per_doctor"], name=t("Выручка на врача", "Revenue per doctor"), mode="lines+markers+text",
        line=dict(color=DARK_GREEN, shape="spline", smoothing=1.3), text=[fmt_num(v) for v in rpd_by_month["revenue_per_doctor"]],
        textposition="top center", textfont=dict(color=DARK_GREEN, size=11),
    )
    fig_rpd.update_layout(
        title=dict(text=t("Выручка на 1 врача по месяцам", "Revenue per doctor by month"), x=0.02, xanchor="left", y=0.97, yanchor="top",
                  font=dict(size=14, color=TEXT_DARK)),
        yaxis_title=t("Выручка на врача, ₽", "Revenue per doctor, ₽"), showlegend=False, margin=dict(t=60),
    )
    st.plotly_chart(fig_rpd, use_container_width=True)
    if rpd_delta is not None:
        rpd_word = t("выросла", "grew") if rpd_delta >= 0 else t("снизилась", "declined")
        st.markdown(t(f"**Выручка на врача {rpd_word} на {abs(rpd_delta):.0%} к прошлому периоду.**",
                      f"**Revenue per doctor {rpd_word} {abs(rpd_delta):.0%} vs. the prior period.**"))
    pptx_sections.append({"tab": t("Операционная эффективность", "Operations"), "heading": t("Выручка на 1 врача по месяцам", "Revenue per doctor by month"), "figs": [fig_rpd]})


with tab4:
    T.section(t("Распределение консультаций по грейдам", "Consultation share by grade"))
    grade_share = data["grade_metrics"][data["grade_metrics"]["month"].isin(HIST_MONTHS)].pivot(index="month", columns="grade", values="n_visits").fillna(0)
    grade_share_pct = grade_share.div(grade_share.sum(axis=1), axis=0)
    fig12 = go.Figure()
    for g in grade_share_pct.columns:
        fig12.add_scatter(x=grade_share_pct.index, y=grade_share_pct[g], name=glabel(g), mode="lines+markers", stackgroup="one")
    fig12.update_layout(title=t("Распределение консультаций по грейдам", "Consultation share by grade"), yaxis_tickformat=".0%")
    fig12.update_traces(line_shape="spline", line_smoothing=1.3, selector=dict(type="scatter"))
    st.plotly_chart(fig12, use_container_width=True)
    if len(grade_share_pct):
        last_row = grade_share_pct.iloc[-1]
        top_grade = last_row.idxmax()
        st.markdown(t(f"**Больше всего консультаций в {grade_share_pct.index[-1]} — у грейда {top_grade} ({last_row[top_grade]:.0%}).**",
                      f"**{grade_share_pct.index[-1]} had the most consultations from {glabel(top_grade)} ({last_row[top_grade]:.0%}).**"))
    pptx_sections.append({"tab": t("Продукты/направления", "Products/Directions"), "heading": t("Распределение консультаций по грейдам", "Consultation share by grade"), "figs": [fig12]})

    T.section(t("Распределение консультаций по длительности приёма (внутри грейдов)", "Consultation share by visit length (within grades)"))
    fmt_cur = data["format_by_grade"][data["format_by_grade"]["month"].isin(cur_months)]
    fmt_pivot = fmt_cur.groupby(["grade", "format_min"])["n_visits"].sum().unstack("format_min").fillna(0)
    fmt_pivot_pct = fmt_pivot.div(fmt_pivot.sum(axis=1), axis=0)
    # Только оттенки зелёного (в тон остальной палитре), но с явным разбросом
    # по светлоте — от самого тёмного до самого светлого, а не три близких по
    # тону зелёных, которые сливались на стековом графике.
    fmt_colors = {25: TEXT_DARK, 50: LIGHT_GREEN, 80: SAGE}
    fig13 = go.Figure()
    for fmt_m in sorted(fmt_pivot_pct.columns):
        fig13.add_bar(
            x=[glabel(g) for g in fmt_pivot_pct.index], y=fmt_pivot_pct[fmt_m], name=t(f"{int(fmt_m)} мин", f"{int(fmt_m)} min"),
            marker_color=fmt_colors.get(int(fmt_m), GRAY),
            text=[f"{v:.0%}" for v in fmt_pivot_pct[fmt_m]], textposition="inside",
            textfont=dict(size=DATA_LABEL_SIZE), constraintext="none",
        )
    fig13.update_layout(barmode="stack", title=t(f"Форматы приёмов по грейдам — {selected_period}", f"Visit formats by grade — {selected_period}"), yaxis_tickformat=".0%")
    st.plotly_chart(fig13, use_container_width=True)
    if len(fmt_pivot_pct):
        longest_fmt = int(sorted(fmt_pivot_pct.columns)[-1])
        avg_share_longest = fmt_pivot_pct[max(fmt_pivot_pct.columns)].mean()
        st.markdown(t(f"**Самый длинный формат ({longest_fmt} мин) в среднем занимает {avg_share_longest:.0%} визитов по грейдам.**",
                      f"**The longest format ({longest_fmt} min) accounts for {avg_share_longest:.0%} of visits on average across grades.**"))
    pptx_sections.append({"tab": t("Продукты/направления", "Products/Directions"), "heading": t("Распределение форматов по грейдам", "Consultation share by visit length (within grades)"), "figs": [fig13]})

# ═══════════════════════ БЛОК 3: Направления и эффективность ═══════════════════════
with tab4:
    st.divider()
    T.section(t("Стоматология: выручка и загрузка специалистов по грейдам", "Dentistry: revenue and specialist workload by grade"))
    st.markdown(f"**{ins.grade_insight(data['grade_metrics'], cur_months, prev_months, lang=LANG.lower())}**")
    st.markdown(
        f'<p style="{CAPTION_STYLE}">{t(
            "Детализация по грейдам считается по CRM-визитам (в ЗП нет длительности и "
            "форматов приёма), поэтому суммы могут отличаться от вкладки «Юнит-экономика» на несколько визитов, "
            "ещё не подтверждённых в ЗП.",
            "Grade-level detail is computed from CRM visits (payroll data has no duration/format), so totals "
            "may differ from the Unit Economics tab by a few visits not yet confirmed in payroll.",
        )}</p>',
        unsafe_allow_html=True,
    )
    gm_cur = data["grade_metrics"][data["grade_metrics"]["month"].isin(cur_months)].groupby("grade").agg(
        revenue=("revenue", "sum"), n_visits=("n_visits", "sum"), n_doctors=("n_doctors", "max"),
        total_duration_min=("total_duration_min", "sum"),
    )
    gm_cur["avg_check"] = gm_cur["revenue"] / gm_cur["n_visits"]
    gm_cur["revenue_per_doctor"] = gm_cur["revenue"] / gm_cur["n_doctors"]
    gm_cur["revenue_per_min"] = gm_cur["revenue"] / gm_cur["total_duration_min"]
    gm_cur["visits_per_doctor"] = gm_cur["n_visits"] / gm_cur["n_doctors"]

    # Сводные карточки по направлению (Стоматология) — как на Сводке/Косметологии:
    # выручка/визиты/врачи за период со спарклайном реальной истории.
    gm_prev = data["grade_metrics"][data["grade_metrics"]["month"].isin(prev_months)] if prev_months else None
    psy_hist = data["grade_metrics"][data["grade_metrics"]["month"].isin(HIST_MONTHS[-6:])]
    psy_months = sorted(psy_hist["month"].unique())
    psy_rev_trend = [psy_hist[psy_hist["month"] == m]["revenue"].sum() for m in psy_months]
    psy_visits_trend = [psy_hist[psy_hist["month"] == m]["n_visits"].sum() for m in psy_months]
    psy_rev_cur, psy_rev_prev = gm_cur["revenue"].sum(), (gm_prev["revenue"].sum() if gm_prev is not None else None)
    psy_visits_cur, psy_visits_prev = gm_cur["n_visits"].sum(), (gm_prev["n_visits"].sum() if gm_prev is not None else None)
    psy_doctors_cur = gm_cur["n_doctors"].sum()
    rev_delta = pct_change(psy_rev_cur, psy_rev_prev) if prev_months else None
    visits_delta = pct_change(psy_visits_cur, psy_visits_prev) if prev_months else None
    T.metric_grid([
        T.metric_card(t("Выручка стоматологии", "Dentistry revenue"), fmt_money(psy_rev_cur), f"{abs(rev_delta):.0%}" if rev_delta is not None else None,
                      rev_delta is None or rev_delta >= 0, psy_rev_trend),
        T.metric_card(t("Визиты", "Visits"), fmt_num(psy_visits_cur), f"{abs(visits_delta):.0%}" if visits_delta is not None else None,
                      visits_delta is None or visits_delta >= 0, psy_visits_trend),
        T.metric_card(t("Врачей-стоматологов", "Dentists"), fmt_num(psy_doctors_cur)),
    ], cols=3)

    col1, col2 = st.columns(2)
    with col1:
        gm_display = gm_cur.reset_index()
        gm_display["grade"] = gm_display["grade"].map(glabel)
        gm_display["revenue_k"] = to_k(gm_display["revenue"])
        fig14 = px.bar(gm_display, x="grade", y="revenue_k", title=t(f"Выручка по грейдам — {selected_period}", f"Revenue by grade — {selected_period}"), text_auto=",.0f",
                        labels={"grade": t("Грейд", "Grade"), "revenue_k": t("Выручка, тыс. ₽", "Revenue, ₽ thousand")})
        st.plotly_chart(fig14, use_container_width=True)
    with col2:
        # Средняя линия по 3 грейдам — чтобы сразу видеть, кто выше/ниже среднего.
        avg_visits_per_doctor = gm_cur["visits_per_doctor"].mean()
        gm_display_visits = gm_cur.reset_index()
        gm_display_visits["grade"] = gm_display_visits["grade"].map(glabel)
        fig15 = px.bar(gm_display_visits, x="grade", y="visits_per_doctor", title=t("Визитов на врача в месяц", "Visits per doctor per month"),
                        text_auto=".0f", labels={"grade": t("Грейд", "Grade"), "visits_per_doctor": t("Визитов на врача", "Visits per doctor")})
        fig15.add_hline(y=avg_visits_per_doctor, line_dash="dash", line_color=GRAY,
                        annotation_text=t(f"Среднее: {avg_visits_per_doctor:.0f}", f"Average: {avg_visits_per_doctor:.0f}"), annotation_position="top right")
        st.plotly_chart(fig15, use_container_width=True)
    pptx_sections.append({"tab": t("Продукты/направления", "Products/Directions"), "heading": ins.grade_insight(data['grade_metrics'], cur_months, prev_months, lang=LANG.lower()), "figs": [fig14, fig15]})

    T.section(t("Эффективность грейдов в стоматологии", "Grade efficiency in dentistry"))
    top_rpd_grade = gm_cur["revenue_per_doctor"].idxmax()
    st.markdown(t(f"**Больше всего выручки на врача приносит грейд {top_rpd_grade} ({fmt_money(gm_cur.loc[top_rpd_grade, 'revenue_per_doctor'])}/мес).**",
                  f"**{glabel(top_rpd_grade)} brings the most revenue per doctor ({fmt_money(gm_cur.loc[top_rpd_grade, 'revenue_per_doctor'])}/mo).**"))
    col1, col2 = st.columns(2)
    with col1:
        gm_display2 = gm_cur.reset_index()
        gm_display2["grade"] = gm_display2["grade"].map(glabel)
        gm_display2["revenue_per_doctor_k"] = to_k(gm_display2["revenue_per_doctor"])
        fig16 = px.bar(gm_display2, x="grade", y="revenue_per_doctor_k", title=t("Выручка на 1 врача по грейдам", "Revenue per doctor by grade"), text_auto=",.0f",
                        labels={"grade": t("Грейд", "Grade"), "revenue_per_doctor_k": t("Выручка на врача, тыс. ₽", "Revenue per doctor, ₽ thousand")})
        fig16.update_traces(line_shape="spline", line_smoothing=1.3, selector=dict(type="scatter"))
        st.plotly_chart(fig16, use_container_width=True)
    with col2:
        fig17 = go.Figure()
        gm_cur_x = [glabel(g) for g in gm_cur.index]
        fig17.add_bar(x=gm_cur_x, y=gm_cur["avg_check"], name=t("Средний чек, ₽", "Average check, ₽"), yaxis="y1",
                      text=[fmt_num(v) for v in gm_cur["avg_check"]], textposition="outside")
        fig17.add_scatter(x=gm_cur_x, y=gm_cur["revenue_per_min"], name=t("Выручка/мин, ₽", "Revenue/min, ₽"), yaxis="y2", mode="lines+markers+text",
                          text=[fmt_num(v) for v in gm_cur["revenue_per_min"]], textposition="top center", textfont=dict(size=DATA_LABEL_SIZE, color=PINK))
        fig17.update_layout(yaxis=dict(title=t("₽/визит", "₽/visit")), yaxis2=dict(title=t("₽/мин", "₽/min"), overlaying="y", side="right"), title=t("Средний чек и выручка/мин по грейдам", "Average check and revenue/min by grade"))
        fig17.update_traces(line_shape="spline", line_smoothing=1.3, selector=dict(type="scatter"))
        st.plotly_chart(fig17, use_container_width=True)
    pptx_sections.append({"tab": t("Продукты/направления", "Products/Directions"), "heading": t("Эффективность грейдов в стоматологии", "Grade efficiency in dentistry"), "figs": [fig16, fig17]})

    T.section(t("Длительность приёмов в стоматологии", "Visit length in dentistry"))
    fmt_total = fmt_pivot.sum(axis=0)
    top_fmt = fmt_total.idxmax()
    st.markdown(t(f"**Самый частый формат приёма — {int(top_fmt)} мин ({fmt_total[top_fmt] / fmt_total.sum():.0%} визитов).**",
                  f"**The most common visit format is {int(top_fmt)} min ({fmt_total[top_fmt] / fmt_total.sum():.0%} of visits).**"))
    col1, col2 = st.columns(2)
    with col1:
        # Зелёная гамма (не смешанная CORPORATE_SEQUENCE) + целые проценты.
        fmt_green_colors = [DARK_GREEN, LIGHT_GREEN, "#A9BBB0", "#C7D0CA"][:len(fmt_total)]
        fig18 = go.Figure(go.Pie(values=fmt_total.values, labels=[t(f"{int(f)} мин", f"{int(f)} min") for f in fmt_total.index], hole=0.5,
                                 marker=dict(colors=fmt_green_colors, line=dict(width=2, color=CREAM))))
        fig18.update_traces(texttemplate="%{percent:.0%}")
        fig18.update_layout(title=t(f"Длительность консультаций — {selected_period}", f"Consultation length — {selected_period}"))
        st.plotly_chart(fig18, use_container_width=True)
    with col2:
        bubble = fmt_cur.groupby(["grade", "format_min"]).agg(n_visits=("n_visits", "sum"), revenue=("revenue", "sum")).reset_index()
        bubble["avg_check"] = bubble["revenue"] / bubble["n_visits"]
        bubble["grade"] = bubble["grade"].map(glabel)
        fig19 = px.scatter(bubble, x="avg_check", y="n_visits", size="revenue", color="grade", hover_data=["format_min"],
                            title=t("Грейд x формат: чек, кол-во, размер = выручка", "Grade x format: check, count, size = revenue"),
                            labels={"avg_check": t("Средний чек, ₽", "Average check, ₽"), "n_visits": t("Кол-во визитов", "Visit count"), "grade": t("Грейд", "Grade"), "format_min": t("Формат, мин", "Format, min")})
        fig19.update_traces(line_shape="spline", line_smoothing=1.3, selector=dict(type="scatter"))
        st.plotly_chart(fig19, use_container_width=True)
    pptx_sections.append({"tab": t("Продукты/направления", "Products/Directions"), "heading": t("Длительность приёмов в стоматологии", "Visit length in dentistry"), "figs": [fig18, fig19]})

    st.divider()
    T.section(t("Косметология: выручка и эффективность", "Cosmetology: revenue and efficiency"))
    st.markdown(f"**{ins.neuro_insight(data['neuro'], data['neuro_top_doctor'], cur_months, prev_months, lang=LANG.lower())}**")
    st.markdown(
        f'<p style="{CAPTION_STYLE}">{t(
            "Выручка здесь — визиты к косметологам по CRM без инъекционных допуслуг "
            "(они отдельно ниже, в блоке «Инъекции и гигиенические услуги»).",
            "Revenue here covers CRM visits to cosmetologists excluding injectable add-on services "
            "(shown separately below in \"Injectables and hygiene services\").",
        )}</p>',
        unsafe_allow_html=True,
    )
    neuro_cur = data["neuro"][data["neuro"]["month"].isin(cur_months)][["revenue", "n_visits", "n_doctors"]].sum()
    neuro_prev = data["neuro"][data["neuro"]["month"].isin(prev_months)][["revenue", "n_visits", "n_doctors"]].sum() if prev_months else None
    neuro_hist = data["neuro"][data["neuro"]["month"].isin(HIST_MONTHS[-6:])].sort_values("month")
    rev_delta = pct_change(neuro_cur["revenue"], neuro_prev["revenue"]) if prev_months else None
    visits_delta = pct_change(neuro_cur["n_visits"], neuro_prev["n_visits"]) if prev_months else None
    top_share = data["neuro_top_doctor"][data["neuro_top_doctor"]["month"].isin(cur_months)]["top_doctor_share"].mean()
    T.metric_grid([
        T.metric_card(t("Выручка", "Revenue"), fmt_money(neuro_cur["revenue"]), f"{abs(rev_delta):.0%}" if rev_delta is not None else None,
                      rev_delta is None or rev_delta >= 0, neuro_hist["revenue"].tolist()),
        T.metric_card(t("Визиты", "Visits"), fmt_num(neuro_cur["n_visits"]), f"{abs(visits_delta):.0%}" if visits_delta is not None else None,
                      visits_delta is None or visits_delta >= 0, neuro_hist["n_visits"].tolist()),
        T.metric_card(t("Доля топ-1 косметолога в выручке", "Top-1 cosmetologist revenue share"), f"{top_share:.0%}" if pd.notna(top_share) else t("н/д", "n/a")),
    ], cols=3)

    neuro_display = data["neuro"][data["neuro"]["month"].isin(HIST_MONTHS)].copy()
    neuro_display["revenue_k"] = to_k(neuro_display["revenue"])
    fig20 = px.line(neuro_display, x="month", y="revenue_k", markers=True, title=t(f"Динамика выручки косметологии — по {cur_months[-1]}", f"Cosmetology revenue trend — through {cur_months[-1]}"),
                     labels={"month": t("Месяц", "Month"), "revenue_k": t("Выручка, тыс. ₽", "Revenue, ₽ thousand")})
    fig20.update_traces(line_shape="spline", line_smoothing=1.3, selector=dict(type="scatter"))
    st.plotly_chart(fig20, use_container_width=True)
    pptx_sections.append({"tab": t("Продукты/направления", "Products/Directions"), "heading": ins.neuro_insight(data['neuro'], data['neuro_top_doctor'], cur_months, prev_months, lang=LANG.lower()), "figs": [fig20]})

    st.divider()
    T.section(t("Инъекции и гигиенические услуги", "Injectables and hygiene services"))
    inj = data["by_direction"][(data["by_direction"]["direction"] == "Инъекции") & (data["by_direction"]["month"].isin(HIST_MONTHS))]
    psy_serv = data["by_direction"][(data["by_direction"]["direction"] == "Гигиенист") & (data["by_direction"]["month"].isin(HIST_MONTHS))]

    def _dir_card(label, df, cur_months_):
        cur_df = df[df["month"].isin(cur_months_)]
        if cur_df.empty or cur_df["revenue"].sum() == 0:
            return T.metric_card(label, t("н/д", "n/a"))
        cur_rev = cur_df["revenue"].sum()
        prev_rev = df[df["month"].isin(prev_months)]["revenue"].sum() if prev_months else None
        delta = pct_change(cur_rev, prev_rev) if prev_rev else None
        return T.metric_card(label, fmt_money(cur_rev), f"{abs(delta):.0%}" if delta is not None else None,
                             delta is None or delta >= 0, df.sort_values("month")["revenue"].tail(6).tolist())

    T.metric_grid([
        _dir_card(t("Выручка — инъекции", "Revenue — injectables"), inj, cur_months),
        _dir_card(t("Выручка — гигиенист", "Revenue — hygienist"), psy_serv, cur_months),
    ], cols=2)
    inj_cur_rev = inj[inj["month"].isin(cur_months)]["revenue"].sum()
    st.markdown(t(f"**Инъекционная терапия за период — {fmt_money(inj_cur_rev)}.**", f"**Injectable therapy for the period — {fmt_money(inj_cur_rev)}.**"))
    if psy_serv[psy_serv["month"].isin(cur_months)]["revenue"].sum() == 0:
        T.caption(t("Гигиенические услуги не оказывались в этом периоде — карточка и график сохранены для истории.",
                    "No hygiene services were provided in this period — the card and chart are kept for historical context."))

    col1, col2 = st.columns(2)
    with col1:
        fig21 = go.Figure()
        fig21.add_bar(x=inj["month"], y=to_k(inj["revenue"]), name=t("Выручка, тыс. ₽", "Revenue, ₽ thousand"), yaxis="y1")
        fig21.add_scatter(x=inj["month"], y=inj["n_services"], name=t("Услуги", "Services"), yaxis="y2", mode="lines+markers")
        fig21.update_layout(title=t("Инъекционная терапия", "Injectable therapy"), yaxis=dict(title=t("тыс. ₽", "₽ thousand")), yaxis2=dict(overlaying="y", side="right"))
        fig21.update_traces(line_shape="spline", line_smoothing=1.3, selector=dict(type="scatter"))
        st.plotly_chart(fig21, use_container_width=True)
    with col2:
        fig22 = go.Figure()
        fig22.add_bar(x=psy_serv["month"], y=to_k(psy_serv["revenue"]), name=t("Выручка, тыс. ₽", "Revenue, ₽ thousand"), yaxis="y1")
        fig22.add_scatter(x=psy_serv["month"], y=psy_serv["n_services"], name=t("Сессии", "Sessions"), yaxis="y2", mode="lines+markers")
        fig22.update_layout(title=t("Гигиенические услуги", "Hygiene services"), yaxis=dict(title=t("тыс. ₽", "₽ thousand")), yaxis2=dict(overlaying="y", side="right"))
        fig22.update_traces(line_shape="spline", line_smoothing=1.3, selector=dict(type="scatter"))
        st.plotly_chart(fig22, use_container_width=True)
    pptx_sections.append({"tab": t("Продукты/направления", "Products/Directions"), "heading": t("Инъекции и гигиенические услуги", "Injectables and hygiene services"), "figs": [fig21, fig22]})

    st.divider()
    T.section(t("Маржа с продажи 1 упаковки препарата", "Margin per package sold"))
    T.caption(t("Выручка минус закупочная стоимость препарата, из финансовой модели.", "Revenue minus procurement cost, from the financial model."))
    if data["drug_margin"] is not None and len(data["drug_margin"][data["drug_margin"]["month"].isin(cur_months)]):
        dmg_cur = data["drug_margin"][data["drug_margin"]["month"].isin(cur_months)].groupby("drug").agg(
            revenue=("revenue", "sum"), cost=("cost", "sum"), margin=("margin", "sum")
        )
        dmg_cur["margin_pct"] = dmg_cur["margin"] / dmg_cur["revenue"]
        best_drug = dmg_cur["margin"].idxmax()
        worst_drug = dmg_cur["margin"].idxmin()
        st.markdown(t(
            f"**Самая маржинальная позиция — {best_drug} ({fmt_num(dmg_cur.loc[best_drug, 'margin'])} ₽); "
            f"наименее маржинальная — {worst_drug} ({fmt_num(dmg_cur.loc[worst_drug, 'margin'])} ₽).**",
            f"**The highest-margin item is {plabel(best_drug)} ({fmt_num(dmg_cur.loc[best_drug, 'margin'])} ₽); "
            f"the lowest-margin is {plabel(worst_drug)} ({fmt_num(dmg_cur.loc[worst_drug, 'margin'])} ₽).**",
        ))
        fig_dmg = go.Figure()
        fig_dmg.add_bar(x=[plabel(d) for d in dmg_cur.index], y=dmg_cur["margin"], name=t("Маржа, ₽", "Margin, ₽"), marker_color=dmg_cur["margin"].apply(lambda v: DARK_GREEN if v >= 0 else PINK),
                        text=[fmt_num(v) for v in dmg_cur["margin"]], textposition="outside")
        fig_dmg.update_layout(title=t(f"Маржа по препаратам — {selected_period}", f"Margin by product — {selected_period}"), yaxis_title="₽")
        fig_dmg.update_traces(line_shape="spline", line_smoothing=1.3, selector=dict(type="scatter"))
        st.plotly_chart(fig_dmg, use_container_width=True)
        with st.expander(t("Детализация по препаратам", "Detail by product")):
            dmg_display = dmg_cur.rename(index=plabel)
            st.dataframe(dmg_display.style.format({"revenue": fmt_num, "cost": fmt_num, "margin": fmt_num, "margin_pct": "{:.0%}"}), use_container_width=True)
        pptx_sections.append({"tab": t("Продукты/направления", "Products/Directions"), "heading": t(f"Маржа по препаратам — {selected_period}", f"Margin by product — {selected_period}"), "figs": [fig_dmg]})
    else:
        st.info(t("Нет данных по марже препаратов на выбранный период.", "No product-margin data for the selected period."))

    st.divider()
    T.section("Cross-sell rate")
    T.caption(t("Доля пациентов месяца, получивших услуги более чем одного направления (например, стоматология + инъекции).",
                "Share of the month's patients who received services from more than one direction (e.g. dentistry + injectables)."))
    if data["cross_sell"] is not None:
        cs_cur = data["cross_sell"][data["cross_sell"]["month"].isin(cur_months)]
        cs_rate_cur = (cs_cur["n_cross_sell"].sum() / cs_cur["n_patients"].sum()) if cs_cur["n_patients"].sum() else None
        cs_hist_series = data["cross_sell"][data["cross_sell"]["month"].isin(HIST_MONTHS[-6:])].sort_values("month")["cross_sell_rate"].tolist()
        T.metric_grid([T.metric_card(t("Cross-sell rate за период", "Cross-sell rate for period"), f"{cs_rate_cur:.1%}" if cs_rate_cur is not None else t("н/д", "n/a"), trend=cs_hist_series)], cols=1)
        if cs_rate_cur is not None:
            st.markdown(t(f"**{cs_rate_cur:.0%} пациентов месяца получили услуги более чем одного направления.**",
                          f"**{cs_rate_cur:.0%} of the month's patients received services from more than one direction.**"))
        fig_cs = px.line(data["cross_sell"][data["cross_sell"]["month"].isin(HIST_MONTHS)], x="month", y="cross_sell_rate", markers=True, title=t("Cross-sell rate по месяцам", "Cross-sell rate by month"),
                          labels={"month": t("Месяц", "Month"), "cross_sell_rate": "Cross-sell rate"})
        fig_cs.update_yaxes(tickformat=".1%")
        fig_cs.update_traces(line_shape="spline", line_smoothing=1.3, selector=dict(type="scatter"))
        st.plotly_chart(fig_cs, use_container_width=True)
        pptx_sections.append({"tab": t("Продукты/направления", "Products/Directions"), "heading": t("Cross-sell rate по месяцам", "Cross-sell rate by month"), "figs": [fig_cs]})
    else:
        st.info(t("Нет данных по cross-sell rate — запустите etl/build_report_metrics.py", "No cross-sell data — run etl/build_report_metrics.py"))

# ═══════════════════════ KPI ═══════════════════════
with tab7:
    T.section(t(f"Выполнение плана — {selected_period}", f"Plan performance — {selected_period}"))
    st.markdown(f"**{ins.kpi_insight(data['breakeven'], cur_months, lang=LANG.lower())}**")
    be_cur = data["breakeven"][data["breakeven"]["month"].isin(cur_months)]
    kpi_rows = []
    if be_cur["plan_sessions"].notna().any() and be_cur["plan_sessions"].sum() > 0:
        actual_sessions = be_cur["n_visits_actual"].sum()
        plan_sessions = be_cur["plan_sessions"].sum()
        actual_revenue = be_cur["revenue_actual"].sum()
        plan_revenue = be_cur["plan_revenue"].sum()
        actual_check = actual_revenue / actual_sessions
        plan_check = plan_revenue / plan_sessions

        kpi_rows += [
            (t("Консультации", "Consultations"), actual_sessions / plan_sessions if plan_sessions else None),
            (t("Выручка", "Revenue"), actual_revenue / plan_revenue if plan_revenue else None),
            (t("Средний чек", "Average check"), actual_check / plan_check if plan_check else None),
        ]

    if data["kpi_plan"] is not None:
        plan_cur = data["kpi_plan"][data["kpi_plan"]["month"].isin(cur_months)]

        if data["funnel"] is not None:
            funnel_cur_kpi = data["funnel"][data["funnel"]["month"].isin(cur_months)][["n_booked", "n_completed", "n_cancelled"]].sum()
            actual_conv = funnel_cur_kpi["n_completed"] / funnel_cur_kpi["n_booked"] if funnel_cur_kpi["n_booked"] else None
            actual_cancel = funnel_cur_kpi["n_cancelled"] / funnel_cur_kpi["n_booked"] if funnel_cur_kpi["n_booked"] else None
            plan_conv = plan_cur["conversion_plan"].mean()
            plan_cancel = plan_cur["cancellation_plan"].mean()
            if actual_conv is not None and pd.notna(plan_conv) and plan_conv:
                kpi_rows.append((t("Конверсия", "Conversion"), actual_conv / plan_conv))
            if actual_cancel is not None and pd.notna(plan_cancel) and plan_cancel:
                # для % отмен "выполнение плана" = план/факт (меньше факт — лучше)
                kpi_rows.append((t("% отмен (план/факт)", "% cancelled (plan/actual)"), plan_cancel / actual_cancel if actual_cancel else None))

        actual_util = data["doctors_util"][data["doctors_util"]["month"].isin(cur_months)]["fill_rate"].mean()
        plan_util = plan_cur["doctor_utilization_plan"].mean()
        if pd.notna(actual_util) and pd.notna(plan_util) and plan_util:
            kpi_rows.append((t("Загрузка врачей", "Doctor utilization"), actual_util / plan_util))

        monthly_cur_kpi = data["monthly_client"][data["monthly_client"]["visit_month"].isin(cur_months)]
        total_clients = monthly_cur_kpi["n_clients_new"].sum() + monthly_cur_kpi["n_clients_repeat"].sum()
        actual_repeat_share = monthly_cur_kpi["n_clients_repeat"].sum() / total_clients if total_clients else None
        plan_repeat_share = plan_cur["repeat_visit_share_plan"].mean()
        if actual_repeat_share is not None and pd.notna(plan_repeat_share) and plan_repeat_share:
            kpi_rows.append((t("Повторные визиты", "Returning visits"), actual_repeat_share / plan_repeat_share))

    kpi_rows = [(k, v) for k, v in kpi_rows if v is not None and pd.notna(v)]
    if kpi_rows:
        # Сетка мини-gauge вместо одного длинного bar chart — на неё сразу приятно
        # смотреть; невыполненный план — розовым кольцом и розовым текстом внутри.
        kpi_cols = st.columns(3)
        kpi_figs = []
        for i, (label, v) in enumerate(kpi_rows):
            ok = v >= 1.0
            color = DARK_GREEN if ok else T.NEGATIVE
            text_color = TEXT_DARK if ok else T.NEGATIVE_DEEP
            fig_k = T.gauge_donut(v, label, color=color, text_color=text_color)
            kpi_cols[i % 3].plotly_chart(fig_k, use_container_width=True)
            kpi_figs.append(fig_k)
        pptx_sections.append({"tab": t("KPI", "KPI"), "heading": ins.kpi_insight(data['breakeven'], cur_months, lang=LANG.lower()), "figs": kpi_figs})
    else:
        st.info(t(f"Нет плановых значений на {selected_period} в KPI-файле.", f"No plan values for {selected_period} in the KPI file."))

    with st.expander(t("Полная таблица план/факт/ТБУ по месяцам", "Full plan/actual/break-even table by month")):
        st.dataframe(
            data["breakeven"].style.format(
                {"revenue_actual": fmt_num, "avg_check_actual": fmt_num, "margin_pct": "{:.1%}",
                 "fixed_costs": fmt_num, "be_revenue": fmt_num, "be_sessions": fmt_num,
                 "plan_sessions": fmt_num, "plan_revenue": fmt_num}
            ),
            use_container_width=True,
        )
    if data["kpi_plan"] is not None:
        with st.expander(t("Плановые значения KPI по месяцам", "Planned KPI values by month")):
            st.dataframe(
                data["kpi_plan"].style.format(
                    {"conversion_plan": "{:.0%}", "cancellation_plan": "{:.0%}",
                     "doctor_utilization_plan": "{:.0%}", "repeat_visit_share_plan": "{:.0%}"}
                ),
                use_container_width=True,
            )

# ═══════════════════════ ЗАПАС ПРОЧНОСТИ ═══════════════════════
with tab6:
    T.section(t("Точка безубыточности", "Break-even point"))
    be_cur_runway = data["breakeven"][data["breakeven"]["month"].isin(cur_months)]
    if len(be_cur_runway):
        be_row = be_cur_runway.iloc[-1]
        be_hist = data["breakeven"][data["breakeven"]["month"].isin(HIST_MONTHS[-6:])].sort_values("month")
        status_positive = str(be_row["status"]).lower().find("ниже") == -1
        gap_word = t("выше", "above") if be_row["gap_sessions_vs_be"] >= 0 else t("ниже", "below")
        status_display = t(str(be_row["status"]), "above break-even" if status_positive else "below break-even")
        st.markdown(t(f"**Факт визитов {gap_word} точки безубыточности на {fmt_num(abs(be_row['gap_sessions_vs_be']))} — статус «{be_row['status']}».**",
                      f"**Actual visits are {gap_word} break-even by {fmt_num(abs(be_row['gap_sessions_vs_be']))} — status \"{status_display}\".**"))
        T.metric_grid([
            T.metric_card(t("ТБУ, визитов/мес", "Break-even, visits/mo"), fmt_num(be_row["be_sessions"]), trend=be_hist["be_sessions"].tolist()),
            T.metric_card(t("Факт визитов", "Actual visits"), fmt_num(be_row["n_visits_actual"]), trend=be_hist["n_visits_actual"].tolist()),
            T.metric_card(t("Разрыв к ТБУ", "Gap to break-even"), fmt_num(be_row["gap_sessions_vs_be"]), trend=be_hist["gap_sessions_vs_be"].tolist(),
                          positive=be_row["gap_sessions_vs_be"] >= 0),
            T.metric_card(t("Статус", "Status"), status_display, positive=status_positive),
        ])
        T.caption(t("Подробный план/факт по ТБУ — во вкладке KPI.", "Detailed plan/actual for break-even — see the KPI tab."))
    else:
        st.info(t("Нет данных по точке безубыточности на выбранный период.", "No break-even data for the selected period."))

    st.divider()
    if data["cash_runway"] is not None:
        cr = data["cash_runway"]
        cr_cur = cr[cr["month"].isin(cur_months)].iloc[-1] if len(cr[cr["month"].isin(cur_months)]) else None
        cr_prev = cr[cr["month"].isin(prev_months)].iloc[-1] if prev_months and len(cr[cr["month"].isin(prev_months)]) else None

        T.section(t("Финансирование и денежные средства", "Financing and cash"))
        T.caption(t('Остаток и долг — по данным финансовой модели.', 'Cash and debt — from the financial model.'))
        if cr_cur is not None:
            cash_word = t("положительный", "positive") if cr_cur["cash"] >= 0 else t("отрицательный", "negative")
            st.markdown(t(f"**Остаток денежных средств {cash_word}: {fmt_money(cr_cur['cash'])}; долговая нагрузка — {fmt_money(cr_cur['total_debt'])}.**",
                          f"**Cash balance is {cash_word}: {fmt_money(cr_cur['cash'])}; debt load — {fmt_money(cr_cur['total_debt'])}.**"))

        if cr_cur is not None:
            cr_hist_early = cr[cr["month"].isin(HIST_MONTHS[-6:])].sort_values("month")
            cash_delta = pct_change(cr_cur["cash"], cr_prev["cash"]) if cr_prev is not None else None
            burn_delta = pct_change(cr_cur["burn_3mo_avg"], cr_prev["burn_3mo_avg"]) if cr_prev is not None else None
            debt_delta = pct_change(cr_cur["total_debt"], cr_prev["total_debt"]) if cr_prev is not None else None
            cards = [
                T.metric_card(t("Остаток денежных средств", "Cash balance"), fmt_money(cr_cur["cash"]),
                              f"{abs(cash_delta):.0%}" if cash_delta is not None else None,
                              cash_delta is None or cash_delta >= 0, cr_hist_early["cash"].tolist()),
                T.metric_card(t("Средний burn (3 мес)", "Average burn (3 mo)"), fmt_money(cr_cur["burn_3mo_avg"]),
                              f"{abs(burn_delta):.0%}" if burn_delta is not None else None,
                              burn_delta is None or burn_delta <= 0, cr_hist_early["burn_3mo_avg"].tolist()),
                T.metric_card(t("Долговая нагрузка", "Debt load"), fmt_money(cr_cur["total_debt"]),
                              f"{abs(debt_delta):.0%}" if debt_delta is not None else None,
                              debt_delta is None or debt_delta <= 0, cr_hist_early["total_debt"].tolist()),
            ]
            if cr_cur["burn_3mo_avg"] and cr_cur["burn_3mo_avg"] > 0:
                cards.append(T.metric_card(t("Доп. финансирование уже используется", "Extra financing already used"),
                                           fmt_money(abs(cr_cur["cash"])) if cr_cur["cash"] < 0 else t("нет", "none")))
            else:
                cards.append(T.metric_card("Cash runway", t("н/д", "n/a")))
            T.metric_grid(cards)

            # Пороговый флаг по запасу прочности: кассовый разрыв (остаток < 0) —
            # error; иначе, если остаток покрывает меньше 3 месяцев текущего burn —
            # warning. 3 месяца — не официальный KPI, обычный ориентир "подушки".
            if cr_cur["cash"] < 0:
                st.error(t(f"Кассовый разрыв: остаток отрицательный ({fmt_money(cr_cur['cash'])}), покрывается займом от учредителей.",
                          f"Cash gap: the balance is negative ({fmt_money(cr_cur['cash'])}), covered by a founder loan."))
            elif cr_cur["burn_3mo_avg"] and cr_cur["burn_3mo_avg"] > 0:
                runway_months = cr_cur["cash"] / cr_cur["burn_3mo_avg"]
                if runway_months < 3:
                    st.warning(t(f"Запас прочности — около {runway_months:.1f} мес. текущего burn rate (порог 3 мес.).",
                                f"Margin of safety — about {runway_months:.1f} mo. of current burn rate (threshold 3 mo.)."))

        st.divider()
        T.section(t("Динамика остатка денежных средств", "Cash balance over time"))
        cr_hist = cr[cr["month"].isin(HIST_MONTHS)].copy()
        cr_hist["cash_k"] = to_k(cr_hist["cash"])
        fig_cash = go.Figure()
        T.area_gradient(fig_cash, cr_hist["month"], cr_hist["cash_k"], t("Остаток, тыс. ₽", "Balance, ₽ thousand"), color=DARK_GREEN)
        fig_cash.add_hline(y=0, line_dash="dash", line_color=GRAY)
        fig_cash.update_layout(title=t("Остаток денежных средств по месяцам (накопительно)", "Cash balance by month (cumulative)"), showlegend=False, yaxis_title=t("тыс. ₽", "₽ thousand"))
        fig_cash.update_xaxes(type="category")
        st.plotly_chart(fig_cash, use_container_width=True)
        if len(cr_hist) >= 2:
            first_neg = cr_hist[cr_hist["cash"] < 0]
            if len(first_neg):
                st.markdown(t(f"**Остаток впервые ушёл в минус в {first_neg.iloc[0]['month']}.**", f"**The balance first went negative in {first_neg.iloc[0]['month']}.**"))
                T.caption(t(
                    "Остаток уходит в минус за счёт операционных убытков большинства месяцев — "
                    "финансируется займом от учредителей (см. ниже). Это не признак банкротства, а показатель того, сколько "
                    "уже потребовалось доп. финансирования сверх операционной деятельности.",
                    "The balance goes negative due to operating losses in most months — funded by a founder loan "
                    "(see below). This isn't a sign of insolvency, but a measure of how much extra financing has "
                    "already been needed beyond operating activity.",
                ))
            else:
                st.markdown(t("**Остаток пока не уходил в минус за отслеживаемый период.**", "**The balance has not gone negative over the tracked period.**"))
                T.caption(t("Клиника прибыльна на всём отслеживаемом периоде — остаток растёт за счёт операционной прибыли, без займов от учредителей.",
                            "The clinic has been profitable throughout the tracked period — the balance grows from operating profit, with no founder loans."))

        st.divider()
        T.section(t("Burn rate и долговая нагрузка", "Burn rate and debt load"))
        cr_hist["burn_k"] = to_k(cr_hist["burn_3mo_avg"])
        cr_hist["debt_k"] = to_k(cr_hist["total_debt"])
        fig_combo = go.Figure()
        fig_combo.add_bar(x=cr_hist["month"], y=cr_hist["burn_k"], name=t("Burn, тыс. ₽", "Burn, ₽ thousand"), yaxis="y1", marker_color=SAGE)
        fig_combo.add_scatter(x=cr_hist["month"], y=cr_hist["debt_k"], name=t("Долг, тыс. ₽", "Debt, ₽ thousand"), yaxis="y2",
                              mode="lines+markers", line=dict(color=ESPRESSO, width=2.4, shape="spline", smoothing=1.3))
        T.dual_axis(fig_combo, t("Burn, тыс. ₽", "Burn, ₽ thousand"), t("Долг, тыс. ₽", "Debt, ₽ thousand"))
        fig_combo.update_layout(title=t("Burn rate vs долговая нагрузка", "Burn rate vs. debt load"))
        fig_combo.update_xaxes(type="category")
        st.plotly_chart(fig_combo, use_container_width=True)
        if len(cr_hist) >= 2:
            burn_trend_delta = pct_change(cr_hist.iloc[-1]["burn_3mo_avg"], cr_hist.iloc[0]["burn_3mo_avg"])
            if burn_trend_delta is not None:
                burn_word = t("вырос", "grew") if burn_trend_delta >= 0 else t("снизился", "declined")
                st.markdown(t(f"**Burn rate {burn_word} на {abs(burn_trend_delta):.0%} за отслеживаемый период; долг — {fmt_money(cr_hist.iloc[-1]['total_debt'])}.**",
                              f"**Burn rate {burn_word} {abs(burn_trend_delta):.0%} over the tracked period; debt — {fmt_money(cr_hist.iloc[-1]['total_debt'])}.**"))
        pptx_sections.append({"tab": t("Запас прочности", "Margin of Safety"), "heading": t("Остаток денежных средств и burn rate (по данным финмодели)", "Cash balance and burn rate (per financial model)"), "figs": [fig_cash]})
        pptx_sections.append({"tab": t("Запас прочности", "Margin of Safety"), "heading": t("Burn rate и долговая нагрузка", "Burn rate and debt load"), "figs": [fig_combo]})

        st.markdown(
            f'<p style="{CAPTION_STYLE}">{t(
                "Точка, когда потребуется доп. финансирование сверх уже привлечённого долга, не определена в модели явно.",
                "The point at which additional financing beyond the current debt would be needed is not explicitly modeled.",
            )}</p>',
            unsafe_allow_html=True,
        )
        with st.expander(t("Детализация по месяцам", "Detail by month")):
            st.dataframe(
                cr.style.format({"cash": fmt_num, "debt_credit": fmt_num, "debt_loan": fmt_num, "total_debt": fmt_num,
                                  "operating_profit": fmt_num, "burn_3mo_avg": fmt_num}),
                use_container_width=True,
            )
    else:
        st.info(t("Нет данных по денежным остаткам — запустите etl/load_cash_runway.py", "No cash-runway data — run etl/load_cash_runway.py"))

# ═══════════════════════ ЮНИТ-ЭКОНОМИКА ВРАЧЕЙ ═══════════════════════
with tab5:
    if data["doctor_economics"] is not None:
        econ = data["doctor_economics"]
        econ_cur = econ[econ["month"].isin(cur_months)]

        # Инсайт-карточка: изменение чистой маржи к предыдущему периоду + грейд-драйвер.
        econ_prev = econ[econ["month"].isin(prev_months)] if prev_months else None
        margin_now = econ_cur["net_margin"].sum() / econ_cur["revenue"].sum() if econ_cur["revenue"].sum() else None
        margin_before = (econ_prev["net_margin"].sum() / econ_prev["revenue"].sum()) if (econ_prev is not None and econ_prev["revenue"].sum()) else None
        by_grade_top = econ_cur.groupby("grade").agg(revenue=("revenue", "sum"), net_margin=("net_margin", "sum"))
        by_grade_top["margin_pct"] = by_grade_top["net_margin"] / by_grade_top["revenue"]
        driver_grade = by_grade_top["margin_pct"].idxmax() if len(by_grade_top) else None
        # Как на Сводке: T.section + жирная строка-вывод, без отдельной
        # спец-карточки с крупной цифрой.
        T.section(t("Юнит-экономика месяца", "Unit economics for the month"))
        st.markdown(
            f'<p style="{CAPTION_STYLE}">{t(
                "Это расчётная маржа: налоги и взносы считаются от выплаты обратным счётом "
                "(НДФЛ 13% + взносы 30%) в периоде оказания услуги. Она не равна фактической марже в отчётах "
                "\"Сводка\"/\"Финансовые показатели\" — там расходы учитываются по факту оплаты, с лагом по налогам, "
                "поэтому цифры на разных вкладках могут не совпадать.",
                "This is a computed margin: taxes and contributions are calculated back from the net payout "
                "(13% income tax + 30% contributions) in the period of service. It is not the same as the actual "
                "margin on the Summary/Financials tabs — those recognize costs on a payment-date basis with a tax "
                "lag, so figures across tabs may not match.",
            )}</p>',
            unsafe_allow_html=True,
        )
        if margin_now is not None and margin_before is not None and margin_before:
            delta_pp = (margin_now - margin_before) * 100
            T.metric_grid([T.metric_card(t("Валовая маржа за период", "Gross margin for period"), f"{margin_now:.0%}",
                                         f"{abs(delta_pp):.0f} {t('п.п.', 'pp')}", delta_pp >= 0)], cols=4)
            if driver_grade:
                st.markdown(t(f"**Самая высокая маржинальность — у грейда {driver_grade} ({by_grade_top.loc[driver_grade, 'margin_pct']:.0%}).**",
                              f"**The highest margin is {glabel(splabel(driver_grade))} ({by_grade_top.loc[driver_grade, 'margin_pct']:.0%}).**"))
        elif margin_now is not None:
            T.metric_grid([T.metric_card(t("Валовая маржа за период", "Gross margin for period"), f"{margin_now:.0%}")], cols=4)
            if driver_grade:
                st.markdown(t(f"**Лидер по марже: грейд {driver_grade}.**", f"**Margin leader: {glabel(splabel(driver_grade))}.**"))
        st.divider()

        T.section(t(f"Валовая маржа по грейдам/специальностям — {selected_period}", f"Gross margin by grade/specialty — {selected_period}"))
        by_grade = econ_cur.groupby("grade").agg(
            revenue=("revenue", "sum"), commission_cost=("commission_cost", "sum"), net_margin=("net_margin", "sum"), n_doctors=("doctor", "nunique")
        )
        by_grade["margin_pct"] = by_grade["net_margin"] / by_grade["revenue"]
        top_margin_grade = by_grade["margin_pct"].idxmax() if len(by_grade) else None
        if top_margin_grade is not None:
            st.markdown(t(f"**Самая высокая маржинальность — {top_margin_grade} ({by_grade.loc[top_margin_grade, 'margin_pct']:.0%}).**",
                          f"**The highest margin is {glabel(splabel(top_margin_grade))} ({by_grade.loc[top_margin_grade, 'margin_pct']:.0%}).**"))

        col1, col2 = st.columns(2)
        with col1:
            bg_display = by_grade.reset_index()
            bg_display["grade"] = bg_display["grade"].map(gslabel)
            bg_display["revenue_k"] = to_k(bg_display["revenue"])
            bg_display["net_margin_k"] = to_k(bg_display["net_margin"])
            fig_margin = go.Figure()
            fig_margin.add_bar(x=bg_display["grade"], y=bg_display["revenue_k"], name=t("Выручка, тыс. ₽", "Revenue, ₽ thousand"), marker_color=SAGE)
            fig_margin.add_bar(x=bg_display["grade"], y=bg_display["net_margin_k"], name=t("Валовая маржа, тыс. ₽", "Gross margin, ₽ thousand"), marker_color=DARK_GREEN)
            # title как явный dict (yanchor="top" + свой margin) — иначе в узкой
            # колонке заголовок съезжает вниз и прячется ПОД столбцами графика
            # (проверено в devtools: текст есть в DOM, но перекрыт заливкой баров).
            fig_margin.update_layout(
                title=dict(text=t("Выручка vs валовая маржа по грейдам/специальностям", "Revenue vs. gross margin by grade/specialty"), x=0.02, xanchor="left",
                          y=0.97, yanchor="top", font=dict(size=14, color=TEXT_DARK)),
                barmode="group", yaxis_title=t("тыс. ₽", "₽ thousand"), margin=dict(t=64),
            )
            st.plotly_chart(fig_margin, use_container_width=True)
        with col2:
            by_grade_display = by_grade.reset_index()
            by_grade_display["grade"] = by_grade_display["grade"].map(gslabel)
            fig_margin_pct = px.bar(by_grade_display, x="grade", y="margin_pct", text_auto=".0%",
                                     labels={"grade": t("Грейд/специальность", "Grade/specialty"), "margin_pct": t("Маржинальность", "Margin")})
            fig_margin_pct.update_yaxes(tickformat=".0%")
            fig_margin_pct.update_layout(
                title=dict(text=t("Маржинальность по грейдам, %", "Margin by grade, %"), x=0.02, xanchor="left",
                          y=0.97, yanchor="top", font=dict(size=14, color=TEXT_DARK)),
                margin=dict(t=64),
            )
            st.plotly_chart(fig_margin_pct, use_container_width=True)
        pptx_sections.append({"tab": t("Юнит-экономика", "Unit Economics"), "heading": t(f"Валовая маржа по грейдам/специальностям — {selected_period}", f"Gross margin by grade/specialty — {selected_period}"), "figs": [fig_margin, fig_margin_pct]})

        st.divider()
        T.section(t("Валовая маржа на 1 врача по месяцам", "Gross margin per doctor by month"))
        per_doctor = econ[econ["month"].isin(HIST_MONTHS)].groupby(["month", "grade"]).agg(
            revenue=("revenue", "sum"), commission_cost=("commission_cost", "sum"), net_margin=("net_margin", "sum"), n_doctors=("doctor", "nunique")
        ).reset_index()
        per_doctor["net_margin_per_doctor"] = per_doctor["net_margin"] / per_doctor["n_doctors"]
        per_doctor["net_margin_per_doctor_k"] = to_k(per_doctor["net_margin_per_doctor"])

        grade_list = list(per_doctor["grade"].unique())
        grade_area_figs = []
        area_cols = st.columns(len(grade_list)) if grade_list else []
        for col, grade, color in zip(area_cols, grade_list, CORPORATE_SEQUENCE):
            sub = per_doctor[per_doctor["grade"] == grade].sort_values("month")
            fig_g = go.Figure()
            T.area_gradient(fig_g, sub["month"], sub["net_margin_per_doctor_k"], gslabel(grade), color=color)
            fig_g.update_layout(
                title=dict(text=t(f"{grade} — маржа на врача, тыс. ₽", f"{gslabel(grade)} — margin per doctor, ₽ thousand"), x=0.02, xanchor="left",
                          y=0.97, yanchor="top", font=dict(size=13, color=TEXT_DARK)),
                showlegend=False, yaxis_title=t("тыс. ₽", "₽ thousand"), margin=dict(t=60),
            )
            fig_g.update_xaxes(type="category")
            col.plotly_chart(fig_g, use_container_width=True)
            grade_area_figs.append(fig_g)
        pptx_sections.append({"tab": t("Юнит-экономика", "Unit Economics"), "heading": t("Валовая маржа на 1 врача в месяц по грейдам", "Gross margin per doctor by month, by grade"), "figs": grade_area_figs})

        with st.expander(t("Все врачи за период — детализация юнит-экономики", "All doctors for the period — unit economics detail")):
            doctor_detail = econ_cur.groupby(["doctor", "grade", "specialty"]).agg(
                revenue=("revenue", "sum"), zp=("zp", "sum"), tax=("tax", "sum"), drug_cost=("drug_cost", "sum"),
                net_margin=("net_margin", "sum"), n_services=("n_services", "sum")
            ).reset_index()
            doctor_detail["margin_pct"] = doctor_detail["net_margin"] / doctor_detail["revenue"]
            doctor_detail["grade"] = doctor_detail["grade"].map(gslabel)
            doctor_detail["specialty"] = doctor_detail["specialty"].map(splabel)
            rename_map = ({"doctor": "Doctor", "grade": "Grade/specialty", "specialty": "Specialty", "revenue": "Revenue", "zp": "Net payout", "tax": "Tax & contributions", "drug_cost": "Drugs (injectables)",
                          "net_margin": "Gross margin", "n_services": "Services", "margin_pct": "Margin"} if LANG == "EN" else
                          {"doctor": "Врач", "grade": "Грейд/специальность", "specialty": "Специальность", "revenue": "Выручка", "zp": "ЗП на руки", "tax": "Налоги и взносы", "drug_cost": "Препараты (инъекции)",
                          "net_margin": "Валовая маржа", "n_services": "Услуг", "margin_pct": "Маржинальность"})
            doctor_detail = doctor_detail.rename(columns=rename_map)
            st.dataframe(
                doctor_detail.style.format({
                    rename_map["revenue"]: fmt_num, rename_map["zp"]: fmt_num, rename_map["tax"]: fmt_num,
                    rename_map["drug_cost"]: fmt_num, rename_map["net_margin"]: fmt_num, rename_map["margin_pct"]: "{:.0%}",
                }),
                use_container_width=True,
            )

        st.divider()
        T.section(t("Врачи с аномальным удержанием", "Doctors with anomalous retention"),
                  t("Возврат на 2-й приём по когорте \"первый визит к этому врачу\", не по месяцу — не зависит от выбранного периода",
                    "2nd-visit return by \"first visit to this doctor\" cohort, not by month — independent of the selected period"))
        T.caption(t(
            "Когорта — пациенты, у которых первый визит в истории клиники был именно к этому врачу. "
            "Возврат на 2-й приём — есть ли у пациента любой визит после первого (к любому врачу). "
            "Считаются только «зрелые» когорты (с первого визита прошло ≥90 дней) и врачи с ≥8 пациентами "
            "в выборке — иначе разброс % статистически не значим.",
            "Cohort — patients whose first-ever visit to the clinic was to this specific doctor. "
            "2nd-visit return — whether the patient has any visit after the first (to any doctor). "
            "Only \"mature\" cohorts (≥90 days since first visit) and doctors with ≥8 patients in the "
            "sample are counted — otherwise the % spread isn't statistically meaningful.",
        ))
        if data["doctor_retention_anomalies"] is not None:
            anomalies = data["doctor_retention_anomalies"]
            worst = anomalies[anomalies["delta_vs_specialty_avg"] < -0.10].sort_values("delta_vs_specialty_avg")
            if len(worst):
                st.markdown(t(
                    f"**{len(worst)} врач(ей) с возвратом на 2-й приём заметно (>10 п.п.) ниже среднего по своей специальности.**",
                    f"**{len(worst)} doctor(s) with 2nd-visit return notably (>10 pp) below their specialty's average.**",
                ))
                worst_plot = worst.copy()
                worst_plot["specialty"] = worst_plot["specialty"].map(splabel)
                fig_anom = px.bar(
                    worst_plot, x="delta_vs_specialty_avg", y="doctor", orientation="h", color="specialty",
                    text=worst_plot["return_2nd_rate"].map(lambda v: f"{v:.0%}"),
                    labels={"delta_vs_specialty_avg": t("Отклонение от среднего по специальности, п.п.", "Deviation from specialty average, pp"), "doctor": t("Врач", "Doctor"), "specialty": t("Специальность", "Specialty")},
                    color_discrete_map={splabel("Стоматолог"): DARK_GREEN, splabel("Косметолог"): ESPRESSO},
                )
                fig_anom.update_xaxes(tickformat=".0%")
                fig_anom.update_layout(title=t("Отклонение возврата на 2-й приём от среднего по специальности", "2nd-visit return deviation from specialty average"), yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig_anom, use_container_width=True)
                pptx_sections.append({"tab": t("Юнит-экономика", "Unit Economics"), "heading": t("Врачи с аномальным удержанием", "Doctors with anomalous retention"), "figs": [fig_anom]})
            else:
                st.markdown(t("**Явных аномалий по удержанию (>10 п.п. ниже среднего по специальности) не найдено.**",
                              "**No clear retention anomalies (>10 pp below specialty average) found.**"))
            with st.expander(t("Все врачи, прошедшие фильтр (n≥8, когорта зрелая) — детализация", "All doctors passing the filter (n≥8, mature cohort) — detail")):
                anomalies_display = anomalies.copy()
                anomalies_display["specialty"] = anomalies_display["specialty"].map(splabel)
                st.dataframe(
                    anomalies_display.style.format({"return_2nd_rate": "{:.0%}", "specialty_avg_rate": "{:.0%}", "delta_vs_specialty_avg": "{:.0%}"}),
                    use_container_width=True,
                )
        else:
            st.info(t("Нет данных по аномальному удержанию — запустите etl/doctor_retention_check.py", "No retention-anomaly data — run etl/doctor_retention_check.py"))
    else:
        st.info(t("Нет данных по юнит-экономике врачей — запустите etl/load_doctor_economics.py", "No doctor unit-economics data — run etl/load_doctor_economics.py"))

    if data["grade_retention"] is not None and len(data["grade_retention"]):
        st.divider()
        T.section(t("Удержание и LTV по грейдам (стоматология)", "Retention and LTV by grade (dentistry)"))
        T.caption(t(
            "Из Google-таблицы удержания: за всю историю по грейду — возврат на 2-й приём, "
            "удержание 3/6 мес, LTV, выручка за визит, интервал. Показывает, какой грейд "
            "не только маржинальнее, но и лучше удерживает пациентов.",
            "From the retention Google Sheet: full-history figures by grade — 2nd-visit return, "
            "3/6-mo. retention, LTV, revenue per visit, interval. Shows which grade is not only "
            "more profitable but also retains patients better.",
        ))
        gr = data["grade_retention"].copy()
        if len(gr) and gr["retention_6mo"].notna().any():
            best_retention_grade = gr.loc[gr["retention_6mo"].idxmax(), "grade"]
            st.markdown(t(f"**Лучше всего удерживает пациентов на 6 месяцев — грейд {best_retention_grade}.**",
                          f"**{glabel(best_retention_grade)} retains patients best at 6 months.**"))
        retention_metric_labels = {"return_2nd": t("Возврат на 2-й приём", "2nd-visit return"), "retention_3mo": t("Удержание 3 мес", "3-mo. retention"), "retention_6mo": t("Удержание 6 мес", "6-mo. retention")}
        gr_cols = st.columns(len(gr))
        for col, (_, row) in zip(gr_cols, gr.iterrows()):
            with col:
                st.markdown(t(f"**{row['grade']}** · {fmt_num(row['n_patients'])} пациентов", f"**{glabel(row['grade'])}** · {fmt_num(row['n_patients'])} patients"))
                fig_gr = go.Figure(go.Bar(
                    y=[retention_metric_labels[m] for m in retention_metric_labels],
                    x=[row[m] for m in retention_metric_labels], orientation="h",
                    text=[f"{row[m]:.0%}" if pd.notna(row[m]) else "—" for m in retention_metric_labels],
                    textposition="outside", marker_color=DARK_GREEN,
                ))
                fig_gr.update_layout(xaxis=dict(tickformat=".0%", range=[0, 1]), showlegend=False,
                                     margin=dict(l=10, r=10, t=10, b=10), height=180)
                st.plotly_chart(fig_gr, use_container_width=True)
                T.metric_grid([
                    T.metric_card("LTV, ₽", fmt_num(row["ltv"]) if pd.notna(row["ltv"]) else t("н/д", "n/a")),
                    T.metric_card(t("Выручка/визит, ₽", "Revenue/visit, ₽"), fmt_num(row["revenue_per_visit"]) if pd.notna(row["revenue_per_visit"]) else t("н/д", "n/a")),
                    T.metric_card(t("Интервал, дн", "Interval, days"), fmt_num(row["avg_interval_days"]) if pd.notna(row["avg_interval_days"]) else t("н/д", "n/a")),
                ], cols=1)

# ═══════════════════════ CAC ═══════════════════════
with tab8:
    T.section(t("Стоимость привлечения клиента (CAC)", "Customer acquisition cost (CAC)"))
    if data["marketing_spend"] is None:
        st.info(t("Нет данных по расходам на маркетинг (marketing_spend_monthly.csv не найден).", "No marketing spend data (marketing_spend_monthly.csv not found)."))
    else:
        mkt = data["marketing_spend"]
        mkt_cur = mkt[mkt["month"].isin(cur_months)]
        spend_cur = mkt_cur["spend"].sum()
        spend_prev = mkt[mkt["month"].isin(prev_months)]["spend"].sum() if prev_months else None

        mc_cur = data["monthly_client"][data["monthly_client"]["visit_month"].isin(cur_months)]
        n_new_cur = mc_cur["n_clients_new"].sum()
        cac_cur = spend_cur / n_new_cur if n_new_cur else None
        if prev_months:
            mc_prev = data["monthly_client"][data["monthly_client"]["visit_month"].isin(prev_months)]
            n_new_prev = mc_prev["n_clients_new"].sum()
            cac_prev = (spend_prev / n_new_prev) if n_new_prev else None
        else:
            cac_prev = None

        margin_cur_cac = pnl_cur_top["gross_profit"] / pnl_cur_top["revenue"] if pnl_cur_top["revenue"] else None
        total_clients_cur = mc_cur["total_clients"].sum()
        total_revenue_cur = mc_cur["total_revenue"].sum()
        margin_per_client_month = (total_revenue_cur / total_clients_cur * margin_cur_cac) if total_clients_cur and margin_cur_cac else None
        payback_cur = (cac_cur / margin_per_client_month) if cac_cur and margin_per_client_month else None

        ltv_cac_cur = (ltv_cur_top / cac_cur) if (ltv_cur_top and cac_cur) else None

        cac_delta = pct_change(cac_cur, cac_prev) if cac_prev else None
        cac_cols = st.columns(3)
        with cac_cols[0]:
            with st.container(border=True):
                st.metric("CAC", fmt_money(cac_cur) if cac_cur is not None else t("н/д", "n/a"),
                          fmt_pct(cac_delta) if cac_delta is not None else None, delta_color="inverse")  # рост CAC = плохо
        with cac_cols[1]:
            with st.container(border=True):
                st.metric("CAC Payback", t(f"{payback_cur:.1f} мес.", f"{payback_cur:.1f} mo.") if payback_cur is not None else t("н/д", "n/a"))
        with cac_cols[2]:
            with st.container(border=True):
                st.metric("LTV:CAC", f"{ltv_cac_cur:.1f}:1" if ltv_cac_cur is not None else t("н/д", "n/a"))

        st.markdown(f"**{ins.cac_insight(mkt, data['monthly_client'], data['pnl'], cur_months, ltv_cur_top, lang=LANG.lower())}**")
        T.caption(t(
            "Окупаемость считается в визитах/месяцах, а не как в подписочных сервисах — здесь клиент платит "
            "за визит, а не небольшую регулярную сумму, поэтому окупаемость в 1 визит — ожидаемо, а не аномалия. "
            "Главный индикатор здоровья юнит-экономики здесь — LTV:CAC (ориентир ≥ 3:1), не скорость payback.",
            "Payback is measured in visits/months rather than as in subscription services — the client pays "
            "per visit, not a small recurring fee, so payback within a single visit is expected, not an anomaly. "
            "The key unit-economics health indicator here is LTV:CAC (target ≥ 3:1), not payback speed.",
        ))

        st.divider()
        T.section(t("Расходы на маркетинг по каналам", "Marketing spend by channel"))
        mkt_hist = mkt[mkt["month"].isin(HIST_MONTHS)]
        mkt_plot = mkt_hist.copy()
        if LANG == "EN":
            mkt_plot["channel"] = mkt_plot["channel"].map(lambda c: {"Таргетированная реклама": "Targeted ads", "Контекстная реклама": "Search ads", "Партнёрства и рефералы": "Partnerships & referrals"}.get(c, c))
        fig_mkt = px.bar(
            mkt_plot, x="month", y="spend", color="channel", barmode="stack",
            labels={"month": t("Месяц", "Month"), "spend": t("Расходы, ₽", "Spend, ₽"), "channel": t("Канал", "Channel")},
        )
        fig_mkt.update_layout(title=t(f"Расходы на маркетинг по месяцам — по {cur_months[-1]}", f"Marketing spend by month — through {cur_months[-1]}"))
        st.plotly_chart(fig_mkt, use_container_width=True)

        st.divider()
        T.section(t("Динамика CAC", "CAC over time"))
        cac_by_month = mkt_hist.groupby("month")["spend"].sum().reset_index()
        mc_hist = data["monthly_client"][data["monthly_client"]["visit_month"].isin(HIST_MONTHS)][["visit_month", "n_clients_new"]]
        cac_by_month = cac_by_month.merge(mc_hist, left_on="month", right_on="visit_month", how="left")
        cac_by_month["cac"] = cac_by_month["spend"] / cac_by_month["n_clients_new"].replace(0, pd.NA)
        fig_cac = go.Figure()
        T.area_gradient(fig_cac, cac_by_month["month"], cac_by_month["cac"], "CAC, ₽", color=DARK_GREEN)
        fig_cac.update_layout(title=t("CAC по месяцам", "CAC by month"), yaxis_title="₽")
        fig_cac.update_xaxes(type="category")
        st.plotly_chart(fig_cac, use_container_width=True)

        with st.expander(t("Формулы", "Formulas")):
            st.markdown(t(
                "- CAC = расходы на маркетинг за период / новые клиенты за период\n"
                "- CAC Payback = CAC / средняя маржа с клиента в месяц (сколько месяцев "
                "окупается привлечение одного клиента)\n"
                "- LTV:CAC = LTV (см. вкладку «Клиенты») / CAC — ориентир для здоровой "
                "экономики обычно ≥ 3:1",
                "- CAC = marketing spend for the period / new clients for the period\n"
                "- CAC Payback = CAC / average monthly margin per client (how many months "
                "it takes to recoup acquiring one client)\n"
                "- LTV:CAC = LTV (see the Clients tab) / CAC — a healthy target is usually ≥ 3:1",
            ))
        pptx_sections.append({"tab": t("CAC", "CAC"), "heading": ins.cac_insight(mkt, data['monthly_client'], data['pnl'], cur_months, ltv_cur_top, lang=LANG.lower()), "figs": [fig_mkt, fig_cac]})

# ═══════════════════════ ПРОГНОЗ ═══════════════════════
with tab9:
    T.section(t("Сценарный прогноз P&L и денежного потока", "Scenario forecast: P&L and cash flow"))
    T.caption(t(
        "База — среднее/срез за последние 3 факт-месяца. Сценарий держит все "
        "допущения неизменными на весь горизонт (не разгоняется постепенно по "
        "месяцам) — это ответ на вопрос «что если это станет новой нормой», а не "
        "помесячный план перехода. Модель визитов: спрос (запись × конверсия) "
        "ограничен мощностью команды (врачи × загрузка на врача) — берётся "
        "меньшее из двух, если спрос превышает мощность.",
        "Base — average/snapshot over the last 3 actual months. The scenario holds all "
        "assumptions constant across the whole horizon (it doesn't ramp up gradually month "
        "by month) — this answers \"what if this became the new normal\", not a month-by-month "
        "transition plan. Visit model: demand (bookings × conversion) is capped by team "
        "capacity (doctors × workload per doctor) — the smaller of the two is used when "
        "demand exceeds capacity.",
    ))

    base_months = ALL_MONTHS[-3:]
    pnl_base_df = data["pnl"][data["pnl"]["month"].isin(base_months)]
    base_revenue_total = pnl_base_df["revenue"].sum()
    base_visits_total = n_visits_actual(base_months)
    base_avg_check = base_revenue_total / base_visits_total if base_visits_total else 0
    base_variable_costs_total = pnl_base_df["variable_costs"].sum()
    base_var_cost_ratio = base_variable_costs_total / base_revenue_total if base_revenue_total else 0
    base_fixed_costs = pnl_base_df["fixed_costs"].mean()

    funnel_base = data["funnel"][data["funnel"]["month"].isin(base_months)] if data["funnel"] is not None else None
    base_n_booked_month = (funnel_base["n_booked"].sum() / len(base_months)) if funnel_base is not None and len(funnel_base) else None
    base_conversion = (funnel_base["n_completed"].sum() / funnel_base["n_booked"].sum()) if funnel_base is not None and funnel_base["n_booked"].sum() else None

    team_base_month = data["team"][data["team"]["month"] == base_months[-1]]
    base_n_doctors = team_base_month.groupby("specialty")["n_doctors"].max().sum() if len(team_base_month) else None

    visits_per_doctor_base = (base_visits_total / len(base_months)) / base_n_doctors if base_n_doctors else None

    clients_base_total = data["monthly_client"][data["monthly_client"]["visit_month"].isin(base_months)]["total_clients"].sum()
    visits_per_client_base = base_visits_total / clients_base_total if clients_base_total else None

    cash_base = None
    if data["cash_runway"] is not None:
        cr_base = data["cash_runway"][data["cash_runway"]["month"].isin(base_months)]
        if len(cr_base):
            cash_base = cr_base.sort_values("month").iloc[-1]["cash"]

    missing_base = [name for name, v in [
        (t("запись/конверсия (funnel_monthly.csv)", "booking/conversion (funnel_monthly.csv)"), base_n_booked_month),
        (t("команда врачей (doctor_team_monthly.csv)", "doctor team (doctor_team_monthly.csv)"), base_n_doctors),
        (t("остаток денег (cash_runway_monthly.csv)", "cash balance (cash_runway_monthly.csv)"), cash_base),
        (t("визиты на клиента (monthly_client_summary.csv)", "visits per client (monthly_client_summary.csv)"), visits_per_client_base),
    ] if v is None]

    if missing_base:
        st.info(t(f"Не хватает базовых данных для прогноза: {', '.join(missing_base)}.", f"Missing base data for the forecast: {', '.join(missing_base)}."))
    else:
        st.markdown(t(
            f"**База (среднее за {base_months[0]} — {base_months[-1]}):** "
            f"{fmt_num(base_visits_total / len(base_months))} визитов/мес, средний чек {fmt_money(base_avg_check)}, "
            f"{fmt_num(base_n_doctors)} врачей, конверсия {base_conversion:.0%}, "
            f"постоянные расходы {fmt_money(base_fixed_costs)}/мес.",
            f"**Base (average over {base_months[0]} — {base_months[-1]}):** "
            f"{fmt_num(base_visits_total / len(base_months))} visits/mo, average check {fmt_money(base_avg_check)}, "
            f"{fmt_num(base_n_doctors)} doctors, conversion {base_conversion:.0%}, "
            f"fixed costs {fmt_money(base_fixed_costs)}/mo.",
        ))

        horizon = st.radio(t("Горизонт прогноза", "Forecast horizon"), [6, 12], horizontal=True, format_func=lambda x: t(f"{x} мес.", f"{x} mo."))

        st.markdown(t("**Допущения (% к базе — под каждым слайдером показано «было → станет»):**",
                      "**Assumptions (% vs. base — each slider shows \"was → becomes\" below it):**"))
        s1, s2, s3 = st.columns(3)
        with s1:
            team_delta = st.slider(t("Рост/снижение команды врачей", "Doctor team growth/decline"), -50, 100, 0, step=5, format="%d%%") / 100
            T.caption(t(f"{fmt_num(base_n_doctors)} → {fmt_num(base_n_doctors * (1 + team_delta))} врачей", f"{fmt_num(base_n_doctors)} → {fmt_num(base_n_doctors * (1 + team_delta))} doctors"))
            booking_delta = st.slider(t("Изменение объёма записи", "Change in booking volume"), -50, 100, 0, step=5, format="%d%%") / 100
            T.caption(t(f"{fmt_num(base_n_booked_month)} → {fmt_num(base_n_booked_month * (1 + booking_delta))} записей/мес", f"{fmt_num(base_n_booked_month)} → {fmt_num(base_n_booked_month * (1 + booking_delta))} bookings/mo"))
        with s2:
            conversion_delta = st.slider(t("Изменение конверсии", "Change in conversion"), -50, 100, 0, step=5, format="%d%%") / 100
            conversion_preview = min(max(base_conversion * (1 + conversion_delta), 0), 1)
            T.caption(f"{base_conversion:.0%} → {conversion_preview:.0%}")
            utilization_delta = st.slider(t("Рост загрузки (визитов/врача)", "Workload growth (visits/doctor)"), -50, 100, 0, step=5, format="%d%%") / 100
            T.caption(t(f"{visits_per_doctor_base:.1f} → {visits_per_doctor_base * (1 + utilization_delta):.1f} визитов/врача/мес", f"{visits_per_doctor_base:.1f} → {visits_per_doctor_base * (1 + utilization_delta):.1f} visits/doctor/mo"))
        with s3:
            price_delta = st.slider(t("Средний чек / цены", "Average check / prices"), -50, 100, 0, step=5, format="%d%%") / 100
            T.caption(f"{fmt_money(base_avg_check)} → {fmt_money(base_avg_check * (1 + price_delta))}")
            fixed_costs_delta = st.slider(t("Постоянные расходы", "Fixed costs"), -50, 100, 0, step=5, format="%d%%") / 100
            T.caption(f"{fmt_money(base_fixed_costs)} → {fmt_money(base_fixed_costs * (1 + fixed_costs_delta))}")

        # Расчёт сценария — одинаковый для каждого месяца горизонта ("новая
        # нормальность"), не постепенный разгон по месяцам.
        n_doctors_scn = base_n_doctors * (1 + team_delta)
        capacity_scn = n_doctors_scn * visits_per_doctor_base * (1 + utilization_delta)
        n_booked_scn = base_n_booked_month * (1 + booking_delta)
        conversion_scn = min(max(base_conversion * (1 + conversion_delta), 0), 1)
        demand_scn = n_booked_scn * conversion_scn
        n_visits_scn = min(demand_scn, capacity_scn)
        # Допуск 1% — при нулевых допущениях спрос (из воронки) и мощность (из
        # факт. визитов) почти совпадают, но приходят из разных источников и
        # отличаются на уровне шума (доли визита), это не реальное ограничение.
        capacity_constrained = demand_scn > capacity_scn * 1.01

        avg_check_scn = base_avg_check * (1 + price_delta)
        revenue_scn = n_visits_scn * avg_check_scn
        variable_costs_scn = revenue_scn * base_var_cost_ratio
        fixed_costs_scn = base_fixed_costs * (1 + fixed_costs_delta)
        gross_profit_scn = revenue_scn - variable_costs_scn
        operating_profit_scn = gross_profit_scn - fixed_costs_scn

        margin_scn = 1 - base_var_cost_ratio
        be_revenue_scn = fixed_costs_scn / margin_scn if margin_scn else None
        be_visits_scn = be_revenue_scn / avg_check_scn if be_revenue_scn is not None and avg_check_scn else None
        be_clients_scn = be_visits_scn / visits_per_client_base if be_visits_scn is not None else None

        if capacity_constrained:
            st.warning(t(
                f"При этих допущениях спрос ({fmt_num(demand_scn)} визитов/мес) превышает мощность "
                f"команды ({fmt_num(capacity_scn)} визитов/мес) — визиты в расчёте ограничены мощностью.",
                f"Under these assumptions, demand ({fmt_num(demand_scn)} visits/mo) exceeds team "
                f"capacity ({fmt_num(capacity_scn)} visits/mo) — visits in the calculation are capped by capacity.",
            ))

        st.divider()
        T.section(t(f"Сценарий против базы — горизонт {horizon} мес.", f"Scenario vs. base — {horizon}-mo. horizon"))
        scn_rows = [
            (t("Визиты/мес", "Visits/mo"), base_visits_total / len(base_months), n_visits_scn, "num"),
            (t("Выручка/мес", "Revenue/mo"), base_revenue_total / len(base_months), revenue_scn, "money"),
            (t("Операционная прибыль/мес", "Operating profit/mo"),
             (base_revenue_total - base_variable_costs_total) / len(base_months) - base_fixed_costs,
             operating_profit_scn, "money"),
        ]
        scn_cards = []
        for label, base_v, scn_v, kind in scn_rows:
            fmt = fmt_money if kind == "money" else fmt_num
            delta = pct_change(scn_v, base_v)
            scn_cards.append(T.metric_card(label, fmt(scn_v), f"{abs(delta):.0%}" if delta is not None else None,
                                            delta is None or delta >= 0))
        T.metric_grid(scn_cards, cols=3)

        st.markdown(t(
            f"**Точка безубыточности при этом сценарии: {fmt_num(be_visits_scn)} визитов/мес** "
            f"(≈ {fmt_num(be_clients_scn)} клиентов при {visits_per_client_base:.1f} визита/клиента в среднем). "
            f"Факт по базе — {fmt_num(base_visits_total / len(base_months))} визитов/мес.",
            f"**Break-even under this scenario: {fmt_num(be_visits_scn)} visits/mo** "
            f"(≈ {fmt_num(be_clients_scn)} clients at {visits_per_client_base:.1f} visits/client on average). "
            f"Actual base — {fmt_num(base_visits_total / len(base_months))} visits/mo.",
        ))

        # Карточки выше — среднемесячные (не зависят от горизонта, это одна и та
        # же "новая нормальность" каждый месяц). Чтобы при переключении 6/12 мес
        # было видно, что именно меняется — показываем итог, накопленный за весь
        # выбранный горизонт.
        T.caption(t(f"Ниже — то же самое, накопленным итогом за весь горизонт ({horizon} мес.), это и меняется при переключении 6/12 мес.:",
                    f"Below — the same figures as a cumulative total over the whole horizon ({horizon} mo.); this is what changes when you switch 6/12 mo.:"))
        horizon_cards = [
            T.metric_card(t(f"Визиты за {horizon} мес.", f"Visits over {horizon} mo."), fmt_num(n_visits_scn * horizon)),
            T.metric_card(t(f"Выручка за {horizon} мес.", f"Revenue over {horizon} mo."), fmt_money(revenue_scn * horizon)),
            T.metric_card(t(f"Операционный результат за {horizon} мес.", f"Operating result over {horizon} mo."), fmt_money(operating_profit_scn * horizon),
                          positive=operating_profit_scn >= 0),
        ]
        T.metric_grid(horizon_cards, cols=3)

        text_colors_scn = ["#FFFFFF", TEXT_DARK, TEXT_DARK, TEXT_DARK,
                            (TEXT_DARK if operating_profit_scn >= 0 else T.NEGATIVE_DEEP)]
        # При убытке столбец маленький — подпись внутри не влезает, выносим наружу.
        text_positions_scn = ["inside", "inside", "inside", "inside", "outside" if operating_profit_scn < 0 else "inside"]
        fig_scn = go.Figure(
            go.Waterfall(
                orientation="v",
                measure=["relative", "relative", "total", "relative", "total"],
                x=[t("Выручка", "Revenue"), t("Переменные расходы", "Variable costs"), t("Маржинальная прибыль", "Gross profit"),
                   t("Постоянные расходы", "Fixed costs"), t("Операционный результат", "Operating result")],
                y=[to_k(revenue_scn), to_k(-variable_costs_scn), 0, to_k(-fixed_costs_scn), 0],
                text=[fmt_k(v) for v in [revenue_scn, -variable_costs_scn, gross_profit_scn, -fixed_costs_scn, operating_profit_scn]],
                textposition=text_positions_scn,
                textfont=dict(color=text_colors_scn, size=DATA_LABEL_SIZE),
                increasing=dict(marker=dict(color=DARK_GREEN)),
                decreasing=dict(marker=dict(color=GRAY)),
                totals=dict(marker=dict(color=SAGE)),
                connector=dict(line=dict(color=GRAY)),
            )
        )
        fig_scn.update_layout(title=t("P&L сценария (среднемесячно)", "Scenario P&L (monthly average)"), showlegend=False, yaxis_title=t("тыс. ₽", "₽ thousand"))
        st.plotly_chart(fig_scn, use_container_width=True)
        pptx_sections.append({"tab": t("Прогноз", "Forecast"), "heading": t(f"Сценарный P&L — горизонт {horizon} мес.", f"Scenario P&L — {horizon}-mo. horizon"), "figs": [fig_scn]})

        st.divider()
        T.section(t("Денежный поток по сценарию", "Cash flow under the scenario"), t("Остаток = текущий факт + накопленная сценарная прибыль/убыток", "Balance = current actual + accumulated scenario profit/loss"))
        months_ahead = list(range(1, horizon + 1))
        cash_traj = [cash_base + operating_profit_scn * m for m in months_ahead]
        fig_cash_scn = go.Figure()
        T.area_gradient(fig_cash_scn, [t(f"+{m} мес.", f"+{m} mo.") for m in months_ahead], [to_k(c) for c in cash_traj],
                         t("Остаток, тыс. ₽", "Balance, ₽ thousand"), color=DARK_GREEN)
        fig_cash_scn.add_hline(y=0, line_dash="dash", line_color=GRAY)
        fig_cash_scn.update_layout(title=t("Прогнозный остаток денежных средств", "Projected cash balance"), showlegend=False, yaxis_title=t("тыс. ₽", "₽ thousand"))
        fig_cash_scn.update_xaxes(type="category")
        st.plotly_chart(fig_cash_scn, use_container_width=True)
        pptx_sections.append({"tab": t("Прогноз", "Forecast"), "heading": t("Прогнозный остаток денежных средств", "Projected cash balance"), "figs": [fig_cash_scn]})

        first_negative = next((m for m, c in zip(months_ahead, cash_traj) if c < 0), None)
        if cash_base < 0:
            if operating_profit_scn >= 0:
                first_positive = next((m for m, c in zip(months_ahead, cash_traj) if c >= 0), None)
                if first_positive is not None:
                    st.markdown(t(
                        f"**Остаток пока отрицательный ({fmt_money(cash_base)}), но при этом сценарии "
                        f"дефицит будет сокращаться и выйдет в плюс примерно через {first_positive} мес.**",
                        f"**The balance is still negative ({fmt_money(cash_base)}), but under this scenario "
                        f"the deficit will shrink and turn positive in about {first_positive} mo.**",
                    ))
                else:
                    st.markdown(t(
                        f"**Остаток пока отрицательный ({fmt_money(cash_base)}) — при этом сценарии дефицит "
                        f"будет сокращаться, но не выйдет в плюс за {horizon} мес. (останется {fmt_money(cash_traj[-1])}).**",
                        f"**The balance is still negative ({fmt_money(cash_base)}) — under this scenario the deficit "
                        f"will shrink but won't turn positive within {horizon} mo. (will remain {fmt_money(cash_traj[-1])}).**",
                    ))
            else:
                st.markdown(t(
                    f"**Остаток уже отрицательный ({fmt_money(cash_base)}) — при этом сценарии дефицит будет "
                    f"расти дальше (через {horizon} мес. — {fmt_money(cash_traj[-1])}).**",
                    f"**The balance is already negative ({fmt_money(cash_base)}) — under this scenario the deficit "
                    f"will keep growing (after {horizon} mo. — {fmt_money(cash_traj[-1])}).**",
                ))
        elif first_negative is not None:
            st.markdown(t(f"**При этих допущениях остаток уйдёт в минус через {first_negative} мес.**",
                          f"**Under these assumptions, the balance will turn negative in {first_negative} mo.**"))
        else:
            st.markdown(t(f"**Остаток не уходит в минус за {horizon} мес. при этих допущениях.**",
                          f"**The balance does not turn negative within {horizon} mo. under these assumptions.**"))

        st.divider()

        def _build_forecast_excel() -> bytes:
            """Собирает 3 листа: допущения (было/станет), P&L сценария (среднемесячно),
            денежный поток по месяцам горизонта — для выгрузки кнопкой ниже."""
            col_metric, col_assumption, col_base, col_scenario = t("Показатель", "Metric"), t("Допущение", "Assumption"), t("База", "Base"), t("Сценарий", "Scenario")
            assumptions_df = pd.DataFrame([
                {col_metric: t("Команда врачей", "Doctor team"), col_assumption: f"{team_delta:+.0%}",
                 col_base: base_n_doctors, col_scenario: n_doctors_scn},
                {col_metric: t("Объём записи, шт/мес", "Bookings, per month"), col_assumption: f"{booking_delta:+.0%}",
                 col_base: base_n_booked_month, col_scenario: n_booked_scn},
                {col_metric: t("Конверсия", "Conversion"), col_assumption: f"{conversion_delta:+.0%}",
                 col_base: base_conversion, col_scenario: conversion_scn},
                {col_metric: t("Загрузка, визитов/врача/мес", "Workload, visits/doctor/month"), col_assumption: f"{utilization_delta:+.0%}",
                 col_base: visits_per_doctor_base, col_scenario: visits_per_doctor_base * (1 + utilization_delta)},
                {col_metric: t("Средний чек, ₽", "Average check, ₽"), col_assumption: f"{price_delta:+.0%}",
                 col_base: base_avg_check, col_scenario: avg_check_scn},
                {col_metric: t("Постоянные расходы, ₽/мес", "Fixed costs, ₽/month"), col_assumption: f"{fixed_costs_delta:+.0%}",
                 col_base: base_fixed_costs, col_scenario: fixed_costs_scn},
                {col_metric: t("Визиты, шт/мес (спрос ограничен мощностью)", "Visits/month (demand capped by capacity)"), col_assumption: "—",
                 col_base: base_visits_total / len(base_months), col_scenario: n_visits_scn},
            ])
            pnl_df = pd.DataFrame([{
                t("Выручка/мес", "Revenue/mo"): revenue_scn, t("Переменные расходы/мес", "Variable costs/mo"): variable_costs_scn,
                t("Маржинальная прибыль/мес", "Gross profit/mo"): gross_profit_scn, t("Постоянные расходы/мес", "Fixed costs/mo"): fixed_costs_scn,
                t("Операционная прибыль/мес", "Operating profit/mo"): operating_profit_scn,
                t("ТБУ, визитов/мес", "Break-even, visits/mo"): be_visits_scn, t("ТБУ, клиентов/мес", "Break-even, clients/mo"): be_clients_scn,
                t("Горизонт, мес.", "Horizon, mo."): horizon,
            }])
            cash_df = pd.DataFrame({
                t("Месяц горизонта", "Month of horizon"): [f"+{m}" for m in months_ahead],
                t("Прогнозный остаток, ₽", "Projected balance, ₽"): cash_traj,
            })
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                assumptions_df.to_excel(writer, sheet_name=t("Допущения", "Assumptions"), index=False)
                pnl_df.to_excel(writer, sheet_name=t("P&L сценария", "Scenario P&L"), index=False)
                cash_df.to_excel(writer, sheet_name=t("Денежный поток", "Cash flow"), index=False)
            return buf.getvalue()

        st.download_button(
            t("⬇️ Выгрузить прогноз в Excel", "⬇️ Export forecast to Excel"),
            data=_build_forecast_excel(),
            file_name=t(f"Прогноз_{selected_period}_{horizon}мес.xlsx", f"Forecast_{selected_period}_{horizon}mo.xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

# ═══════════════════════ Экспорт в PPTX ═══════════════════════
# Секции добавляются в порядке выполнения кода (вкладки перемешаны), поэтому
# сортируем по порядку вкладок дашборда — иначе одна вкладка в PPTX разбивается
# на несколько блоков с повторяющимся заголовком.
PPTX_TAB_ORDER = [t("Финансовые показатели", "Financials"), t("Клиенты", "Clients"), t("Операционная эффективность", "Operations"),
                  t("Продукты/направления", "Products/Directions"), t("Юнит-экономика", "Unit Economics"), t("Запас прочности", "Margin of Safety"), "KPI"]
pptx_sections.sort(key=lambda s: PPTX_TAB_ORDER.index(s["tab"]) if s["tab"] in PPTX_TAB_ORDER else 99)

if pptx_button_placeholder.button(t("📊 Сформировать PPTX", "📊 Generate PPTX"), use_container_width=True):
    with st.spinner(t("Собираю презентацию...", "Building the presentation...")):
        import pptx_export

        pptx_bytes = pptx_export.build_pptx(
            logo_path=str(ASSETS_DIR / "logo.png"),
            selected_period=selected_period,
            data_range=f"{data['visits']['visit_datetime'].min().date()} — {data['visits']['visit_datetime'].max().date()}",
            metrics=summary_metrics_for_pptx,
            narrative=summary_narrative,
            sections=pptx_sections,
            lang=LANG.lower(),
        )
    pptx_download_placeholder.download_button(
        t("⬇️ Скачать PPTX", "⬇️ Download PPTX"),
        data=pptx_bytes,
        file_name=t(f"Отчет_Meridian_Health_{selected_period}.pptx", f"Report_Meridian_Health_{selected_period}.pptx"),
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        use_container_width=True,
    )
