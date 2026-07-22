"""
Генератор синтетического warehouse/ для портфолио-версии дашборда клиники
"Meridian Health" — вымышленное название, вымышленные врачи и цифры, но
согласованные между собой по той же бизнес/финансовой логике, что в оригинале
(см. etl/*.py оригинального проекта Clinic_Analytics_Platform).

Ничего не читает из реального проекта — все числа сгенерированы с нуля.

Usage:
    python generate_demo_data.py
"""

import calendar
import random
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

BASE_DIR = Path(__file__).resolve().parent
WAREHOUSE_DIR = BASE_DIR / "warehouse"
CLINIC_NAME = "Meridian Health"

TAX_MULTIPLIER = (0.13 + 0.30) / (1 - 0.13)  # НДФЛ+взносы обратным счётом от ЗП на руки
ROOMS = {"Стоматолог": 1, "Косметолог": 1}
HOURS_PER_DAY = 12
DRUGS = ["Ботокс", "Диспорт", "Гиалуроновые филлеры", "Мезонити", "Биоревитализация"]
DIR_COLS = ["Стоматология", "Косметология", "Инъекции", "Гигиенист", "Прочее (доп. доход)"]
DIRECTIONS_3 = ["Стоматология", "Косметология", "Инъекции"]


def month_range(start: str, end: str) -> list[str]:
    return [str(p) for p in pd.period_range(start, end, freq="M")]


# Период — динамический, относительно даты запуска скрипта (не зашитая дата):
# 10 факт-месяцев до последнего ПОЛНОСТЬЮ завершённого месяца. При перегенерации
# позже вся история сдвигается вперёд вместе с текущей датой — не устаревает.
_last_complete_month = pd.Timestamp.now().to_period("M") - 1
MONTHS_ACTUAL = month_range(str(_last_complete_month - 9), str(_last_complete_month))      # 10 факт-месяцев
MONTHS_PNL = month_range(str(_last_complete_month - 9), str(_last_complete_month + 6))      # 16 (факт + план)
MONTHS_CASH = month_range(str(_last_complete_month - 21), str(_last_complete_month + 18))   # 40
MONTHS_KPI = month_range(MONTHS_ACTUAL[4], MONTHS_PNL[-1])                                  # 12

N_ACTUAL = len(MONTHS_ACTUAL)
N_PNL = len(MONTHS_PNL)


def lerp(a, b, i, n):
    return a + (b - a) * i / max(n - 1, 1)


# ───────────────────────── 1. Врачи ─────────────────────────

DOCTOR_ROWS = [
    ("Соколова Анна Дмитриевна", "Стоматолог", "Грейд 1"),
    ("Морозов Игорь Сергеевич", "Стоматолог", "Грейд 1"),
    ("Волкова Елена Павловна", "Стоматолог", "Грейд 1"),
    ("Козлов Артём Николаевич", "Стоматолог", "Грейд 1"),
    ("Лебедева Мария Игоревна", "Стоматолог", "Грейд 1"),
    ("Новикова Ольга Витальевна", "Стоматолог", "Грейд 1"),
    ("Фёдоров Дмитрий Алексеевич", "Стоматолог", "Грейд 1"),
    ("Григорьева Наталья Сергеевна", "Стоматолог", "Грейд 1"),
    ("Павлова Виктория Олеговна", "Стоматолог", "Грейд 2"),
    ("Романов Кирилл Андреевич", "Стоматолог", "Грейд 2"),
    ("Захарова Юлия Владимировна", "Стоматолог", "Грейд 2"),
    ("Никитин Максим Борисович", "Стоматолог", "Грейд 2"),
    ("Орлова Светлана Ивановна", "Стоматолог", "Грейд 2"),
    ("Кузьмина Анастасия Романовна", "Стоматолог", "Грейд 2"),
    ("Тарасов Владислав Юрьевич", "Стоматолог", "Грейд 2"),
    ("Беляева Ирина Александровна", "Стоматолог", "Грейд 2"),
    ("Медведева Ксения Витальевна", "Стоматолог", "Грейд 3"),
    ("Поляков Егор Дмитриевич", "Стоматолог", "Грейд 3"),
    ("Сорокина Дарья Максимовна", "Стоматолог", "Грейд 3"),
    ("Крылова Полина Андреевна", "Стоматолог", "Грейд 3"),
    ("Ефимова Татьяна Игоревна", "Стоматолог", "Грейд 3"),
    ("Гусева Вероника Олеговна", "Стоматолог", "Грейд 3"),
    ("Жукова Алина Сергеевна", "Стоматолог", "Грейд 3"),
    ("Смирнов Роман Валерьевич", "Косметолог", "Косметолог"),
    ("Воронова Екатерина Дмитриевна", "Косметолог", "Косметолог"),
    ("Панов Станислав Игоревич", "Косметолог", "Косметолог"),
    ("Малышева Виктория Сергеевна", "Косметолог", "Косметолог"),
    ("Дорофеев Артур Николаевич", "Косметолог", "Косметолог"),
    ("Соловьёва Вера Александровна", "Гигиенист", "Гигиенист"),
]

# стаггер найма — часть врачей выходит не с первого месяца (рост команды)
JOIN_MONTH_IDX = {
    "Крылова Полина Андреевна": 1,
    "Ефимова Татьяна Игоревна": 2,
    "Гусева Вероника Олеговна": 3,
    "Дорофеев Артур Николаевич": 2,
    "Жукова Алина Сергеевна": 4,
}

DOCTORS = pd.DataFrame(DOCTOR_ROWS, columns=["doctor", "specialty", "grade"])
DOCTORS["join_idx"] = DOCTORS["doctor"].map(JOIN_MONTH_IDX).fillna(0).astype(int)
# случайная ставка ЗП-на-руки как % от выручки — фиксирована по врачу
DOCTORS["payout_ratio"] = np.random.uniform(0.26, 0.38, size=len(DOCTORS))
# ценовой множитель грейда/врача (сениорность)
GRADE_MULT = {"Грейд 1": 1.15, "Грейд 2": 1.0, "Грейд 3": 0.85}
DOCTORS["price_mult"] = DOCTORS["grade"].map(GRADE_MULT).fillna(1.0) * np.random.uniform(0.93, 1.07, size=len(DOCTORS))

