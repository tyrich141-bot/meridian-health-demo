"""
Генерация текстовых автовыводов для дашборда: берёт посчитанные метрики
(текущий период vs предыдущий) и собирает предложения в стиле операционного
отчёта клиники ("Выручка +1% к апрелю, но операционный убыток вырос в 2,8 раз...").

Это не LLM-генерация — простые шаблоны на основе знака/размера изменения,
детерминированные и воспроизводимые. Глаголы согласуются с родом/числом
существительного вручную в каждом шаблоне (a не через один общий помощник),
чтобы не ломать грамматику. Каждая функция принимает lang="ru"/"en" и строит
предложение на нужном языке веткой if/else — раздельные шаблоны, а не перевод
готовой строки, чтобы согласование слов оставалось корректным в обоих языках.
"""

import pandas as pd

from formatting import fmt_money, fmt_num


def pct_change(new, old):
    if old in (0, None) or pd.isna(old) or pd.isna(new):
        return None
    return (new - old) / abs(old)


def verb(delta, forms, threshold=0.01):
    """forms = (выросла, снизилась, осталась_на_уровне) — под конкретное слово/род."""
    rose, fell, flat = forms
    if delta is None:
        return None
    if abs(delta) < threshold:
        return flat
    return rose if delta > 0 else fell


def sum_col(df, month_col, months, col):
    return df[df[month_col].isin(months)][col].sum()


def oblique(spec: str, lang: str = "ru") -> str:
    """Родительный/дательный/предложный падеж для 'Стоматология'/'Косметология', в нижнем
    регистре для использования в середине предложения (у существительных ж.р. на -ия
    все три падежа в ед.ч. совпадают: -ии). В английском склонения нет — просто нижний регистр."""
    if lang == "en":
        return spec.lower()
    base = spec[:-1] + "и" if spec.endswith("я") else spec
    return base.lower()


# ───────────────────────── P&L ─────────────────────────
def pnl_insight(pnl_df, cur_months, prev_months, lang="ru"):
    cols = ["revenue", "variable_costs", "gross_profit", "fixed_costs", "operating_profit"]
    cur = pnl_df[pnl_df["month"].isin(cur_months)][cols].sum()
    if not prev_months:
        if lang == "en":
            return f"Revenue for the period — {fmt_money(cur['revenue'])}, operating result — {fmt_money(cur['operating_profit'])}."
        return f"Выручка периода — {fmt_money(cur['revenue'])}, операционный результат — {fmt_money(cur['operating_profit'])}."
    prev = pnl_df[pnl_df["month"].isin(prev_months)][cols].sum()
    margin_cur = cur["gross_profit"] / cur["revenue"] if cur["revenue"] else 0
    margin_prev = prev["gross_profit"] / prev["revenue"] if prev["revenue"] else 0

    rev_delta = pct_change(cur["revenue"], prev["revenue"])
    op_cur, op_prev = cur["operating_profit"], prev["operating_profit"]
    margin_delta = margin_cur - margin_prev
    var_delta = pct_change(cur["variable_costs"], prev["variable_costs"])

    if lang == "en":
        rev_verb = verb(rev_delta, ("grew", "declined", "stayed flat"))
        sentence = f"Revenue {rev_verb} {abs(rev_delta):.0%} to {fmt_money(cur['revenue'])}" if rev_delta is not None else f"Revenue — {fmt_money(cur['revenue'])}"
        if op_cur < 0 and op_prev < 0:
            loss_grew = abs(op_cur) > abs(op_prev)
            loss_verb = "grew" if loss_grew else "shrank"
            ratio = abs(op_cur / op_prev) if loss_grew else abs(op_prev / op_cur)
            if ratio > 1.3:
                sentence += f", the operating loss {loss_verb} {ratio:.1f}x (to {fmt_money(abs(op_cur))})."
            else:
                sentence += f", the operating loss {loss_verb} to {fmt_money(abs(op_cur))}."
        elif op_cur >= 0 and op_prev >= 0:
            profit_verb = "grew" if op_cur > op_prev else ("declined" if op_cur < op_prev else "stayed flat")
            sentence += f", operating profit {profit_verb} to {fmt_money(op_cur)}."
        elif op_cur < 0 <= op_prev:
            sentence += f", the result flipped from a profit ({fmt_money(op_prev)}) to a loss ({fmt_money(abs(op_cur))})."
        else:
            sentence += f", the clinic turned around from a loss to a profit ({fmt_money(op_cur)} vs. a loss of {fmt_money(abs(op_prev))})."
        margin_verb = verb(margin_delta, ("grew", "declined", "stayed flat"), threshold=0.005)
        sentence += f" Margin {margin_verb} from {margin_prev:.0%} to {margin_cur:.0%}."
        if var_delta is not None and rev_delta is not None and var_delta > rev_delta + 0.05:
            var_verb = "grew" if var_delta > 0 else "declined"
            sentence += f" Variable costs {var_verb} {abs(var_delta):.0%}, outpacing revenue growth."
        return sentence

    rev_verb = verb(rev_delta, ("выросла", "снизилась", "осталась на уровне"))
    sentence = f"Выручка {rev_verb} на {abs(rev_delta):.0%} до {fmt_money(cur['revenue'])}" if rev_delta is not None else f"Выручка — {fmt_money(cur['revenue'])}"

    if op_cur < 0 and op_prev < 0:
        # оба периода в убытке: "рост убытка" = убыток стал больше по модулю
        loss_grew = abs(op_cur) > abs(op_prev)
        loss_verb = "вырос" if loss_grew else "сократился"
        ratio = abs(op_cur / op_prev) if loss_grew else abs(op_prev / op_cur)
        if ratio > 1.3:
            sentence += f", операционный убыток {loss_verb} в {ratio:.1f} раза (до {fmt_money(abs(op_cur))})."
        else:
            sentence += f", операционный убыток {loss_verb} до {fmt_money(abs(op_cur))}."
    elif op_cur >= 0 and op_prev >= 0:
        # оба периода в прибыли
        profit_verb = "выросла" if op_cur > op_prev else ("снизилась" if op_cur < op_prev else "не изменилась")
        sentence += f", операционная прибыль {profit_verb} до {fmt_money(op_cur)}."
    elif op_cur < 0 <= op_prev:
        sentence += f", результат перешёл из прибыли ({fmt_money(op_prev)}) в убыток ({fmt_money(abs(op_cur))})."
    else:  # op_prev < 0 <= op_cur
        sentence += f", клиника вышла из убытка в прибыль ({fmt_money(op_cur)} против убытка {fmt_money(abs(op_prev))})."

    margin_verb = verb(margin_delta, ("выросла", "снизилась", "осталась на уровне"), threshold=0.005)
    sentence += f" Маржинальность {margin_verb} с {margin_prev:.0%} до {margin_cur:.0%}."

    if var_delta is not None and rev_delta is not None and var_delta > rev_delta + 0.05:
        var_verb = "выросли" if var_delta > 0 else "снизились"
        sentence += f" Переменные расходы {var_verb} на {abs(var_delta):.0%}, опережая рост выручки."
    return sentence