PSYCHIATRISTS = DOCTORS[DOCTORS["specialty"] == "Стоматолог"]["doctor"].tolist()
NEUROLOGISTS = DOCTORS[DOCTORS["specialty"] == "Косметолог"]["doctor"].tolist()
PSYCHOLOGISTS = DOCTORS[DOCTORS["specialty"] == "Гигиенист"]["doctor"].tolist()


def active_doctors(month_idx: int, pool: list[str]) -> list[str]:
    join = DOCTORS.set_index("doctor")["join_idx"]
    return [d for d in pool if join[d] <= month_idx]


# ───────────────────────── 2. monthly_pnl (16 мес, источник истины по выручке) ─────────────────────────

REVENUE_TARGET = [
    705_000, 760_000, 830_000, 910_000, 860_000, 940_000, 1_040_000, 1_120_000,
    1_230_000, 1_340_000, 1_420_000, 1_480_000, 1_560_000, 1_650_000, 1_730_000, 1_830_000,
]
assert len(REVENUE_TARGET) == N_PNL

# Прибыльная клиника с самого начала истории: постоянные расходы — доля от
# выручки, снижающаяся по мере роста (эффект масштаба) — 18% -> 29% операционной
# маржи, без единого убыточного месяца.
pnl_rows = []
for i, month in enumerate(MONTHS_PNL):
    revenue = REVENUE_TARGET[i]
    margin_pct = lerp(0.60, 0.67, i, N_PNL)
    gross_profit = revenue * margin_pct
    variable_costs = revenue - gross_profit
    fixed_pct = lerp(0.42, 0.38, i, N_PNL) * np.random.uniform(0.97, 1.03)
    fixed_costs = revenue * fixed_pct
    operating_profit = gross_profit - fixed_costs
    other_expense = np.random.uniform(15_000, 35_000)
    net_profit = operating_profit - other_expense
    pnl_rows.append({
        "month": month, "revenue": round(revenue), "variable_costs": round(variable_costs),
        "gross_profit": round(gross_profit), "margin_pct": round(margin_pct, 4),
        "fixed_costs": round(fixed_costs), "operating_profit": round(operating_profit),
        "net_profit": round(net_profit),
    })
pnl = pd.DataFrame(pnl_rows)
pnl.to_csv(WAREHOUSE_DIR / "monthly_pnl.csv", index=False)

# ───────────────────────── 3. revenue_by_direction_monthly (16 мес x 5 направлений) ─────────────────────────

DIR_SHARE = {"Стоматология": 0.54, "Косметология": 0.24, "Инъекции": 0.09, "Гигиенист": 0.05, "Прочее (доп. доход)": 0.08}

by_direction_rows = []
by_direction_value = {}  # (month, direction) -> revenue, для повторного использования ниже
for i, month in enumerate(MONTHS_PNL):
    revenue = pnl.loc[i, "revenue"]
    shares = np.array([DIR_SHARE[d] * np.random.uniform(0.92, 1.08) for d in DIR_COLS])
    shares = shares / shares.sum()
    values = np.round(revenue * shares, -1)
    values[-1] += revenue - values.sum()  # точная сумма = revenue
    for d, v in zip(DIR_COLS, values):
        by_direction_value[(month, d)] = v
        by_direction_rows.append({"month": month, "direction": d, "revenue": v})
by_direction = pd.DataFrame(by_direction_rows)

print(f"monthly_pnl: {len(pnl)} строк, revenue_by_direction (до n_services): {len(by_direction)} строк")


# ───────────────────────── 4. Визиты (только 10 факт-месяцев) ─────────────────────────
# Направление визита -> (пул врачей, псевдо-имя услуги для categorize_direction,
# базовая цена, длительность в минутах). "Инъекции" всегда ведут косметологи.

def service_name_for(bucket: str, doctor_grade: str, fmt_min: int | None) -> str:
    suffix = f", {fmt_min} мин" if fmt_min else ""
    if bucket == "Стоматология":
        return f"Приём врача-стоматолога{suffix}"
    if bucket == "Косметология":
        return f"Приём врача-косметолога{suffix}"
    if bucket == "Инъекции":
        return random.choice(["Инъекции ботокса", "Инъекции филлеров"])
    if bucket == "Гигиенист":
        return f"Консультация гигиениста{suffix}"
    return "Дополнительная услуга"


patients = {}          # patient_id -> {"first_month": str, "first_bucket": str}
next_patient_id = 1
visit_rows = []
next_visit_id = 1

BUCKET_POOL = {"Стоматология": PSYCHIATRISTS, "Косметология": NEUROLOGISTS, "Инъекции": NEUROLOGISTS, "Гигиенист": PSYCHOLOGISTS}
FORMAT_WEIGHTS = [0.20, 0.55, 0.25]
FORMATS = [25, 50, 80]
BASE_PRICE = {"Стоматология": {25: 3200, 50: 5800, 80: 8600}, "Гигиенист": {25: 2600, 50: 4200, 80: 6200}}


def pick_patient(bucket: str, month_idx: int, month: str) -> str:
    global next_patient_id
    new_prob = lerp(0.55, 0.30, month_idx, N_ACTUAL) if month_idx > 0 else 1.0
    eligible = [pid for pid, info in patients.items() if info["first_month"] < month]
    if month_idx == 0 or not eligible or random.random() < new_prob:
        pid = f"P{next_patient_id:05d}"
        next_patient_id += 1
        patients[pid] = {"first_month": month, "first_bucket": bucket}
        return pid
    same_bucket = [pid for pid in eligible if patients[pid]["first_bucket"] == bucket]
    if same_bucket and random.random() < 0.8:
        return random.choice(same_bucket)
    return random.choice(eligible)


def gen_bucket_visits(bucket: str, month_idx: int, month: str, target_revenue: float):
    global next_visit_id
    pool = active_doctors(month_idx, BUCKET_POOL[bucket])
    if not pool or target_revenue <= 0:
        return
    year, mon = map(int, month.split("-"))
    days_in_month = calendar.monthrange(year, mon)[1]
    day_start = 12 if month_idx == 0 else 1  # вымышленная дата открытия — история начинается с 12-го числа первого месяца

    raw = []
    if bucket in ("Стоматология", "Гигиенист"):
        avg_price = BASE_PRICE[bucket][50]
        n_visits = max(1, round(target_revenue / avg_price))
        for _ in range(n_visits):
            fmt = int(np.random.choice(FORMATS, p=FORMAT_WEIGHTS))
            doctor = random.choice(pool)
            grade = DOCTORS.set_index("doctor").loc[doctor, "grade"]
            mult = DOCTORS.set_index("doctor").loc[doctor, "price_mult"]
            price = BASE_PRICE[bucket][fmt] * mult * np.random.uniform(0.9, 1.1)
            raw.append((doctor, fmt, fmt, price))
    elif bucket == "Косметология":
        avg_price = 5500
        n_visits = max(1, round(target_revenue / avg_price))
        for _ in range(n_visits):
            doctor = random.choice(pool)
            duration = int(np.random.choice([25, 30, 45], p=[0.3, 0.5, 0.2]))
            price = avg_price * np.random.uniform(0.85, 1.15)
            raw.append((doctor, None, duration, price))
    else:  # Инъекции
        avg_price = 27_000
        n_visits = max(1, round(target_revenue / avg_price))
        for _ in range(n_visits):
            doctor = random.choice(pool)
            duration = 45
            price = avg_price * np.random.uniform(0.6, 1.5)
            raw.append((doctor, None, duration, price))

    scale = target_revenue / sum(r[3] for r in raw) if raw else 1.0
    for doctor, fmt, duration, price in raw:
        revenue = round(price * scale, -1) or 10.0
        grade = DOCTORS.set_index("doctor").loc[doctor, "grade"]
        pid = pick_patient(bucket, month_idx, month)
        is_primary = patients[pid]["first_month"] == month and patients[pid]["first_bucket"] == bucket
        day = random.randint(day_start, days_in_month)
        hour = random.randint(9, 20)
        minute = random.choice([0, 15, 30, 45])
        visit_dt = pd.Timestamp(year=year, month=mon, day=day, hour=hour, minute=minute)
        n_services = 2 if random.random() < 0.07 else 1
        visit_rows.append({
            "visit_id": next_visit_id, "visit_datetime": visit_dt, "clinic": CLINIC_NAME,
            "doctor": doctor, "specialty": DOCTORS.set_index("doctor").loc[doctor, "specialty"],
            "grade": grade, "patient_id": pid, "bucket": bucket, "format_min": fmt, "duration_min": duration,
            "n_services": n_services, "revenue": revenue, "is_primary": is_primary, "month": month,
        })
        next_visit_id += 1


for i, month in enumerate(MONTHS_ACTUAL):
    for bucket in ["Стоматология", "Косметология", "Инъекции", "Гигиенист"]:
        target = by_direction_value[(month, bucket)]
        gen_bucket_visits(bucket, i, month, target)

visits = pd.DataFrame(visit_rows)
visits["service_name"] = visits.apply(lambda r: service_name_for(r["bucket"], r["grade"], r["format_min"]), axis=1)
visits["visit_date"] = visits["visit_datetime"].dt.date.astype(str)
print(f"Сгенерировано визитов: {len(visits)}, пациентов: {len(patients)}")

# ───────────────────────── 5. visits_enriched / fact_visits / fact_service_lines / dim_doctors ─────────────────────────

visits_enriched = visits[[
    "visit_id", "visit_datetime", "clinic", "doctor", "patient_id", "n_services", "duration_min",
    "visit_date", "is_primary", "revenue", "month", "specialty", "grade", "service_name", "format_min",
]].copy()
visits_enriched.to_csv(WAREHOUSE_DIR / "visits_enriched.csv", index=False)

fact_visits = visits_enriched[[
    "visit_id", "visit_datetime", "clinic", "doctor", "patient_id", "n_services", "duration_min",
    "visit_date", "is_primary", "revenue",
]].copy()
fact_visits.to_csv(WAREHOUSE_DIR / "fact_visits.csv", index=False)

DOCTORS[["doctor", "specialty", "grade"]].to_csv(WAREHOUSE_DIR / "dim_doctors.csv", index=False)

lines_rows = []
line_id = 1
for _, r in visits.iterrows():
    n = r["n_services"]
    amounts = [r["revenue"]] if n == 1 else [round(r["revenue"] * 0.6), r["revenue"] - round(r["revenue"] * 0.6)]
    for k, amount in enumerate(amounts):
        lines_rows.append({
            "visit_id": r["visit_id"], "visit_datetime": r["visit_datetime"], "duration_min": r["duration_min"],
            "clinic": r["clinic"], "doctor": r["doctor"], "patient_id": r["patient_id"],
            "service_code": f"S{line_id:06d}", "service_name": r["service_name"] if k == 0 else "Доп. услуга",
            "amount": amount, "source_file": "meridian_health_export.xlsx",
            "amount_crm_list_price": round(amount * np.random.uniform(0.97, 1.03)),
            "amount_source": random.choice(["payroll_actual", "crm_list_price"]),
            "month": r["month"], "direction": r["bucket"] if k == 0 else "Прочее",
        })
        line_id += 1
lines = pd.DataFrame(lines_rows)
lines.drop(columns=["month", "direction"]).to_csv(WAREHOUSE_DIR / "fact_service_lines.csv", index=False)

# n_services по направлению — довешиваем к revenue_by_direction (как в build_report_metrics.py)
n_services_by_dir = lines.groupby(["month", "direction"])["service_code"].count().rename("n_services").reset_index()
by_direction = by_direction.merge(n_services_by_dir, on=["month", "direction"], how="left")
by_direction["n_services"] = by_direction["n_services"].fillna(0).astype(int)
by_direction.to_csv(WAREHOUSE_DIR / "revenue_by_direction_monthly.csv", index=False)

# ───────────────────────── 6. Метрики по грейдам/форматам/косметологии/кабинетам/команде ─────────────────────────