# ───────────────────────── Клиенты ─────────────────────────
def clients_insight(monthly_df, cur_months, prev_months, avg_check_cur=None, avg_check_prev=None, lang="ru"):
    """avg_check_cur/avg_check_prev — переопределение среднего чека извне, чтобы
    тезис использовал ту же формулу, что и карточка на Сводке (выручка модели /
    консультации по ЗП), а не пересчитывал из CRM-выручки с другим результатом."""
    def totals(months):
        return {
            "new": sum_col(monthly_df, "visit_month", months, "n_clients_new"),
            "repeat": sum_col(monthly_df, "visit_month", months, "n_clients_repeat"),
            "n_visits": sum_col(monthly_df, "visit_month", months, "n_visits_new") + sum_col(monthly_df, "visit_month", months, "n_visits_repeat"),
            "revenue": sum_col(monthly_df, "visit_month", months, "total_revenue"),
        }
    cur = totals(cur_months)
    cur["avg_check"] = avg_check_cur if avg_check_cur is not None else (cur["revenue"] / cur["n_visits"] if cur["n_visits"] else 0)
    cur["repeat_share"] = cur["repeat"] / (cur["new"] + cur["repeat"]) if (cur["new"] + cur["repeat"]) else 0

    if not prev_months:
        if lang == "en":
            return f"New clients: {fmt_num(cur['new'])}, returning: {fmt_num(cur['repeat'])} (returning share {cur['repeat_share']:.0%}). Average check: {fmt_money(cur['avg_check'])}."
        return f"Новые клиенты: {fmt_num(cur['new'])}, повторные: {fmt_num(cur['repeat'])} (доля повторных {cur['repeat_share']:.0%}). Средний чек: {fmt_money(cur['avg_check'])}."

    prev = totals(prev_months)
    prev["avg_check"] = avg_check_prev if avg_check_prev is not None else (prev["revenue"] / prev["n_visits"] if prev["n_visits"] else 0)
    prev["repeat_share"] = prev["repeat"] / (prev["new"] + prev["repeat"]) if (prev["new"] + prev["repeat"]) else 0

    new_delta = pct_change(cur["new"], prev["new"])
    repeat_delta = pct_change(cur["repeat"], prev["repeat"])
    check_delta = pct_change(cur["avg_check"], prev["avg_check"])
    share_delta = cur["repeat_share"] - prev["repeat_share"]

    if lang == "en":
        new_verb = verb(new_delta, ("grew", "declined", "stayed flat"))
        repeat_verb = verb(repeat_delta, ("grew", "declined", "stayed flat"))
        share_verb = verb(share_delta, ("grew", "declined", "stayed flat"), threshold=0.005)
        check_verb = verb(check_delta, ("grew", "declined", "stayed flat"))
        sentence = f"New clients {new_verb} to {fmt_num(cur['new'])} ({new_delta:+.0%})" if new_delta is not None else f"New clients: {fmt_num(cur['new'])}"
        sentence += f", returning clients {repeat_verb} to {fmt_num(cur['repeat'])} ({repeat_delta:+.0%})." if repeat_delta is not None else "."
        sentence += f" Returning client share {share_verb} from {prev['repeat_share']:.0%} to {cur['repeat_share']:.0%}."
        sentence += f" Average check {check_verb} {abs(check_delta):.0%} to {fmt_money(cur['avg_check'])}." if check_delta is not None else ""
        return sentence

    new_verb = verb(new_delta, ("выросло", "снизилось", "не изменилось"))
    repeat_verb = verb(repeat_delta, ("выросло", "снизилось", "не изменилось"))
    share_verb = verb(share_delta, ("выросла", "снизилась", "не изменилась"), threshold=0.005)
    check_verb = verb(check_delta, ("вырос", "снизился", "не изменился"))

    sentence = f"Количество новых клиентов {new_verb} до {fmt_num(cur['new'])} ({new_delta:+.0%})" if new_delta is not None else f"Новые клиенты: {fmt_num(cur['new'])}"
    sentence += f", повторных {repeat_verb} до {fmt_num(cur['repeat'])} ({repeat_delta:+.0%})." if repeat_delta is not None else "."
    sentence += f" Доля повторных клиентов в базе {share_verb} с {prev['repeat_share']:.0%} до {cur['repeat_share']:.0%}."
    sentence += f" Средний чек {check_verb} на {abs(check_delta):.0%} до {fmt_money(cur['avg_check'])}." if check_delta is not None else ""
    return sentence


# ───────────────────────── Выручка по направлениям ─────────────────────────
DIRECTION_EN = {
    "Стоматология": "Dentistry", "Косметология": "Cosmetology", "Инъекции": "Injectables",
    "Гигиенист": "Hygienist", "Прочее (доп. доход)": "Other (extra income)",
}