psy = visits_enriched[visits_enriched["grade"].isin(["Грейд 1", "Грейд 2", "Грейд 3"])]
grade_metrics = psy.groupby(["month", "grade"]).agg(
    revenue=("revenue", "sum"), n_visits=("visit_id", "count"), n_doctors=("doctor", "nunique"),
    total_duration_min=("duration_min", "sum"),
).reset_index()
grade_metrics["avg_check"] = grade_metrics["revenue"] / grade_metrics["n_visits"]
grade_metrics["revenue_per_doctor"] = grade_metrics["revenue"] / grade_metrics["n_doctors"]
grade_metrics["revenue_per_min"] = grade_metrics["revenue"] / grade_metrics["total_duration_min"]
grade_metrics["visits_per_doctor"] = grade_metrics["n_visits"] / grade_metrics["n_doctors"]
grade_metrics.to_csv(WAREHOUSE_DIR / "grade_monthly_metrics.csv", index=False)

format_by_grade = psy.dropna(subset=["format_min"]).groupby(["month", "grade", "format_min"]).agg(
    n_visits=("visit_id", "count"), revenue=("revenue", "sum")
).reset_index()
format_by_grade.to_csv(WAREHOUSE_DIR / "format_monthly_by_grade.csv", index=False)

neuro = visits_enriched[(visits_enriched["specialty"] == "Косметолог") & (visits["bucket"] != "Инъекции")]
neuro_metrics = neuro.groupby("month").agg(
    revenue=("revenue", "sum"), n_visits=("visit_id", "count"), n_doctors=("doctor", "nunique"),
).reset_index()
neuro_metrics["avg_check"] = neuro_metrics["revenue"] / neuro_metrics["n_visits"]
neuro_metrics["visits_per_doctor"] = neuro_metrics["n_visits"] / neuro_metrics["n_doctors"]
neuro_metrics.to_csv(WAREHOUSE_DIR / "neurology_monthly_metrics.csv", index=False)

neuro_by_doctor = neuro.groupby(["month", "doctor"])["revenue"].sum().reset_index()
top_doctor_share = (
    neuro_by_doctor.sort_values("revenue", ascending=False)
    .groupby("month")
    .apply(lambda g: g.iloc[0]["revenue"] / g["revenue"].sum(), include_groups=False)
    .rename("top_doctor_share").reset_index()
)
top_doctor_share.to_csv(WAREHOUSE_DIR / "neurology_top_doctor_share.csv", index=False)

room_rows = []
for month, grp in visits_enriched.groupby("month"):
    year, mon = map(int, month.split("-"))
    days_in_month = calendar.monthrange(year, mon)[1]
    for specialty, n_rooms in ROOMS.items():
        capacity_hours = n_rooms * HOURS_PER_DAY * days_in_month
        spec_grp = grp[grp["specialty"] == specialty]
        if specialty == "Косметолог":
            actual_hours = len(spec_grp) * 60 / 60
        else:
            actual_hours = spec_grp["format_min"].sum() / 60
        room_rows.append({
            "month": month, "specialty": specialty, "n_rooms": n_rooms, "capacity_hours": capacity_hours,
            "actual_hours": actual_hours, "utilization_pct": actual_hours / capacity_hours if capacity_hours else None,
        })
pd.DataFrame(room_rows).to_csv(WAREHOUSE_DIR / "room_utilization_monthly.csv", index=False)

team = visits_enriched.groupby(["month", "specialty"]).agg(
    n_doctors=("doctor", "nunique"), n_visits=("visit_id", "count")
).reset_index()
team.to_csv(WAREHOUSE_DIR / "doctor_team_monthly.csv", index=False)

cross_sell_src = lines.groupby(["month", "patient_id"])["direction"].nunique().reset_index(name="n_directions")
cross_sell = cross_sell_src.groupby("month").agg(
    n_patients=("patient_id", "count"), n_cross_sell=("n_directions", lambda s: (s > 1).sum()),
    avg_directions_per_patient=("n_directions", "mean"),
).reset_index()
cross_sell["cross_sell_rate"] = cross_sell["n_cross_sell"] / cross_sell["n_patients"]
cross_sell.to_csv(WAREHOUSE_DIR / "cross_sell_monthly.csv", index=False)

print("Готово: визиты, врачи, грейды, форматы, косметология, кабинеты, команда, cross-sell.")

# ───────────────────────── 7. direction_margin_monthly / drug_margin_monthly ─────────────────────────

DIR_MARGIN_PCT = {"Стоматология": 0.66, "Косметология": 0.60, "Инъекции": 0.42}
dir_margin_rows = []
for month in MONTHS_ACTUAL:
    for d in DIRECTIONS_3:
        revenue = by_direction_value[(month, d)]
        margin_pct = DIR_MARGIN_PCT[d] * np.random.uniform(0.95, 1.05)
        margin = revenue * margin_pct
        dir_margin_rows.append({
            "month": month, "direction": d, "revenue": round(revenue), "cost": round(revenue - margin),
            "margin": round(margin), "margin_pct": round(margin_pct, 4),
        })
pd.DataFrame(dir_margin_rows).to_csv(WAREHOUSE_DIR / "direction_margin_monthly.csv", index=False)

DRUG_WEIGHTS = [0.30, 0.25, 0.20, 0.15, 0.10]
drug_rows = []
for month in MONTHS_ACTUAL:
    inj_revenue = by_direction_value[(month, "Инъекции")]
    for drug, w in zip(DRUGS, DRUG_WEIGHTS):
        if random.random() < 0.15:
            continue  # не каждый препарат продаётся каждый месяц
        revenue = inj_revenue * w * np.random.uniform(0.8, 1.2)
        margin_pct = np.random.uniform(0.35, 0.50)
        margin = revenue * margin_pct
        drug_rows.append({
            "month": month, "drug": drug, "revenue": round(revenue), "cost": round(revenue - margin),
            "margin": round(margin), "margin_pct": round(margin_pct, 4),
        })
pd.DataFrame(drug_rows).to_csv(WAREHOUSE_DIR / "drug_margin_monthly.csv", index=False)

# ───────────────────────── 8. Клиенты: monthly_client_summary / cohort_ltv / churn_monthly ─────────────────────────

v = visits_enriched.copy()
v["visit_month"] = v["month"].apply(lambda m: pd.Period(m, freq="M"))
cohort = v.groupby("patient_id")["visit_datetime"].min().dt.to_period("M").rename("cohort_month")
v = v.merge(cohort, on="patient_id")


def month_diff(later: pd.Period, earlier: pd.Period) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


v["month_index"] = v.apply(lambda r: month_diff(r["visit_month"], r["cohort_month"]), axis=1)
v["is_repeat_month"] = v["month_index"] > 0