def direction_insight(by_direction_df, cur_months, prev_months, lang="ru"):
    cur = by_direction_df[by_direction_df["month"].isin(cur_months)].groupby("direction")["revenue"].sum()
    prev = by_direction_df[by_direction_df["month"].isin(prev_months)].groupby("direction")["revenue"].sum() if prev_months else pd.Series(dtype=float)
    total_cur = cur.sum()
    parts = []
    for direction in cur.sort_values(ascending=False).index:
        v = cur[direction]
        if v <= 0:
            continue
        share = v / total_cur if total_cur else 0
        delta = pct_change(v, prev.get(direction, 0)) if prev_months else None
        label = DIRECTION_EN.get(direction, direction) if lang == "en" else direction
        if delta is not None:
            if lang == "en":
                parts.append(f"{label} ({share:.0%} of revenue, {delta:+.0%} vs. prior period)")
            else:
                parts.append(f"{label} ({share:.0%} выручки, {delta:+.0%} к пред. периоду)")
        else:
            parts.append(f"{label} ({share:.0%} {'of revenue' if lang == 'en' else 'выручки'})")
    if lang == "en":
        return "Revenue breakdown: " + "; ".join(parts) + "." if parts else "No direction data for the period."
    return "Структура выручки: " + "; ".join(parts) + "." if parts else "Нет данных по направлениям за период."


# ───────────────────────── Команда врачей ─────────────────────────
def doctors_insight(team_df, cur_months, prev_months, visits_cur=None, visits_prev=None, lang="ru"):
    """visits_cur/visits_prev — переопределение числа визитов извне (по ЗП),
    чтобы тезис совпадал с карточкой "Консультации" на Сводке, а не пересчитывал
    из CRM-счётчика team_df с другим результатом.
    n_doctors — снапшот последнего месяца периода, не максимум по месяцам
    (иначе врачи, ушедшие в середине периода, завышают число — баг, найден 2026-07)."""
    cur = team_df[team_df["month"].isin(cur_months)].groupby("specialty").agg(n_visits=("n_visits", "sum"))
    total_doctors_cur = team_df[team_df["month"] == cur_months[-1]]["n_doctors"].sum()
    total_visits_cur = visits_cur if visits_cur is not None else cur["n_visits"].sum()
    if not prev_months:
        if lang == "en":
            return f"Team: {fmt_num(total_doctors_cur)} doctors, {fmt_num(total_visits_cur)} visits for the period."
        return f"Команда: {fmt_num(total_doctors_cur)} врачей, {fmt_num(total_visits_cur)} визитов за период."
    prev = team_df[team_df["month"].isin(prev_months)].groupby("specialty").agg(n_visits=("n_visits", "sum"))
    total_doctors_prev = team_df[team_df["month"] == prev_months[-1]]["n_doctors"].sum()
    total_visits_prev = visits_prev if visits_prev is not None else prev["n_visits"].sum()

    doc_delta = pct_change(total_doctors_cur, total_doctors_prev)
    visit_delta = pct_change(total_visits_cur, total_visits_prev)

    if lang == "en":
        doc_verb = verb(doc_delta, ("grew", "declined", "stayed flat"))
        visit_verb = verb(visit_delta, ("grew", "declined", "stayed flat"))
        sentence = f"The team {doc_verb} from {fmt_num(total_doctors_prev)} to {fmt_num(total_doctors_cur)}" if doc_delta is not None else f"Team size: {fmt_num(total_doctors_cur)}"
        sentence += f", visits {visit_verb} to {fmt_num(total_visits_cur)}." if visit_delta is not None else "."
        if doc_delta is not None and visit_delta is not None:
            if doc_delta < -0.01 and visit_delta >= -0.01:
                sentence += " Suggests rising per-doctor productivity."
            elif doc_delta > 0.01 and (visit_delta is None or visit_delta < doc_delta):
                sentence += " Visit growth is lagging team growth -> per-doctor productivity is declining."
        return sentence

    doc_verb = verb(doc_delta, ("выросло", "снизилось", "не изменилось"))
    visit_verb = verb(visit_delta, ("выросли", "снизились", "не изменились"))
    sentence = f"Число врачей {doc_verb} с {fmt_num(total_doctors_prev)} до {fmt_num(total_doctors_cur)}" if doc_delta is not None else f"Число врачей: {fmt_num(total_doctors_cur)}"
    sentence += f", визиты {visit_verb} до {fmt_num(total_visits_cur)}." if visit_delta is not None else "."
    if doc_delta is not None and visit_delta is not None:
        if doc_delta < -0.01 and visit_delta >= -0.01:
            sentence += " Указывает на рост производительности врачей."
        elif doc_delta > 0.01 and (visit_delta is None or visit_delta < doc_delta):
            sentence += " Рост числа визитов отстаёт от роста числа врачей -> производительность на врача снижается."
    return sentence


# ───────────────────────── Топ-5 врачей ─────────────────────────
def top5_insight(doc_df, month_col, cur_months, visits_col="n_visits", revenue_col="revenue", lang="ru"):
    """doc_df — помесячная сводка по врачам (doctor, n_visits, revenue) — тот же
    источник (ЗП), что и графики топ-5, чтобы доли в тезисе и на графике совпадали."""
    cur = doc_df[doc_df[month_col].isin(cur_months)]
    by_doctor = cur.groupby("doctor").agg(n_visits=(visits_col, "sum"), revenue=(revenue_col, "sum")).sort_values("n_visits", ascending=False)
    if by_doctor.empty:
        return "No doctor data for the period." if lang == "en" else "Нет данных по врачам за период."
    total_visits, total_revenue = by_doctor["n_visits"].sum(), by_doctor["revenue"].sum()
    top5 = by_doctor.head(5)
    visit_share = top5["n_visits"].sum() / total_visits if total_visits else 0
    revenue_share = top5["revenue"].sum() / total_revenue if total_revenue else 0
    leader = top5.index[0]
    leader_share = top5.iloc[0]["n_visits"] / total_visits if total_visits else 0
    if lang == "en":
        return (
            f"The top 5 specialists account for {visit_share:.0%} of visits and {revenue_share:.0%} of revenue, "
            f"including {leader_share:.0%} of visits by {leader}. The clinic still depends on its lead doctors."
        )
    return (
        f"На топ-5 специалистов приходится {visit_share:.0%} консультаций и {revenue_share:.0%} выручки клиники, "
        f"из них {leader_share:.0%} консультаций — у {leader}. Сохраняется зависимость от врачей-лидеров."
    )


# ───────────────────────── Грейды стоматологии ─────────────────────────
def grade_insight(grade_metrics_df, cur_months, prev_months, lang="ru"):
    cur = grade_metrics_df[grade_metrics_df["month"].isin(cur_months)].groupby("grade")["revenue"].sum()
    if not prev_months or cur.empty:
        return "Not enough data by grade for the period." if lang == "en" else "Недостаточно данных по грейдам за период."
    prev = grade_metrics_df[grade_metrics_df["month"].isin(prev_months)].groupby("grade")["revenue"].sum()
    deltas = {g: pct_change(cur.get(g, 0), prev.get(g, 0)) for g in cur.index}
    deltas = {g: d for g, d in deltas.items() if d is not None}
    if not deltas:
        return "Not enough data by grade for the prior period." if lang == "en" else "Недостаточно данных по грейдам за предыдущий период."
    best = max(deltas, key=deltas.get)
    worst = min(deltas, key=deltas.get)
    if lang == "en":
        best_en, worst_en = best.replace("Грейд", "Grade"), worst.replace("Грейд", "Grade")
        return f"{best_en} had the strongest revenue growth ({deltas[best]:+.0%}), {worst_en} the steepest decline ({deltas[worst]:+.0%})."
    return (
        f"{best} показал наибольший рост выручки ({deltas[best]:+.0%}), "
        f"{worst} — наибольшее падение ({deltas[worst]:+.0%})."
    )


# ───────────────────────── Косметология ─────────────────────────
def neuro_insight(neuro_df, top_doctor_df, cur_months, prev_months, lang="ru"):
    cur = neuro_df[neuro_df["month"].isin(cur_months)][["revenue", "n_visits"]].sum()
    top_share = top_doctor_df[top_doctor_df["month"].isin(cur_months)]["top_doctor_share"].mean()
    if lang == "en":
        if not prev_months:
            sentence = f"Cosmetology revenue for the period: {fmt_money(cur['revenue'])}, visits: {fmt_num(cur['n_visits'])}."
        else:
            prev = neuro_df[neuro_df["month"].isin(prev_months)][["revenue", "n_visits"]].sum()
            rev_delta = pct_change(cur["revenue"], prev["revenue"])
            visits_delta = pct_change(cur["n_visits"], prev["n_visits"])
            rev_verb = verb(rev_delta, ("grew", "declined", "stayed flat"))
            visits_verb = verb(visits_delta, ("grew", "declined", "stayed flat"))
            sentence = f"Cosmetology revenue {rev_verb} to {fmt_money(cur['revenue'])}" if rev_delta is not None else f"Cosmetology revenue: {fmt_money(cur['revenue'])}"
            sentence += f", visits {visits_verb} to {fmt_num(cur['n_visits'])}." if visits_delta is not None else "."
        if pd.notna(top_share):
            sentence += f" Revenue share from a single key specialist: {top_share:.0%} — dependency on one doctor persists."
        return sentence

    if not prev_months:
        sentence = f"Выручка косметологии за период: {fmt_money(cur['revenue'])}, визитов: {fmt_num(cur['n_visits'])}."
    else:
        prev = neuro_df[neuro_df["month"].isin(prev_months)][["revenue", "n_visits"]].sum()
        rev_delta = pct_change(cur["revenue"], prev["revenue"])
        visits_delta = pct_change(cur["n_visits"], prev["n_visits"])
        rev_verb = verb(rev_delta, ("выросла", "снизилась", "не изменилась"))
        visits_verb = verb(visits_delta, ("выросли", "снизились", "не изменились"))
        sentence = f"Выручка косметологии {rev_verb} до {fmt_money(cur['revenue'])}" if rev_delta is not None else f"Выручка косметологии: {fmt_money(cur['revenue'])}"
        sentence += f", визиты {visits_verb} до {fmt_num(cur['n_visits'])}." if visits_delta is not None else "."
    if pd.notna(top_share):
        sentence += f" Доля выручки от одного ключевого специалиста: {top_share:.0%} — зависимость от врача сохраняется."
    return sentence


# ───────────────────────── Загрузка кабинетов ─────────────────────────
SPECIALTY_EN = {"Стоматолог": "Dentist", "Косметолог": "Cosmetologist", "Гигиенист": "Hygienist", "Инъекции": "Injectables"}


def rooms_insight(room_util_df, cur_months, prev_months, lang="ru"):
    cur = room_util_df[room_util_df["month"].isin(cur_months)].groupby("specialty").agg(capacity_hours=("capacity_hours", "sum"), actual_hours=("actual_hours", "sum"))
    cur["utilization_pct"] = cur["actual_hours"] / cur["capacity_hours"]
    if lang == "en":
        parts = [f"{SPECIALTY_EN.get(specialty, specialty)} — {row['utilization_pct']:.0%}" for specialty, row in cur.iterrows()]
        return "Room utilization for the period: " + "; ".join(parts) + "."
    parts = [f"{specialty} — {row['utilization_pct']:.0%}" for specialty, row in cur.iterrows()]
    return "Загрузка кабинетов за период: " + "; ".join(parts) + "."