grouped = v.groupby(["visit_month", "is_repeat_month"]).agg(
    n_clients=("patient_id", "nunique"), n_visits=("visit_id", "count"),
    revenue=("revenue", "sum"), n_services=("n_services", "sum"),
)
monthly_client = grouped.unstack("is_repeat_month", fill_value=0)
monthly_client.columns = [f"{metric}_{'repeat' if is_repeat else 'new'}" for metric, is_repeat in monthly_client.columns]
monthly_client["total_revenue"] = monthly_client.get("revenue_new", 0) + monthly_client.get("revenue_repeat", 0)
monthly_client["total_clients"] = monthly_client.get("n_clients_new", 0) + monthly_client.get("n_clients_repeat", 0)
monthly_client = monthly_client.reset_index().sort_values("visit_month")
monthly_client["visit_month"] = monthly_client["visit_month"].astype(str)
monthly_client.to_csv(WAREHOUSE_DIR / "monthly_client_summary.csv", index=False)


def expand_patient_history(grp, data_max_month):
    cohort_month = grp["cohort_month"].iloc[0]
    max_age = month_diff(data_max_month, cohort_month)
    s = grp.set_index("month_index")[["revenue", "n_services"]].reindex(range(max_age + 1), fill_value=0)
    s["cum_revenue"] = s["revenue"].cumsum()
    s["cum_services"] = s["n_services"].cumsum()
    s = s.reset_index().rename(columns={"index": "month_index"})
    s["cohort_month"] = cohort_month
    return s


patient_month = v.groupby(["patient_id", "cohort_month", "month_index"]).agg(
    revenue=("revenue", "sum"), n_services=("n_services", "sum")
).reset_index()
data_max_month = v["visit_month"].max()
expanded = (
    patient_month.groupby("patient_id", group_keys=True)
    .apply(lambda g: expand_patient_history(g, data_max_month), include_groups=False)
    .reset_index(level=0)
)
cohort_ltv = expanded.groupby(["cohort_month", "month_index"]).agg(
    n_clients=("patient_id", "nunique"), avg_cum_revenue=("cum_revenue", "mean"), avg_cum_services=("cum_services", "mean"),
).reset_index().sort_values(["cohort_month", "month_index"])
cohort_ltv["cohort_month"] = cohort_ltv["cohort_month"].astype(str)
cohort_ltv.to_csv(WAREHOUSE_DIR / "cohort_ltv.csv", index=False)

active_months_by_patient = v.groupby("patient_id")["visit_month"].apply(set)
all_months_set = set(v["visit_month"].unique())
churn_rows = []
for m in sorted(all_months_set):
    active_in_m = v.loc[v["visit_month"] == m, "patient_id"].unique()
    future_needed = {m + 1, m + 2, m + 3}
    if not future_needed.issubset(all_months_set):
        churn_rows.append({"month": str(m), "active_clients": len(active_in_m), "churned_clients": None, "churn_rate": None})
        continue
    churned = sum(1 for pid in active_in_m if not (active_months_by_patient[pid] & future_needed))
    churn_rows.append({
        "month": str(m), "active_clients": len(active_in_m), "churned_clients": churned,
        "churn_rate": churned / len(active_in_m) if len(active_in_m) else None,
    })
pd.DataFrame(churn_rows).to_csv(WAREHOUSE_DIR / "churn_monthly.csv", index=False)

print(f"monthly_client_summary: {len(monthly_client)} строк, cohort_ltv: {len(cohort_ltv)} строк")

# ───────────────────────── 9. KPI план (2026, 12 мес) ─────────────────────────

kpi_plan_rows = []
for i, month in enumerate(MONTHS_KPI):
    kpi_plan_rows.append({
        "month": month,
        "conversion_plan": round(0.75 * np.random.uniform(0.97, 1.03), 3),
        "cancellation_plan": round(0.08 * np.random.uniform(0.9, 1.1), 3),
        "doctor_utilization_plan": round(0.70 * np.random.uniform(0.97, 1.03), 3),
        "repeat_visit_share_plan": round(0.55 * np.random.uniform(0.95, 1.05), 3),
    })
kpi_plan = pd.DataFrame(kpi_plan_rows)
kpi_plan.to_csv(WAREHOUSE_DIR / "kpi_plan_monthly.csv", index=False)

# ───────────────────────── 10. breakeven_monthly (10 факт-месяцев) ─────────────────────────

actual_agg = v.groupby("month").agg(n_visits_actual=("visit_id", "count"), revenue_actual=("revenue", "sum")).reset_index()
actual_agg["avg_check_actual"] = actual_agg["revenue_actual"] / actual_agg["n_visits_actual"]

pnl_actual = pnl[pnl["month"].isin(MONTHS_ACTUAL)][["month", "margin_pct", "fixed_costs"]].reset_index(drop=True)
be = pnl_actual.merge(actual_agg, on="month", how="left").merge(kpi_plan[["month"]], on="month", how="left")
# план-консультации/выручка (для месяцев 2026) — план чуть ниже факта, клиника опережает план
plan_lookup = {m: v for m, v in zip(MONTHS_KPI, np.linspace(0.90, 0.94, len(MONTHS_KPI)))}
be["plan_sessions"] = be.apply(
    lambda r: round(r["n_visits_actual"] * plan_lookup[r["month"]]) if r["month"] in plan_lookup else None, axis=1
)
be["plan_revenue"] = be.apply(
    lambda r: round(r["revenue_actual"] * plan_lookup[r["month"]]) if r["month"] in plan_lookup else None, axis=1
)
be["margin_pct_3m"] = be["margin_pct"].rolling(window=3, min_periods=1).mean()
be["fixed_costs_3m"] = be["fixed_costs"].rolling(window=3, min_periods=1).mean()
be["be_revenue"] = be["fixed_costs_3m"] / be["margin_pct_3m"]
be["be_sessions"] = (be["be_revenue"] / be["avg_check_actual"]).round(0)
be["gap_sessions_vs_be"] = be["n_visits_actual"] - be["be_sessions"]
be["status"] = be["gap_sessions_vs_be"].apply(lambda x: "выше ТБУ" if x >= 0 else "НИЖЕ ТБУ")
be = be[[
    "month", "revenue_actual", "n_visits_actual", "avg_check_actual", "margin_pct", "fixed_costs",
    "margin_pct_3m", "fixed_costs_3m", "be_revenue", "be_sessions", "gap_sessions_vs_be", "status",
    "plan_sessions", "plan_revenue",
]]
be.to_csv(WAREHOUSE_DIR / "breakeven_monthly.csv", index=False)

# ───────────────────────── 11. funnel_monthly (10 факт-месяцев) ─────────────────────────

funnel_rows = []
for i, row in actual_agg.iterrows():
    completion_rate = lerp(0.82, 0.90, i, N_ACTUAL)
    cancel_rate = lerp(0.09, 0.06, i, N_ACTUAL)
    n_completed = int(row["n_visits_actual"])
    n_booked = round(n_completed / completion_rate)
    n_cancelled = round(n_booked * cancel_rate)
    n_rescheduled = max(0, n_booked - n_completed - n_cancelled)
    n_booked = n_completed + n_cancelled + n_rescheduled
    funnel_rows.append({
        "month": row["month"], "n_booked": n_booked, "n_completed": n_completed, "n_cancelled": n_cancelled,
        "n_rescheduled": n_rescheduled, "conversion_pct": round(n_completed / n_booked, 4),
        "cancellation_pct": round(n_cancelled / n_booked, 4), "reschedule_pct": round(n_rescheduled / n_booked, 4),
    })
pd.DataFrame(funnel_rows).to_csv(WAREHOUSE_DIR / "funnel_monthly.csv", index=False)

# ───────────────────────── 11б. marketing_spend_monthly (для CAC) ─────────────────────────

MARKETING_CHANNELS = {"Таргетированная реклама": 0.45, "Контекстная реклама": 0.35, "Партнёрства и рефералы": 0.20}
marketing_rows = []
for i, month in enumerate(MONTHS_ACTUAL):
    revenue = pnl.loc[pnl["month"] == month, "revenue"].iloc[0]
    spend_pct = lerp(0.11, 0.09, i, N_ACTUAL) * np.random.uniform(0.95, 1.05)  # растущая эффективность маркетинга
    total_spend = revenue * spend_pct
    shares = np.array([w * np.random.uniform(0.9, 1.1) for w in MARKETING_CHANNELS.values()])
    shares = shares / shares.sum()
    for channel, share in zip(MARKETING_CHANNELS, shares):
        marketing_rows.append({"month": month, "channel": channel, "spend": round(total_spend * share)})
pd.DataFrame(marketing_rows).to_csv(WAREHOUSE_DIR / "marketing_spend_monthly.csv", index=False)

# ───────────────────────── 12. cash_runway_monthly (40 мес, 2024-09..2027-12) ─────────────────────────

op_by_month = dict(zip(pnl["month"], pnl["operating_profit"]))
cash_rows = []
# до старта факт-данных — клиника уже прибыльна, только меньше масштабом:
# операционная прибыль плавно растёт к значению первого факт-месяца
pre_months = [m for m in MONTHS_CASH if m < MONTHS_PNL[0]]
pre_op = np.linspace(40_000, pnl.loc[0, "operating_profit"], len(pre_months) + 1)[:-1]
for m, op in zip(pre_months, pre_op):
    op_by_month[m] = round(op)
# после конца monthly_pnl — продолжаем тренд роста прибыли
post_months = [m for m in MONTHS_CASH if m > MONTHS_PNL[-1]]
last_op = pnl["operating_profit"].iloc[-1]
post_op = np.linspace(last_op, last_op * 1.6, len(post_months) + 1)[1:]
for m, op in zip(post_months, post_op):
    op_by_month[m] = round(op)

cash = 3_000_000.0  # взнос учредителей на старте
for m in MONTHS_CASH:
    op = op_by_month[m]
    cash += op
    cash_rows.append({"month": m, "cash": round(cash), "debt_credit": 0, "debt_loan": 0, "operating_profit": op})
cash_df = pd.DataFrame(cash_rows)
cash_df["total_debt"] = cash_df["debt_credit"] + cash_df["debt_loan"]
cash_df["burn_3mo_avg"] = -cash_df["operating_profit"].rolling(3, min_periods=1).mean()
cash_df = cash_df[["month", "cash", "debt_credit", "debt_loan", "total_debt", "operating_profit", "burn_3mo_avg"]]
cash_df.to_csv(WAREHOUSE_DIR / "cash_runway_monthly.csv", index=False)

print(f"breakeven: {len(be)}, funnel: {len(funnel_rows)}, cash_runway: {len(cash_df)}, kpi_plan: {len(kpi_plan)}")

# ───────────────────────── 13. doctor_economics_monthly ─────────────────────────
# Косметолог: строки "Косметолог" (косметология) и "Инъекции" — как в оригинале (grade override).

econ_src = visits_enriched.copy()
econ_src["econ_grade"] = econ_src["grade"]
is_neuro_injection = (econ_src["specialty"] == "Косметолог") & (visits["bucket"] == "Инъекции")
econ_src.loc[is_neuro_injection.values, "econ_grade"] = "Инъекции"

monthly_econ = econ_src.groupby(["month", "doctor", "econ_grade", "specialty"]).agg(
    revenue=("revenue", "sum"), n_services=("n_services", "sum")
).reset_index().rename(columns={"econ_grade": "grade"})

payout_ratio = DOCTORS.set_index("doctor")["payout_ratio"]
doctor_month_revenue = monthly_econ.groupby(["month", "doctor"])["revenue"].transform("sum")
net_payout_by_doctor_month = doctor_month_revenue * monthly_econ["doctor"].map(payout_ratio)
doctor_revenue_share = (monthly_econ["revenue"] / doctor_month_revenue.replace(0, np.nan)).fillna(0)
monthly_econ["zp"] = net_payout_by_doctor_month * doctor_revenue_share
monthly_econ["tax"] = monthly_econ["zp"] * TAX_MULTIPLIER