# ───────────────────────── Когортная LTV-кривая ─────────────────────────
def cohort_ltv_insight(cohort_df, selected_cohorts, lang="ru"):
    subset = cohort_df[cohort_df["cohort_month"].isin(selected_cohorts)]
    if subset.empty:
        return "Select at least one cohort to see the trend." if lang == "en" else "Выберите хотя бы одну когорту, чтобы увидеть динамику."
    terminal = subset.loc[subset.groupby("cohort_month")["month_index"].idxmax()]
    best = terminal.loc[terminal["avg_cum_revenue"].idxmax()]
    worst = terminal.loc[terminal["avg_cum_revenue"].idxmin()]
    early = subset[subset["month_index"] == 0]["avg_cum_revenue"].mean()
    late = terminal["avg_cum_revenue"].mean()
    growth = pct_change(late, early)
    if lang == "en":
        sentence = (
            f"Cumulative revenue per client is highest for the {best['cohort_month']} cohort "
            f"({fmt_money(best['avg_cum_revenue'])} by month {int(best['month_index'])}), "
            f"lowest for {worst['cohort_month']} ({fmt_money(worst['avg_cum_revenue'])})."
        )
        if growth is not None:
            sentence += f" Across the selected cohorts, LTV grew {growth:+.0%} from the first month to the latest available."
        return sentence
    sentence = (
        f"Выше всего накопленная выручка на клиента у когорты {best['cohort_month']} "
        f"({fmt_money(best['avg_cum_revenue'])} к {int(best['month_index'])}-му месяцу), "
        f"ниже всего — у {worst['cohort_month']} ({fmt_money(worst['avg_cum_revenue'])})."
    )
    if growth is not None:
        sentence += f" В среднем по выбранным когортам LTV вырос на {growth:+.0%} от первого месяца к последнему доступному."
    return sentence


# ───────────────────────── Воронка записи ─────────────────────────
def funnel_insight(funnel_df, cur_months, prev_months, lang="ru"):
    cur = funnel_df[funnel_df["month"].isin(cur_months)][["n_booked", "n_completed", "n_cancelled", "n_rescheduled"]].sum()
    if cur["n_booked"] == 0:
        return "No funnel data for the period." if lang == "en" else "Нет данных по воронке за период."
    conv_cur = cur["n_completed"] / cur["n_booked"]
    cancel_cur = cur["n_cancelled"] / cur["n_booked"]
    if lang == "en":
        sentence = f"Booking-to-visit conversion — {conv_cur:.0%} ({fmt_num(cur['n_completed'])} of {fmt_num(cur['n_booked'])} bookings)."
        if prev_months:
            prev = funnel_df[funnel_df["month"].isin(prev_months)][["n_booked", "n_completed", "n_cancelled"]].sum()
            if prev["n_booked"]:
                conv_prev = prev["n_completed"] / prev["n_booked"]
                conv_verb = verb(conv_cur - conv_prev, ("grew", "declined", "stayed flat"), threshold=0.005)
                sentence += f" Conversion {conv_verb} from {conv_prev:.0%} to {conv_cur:.0%}."
        sentence += f" Cancellation share — {cancel_cur:.0%}."
        return sentence
    sentence = f"Конверсия из записи в состоявшиеся консультации — {conv_cur:.0%} ({fmt_num(cur['n_completed'])} из {fmt_num(cur['n_booked'])} записей)."
    if prev_months:
        prev = funnel_df[funnel_df["month"].isin(prev_months)][["n_booked", "n_completed", "n_cancelled"]].sum()
        if prev["n_booked"]:
            conv_prev = prev["n_completed"] / prev["n_booked"]
            conv_verb = verb(conv_cur - conv_prev, ("выросла", "снизилась", "не изменилась"), threshold=0.005)
            sentence += f" Конверсия {conv_verb} с {conv_prev:.0%} до {conv_cur:.0%}."
    sentence += f" Доля отмен — {cancel_cur:.0%}."
    return sentence


# ───────────────────────── Динамика конверсии/отмен/переносов ─────────────────────────
def funnel_trend_insight(funnel_df, hist_months, lang="ru"):
    hist = funnel_df[funnel_df["month"].isin(hist_months)].dropna(subset=["conversion_pct"]).sort_values("month")
    if len(hist) < 2:
        return "Not enough months to assess conversion trend." if lang == "en" else "Недостаточно месяцев для оценки динамики конверсии."
    first, last = hist.iloc[0], hist.iloc[-1]
    conv_delta = last["conversion_pct"] - first["conversion_pct"]
    cancel_delta = last["cancellation_pct"] - first["cancellation_pct"]
    resch_delta = last["reschedule_pct"] - first["reschedule_pct"]

    if lang == "en":
        conv_verb = verb(conv_delta, ("grew", "dropped", "stayed flat"), threshold=0.01)
        sentence = (
            f"From {first['month']} to {last['month']}, booking-to-visit conversion "
            f"{conv_verb} from {first['conversion_pct']:.0%} to {last['conversion_pct']:.0%}."
        )
        cancel_verb = verb(cancel_delta, ("grew", "declined", "stayed flat"), threshold=0.01)
        sentence += f" Cancellation share {cancel_verb} from {first['cancellation_pct']:.0%} to {last['cancellation_pct']:.0%}"
        resch_verb = verb(resch_delta, ("grew", "declined", "stayed flat"), threshold=0.01)
        sentence += f", reschedule share {resch_verb} from {first['reschedule_pct']:.0%} to {last['reschedule_pct']:.0%}."
        if conv_delta is not None and conv_delta < -0.03:
            sentence += " Conversion decline over the period is worth investigating in monthly cancellation/reschedule causes."
        return sentence

    conv_verb = verb(conv_delta, ("выросла", "упала", "не изменилась"), threshold=0.01)
    sentence = (
        f"С {first['month']} по {last['month']} конверсия в состоявшиеся консультации "
        f"{conv_verb} с {first['conversion_pct']:.0%} до {last['conversion_pct']:.0%}."
    )
    cancel_verb = verb(cancel_delta, ("выросла", "снизилась", "не изменилась"), threshold=0.01)
    sentence += f" Доля отмен {cancel_verb} с {first['cancellation_pct']:.0%} до {last['cancellation_pct']:.0%}"
    resch_verb = verb(resch_delta, ("выросла", "снизилась", "не изменилась"), threshold=0.01)
    sentence += f", доля переносов {resch_verb} с {first['reschedule_pct']:.0%} до {last['reschedule_pct']:.0%}."
    if conv_delta is not None and conv_delta < -0.03:
        sentence += " Снижение конверсии за период — повод разобраться в причинах отмен и переносов по месяцам."
    return sentence