drug_cost_by_month = pd.DataFrame(drug_rows).groupby("month")["cost"].sum() if drug_rows else pd.Series(dtype=float)
monthly_econ["total_drug_cost"] = monthly_econ["month"].map(drug_cost_by_month).fillna(0)
is_injections = monthly_econ["grade"] == "Инъекции"
inj_revenue_by_month = monthly_econ.loc[is_injections].groupby("month")["revenue"].transform("sum")
inj_share = pd.Series(0.0, index=monthly_econ.index)
inj_share.loc[is_injections] = (monthly_econ.loc[is_injections, "revenue"] / inj_revenue_by_month).fillna(0)
monthly_econ["drug_cost"] = monthly_econ["total_drug_cost"] * inj_share
monthly_econ["commission_cost"] = monthly_econ["zp"] + monthly_econ["tax"] + monthly_econ["drug_cost"]
monthly_econ["net_margin"] = monthly_econ["revenue"] - monthly_econ["commission_cost"]
monthly_econ["margin_pct"] = monthly_econ["net_margin"] / monthly_econ["revenue"]
monthly_econ = monthly_econ[[
    "month", "doctor", "grade", "specialty", "revenue", "zp", "tax", "drug_cost",
    "commission_cost", "net_margin", "margin_pct", "n_services",
]].round({"zp": 0, "tax": 0, "drug_cost": 0, "commission_cost": 0, "net_margin": 0, "revenue": 0})
monthly_econ.to_csv(WAREHOUSE_DIR / "doctor_economics_monthly.csv", index=False)

# ───────────────────────── 14. doctor_monthly_utilization ─────────────────────────

PLANNED_HOURS = {"Стоматолог": 140, "Косметолог": 100, "Гигиенист": 80}
util_rows = []
doctor_rev_by_month = visits_enriched.groupby(["month", "doctor"])["revenue"].sum().reset_index()
for i, month in enumerate(MONTHS_ACTUAL):
    for _, doc in DOCTORS.iterrows():
        if doc["join_idx"] > i:
            continue
        base = PLANNED_HOURS[doc["specialty"]]
        planned_hours = round(base * np.random.uniform(0.9, 1.1), 1)
        fill_rate = lerp(0.66, 0.84, i, N_ACTUAL) * np.random.uniform(0.9, 1.08)
        fill_rate = min(fill_rate, 1.0)
        closed_hours = round(planned_hours * fill_rate, 1)
        rev_row = doctor_rev_by_month[(doctor_rev_by_month["month"] == month) & (doctor_rev_by_month["doctor"] == doc["doctor"])]
        revenue = float(rev_row["revenue"].iloc[0]) if not rev_row.empty else 0.0
        util_rows.append({
            "doctor": doc["doctor"], "month": month, "planned_hours": planned_hours, "closed_hours": closed_hours,
            "fill_rate": round(closed_hours / planned_hours, 3), "revenue": round(revenue),
            "revenue_per_hour": round(revenue / closed_hours) if closed_hours else 0,
        })
pd.DataFrame(util_rows).to_csv(WAREHOUSE_DIR / "doctor_monthly_utilization.csv", index=False)

print(f"doctor_economics: {len(monthly_econ)} строк, doctor_monthly_utilization: {len(util_rows)} строк")

# ───────────────────────── 15. Retention/churn — из "внешнего источника" (независимая от cohort_analysis логика) ─────────────────────────

SPEC_LABEL = {"Стоматолог": "Стоматология", "Косметолог": "Косметология"}  # raw specialty -> лейбл внешнего отчёта

first_visit = v.sort_values("visit_datetime").groupby("patient_id").first().reset_index()
first_visit = first_visit.rename(columns={"specialty": "first_specialty", "visit_datetime": "first_visit_dt"})
visit_dates_by_patient = v.groupby("patient_id")["visit_datetime"].apply(lambda s: sorted(s))
n_visits_by_patient = v.groupby("patient_id")["visit_id"].count()
revenue_by_patient = v.groupby("patient_id")["revenue"].sum()
first_visit["n_total_visits"] = first_visit["patient_id"].map(n_visits_by_patient)
first_visit["has_2nd"] = first_visit["n_total_visits"] >= 2
first_visit["lifetime_revenue"] = first_visit["patient_id"].map(revenue_by_patient)


def second_visit_gap_days(pid):
    ds = visit_dates_by_patient[pid]
    return (ds[1] - ds[0]).days if len(ds) >= 2 else None


first_visit["gap_2nd_days"] = first_visit["patient_id"].apply(second_visit_gap_days)


def has_visit_in_window(pid, cohort_month, lo, hi):
    ds = visit_dates_by_patient[pid]
    return any(lo <= month_diff(pd.Period(d, freq="M"), cohort_month) <= hi for d in ds)


def group_metrics(patient_ids: list[str]) -> dict:
    sub = first_visit[first_visit["patient_id"].isin(patient_ids)]
    n = len(sub)
    if n == 0:
        return {"n_patients": 0, "return_2nd": None, "retention_3mo": None, "retention_6mo": None,
                "lost_after_1st": None, "ltv": None, "revenue_per_visit": None, "avg_interval_days": None}
    ret3 = sub.apply(lambda r: has_visit_in_window(r["patient_id"], r["cohort_month"], 1, 3), axis=1)
    ret6 = sub.apply(lambda r: has_visit_in_window(r["patient_id"], r["cohort_month"], 1, 6), axis=1)
    gaps = sub["gap_2nd_days"].dropna()
    total_visits = sub["patient_id"].map(n_visits_by_patient).sum()
    return {
        "n_patients": n, "return_2nd": round(sub["has_2nd"].mean(), 4),
        "retention_3mo": round(ret3.mean(), 4), "retention_6mo": round(ret6.mean(), 4),
        "lost_after_1st": round(1 - sub["has_2nd"].mean(), 4), "ltv": round(sub["lifetime_revenue"].mean()),
        "revenue_per_visit": round(sub["lifetime_revenue"].sum() / total_visits) if total_visits else None,
        "avg_interval_days": round(gaps.mean(), 1) if len(gaps) else None,
    }


def level_for(value):
    if value is None or pd.isna(value):
        return ""
    if value < 0.45:
        return "Ниже среднего"
    if value < 0.60:
        return "Средний"
    if value < 0.75:
        return "Хороший"
    return "Отличный"


BENCHMARK = {"return_2nd": "60–75% хороший диапазон", "retention_3mo": "45–60% средний диапазон", "retention_6mo": "30–45% средний диапазон"}