# ───────────────────────── Отток (churn) ─────────────────────────
def churn_insight(churn_df, lang="ru"):
    # "Оба направления" — агрегат (сумма Стоматологии и Косметологии), а не отдельная
    # специальность: исключаем из нарратива, иначе оба падежа для неё некорректны.
    confirmed = churn_df[(~churn_df["preliminary"]) & (churn_df["specialty"] != "Оба направления")].dropna(subset=["churn_rate"])
    if confirmed.empty:
        return "Not enough confirmed months (90+ days) to assess churn." if lang == "en" else "Недостаточно подтверждённых месяцев (90+ дней) для оценки оттока."

    if lang == "en":
        last_parts, trend_parts = [], []
        for spec in confirmed["specialty"].unique():
            sub = confirmed[confirmed["specialty"] == spec].sort_values("month")
            if sub.empty:
                continue
            label = DIRECTION_EN.get(spec, spec).lower()
            last = sub.iloc[-1]
            last_parts.append(f"{label} — {last['churn_rate']:.0%} (as of {last['month']})")
            if len(sub) >= 2:
                first = sub.iloc[0]
                delta = last["churn_rate"] - first["churn_rate"]
                trend_verb = verb(delta, ("grew", "declined", "stayed flat"), threshold=0.03)
                trend_parts.append(f"{label} churn {trend_verb} from {first['churn_rate']:.0%} ({first['month']}) to {last['churn_rate']:.0%}")
        sentence = "Latest confirmed churn (90 days without return): " + "; ".join(last_parts) + "."
        if trend_parts:
            sentence += " Over the tracked period, " + "; ".join(trend_parts) + "."
        specs = list(confirmed["specialty"].unique())
        if len(specs) == 2:
            last_by_spec = {s: confirmed[confirmed["specialty"] == s].sort_values("month").iloc[-1]["churn_rate"] for s in specs}
            gap = max(last_by_spec.values()) - min(last_by_spec.values())
            if gap > 0.15:
                worse = max(last_by_spec, key=last_by_spec.get)
                sentence += f" Churn in {DIRECTION_EN.get(worse, worse).lower()} is notably higher than the other specialty — a priority for retention programs."
        return sentence

    last_parts, trend_parts = [], []
    for spec in confirmed["specialty"].unique():
        sub = confirmed[confirmed["specialty"] == spec].sort_values("month")
        if sub.empty:
            continue
        last = sub.iloc[-1]
        last_parts.append(f"{spec.lower()} — {last['churn_rate']:.0%} (на {last['month']})")
        if len(sub) >= 2:
            first = sub.iloc[0]
            delta = last["churn_rate"] - first["churn_rate"]
            trend_verb = verb(delta, ("вырос", "снизился", "не изменился"), threshold=0.03)
            trend_parts.append(f"в {oblique(spec)} {trend_verb} с {first['churn_rate']:.0%} ({first['month']}) до {last['churn_rate']:.0%}")

    sentence = "Последний подтверждённый отток (90 дней без возврата): " + "; ".join(last_parts) + "."
    if trend_parts:
        sentence += " За отслеживаемый период churn " + "; ".join(trend_parts) + "."

    specs = list(confirmed["specialty"].unique())
    if len(specs) == 2:
        last_by_spec = {s: confirmed[confirmed["specialty"] == s].sort_values("month").iloc[-1]["churn_rate"] for s in specs}
        gap = max(last_by_spec.values()) - min(last_by_spec.values())
        if gap > 0.15:
            worse = max(last_by_spec, key=last_by_spec.get)
            sentence += f" Отток в {oblique(worse)} заметно выше, чем по второй специальности — приоритет для программ удержания."
    return sentence


# ───────────────────────── Scorecard удержания ─────────────────────────
LEVEL_EN = {"Ниже среднего": "below average", "Средний": "average", "Хороший": "good", "Отличный": "excellent"}
RETENTION_METRIC_RU = {"return_2nd": "Возврат на 2-й приём", "retention_3mo": "Удержание 3 мес", "retention_6mo": "Удержание 6 мес"}
RETENTION_METRIC_EN = {"return_2nd": "2nd-visit return", "retention_3mo": "3-mo. retention", "retention_6mo": "6-mo. retention"}


def retention_scorecard_insight(scorecard_df, lang="ru"):
    sc = scorecard_df.dropna(subset=["value"])
    if sc.empty:
        return "No data to assess retention." if lang == "en" else "Нет данных для оценки удержания."
    key_metric = "return_2nd"

    if lang == "en":
        key_rows = sc[sc["metric"] == key_metric]
        parts = [f"{DIRECTION_EN.get(row['specialty'], row['specialty']).lower()} — {row['value']:.0%} ({LEVEL_EN.get(row['level'], row['level']).lower()})" for _, row in key_rows.iterrows()]
        sentence = f"“{RETENTION_METRIC_EN[key_metric]}”: " + "; ".join(parts) + "." if parts else ""
        below_avg = sc[sc["level"] == "Ниже среднего"]
        if len(sc) and len(below_avg) == len(sc):
            sentence += " Every tracked retention metric for both specialties is below the target average — a systemic growth area, not a one-off dip."
        elif len(below_avg):
            worst = below_avg.iloc[0]
            sentence += f" The weakest metric is “{RETENTION_METRIC_EN.get(worst['metric'], worst['metric']).lower()}” in {DIRECTION_EN.get(worst['specialty'], worst['specialty']).lower()} ({worst['value']:.0%}, below average)."
        if len(key_rows) == 2:
            vals = key_rows.set_index("specialty")["value"]
            specs = list(vals.index)
            v0, v1 = vals[specs[0]], vals[specs[1]]
            if min(v0, v1) > 0 and max(v0, v1) / min(v0, v1) > 1.5:
                better = specs[0] if v0 > v1 else specs[1]
                worse = specs[1] if v0 > v1 else specs[0]
                ratio = max(v0, v1) / min(v0, v1)
                sentence += f" In {DIRECTION_EN.get(better, better).lower()}, 2nd-visit return is {ratio:.1f}x higher than in {DIRECTION_EN.get(worse, worse).lower()}."
        return sentence

    key_rows = sc[sc["metric"] == key_metric]
    parts = [f"{row['specialty'].lower()} — {row['value']:.0%} ({row['level'].lower()})" for _, row in key_rows.iterrows()]
    sentence = f"«{RETENTION_METRIC_RU[key_metric]}»: " + "; ".join(parts) + "." if parts else ""

    below_avg = sc[sc["level"] == "Ниже среднего"]
    if len(sc) and len(below_avg) == len(sc):
        sentence += " Все отслеживаемые метрики удержания по обеим специальностям — ниже среднего целевого уровня: это системная точка роста, а не разовый провал."
    elif len(below_avg):
        worst = below_avg.iloc[0]
        sentence += f" Слабее всего «{RETENTION_METRIC_RU.get(worst['metric'], worst['metric']).lower()}» в {oblique(worst['specialty'])} ({worst['value']:.0%}, ниже среднего)."

    if len(key_rows) == 2:
        vals = key_rows.set_index("specialty")["value"]
        specs = list(vals.index)
        v0, v1 = vals[specs[0]], vals[specs[1]]
        if min(v0, v1) > 0 and max(v0, v1) / min(v0, v1) > 1.5:
            better = specs[0] if v0 > v1 else specs[1]
            worse = specs[1] if v0 > v1 else specs[0]
            ratio = max(v0, v1) / min(v0, v1)
            sentence += f" В {oblique(better)} возврат на 2-й приём в {ratio:.1f} раза выше, чем в {oblique(worse)}."
    return sentence


# ───────────────────────── Удержание по когортам (тренд) ─────────────────────────
def retention_cohort_insight(cohort_df, lang="ru"):
    cr = cohort_df.dropna(subset=["cohort_month"])
    if cr.empty:
        return "No cohort data to assess retention trend." if lang == "en" else "Нет данных по когортам для оценки динамики удержания."

    if lang == "en":
        parts = []
        declined = False
        for spec in cr["specialty"].unique():
            sub = cr[cr["specialty"] == spec].dropna(subset=["return_2nd"]).sort_values("cohort_month")
            if len(sub) < 2:
                continue
            first, last = sub.iloc[0], sub.iloc[-1]
            delta = last["return_2nd"] - first["return_2nd"]
            verb_txt = verb(delta, ("grew", "dropped", "stayed flat"), threshold=0.03)
            if verb_txt == "dropped":
                declined = True
            parts.append(f"in {DIRECTION_EN.get(spec, spec).lower()}, 2nd-visit return {verb_txt} from {first['return_2nd']:.0%} (cohort {first['cohort_month']}) to {last['return_2nd']:.0%} (cohort {last['cohort_month']})")
        if not parts:
            return "Not enough cohorts to assess retention trend."
        sentence = "By cohort: " + "; ".join(parts) + "."
        if declined:
            sentence += " Newer cohorts retain worse than older ones — worth checking for recent changes in booking or patient handling."
        return sentence

    parts = []
    for spec in cr["specialty"].unique():
        sub = cr[cr["specialty"] == spec].dropna(subset=["return_2nd"]).sort_values("cohort_month")
        if len(sub) < 2:
            continue
        first, last = sub.iloc[0], sub.iloc[-1]
        delta = last["return_2nd"] - first["return_2nd"]
        verb_txt = verb(delta, ("вырос", "упал", "не изменился"), threshold=0.03)
        parts.append(f"в {oblique(spec)} возврат на 2-й приём {verb_txt} с {first['return_2nd']:.0%} (когорта {first['cohort_month']}) до {last['return_2nd']:.0%} (когорта {last['cohort_month']})")
    if not parts:
        return "Недостаточно когорт для оценки динамики удержания."
    sentence = "По когортам: " + "; ".join(parts) + "."
    if any("упал" in p for p in parts):
        sentence += " Новые когорты удерживаются хуже старых — стоит проверить, не связано ли это с недавними изменениями в записи или ведении пациентов."
    return sentence


# ───────────────────────── LTV и интервал по когортам ─────────────────────────
def ltv_interval_insight(cohort_df, lang="ru"):
    cr = cohort_df.dropna(subset=["cohort_month"])
    if cr.empty:
        return "No cohort data to assess LTV and visit interval." if lang == "en" else "Нет данных по когортам для оценки LTV и интервала визитов."

    if lang == "en":
        ltv_parts = []
        for spec in cr["specialty"].unique():
            sub = cr[cr["specialty"] == spec].dropna(subset=["ltv"]).sort_values("cohort_month")
            if sub.empty:
                continue
            ltv_parts.append(f"{DIRECTION_EN.get(spec, spec).lower()} — {fmt_money(sub.iloc[0]['ltv'])} for the {sub.iloc[0]['cohort_month']} cohort")
        sentence = "LTV of the earliest (most mature) cohort: " + "; ".join(ltv_parts) + "." if ltv_parts else ""
        interval_parts = []
        grew_any = False
        for spec in cr["specialty"].unique():
            sub = cr[cr["specialty"] == spec].dropna(subset=["avg_interval_days"]).sort_values("cohort_month")
            if len(sub) < 2:
                continue
            first, last = sub.iloc[0], sub.iloc[-1]
            delta = last["avg_interval_days"] - first["avg_interval_days"]
            verb_txt = verb(delta, ("grew", "shrank", "stayed flat"), threshold=2)
            if verb_txt == "grew":
                grew_any = True
            interval_parts.append(f"in {DIRECTION_EN.get(spec, spec).lower()} it {verb_txt} from {first['avg_interval_days']:.0f} to {last['avg_interval_days']:.0f} days")
        if interval_parts:
            sentence += " Average interval between visits by cohort: " + "; ".join(interval_parts) + "."
            if grew_any:
                sentence += " A growing interval may mean patients are returning less often — worth checking against the churn trend."
        return sentence

    ltv_parts = []
    for spec in cr["specialty"].unique():
        sub = cr[cr["specialty"] == spec].dropna(subset=["ltv"]).sort_values("cohort_month")
        if sub.empty:
            continue
        ltv_parts.append(f"{spec.lower()} — {fmt_money(sub.iloc[0]['ltv'])} у когорты {sub.iloc[0]['cohort_month']}")
    sentence = "LTV самой ранней (наиболее зрелой) когорты: " + "; ".join(ltv_parts) + "." if ltv_parts else ""

    interval_parts = []
    for spec in cr["specialty"].unique():
        sub = cr[cr["specialty"] == spec].dropna(subset=["avg_interval_days"]).sort_values("cohort_month")
        if len(sub) < 2:
            continue
        first, last = sub.iloc[0], sub.iloc[-1]
        delta = last["avg_interval_days"] - first["avg_interval_days"]
        verb_txt = verb(delta, ("вырос", "сократился", "не изменился"), threshold=2)
        interval_parts.append(f"в {oblique(spec)} {verb_txt} с {first['avg_interval_days']:.0f} до {last['avg_interval_days']:.0f} дней")
    if interval_parts:
        sentence += " Средний интервал между визитами по когортам: " + "; ".join(interval_parts) + "."
        if any("вырос" in p for p in interval_parts):
            sentence += " Рост интервала может означать, что пациенты стали реже возвращаться — стоит сверить с динамикой оттока."
    return sentence