# --- retention_scorecard.csv ---
scorecard_rows = []
for raw_spec, label in SPEC_LABEL.items():
    pids = first_visit[first_visit["first_specialty"] == raw_spec]["patient_id"].tolist()
    m = group_metrics(pids)
    for metric in ["return_2nd", "retention_3mo", "retention_6mo"]:
        scorecard_rows.append({
            "specialty": label, "metric": metric, "value": m[metric], "n": m["n_patients"],
            "level": level_for(m[metric]), "benchmark": BENCHMARK[metric],
        })
pd.DataFrame(scorecard_rows).to_csv(WAREHOUSE_DIR / "retention_scorecard.csv", index=False)

# --- cohort_retention.csv (specialty x cohort_month) ---
cohort_ret_rows = []
for raw_spec, label in SPEC_LABEL.items():
    spec_first = first_visit[first_visit["first_specialty"] == raw_spec]
    for cm in sorted(spec_first["cohort_month"].unique()):
        pids = spec_first[spec_first["cohort_month"] == cm]["patient_id"].tolist()
        m = group_metrics(pids)
        m["specialty"] = label
        m["cohort_month"] = str(cm)
        cohort_ret_rows.append(m)
cols_order = ["specialty", "cohort_month", "n_patients", "return_2nd", "retention_3mo", "retention_6mo",
              "lost_after_1st", "ltv", "revenue_per_visit", "avg_interval_days"]
pd.DataFrame(cohort_ret_rows)[cols_order].to_csv(WAREHOUSE_DIR / "cohort_retention.csv", index=False)

# --- grade_retention.csv (стоматология по грейду, агрегат без cohort_month) ---
first_doctor_by_patient = v.sort_values("visit_datetime").groupby("patient_id")["doctor"].first()
first_visit["first_doctor"] = first_visit["patient_id"].map(first_doctor_by_patient)
first_visit["first_grade"] = first_visit["first_doctor"].map(DOCTORS.set_index("doctor")["grade"])

grade_ret_rows = []
for grade in ["Грейд 1", "Грейд 2", "Грейд 3"]:
    pids = first_visit[first_visit["first_grade"] == grade]["patient_id"].tolist()
    m = group_metrics(pids)
    m["specialty"] = "Стоматология"
    m["grade"] = grade
    grade_ret_rows.append(m)
cols_order_grade = ["specialty", "grade", "n_patients", "return_2nd", "retention_3mo", "retention_6mo",
                    "lost_after_1st", "ltv", "revenue_per_visit", "avg_interval_days"]
pd.DataFrame(grade_ret_rows)[cols_order_grade].to_csv(WAREHOUSE_DIR / "grade_retention.csv", index=False)

# --- churn_by_specialty.csv (specialty x month, методика "не вернулся 3 мес") ---
CHURN_GROUPS = {"Косметология": ["Косметолог"], "Стоматология": ["Стоматолог"], "Оба направления": ["Косметолог", "Стоматолог", "Гигиенист"]}
churn_spec_rows = []
for label, raw_specs in CHURN_GROUPS.items():
    pids_set = set(first_visit[first_visit["first_specialty"].isin(raw_specs)]["patient_id"])
    for m in sorted(all_months_set):
        active_in_m = set(v.loc[(v["visit_month"] == m) & (v["patient_id"].isin(pids_set)), "patient_id"].unique())
        future_needed = {m + 1, m + 2, m + 3}
        preliminary = not future_needed.issubset(all_months_set)
        if preliminary:
            churn_rate, churned = None, None
        else:
            churned = sum(1 for pid in active_in_m if not (active_months_by_patient[pid] & future_needed))
            churn_rate = churned / len(active_in_m) if active_in_m else None
        churn_spec_rows.append({
            "specialty": label, "month": str(m), "active_clients": len(active_in_m),
            "churned_clients": churned, "churn_rate": round(churn_rate, 4) if churn_rate is not None else None,
            "preliminary": preliminary,
        })
pd.DataFrame(churn_spec_rows).to_csv(WAREHOUSE_DIR / "churn_by_specialty.csv", index=False)

# --- doctor_retention_anomalies.csv (по врачу; специальность в raw-нотации Стоматолог/Косметолог) ---
MATURITY_DAYS, MIN_PATIENTS = 90, 8
today = v["visit_datetime"].max() + pd.Timedelta(days=20)
first_visit["days_since_first"] = (today - first_visit["first_visit_dt"]).dt.days
mature = first_visit[first_visit["days_since_first"] >= MATURITY_DAYS].copy()
doctor_first_month = v.groupby("doctor")["visit_datetime"].min().dt.to_period("M").astype(str)

by_doc = mature.groupby(["first_specialty", "first_doctor"]).agg(
    n_patients=("patient_id", "count"), return_2nd_rate=("has_2nd", "mean")
).reset_index()
by_doc = by_doc[by_doc["n_patients"] >= MIN_PATIENTS]
by_doc["doctor_first_month"] = by_doc["first_doctor"].map(doctor_first_month)
specialty_avg = by_doc.groupby("first_specialty").apply(
    lambda g: (g["return_2nd_rate"] * g["n_patients"]).sum() / g["n_patients"].sum(), include_groups=False
)
by_doc["specialty_avg_rate"] = by_doc["first_specialty"].map(specialty_avg)
by_doc["delta_vs_specialty_avg"] = by_doc["return_2nd_rate"] - by_doc["specialty_avg_rate"]
by_doc = by_doc.rename(columns={"first_specialty": "specialty", "first_doctor": "doctor"})
by_doc = by_doc[[
    "specialty", "doctor", "doctor_first_month", "n_patients", "return_2nd_rate", "specialty_avg_rate", "delta_vs_specialty_avg",
]].sort_values("delta_vs_specialty_avg").round({"return_2nd_rate": 4, "specialty_avg_rate": 4, "delta_vs_specialty_avg": 4})
by_doc.to_csv(WAREHOUSE_DIR / "doctor_retention_anomalies.csv", index=False)

print(f"retention_scorecard: {len(scorecard_rows)}, cohort_retention: {len(cohort_ret_rows)}, "
      f"grade_retention: {len(grade_ret_rows)}, churn_by_specialty: {len(churn_spec_rows)}, "
      f"doctor_retention_anomalies: {len(by_doc)}")
print("\nГенерация warehouse/ завершена.")