# ───────────────────────── CAC ─────────────────────────
def cac_insight(marketing_df, monthly_client_df, pnl_df, cur_months, ltv_cur, lang="ru"):
    spend = marketing_df[marketing_df["month"].isin(cur_months)]["spend"].sum()
    mc = monthly_client_df[monthly_client_df["visit_month"].isin(cur_months)]
    n_new = mc["n_clients_new"].sum()
    if not n_new:
        return "No new clients for the period — CAC is undefined." if lang == "en" else "Нет новых клиентов за период — CAC не определён."
    cac = spend / n_new
    total_clients, total_revenue = mc["total_clients"].sum(), mc["total_revenue"].sum()
    margin_pct = pnl_df[pnl_df["month"].isin(cur_months)]["gross_profit"].sum() / pnl_df[pnl_df["month"].isin(cur_months)]["revenue"].sum()
    margin_per_client_month = (total_revenue / total_clients) * margin_pct if total_clients else None

    if lang == "en":
        sentence = f"CAC for the period — {fmt_money(cac)} ({fmt_money(spend)} spent on {fmt_num(n_new)} new clients)"
        if margin_per_client_month:
            payback = cac / margin_per_client_month
            sentence += f", paid back in {payback:.1f} mo. of visits"
        if ltv_cur:
            ratio = ltv_cur / cac
            verdict = "healthy unit economics" if ratio >= 3 else "below the 3:1 target"
            sentence += f". LTV:CAC = {ratio:.1f}:1 — {verdict}."
        else:
            sentence += "."
        return sentence

    sentence = f"CAC за период — {fmt_money(cac)} ({fmt_money(spend)} расходов на {fmt_num(n_new)} новых клиентов)"
    if margin_per_client_month:
        payback = cac / margin_per_client_month
        sentence += f", окупается за {payback:.1f} мес. визитов"
    if ltv_cur:
        ratio = ltv_cur / cac
        verdict = "здоровая экономика" if ratio >= 3 else "ниже целевого ориентира 3:1"
        sentence += f". LTV:CAC = {ratio:.1f}:1 — {verdict}."
    else:
        sentence += "."
    return sentence


# ───────────────────────── KPI ─────────────────────────
def kpi_insight(breakeven_df, cur_months, lang="ru"):
    be = breakeven_df[breakeven_df["month"].isin(cur_months)]
    if be["plan_sessions"].isna().all() or be["plan_sessions"].sum() == 0:
        return "No plan values for the selected period." if lang == "en" else "Нет плановых значений на выбранный период."
    actual_sessions, plan_sessions = be["n_visits_actual"].sum(), be["plan_sessions"].sum()
    actual_revenue, plan_revenue = be["revenue_actual"].sum(), be["plan_revenue"].sum()
    sessions_pct = actual_sessions / plan_sessions if plan_sessions else None
    revenue_pct = actual_revenue / plan_revenue if plan_revenue else None
    check_pct = (actual_revenue / actual_sessions) / (plan_revenue / plan_sessions) if plan_sessions and actual_sessions and plan_revenue else None

    if lang == "en":
        sentence = f"Visit plan achieved {sessions_pct:.0%}" if sessions_pct else ""
        if revenue_pct:
            sentence += f", revenue plan — {revenue_pct:.0%}"
        if check_pct:
            verdict = "below plan" if check_pct < 0.95 else ("above plan" if check_pct > 1.05 else "on plan")
            sentence += f". Average check is {verdict} ({check_pct:.0%} of planned)"
        sentence += "."
        if sessions_pct and revenue_pct and sessions_pct > 1.1 and revenue_pct < sessions_pct - 0.1:
            sentence += " Visits are ahead of plan but revenue is growing slower -> the average-check plan needs revisiting."
        return sentence

    sentence = f"План по консультациям выполнен на {sessions_pct:.0%}" if sessions_pct else ""
    if revenue_pct:
        sentence += f", по выручке — на {revenue_pct:.0%}"
    if check_pct:
        verdict = "ниже плана" if check_pct < 0.95 else ("выше плана" if check_pct > 1.05 else "на уровне плана")
        sentence += f". Средний чек {verdict} ({check_pct:.0%} от планового)"
    sentence += "."
    if sessions_pct and revenue_pct and sessions_pct > 1.1 and revenue_pct < sessions_pct - 0.1:
        sentence += " Консультаций больше плана, но выручка растёт медленнее -> план по среднему чеку требует пересмотра."
    return sentence
