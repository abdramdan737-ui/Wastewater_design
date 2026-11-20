# -*- coding: utf-8 -*-

import os
import math
import pandas as pd
import streamlit as st
import numpy_financial as npf

# =====================================================
# 1. إعدادات الصفحة الأساسية
# =====================================================

st.set_page_config(
    page_title="منصة إنشاءات للاستشارات الهندسية",
    layout="wide",
    page_icon="🏗️"
)

# =====================================================
# 2. التنسيقات والألوان CSS
# =====================================================

# =====================================================
# 2. تحميل التنسيقات من ملف style.css
# =====================================================

from pathlib import Path

CSS_FILE = Path(__file__).resolve().parent / "style.css"

if CSS_FILE.exists():

    css_content = CSS_FILE.read_text(encoding="utf-8")

    st.markdown(
        f"<style>{css_content}</style>",
        unsafe_allow_html=True
    )

else:
    st.error("لم يتم العثور على ملف style.css")


# =====================================================
# 3. إعداد الاتصال بالذكاء الاصطناعي Gemini
# =====================================================

# ملاحظة أمنية:
# ضع المفتاح في Streamlit Secrets أو متغيرات البيئة.
# لا تضع مفتاح API داخل ملف Python.

API_KEY = os.getenv("GEMINI_API_KEY", "")

try:
    API_KEY = st.secrets.get("GEMINI_API_KEY", API_KEY)
except Exception:
    pass

client = None

if API_KEY:
    try:
        from google import genai
        client = genai.Client(api_key=API_KEY)
    except Exception as e:
        st.sidebar.warning(
            "تعذر تهيئة اتصال Gemini: " + str(e)
        )
else:
    st.sidebar.caption(
        "اتصال Gemini غير مهيأ حالياً."
    )


# =====================================================
# 4. الملفات المرجعية الهندسية
# =====================================================

REFERENCE_FOLDER = "reference_files"


def get_reference_content():

    all_context = ""

    if not os.path.exists(REFERENCE_FOLDER):
        return all_context

    for filename in os.listdir(REFERENCE_FOLDER):

        file_path = os.path.join(
            REFERENCE_FOLDER,
            filename
        )

        try:

            if filename.lower().endswith(".xlsx"):
                df = pd.read_excel(file_path)

            elif filename.lower().endswith(".csv"):
                df = pd.read_csv(file_path)

            else:
                continue

            all_context += (
                f"\nمحتوى ملف {filename}:\n"
                f"{df.to_string(index=False)}\n"
            )

        except Exception as e:

            all_context += (
                f"\nتعذر قراءة الملف {filename}: {e}\n"
            )

    return all_context


# =====================================================
# 5. تخزين بيانات الجلسة
# =====================================================

if "context_data" not in st.session_state:
    st.session_state.context_data = (
        "لا توجد بيانات إضافية مرفوعة حالياً."
    )


# =====================================================
# 5.5 دوال هندسية مساعدة (الجدوى ومحطات الصرف)
# =====================================================

def fmt(v, nd=2, unit=""):
    """تنسيق رقم للعرض (— للقيم غير المتاحة)."""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    return f"{v:,.{nd}f}" + (f" {unit}" if unit else "")


def chk(name, value, lo=None, hi=None, unit=""):
    """فحص تصميمي: القيمة مقابل مدى مرجعي."""
    ok = (
        value is not None
        and math.isfinite(value)
        and (lo is None or value >= lo)
        and (hi is None or value <= hi)
    )
    if lo is not None and hi is not None:
        rng = f"{lo:g}–{hi:g}"
    elif hi is not None:
        rng = f"≤ {hi:g}"
    else:
        rng = f"≥ {lo:g}"
    return {
        "الفحص": name,
        "القيمة": fmt(value, 2),
        "المدى المرجعي": f"{rng} {unit}".strip(),
        "الحالة": "✅" if ok else "⚠️",
    }


def safe_irr(cf):
    try:
        v = float(npf.irr(cf))
        return v if math.isfinite(v) else None
    except Exception:
        return None


def safe_mirr(cf, rate):
    try:
        v = float(npf.mirr(cf, rate, rate))
        return v if math.isfinite(v) else None
    except Exception:
        return None


def tax_with_losses(base, rate, holiday_start, holiday_len):
    """ضريبة دخل مع ترحيل الخسائر وإعفاء ضريبي (سنوات من بدء التشغيل)."""
    tax = [0.0] * len(base)
    nol = 0.0
    for t, b in enumerate(base):
        if b < 0:
            nol += -b
            continue
        if holiday_start <= t < holiday_start + holiday_len:
            continue
        use = min(nol, b)
        nol -= use
        tax[t] = (b - use) * rate
    return tax


def payback_years(cf, n_construction):
    """فترة الاسترداد (سنوات من بدء التشغيل) بالاستيفاء الخطي."""
    cum = 0.0
    for t, x in enumerate(cf):
        prev = cum
        cum += x
        if t >= n_construction and cum >= 0 and x > 0:
            return (t - 1) + (-prev) / x - (n_construction - 1)
    return None


def run_feasibility(p, rev_mult=1.0, exp_mult=1.0, capex_mult=1.0, rate=None):
    """نموذج التدفقات: FCFF و FCFE والمؤشرات. الافتراضات المحايدة تعيد نتائج النموذج المبسط الأصلي."""
    r = p["rate"] if rate is None else rate
    Nc, No = p["Nc"], p["No"]
    T = Nc + No

    # --- الكلفة الرأسمالية (الأرض عند t=0، والباقي موزع على سنوات الإنشاء)
    hard = (p["construction"] + p["other"]) * capex_mult
    cap = [hard / Nc if t < Nc else 0.0 for t in range(T)]
    cap[0] += p["land"]

    rev = [0.0] * T
    opx = [0.0] * T
    rent = [0.0] * T
    dep = [0.0] * T
    repl = [0.0] * T
    for t in range(Nc, T):
        k = t - Nc + 1
        ramp = 1.0
        if p["ramp_years"] > 1 and k < p["ramp_years"]:
            ramp = p["first_ratio"] + (1 - p["first_ratio"]) * (k - 1) / (p["ramp_years"] - 1)
        rev[t] = p["revenue"] * ramp * (1 + p["g_rev"]) ** (k - 1) * rev_mult
        opx[t] = p["expenses"] * (1 + p["g_exp"]) ** (k - 1) * exp_mult
        rent[t] = p["rent"] * (1 + p["g_rent"]) ** (k - 1)
        if k <= p["dep_years"]:
            dep[t] = hard / p["dep_years"]
        if p["repl_year"] > 0 and k == p["repl_year"]:
            repl[t] = p["repl_cost"] * capex_mult

    ebitda = [rev[t] - opx[t] - rent[t] for t in range(T)]
    ebit = [ebitda[t] - dep[t] - repl[t] for t in range(T)]
    tax_u = tax_with_losses(ebit, p["tax"], Nc, p["holiday"])

    wc = [p["wc"] * rev[t] for t in range(T)]
    dwc = [wc[t] - (wc[t - 1] if t > 0 else 0.0) for t in range(T)]
    term = [0.0] * T
    term[-1] = (
        p["salvage"]
        + (p["land"] * (1 + p["land_g"]) ** No if p["land_residual"] else 0.0)
        + wc[-1]
    )

    fcff = [ebitda[t] - tax_u[t] - repl[t] - dwc[t] - cap[t] + term[t] for t in range(T)]

    # --- التمويل (قرض بأقساط أصل متساوية)
    draw = [c * p["debt_pct"] for c in cap]
    total_debt = sum(draw)
    interest = [0.0] * T
    princ = [0.0] * T
    bal = 0.0
    rs, n = Nc + p["grace"], max(p["repay_years"], 1)
    for t in range(T):
        interest[t] = bal * p["int_rate"]
        bal += draw[t]
        if rs <= t < rs + n:
            pay = min(bal, total_debt / n)
            princ[t] = pay
            bal -= pay
    princ[-1] += bal
    tax_l = tax_with_losses([ebit[t] - interest[t] for t in range(T)], p["tax"], Nc, p["holiday"])
    fcfe = [
        ebitda[t] - tax_l[t] - repl[t] - dwc[t] - cap[t] + term[t] + draw[t] - interest[t] - princ[t]
        for t in range(T)
    ]
    cfads = [ebitda[t] - tax_l[t] - repl[t] - dwc[t] for t in range(T)]
    ds = [interest[t] + princ[t] for t in range(T)]
    dscr = [cfads[t] / ds[t] if t >= Nc and ds[t] > 0 else None for t in range(T)]
    dscr_vals = [x for x in dscr if x is not None]

    disc = [(1 + r) ** t for t in range(T)]
    pv = lambda x: sum(x[t] / disc[t] for t in range(T))
    npv = float(npf.npv(r, fcff))
    pv_cap = pv(cap)
    cost_pv = pv(cap) + pv(opx) + pv(rent) + pv(repl) + pv(tax_u) + pv([max(d, 0.0) for d in dwc])
    cum = [sum(fcff[: t + 1]) for t in range(T)]
    dcf = [fcff[t] / disc[t] for t in range(T)]
    dcum = [sum(dcf[: t + 1]) for t in range(T)]

    return dict(
        T=T, Nc=Nc, cap=cap, rev=rev, opx=opx, rent=rent, ebitda=ebitda, dep=dep, tax=tax_u, repl=repl,
        dwc=dwc, term=term, fcff=fcff, cum=cum, dcum=dcum, draw=draw, interest=interest, princ=princ,
        fcfe=fcfe, dscr=dscr, npv=npv, irr=safe_irr(fcff), mirr=safe_mirr(fcff, r),
        pi=(1 + npv / pv_cap) if pv_cap else None,
        bcr=(pv(rev) + pv(term)) / cost_pv if cost_pv else None,
        payback=payback_years(fcff, Nc), dpayback=payback_years(dcf, Nc),
        invest=sum(cap), debt=total_debt,
        roi=(sum(ebitda[Nc:]) - sum(tax_u)) / No / sum(cap) if sum(cap) else None,
        irr_e=safe_irr(fcfe),
        npv_e=float(npf.npv(p["ke"], fcfe)),
        dscr_min=min(dscr_vals) if dscr_vals else None,
        dscr_avg=sum(dscr_vals) / len(dscr_vals) if dscr_vals else None,
    )


def breakeven_revenue(p):
    """أدنى نسبة من الإيراد المتوقع تعطي NPV = 0."""
    lo, hi = 0.0, 5.0
    if run_feasibility(p, rev_mult=hi)["npv"] < 0:
        return None
    for _ in range(40):
        mid = (lo + hi) / 2
        if run_feasibility(p, rev_mult=mid)["npv"] < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def sensitivity_table(p):
    d = [-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3]
    return pd.DataFrame(
        {
            "الإيراد": [run_feasibility(p, rev_mult=1 + x)["npv"] for x in d],
            "المصروفات التشغيلية": [run_feasibility(p, exp_mult=1 + x)["npv"] for x in d],
            "الكلفة الرأسمالية": [run_feasibility(p, capex_mult=1 + x)["npv"] for x in d],
            "معدل الخصم": [run_feasibility(p, rate=p["rate"] * (1 + x))["npv"] for x in d],
        },
        index=[f"{x:+.0%}" for x in d],
    )


# --- محطات الصرف ---

G = 9.81
COMMERCIAL_DN = [100, 125, 150, 200, 250, 300, 350, 400, 450, 500, 600, 700, 800, 900, 1000, 1200, 1400, 1600]
MOTORS_KW = [1.5, 2.2, 3, 4, 5.5, 7.5, 11, 15, 18.5, 22, 30, 37, 45, 55, 75, 90, 110, 132, 160, 200, 250, 315, 355, 400, 450, 500]
WAVE_SPEED = {"HDPE": 250, "PVC": 350, "حديد مرن DI": 1100, "فولاذ": 1200}


def hazen(L, Q, C, D):
    """فقد احتكاك Hazen-Williams (م) لتدفق Q (م³/ث) وقطر D (م)."""
    if L <= 0 or Q <= 0:
        return 0.0
    return 10.67 * L * Q ** 1.852 / (C ** 1.852 * D ** 4.871)


def ww_compute(i):
    W = {}
    Pk = i["population"] / 1000
    q_avg = i["population"] * i["water_consumption"] * i["ret_frac"] * (1 + i["infil"]) / 1000   # م³/يوم
    pf_h, pf_b = 1 + 14 / (4 + math.sqrt(Pk)), 5 / Pk ** 0.2
    pf = {"يدوي (كما في الأصل)": i["peak_factor"], "Harmon": pf_h, "Babbitt": pf_b}[i["pf_method"]]
    q_avg_ls = q_avg / 86.4
    q_peak_ls = q_avg_ls * pf
    q_peak = q_peak_ls / 1000                                                                  # م³/ث
    qr = i["qmin_ratio"] if i["qmin_ratio"] > 0 else 0.2 * Pk ** (1 / 6)
    q_min = q_avg * qr                                                                         # م³/يوم
    bod_kg, tss_kg = i["population"] * i["bod_pc"] / 1000, i["population"] * i["tss_pc"] / 1000
    W.update(q_avg=q_avg, q_avg_ls=q_avg_ls, pf=pf, pf_h=pf_h, pf_b=pf_b, q_peak_ls=q_peak_ls, qr=qr, q_min=q_min,
             bod_kg=bod_kg, tss_kg=tss_kg, bod_mg=bod_kg / q_avg * 1000, tss_mg=tss_kg / q_avg * 1000)

    # --- خط الضخ
    D_calc = math.sqrt(4 * (q_peak / i["V_velocity"]) / math.pi) * 1000
    D_com = int(i["dn_override"]) if i["dn_override"] > 0 else next((d for d in COMMERCIAL_DN if d >= D_calc), None)
    n_duty, n_stby = max(int(i["n_duty"]), 1), int(i["n_standby"])
    W.update(D_calc=D_calc, D_com=D_com, n_duty=n_duty, n_stby=n_stby)
    if D_com is not None:
        D_m = D_com / 1000
        A = math.pi * D_m ** 2 / 4
        v = q_peak / A
        H_fr = hazen(i["L_length"], q_peak, i["C_hazen"], D_m)
        H_minor = 0.10 * H_fr if i["minor_method"].startswith("10") else i["K_sum"] * v ** 2 / (2 * G)
        TDH = i["H_static"] + H_fr + H_minor + i["h_res"]
        P_h = 1000 * G * q_peak * TDH / 1000
        P_shaft = P_h / i["eta_p"]
        P_each = P_shaft / n_duty
        P_req = P_each * i["sf"]
        motor = next((m for m in MOTORS_KW if m >= P_req), None)
        a = WAVE_SPEED[i["pipe_mat"]]
        dH = a * v / G
        qs = [q_peak * x / 20 for x in range(0, 26)]
        curve = {"Q (لتر/ث)": [q * 1000 for q in qs]}
        for c in sorted({100, 120, 140, i["C_hazen"]}):
            curve[f"C={c:g}"] = [i["H_static"] + i["h_res"] + hazen(i["L_length"], q, c, D_m) * (1.1 if i["minor_method"].startswith("10") else 1.0)
                                 + (0 if i["minor_method"].startswith("10") else i["K_sum"] * (q / A) ** 2 / (2 * G)) for q in qs]
        W.update(v=v, v_single=q_peak / n_duty / A, H_fr=H_fr, H_minor=H_minor, TDH=TDH, P_h=P_h, P_shaft=P_shaft,
                 P_each=P_each, P_req=P_req, motor=motor, BHP=P_shaft / 0.7457, curve=curve,
                 a=a, dH=dH, P_max=TDH + dH, TDH_c100=curve["C=100"][-6])
    else:
        W.update(v=None, v_single=None, H_fr=None, H_minor=None, TDH=None, P_h=None, P_shaft=None, P_each=None,
                 P_req=None, motor=None, BHP=None, curve=None, a=None, dH=None, P_max=None, TDH_c100=None)

    # --- بئر الرفع
    Qp_each = q_peak / n_duty
    V_cycle = Qp_each * 60 * i["t_cycle"] / 4
    V_orig = q_avg * i["retention_time"] / 1440
    V_max = q_min * i["retention_time"] / 1440
    A_ww = V_cycle / i["h_ss"]
    W.update(V_cycle=V_cycle, V_orig=V_orig, V_max=V_max, A_orig=V_orig / i["well_depth"], A_ww=A_ww,
             D_ww=math.sqrt(4 * A_ww / math.pi), ret_min_cycle=V_cycle / (q_min / 1440), ret_min_orig=V_orig / (q_min / 1440),
             starts=60 / i["t_cycle"] / (n_duty + n_stby))

    # --- الترسيب الابتدائي
    n_p = max(int(i["n_p"]), 1)
    V_p = q_avg * i["hrt_p"] / 24
    A_p = V_p / i["depth_p"]
    D1 = math.sqrt(4 * (A_p / n_p) / math.pi)
    sludge = tss_kg * i["tss_rem"] / 100
    S0 = W["bod_mg"] * (1 - i["bod_rem"] / 100)
    W.update(V_p=V_p, A_p=A_p, A_p1=A_p / n_p, D1=D1, sor=q_avg / A_p, sor_pk=q_avg * pf / A_p,
             weir=q_avg / n_p / (math.pi * D1), sludge=sludge, sludge_m3=sludge / 41.2, S0=S0)

    # --- الحمأة المنشطة (طريقة SRT) والترسيب الثانوي
    dS = S0 - i["s_eff"]
    W["bio"] = None
    if dS > 0:
        th, X = i["theta_c"], i["mlss"] * i["vss_ratio"]
        V_a = i["Y"] * q_avg * th * dS / (X * (1 + i["kd"] * th))
        Px = i["Y"] / (1 + i["kd"] * th) * q_avg * dS / 1000
        Xr = i["xr_f"] * 1e6 / i["svi"]
        R = i["mlss"] / (Xr - i["mlss"]) if Xr > i["mlss"] else float("nan")
        q_ras, q_was = R * q_avg, V_a * i["mlss"] / (th * Xr)
        O2 = q_avg * dS / 1000 / i["bod_bodu"] - 1.42 * Px
        n_s = max(int(i["n_s"]), 1)
        crit = {
            "SOR عند Q_avg": q_avg / i["sor_s"],
            "SOR عند Q_peak (≤40)": q_avg * pf / 40,
            "تحميل الجوامد عند Q_avg (≤4)": (q_avg + q_ras) * i["mlss"] / 1000 / 24 / 4,
            "تحميل الجوامد عند Q_peak (≤8)": (q_avg * pf + q_ras) * i["mlss"] / 1000 / 24 / 8,
        }
        gov = max(crit, key=crit.get)
        W["bio"] = dict(V_a=V_a, hrt=V_a / q_avg * 24, fm=q_avg * S0 / (V_a * i["mlss"]), vl=q_avg * S0 / 1000 / V_a,
                        Xr=Xr, R=R, q_ras=q_ras, q_was=q_was, Px=Px, O2=O2, A_sec=crit[gov], gov=gov,
                        D_sec=math.sqrt(4 * crit[gov] / n_s / math.pi))
    W["q_ras_orig"], W["q_was_orig"] = q_avg * i["ras_pct"], q_avg * i["was_pct"]

    # --- الفحوص
    C = [chk("معامل الذروة", pf, 1.5, 4.5)]
    if W["v"] is not None:
        C += [chk("سرعة خط الضخ", W["v"], 0.6, 2.5, "م/ث")]
        if n_duty > 1:
            C += [chk("السرعة بمضخة واحدة", W["v_single"], 0.6, None, "م/ث")]
    C += [chk("استبقاء بئر الرفع عند Q_min (حجم زمن الدورة)", W["ret_min_cycle"], None, i["retention_time"], "دقيقة"),
          chk("بدايات/ساعة/مضخة", W["starts"], None, 6),
          chk("SOR الابتدائي عند Q_avg", W["sor"], 30, 50, "م/يوم"),
          chk("SOR الابتدائي عند Q_peak", W["sor_pk"], None, 120, "م/يوم"),
          chk("زمن استبقاء الابتدائي", i["hrt_p"], 1.5, 2.5, "ساعة"),
          chk("حمل الهدّار الابتدائي", W["weir"], 125, 500, "م³/م·يوم")]
    if W["bio"]:
        b = W["bio"]
        C += [chk("F/M", b["fm"], 0.2, 0.6, "1/يوم"), chk("HRT حوض التهوية", b["hrt"], 4, 8.5, "ساعة"),
              chk("الحمل الحجمي", b["vl"], 0.3, 1.0, "كغم BOD/م³·يوم"), chk("نسبة الإرجاع R", b["R"], 0.25, 1.0)]
    W["checks"] = C
    return W


# =====================================================
# 5.6 مكونات الواجهة (الشريط الرئيسي والصفحة الرئيسية)
# =====================================================

def hero(title, subtitle, chips=()):
    """شريط عنوان جذاب أعلى كل قسم (تنسيقه في style.css)."""
    chips_html = "".join(f"<span class='chip'>{c}</span>" for c in chips)
    st.markdown(
        f"<div class='hero'><h1>{title}</h1><p>{subtitle}</p>{chips_html}</div>",
        unsafe_allow_html=True
    )


def go_to(section):
    st.session_state["main_section"] = section


def render_home():
    hero(
        "منصة إنشاءات للاستشارات الهندسية",
        "حسابات هندسية ومالية أولية بخطوات واضحة ونتائج قابلة للمراجعة والتنزيل",
        ["📈 دراسة الجدوى", "🚰 محطات الرفع والمعالجة", "✅ فحوص تصميمية", "⬇️ تنزيل النتائج"]
    )

    c1, c2 = st.columns(2)

    with c1:
        st.markdown(
            "<div class='feature-card'><h3>📈 دراسة الجدوى الاقتصادية</h3><ul>"
            "<li>NPV وIRR وMIRR ومؤشر الربحية PI وBCR</li>"
            "<li>فترة الاسترداد البسيطة والمخصومة</li>"
            "<li>حساسية وTornado وحد التعادل للإيراد</li>"
            "<li>ضريبة وتصاعد سنوي وتمويل بقرض وDSCR</li>"
            "</ul></div>",
            unsafe_allow_html=True
        )
        st.button(
            "ابدأ دراسة الجدوى ←", key="go_feas", use_container_width=True,
            on_click=go_to, args=("دراسة الجدوى الاقتصادية",)
        )

    with c2:
        st.markdown(
            "<div class='feature-card teal'><h3>🚰 تصميم محطة رفع ومعالجة مياه صرف</h3><ul>"
            "<li>التدفق الذروي وقطر الخط وTDH وقدرة المحرك</li>"
            "<li>بئر الرفع بزمن الدورة وعدد البدايات</li>"
            "<li>ترسيب ابتدائي وحمأة منشّطة وRAS/WAS</li>"
            "<li>جدول فحوص ✅/⚠️ وتقدير الصدمة المائية</li>"
            "</ul></div>",
            unsafe_allow_html=True
        )
        st.button(
            "ابدأ تصميم المحطة ←", key="go_ww", use_container_width=True,
            on_click=go_to, args=("تصميم محطة رفع ومعالجة مياه صرف",)
        )

    st.markdown(
        "<div class='steps'>"
        "<div class='step'><b>1</b>اختر القسم</div>"
        "<div class='step'><b>2</b>أدخل بيانات المشروع</div>"
        "<div class='step'><b>3</b>اضغط زر الحساب</div>"
        "<div class='step'><b>4</b>اقرأ المؤشرات ونزّل النتائج</div>"
        "</div>"
        "<div class='home-note'>تصميم المهندس الاستشاري عبد الغفور رمضان اللهيبي — "
        "النتائج حسابات أولية تُراجَع قبل التنفيذ</div>",
        unsafe_allow_html=True
    )


# =====================================================
# 6. القائمة الجانبية
# =====================================================

with st.sidebar:

    st.title("🏛️ منصة إنشاءات للاستشارات الهندسية")

    st.markdown("---")

    choice = st.radio(
    "اختر القسم المطلوب:",
    [
        "🏠 الرئيسية",
        "دراسة الجدوى الاقتصادية",
        "تصميم محطة رفع ومعالجة مياه صرف"
    ],
    key="main_section"
)
    st.markdown("---")

    st.info(
        "تصميم المهندس الاستشاري "
        "عبد الغفور رمضان اللهيبي"
    )


# =====================================================
# 7. قسم دراسة الجدوى الاقتصادية
# =====================================================

if choice == "🏠 الرئيسية":

    render_home()

elif choice == "دراسة الجدوى الاقتصادية":

    hero(
        "📈 دراسة الجدوى والتدفقات النقدية",
        "مؤشرات مالية وتحليل حساسية وتمويل لمشروعك",
        ["NPV", "IRR", "الاسترداد المخصوم", "الحساسية", "DSCR"]
    )

    st.info(
        "أدخل بيانات المشروع للحصول على "
        "المؤشرات المالية الأساسية."
    )

    with st.form("advanced_feasibility_form"):

        col1, col2 = st.columns(2)

        # ---------------------------------------------
        # التكاليف الرأسمالية
        # ---------------------------------------------

        with col1:

            st.subheader("🏗️ التكاليف الرأسمالية")

            land_cost = st.number_input(
                "قيمة الأرض (د.ع)",
                min_value=0.0,
                value=0.0,
                step=1000000.0
            )

            total_construction = st.number_input(
                "كلفة إنشاء المشروع (د.ع)",
                min_value=35000000.0,
                value=35000000.0,
                step=1000000.0
            )

            annual_rent_amount = st.number_input(
                "مبلغ الإيجار السنوي للأرض إن وجد (د.ع)",
                min_value=0.0,
                value=0.0,
                step=2500000.0
            )

            other_initial_costs = st.number_input(
                "تكاليف التأسيس والتراخيص (د.ع)",
                min_value=0.0,
                value=0.0,
                step=1500000.0
            )

            st.markdown("---")

            st.subheader("📊 المؤشرات المالية المطلوبة")

            discount_rate = st.number_input(
                "معدل الخصم السنوي (%)",
                min_value=0.0,
                max_value=100.0,
                value=10.0,
                step=0.5
            ) / 100

        # ---------------------------------------------
        # الإيرادات والمصروفات
        # ---------------------------------------------

        with col2:

            st.subheader("⚙️ الإيرادات والمصروفات التشغيلية")

            project_years = st.number_input(
                "عمر المشروع الافتراضي (سنوات)",
                min_value=1,
                value=30,
                step=1
            )

            annual_expenses = st.number_input(
                "المصروفات السنوية التشغيلية (صيانة، ضرائب...)",
                min_value=10000000.0,
                value=10000000.0,
                step=500000.0
            )

            annual_revenue_est = st.number_input(
                "الإيراد السنوي المتوقع (د.ع)",
                min_value=20000000.0,
                value=20000000.0,
                step=500000.0
            )

            salvage_value = st.number_input(
                "القيمة الدفترية المتوقعة في نهاية المشروع (د.ع)",
                min_value=0.0,
                value=0.0,
                step=1000000.0
            )

        # ---------------------------------------------
        # خيارات هندسية متقدمة (اختيارية)
        # القيم الافتراضية محايدة وتعيد النموذج المبسط الأصلي.
        # ---------------------------------------------

        with st.expander("⚙️ خيارات هندسية متقدمة (اختيارية)"):

            a1, a2, a3 = st.columns(3)

            with a1:

                st.markdown("**الجدول الزمني والتشغيل**")

                construction_years = st.number_input(
                    "مدة الإنشاء (سنوات)",
                    min_value=1, max_value=10, value=1, step=1
                )

                first_ratio = st.number_input(
                    "نسبة الإيراد في أول سنة تشغيل (%)",
                    min_value=10.0, max_value=100.0, value=100.0, step=5.0
                ) / 100

                ramp_years = st.number_input(
                    "سنوات الوصول للطاقة الكاملة",
                    min_value=1, max_value=15, value=1, step=1
                )

                g_rev = st.number_input(
                    "تصاعد الإيراد سنوياً (%)",
                    min_value=0.0, max_value=30.0, value=0.0, step=0.5
                ) / 100

                g_exp = st.number_input(
                    "تصاعد المصروفات سنوياً (%)",
                    min_value=0.0, max_value=30.0, value=0.0, step=0.5
                ) / 100

                g_rent = st.number_input(
                    "تصاعد الإيجار سنوياً (%)",
                    min_value=0.0, max_value=30.0, value=0.0, step=0.5
                ) / 100

            with a2:

                st.markdown("**الضريبة والاندثار ورأس المال العامل**")

                tax_pct = st.number_input(
                    "ضريبة الدخل (%)",
                    min_value=0.0, max_value=50.0, value=0.0, step=1.0
                ) / 100

                holiday = st.number_input(
                    "إعفاء ضريبي (سنوات من بدء التشغيل)",
                    min_value=0, max_value=30, value=0, step=1
                )

                dep_years = st.number_input(
                    "عمر اندثار الإنشاءات (سنة)",
                    min_value=1, max_value=60, value=30, step=1
                )

                wc_pct = st.number_input(
                    "رأس المال العامل (% من الإيراد)",
                    min_value=0.0, max_value=50.0, value=0.0, step=1.0
                ) / 100

                repl_year = st.number_input(
                    "سنة التشغيل لإحلال كبير (0 = لا يوجد)",
                    min_value=0, max_value=80, value=0, step=1
                )

                repl_cost = st.number_input(
                    "كلفة الإحلال الكبير (د.ع)",
                    min_value=0.0, value=0.0, step=1000000.0
                )

            with a3:

                st.markdown("**الأرض والتمويل**")

                land_residual = st.checkbox(
                    "استرداد قيمة الأرض في نهاية المشروع",
                    value=False
                )

                land_g = st.number_input(
                    "نمو قيمة الأرض سنوياً (%)",
                    min_value=0.0, max_value=30.0, value=0.0, step=0.5
                ) / 100

                debt_pct = st.number_input(
                    "نسبة القرض من الكلفة الرأسمالية (%)",
                    min_value=0.0, max_value=90.0, value=0.0, step=5.0
                ) / 100

                int_rate = st.number_input(
                    "فائدة القرض (%)",
                    min_value=0.0, max_value=40.0, value=8.0, step=0.5
                ) / 100

                grace = st.number_input(
                    "فترة سماح بعد التشغيل (سنة)",
                    min_value=0, max_value=15, value=1, step=1
                )

                repay_years = st.number_input(
                    "سنوات السداد",
                    min_value=1, max_value=30, value=8, step=1
                )

                ke = st.number_input(
                    "كلفة حقوق الملكية (%)",
                    min_value=0.0, max_value=80.0, value=18.0, step=0.5
                ) / 100

        calculate_btn = st.form_submit_button(
            "تحليل التدفق النقدي والجدوى الاقتصادية"
        )

    # ---------------------------------------------
    # الحسابات المالية (تُحفظ في الجلسة حتى لا تختفي عند التنزيل)
    # ---------------------------------------------

    if calculate_btn:

        # الإيجار السنوي لا يضاف إلى الاستثمار الأولي.
        # يعامل كمصروف تشغيلي سنوي.

        p = dict(
            land=land_cost, construction=total_construction, other=other_initial_costs,
            rent=annual_rent_amount, rate=discount_rate, No=int(project_years),
            expenses=annual_expenses, revenue=annual_revenue_est, salvage=salvage_value,
            Nc=int(construction_years), first_ratio=first_ratio, ramp_years=int(ramp_years),
            g_rev=g_rev, g_exp=g_exp, g_rent=g_rent, tax=tax_pct, holiday=int(holiday),
            dep_years=int(dep_years), wc=wc_pct, repl_year=int(repl_year), repl_cost=repl_cost,
            land_residual=land_residual, land_g=land_g, debt_pct=debt_pct, int_rate=int_rate,
            grace=int(grace), repay_years=int(repay_years), ke=ke
        )

        st.session_state["feas"] = dict(
            p=p,
            res=run_feasibility(p),
            be=breakeven_revenue(p),
            sens=sensitivity_table(p)
        )

    # ---------------------------------------------
    # عرض النتائج
    # ---------------------------------------------

    if "feas" in st.session_state:

        F = st.session_state["feas"]
        p, R = F["p"], F["res"]
        Nc = R["Nc"]

        st.divider()

        st.subheader(
            "📊 النتائج المالية للمؤشرات الحيوية"
        )

        m1, m2, m3, m4 = st.columns(4)

        m1.metric(
            "إجمالي رأس المال المستثمر",
            f"{R['invest']:,.0f} د.ع"
        )

        m2.metric(
            "صافي التدفق التشغيلي (أول سنة تشغيل)",
            f"{R['ebitda'][Nc]:,.0f} د.ع"
        )

        m3.metric(
            "فترة الاسترداد المبسطة",
            fmt(R["payback"], 2, "سنة") if R["payback"] is not None else "لا تُسترد"
        )

        m4.metric(
            "فترة الاسترداد المخصومة",
            fmt(R["dpayback"], 2, "سنة") if R["dpayback"] is not None else "لا تُسترد"
        )

        k1, k2, k3, k4 = st.columns(4)

        k1.metric("صافي القيمة الحالية NPV", f"{R['npv']:,.0f} د.ع")
        k2.metric("معدل العائد الداخلي IRR", fmt(R["irr"] * 100 if R["irr"] is not None else None, 2, "%"))
        k3.metric("معدل العائد الداخلي المعدّل MIRR", fmt(R["mirr"] * 100 if R["mirr"] is not None else None, 2, "%"))
        k4.metric("مؤشر الربحية PI", fmt(R["pi"], 2))

        k5, k6, k7, k8 = st.columns(4)

        k5.metric("نسبة المنافع/الكلف BCR", fmt(R["bcr"], 2))
        k6.metric("العائد المحاسبي على الاستثمار ROI", fmt(R["roi"] * 100 if R["roi"] is not None else None, 2, "%"))
        k7.metric(
            "الحد الأدنى للإيراد (NPV = 0)",
            fmt(F["be"] * 100 if F["be"] is not None else None, 1, "% من المتوقع")
        )
        if p["debt_pct"] > 0:
            k8.metric("DSCR الأدنى", fmt(R["dscr_min"], 2))

        st.divider()

        st.subheader(
            "🔍 تقييم الجدوى الاستثمارية للمشروع"
        )

        c1, c2 = st.columns(2)

        with c1:

            if R["npv"] > 0:

                st.success(
                    f"صافي القيمة الحالية (NPV): "
                    f"{R['npv']:,.0f} د.ع\n\n"
                    "🟢 المشروع مجدٍ وفق الافتراضات المدخلة."
                )

            elif R["npv"] < 0:

                st.error(
                    f"صافي القيمة الحالية (NPV): "
                    f"{R['npv']:,.0f} د.ع\n\n"
                    "🔴 المشروع غير مجدٍ عند معدل الخصم الحالي."
                )

            else:

                st.warning(
                    f"صافي القيمة الحالية (NPV): "
                    f"{R['npv']:,.0f} د.ع\n\n"
                    "المشروع عند نقطة التعادل الحالية."
                )

        with c2:

            if R["irr"] is not None:

                st.info(
                    f"معدل العائد الداخلي (IRR): "
                    f"{R['irr'] * 100:.2f}%"
                )

            else:

                st.warning(
                    "تعذر تحديد معدل العائد الداخلي "
                    "بصورة موثوقة للتدفقات المدخلة."
                )

        criteria = {
            "NPV > 0": R["npv"] > 0,
            "IRR أكبر من معدل الخصم": R["irr"] is not None and R["irr"] > p["rate"],
            "مؤشر الربحية PI > 1": R["pi"] is not None and R["pi"] > 1,
            "BCR > 1": R["bcr"] is not None and R["bcr"] > 1,
            "الاسترداد المخصوم ≤ عمر المشروع": R["dpayback"] is not None and R["dpayback"] <= p["No"],
        }

        if p["debt_pct"] > 0:
            criteria["DSCR الأدنى ≥ 1.25"] = R["dscr_min"] is not None and R["dscr_min"] >= 1.25

        st.dataframe(
            pd.DataFrame({
                "المعيار": list(criteria.keys()),
                "النتيجة": ["✅" if v else "❌" for v in criteria.values()]
            }),
            hide_index=True
        )

        # ---------------------------------------------
        # جدول التدفقات والتحليلات
        # ---------------------------------------------

        tab_names = ["📋 التدفقات النقدية", "📈 التراكمي", "🎯 الحساسية والتعادل"]

        if p["debt_pct"] > 0:
            tab_names.append("🏦 التمويل")

        tabs = st.tabs(tab_names)

        with tabs[0]:

            st.subheader("📋 جدول التدفقات النقدية السنوية")

            cash_flow_df = pd.DataFrame({
                "السنة": range(R["T"]),
                "الإيراد": R["rev"],
                "المصروفات التشغيلية": [R["opx"][t] + R["rent"][t] for t in range(R["T"])],
                "EBITDA": R["ebitda"],
                "الاندثار": R["dep"],
                "الضريبة": R["tax"],
                "الكلفة الرأسمالية": R["cap"],
                "إحلال": R["repl"],
                "تغير رأس المال العامل": R["dwc"],
                "قيمة نهائية": R["term"],
                "التدفق النقدي (د.ع)": R["fcff"],
                "التراكمي": R["cum"],
                "التراكمي المخصوم": R["dcum"],
            })

            st.dataframe(
                cash_flow_df.style.format(
                    "{:,.0f}",
                    subset=[c for c in cash_flow_df.columns if c != "السنة"]
                ),
                use_container_width=True,
                hide_index=True
            )

            st.download_button(
                "تنزيل جدول التدفقات CSV",
                cash_flow_df.to_csv(index=False).encode("utf-8-sig"),
                "cash_flow.csv",
                "text/csv"
            )

        with tabs[1]:

            st.line_chart(
                pd.DataFrame(
                    {"التراكمي": R["cum"], "التراكمي المخصوم": R["dcum"]},
                    index=range(R["T"])
                )
            )

            st.caption(
                "نقطة عبور الخط للصفر هي فترة الاسترداد؛ "
                "الخط المخصوم يتأخر عن البسيط بمقدار أثر معدل الخصم."
            )

        with tabs[2]:

            sens = F["sens"]

            st.subheader("أثر تغير المتغيرات على NPV (د.ع)")

            st.dataframe(sens.style.format("{:,.0f}"), use_container_width=True)

            st.line_chart(sens)

            tornado = pd.DataFrame({
                "NPV عند -20%": sens.loc["-20%"],
                "NPV عند +20%": sens.loc["+20%"],
            })
            tornado["التأرجح"] = (tornado.iloc[:, 0] - tornado.iloc[:, 1]).abs()

            st.subheader("ترتيب المتغيرات حسب خطورتها (±20%)")

            st.dataframe(
                tornado.sort_values("التأرجح", ascending=False).style.format("{:,.0f}"),
                use_container_width=True
            )

            if F["be"] is not None:
                st.info(
                    f"يتحقق التعادل (NPV = 0) عند {F['be'] * 100:.1f}% من الإيراد المتوقع؛ "
                    f"أي أن هامش الأمان في الإيراد = {(1 - F['be']) * 100:.1f}%."
                )
            else:
                st.warning("لا يتحقق NPV موجب حتى عند خمسة أضعاف الإيراد المتوقع.")

        if p["debt_pct"] > 0:

            with tabs[3]:

                debt_df = pd.DataFrame({
                    "السنة": range(R["T"]),
                    "قرض مسحوب": R["draw"],
                    "فائدة": R["interest"],
                    "أصل القرض": R["princ"],
                    "FCFE": R["fcfe"],
                    "DSCR": R["dscr"],
                })

                st.dataframe(
                    debt_df.style.format(
                        "{:,.0f}", subset=["قرض مسحوب", "فائدة", "أصل القرض", "FCFE"]
                    ).format("{:.2f}", subset=["DSCR"], na_rep="—"),
                    use_container_width=True,
                    hide_index=True
                )

                d1, d2, d3 = st.columns(3)
                d1.metric("IRR لحقوق الملكية", fmt(R["irr_e"] * 100 if R["irr_e"] is not None else None, 2, "%"))
                d2.metric("NPV لحقوق الملكية", f"{R['npv_e']:,.0f} د.ع")
                d3.metric("DSCR المتوسط", fmt(R["dscr_avg"], 2))

        st.caption(
            "ملاحظة: القيم الافتراضية للخيارات المتقدمة محايدة (بلا تضخم أو ضرائب أو تمويل)، "
            "فتعيد النموذج المبسط. الفائدة أثناء الإنشاء تُدفع نقداً من حقوق الملكية، "
            "والإحلال يُعامل مصروفاً قابلاً للخصم الضريبي في سنته. "
            "تحقق من نسبة الضريبة ومدة الإعفاء الممنوحة بموجب إجازة الاستثمار."
        )


# =====================================================
# 8. قسم تصميم محطة رفع ومعالجة مياه الصرف
# =====================================================

elif choice == "تصميم محطة رفع ومعالجة مياه صرف":

    hero(
        "🚰 تصميم محطات الرفع ومعالجة مياه الصرف الصحي",
        "سعات هيدروليكية وأبعاد أحواض وفحوص تصميمية أولية",
        ["الرفع وخط الضخ", "بئر الرفع", "الترسيب", "الحمأة المنشّطة"]
    )

    st.info(
        "قم بإدخال البيانات التصميمية الأساسية "
        "لحساب السعات الهيدروليكية وأبعاد أحواض المحطة."
    )

    with st.form("wwtp_design_form"):

        col_ww1, col_ww2 = st.columns(2)

        # ---------------------------------------------
        # بيانات السكان والتدفق
        # ---------------------------------------------

        with col_ww1:

            st.subheader("👥 بيانات التدفق والسكان")

            population = st.number_input(
                "عدد السكان المستهدف (نسمة)",
                min_value=100,
                value=20000,
                step=100
            )

            water_consumption = st.number_input(
                "معدل استهلاك المياه الفردي (لتر/فرد/يوم)",
                min_value=50,
                value=200,
                step=10
            )

            peak_factor = st.number_input(
                "معامل الذروة (Peak Factor)",
                min_value=1.0,
                value=2.44,
                step=0.01
            )

            V_velocity = st.number_input(
                "السرعة التصميمية في أنبوب الضخ (م/ث)",
                min_value=0.1,
                value=1.2,
                step=0.1
            )

        # ---------------------------------------------
        # محددات الأحواض وخط الضخ
        # ---------------------------------------------

        with col_ww2:

            st.subheader(
                "📐 محددات تصميم حوض الرفع والأحواض"
            )

            retention_time = st.number_input(
                "زمن الاستبقاء الحرج (دقيقة)",
                min_value=5,
                value=30,
                step=5
            )

            well_depth = st.number_input(
                "العمق الفعال المقترح للحوض (متر)",
                min_value=1.0,
                value=5.0,
                step=0.5
            )

            H_static = st.number_input(
                "المنسوب الرأسي الساكن H_static (متر)",
                min_value=0.0,
                value=10.0,
                step=0.5
            )

            L_length = st.number_input(
                "طول خط الضخ L (متر)",
                min_value=0.0,
                value=1500.0,
                step=50.0
            )

        # ---------------------------------------------
        # خيارات هندسية متقدمة (اختيارية)
        # الافتراضات تعيد القيم الأصلية.
        # ---------------------------------------------

        with st.expander("⚙️ خيارات هندسية متقدمة (اختيارية)"):

            g1, g2, g3, g4 = st.columns(4)

            with g1:

                st.markdown("**التدفق والأحمال**")

                pf_method = st.selectbox(
                    "طريقة معامل الذروة",
                    ["يدوي (كما في الأصل)", "Harmon", "Babbitt"]
                )

                ret_frac = st.number_input(
                    "نسبة تحويل الاستهلاك إلى صرف",
                    min_value=0.3, max_value=1.0, value=0.80, step=0.05
                )

                infil = st.number_input(
                    "تسرب/دخيل (% من Q_avg)",
                    min_value=0.0, max_value=100.0, value=0.0, step=5.0
                ) / 100

                qmin_ratio = st.number_input(
                    "Q_min/Q_avg (0 = بالمعادلة)",
                    min_value=0.0, max_value=1.0, value=0.0, step=0.05
                )

                bod_pc = st.number_input(
                    "BOD5 (غم/فرد/يوم)",
                    min_value=20.0, value=60.0, step=5.0
                )

                tss_pc = st.number_input(
                    "TSS (غم/فرد/يوم)",
                    min_value=20.0, value=70.0, step=5.0
                )

            with g2:

                st.markdown("**خط الضخ والمضخات**")

                C_hazen = st.number_input(
                    "معامل Hazen-Williams (C)",
                    min_value=60.0, value=140.0, step=5.0
                )

                minor_method = st.selectbox(
                    "الفواقد الثانوية",
                    ["10% من فاقد الاحتكاك (كما في الأصل)", "ΣK للقطع الفعلية"]
                )

                K_sum = st.number_input(
                    "ΣK (إن اخترت طريقة K)",
                    min_value=0.0, value=4.6, step=0.5
                )

                h_res = st.number_input(
                    "ضاغط متبقٍ عند التفريغ (م)",
                    min_value=0.0, value=0.0, step=0.5
                )

                dn_override = st.number_input(
                    "DN مفروض بالملم (0 = تلقائي)",
                    min_value=0.0, value=0.0, step=50.0
                )

                n_duty = st.number_input(
                    "عدد المضخات العاملة",
                    min_value=1, value=1, step=1
                )

                n_standby = st.number_input(
                    "عدد المضخات الاحتياطية",
                    min_value=0, value=1, step=1
                )

                eta_p = st.number_input(
                    "كفاءة المضخة",
                    min_value=0.3, max_value=0.95, value=0.70, step=0.05
                )

                sf = st.number_input(
                    "معامل خدمة المحرك",
                    min_value=1.0, value=1.15, step=0.05
                )

                pipe_mat = st.selectbox(
                    "مادة الأنبوب (للصدمة المائية)",
                    list(WAVE_SPEED)
                )

            with g3:

                st.markdown("**بئر الرفع والترسيب الابتدائي**")

                t_cycle = st.number_input(
                    "أدنى زمن دورة تشغيل (دقيقة)",
                    min_value=2.0, value=10.0, step=1.0
                )

                h_ss = st.number_input(
                    "فرق منسوبي التشغيل والإيقاف (م)",
                    min_value=0.3, value=1.2, step=0.1
                )

                hrt_p = st.number_input(
                    "زمن استبقاء الترسيب الابتدائي (ساعة)",
                    min_value=0.5, value=2.0, step=0.25
                )

                depth_p = st.number_input(
                    "عمق الترسيب الابتدائي (م)",
                    min_value=1.5, value=3.0, step=0.5
                )

                n_p = st.number_input(
                    "عدد أحواض الترسيب الابتدائي",
                    min_value=1, value=2, step=1
                )

                bod_rem = st.number_input(
                    "إزالة BOD ابتدائياً (%)",
                    min_value=0.0, max_value=90.0, value=30.0, step=5.0
                )

                tss_rem = st.number_input(
                    "إزالة TSS ابتدائياً (%)",
                    min_value=0.0, max_value=95.0, value=60.0, step=5.0
                )

            with g4:

                st.markdown("**الحمأة المنشّطة والثانوي**")

                theta_c = st.number_input("عمر الحمأة SRT (يوم)", min_value=2.0, value=8.0, step=1.0)
                Y_yield = st.number_input("معامل الإنتاج Y", min_value=0.2, value=0.6, step=0.05)
                kd = st.number_input("معامل التحلل kd (1/يوم)", min_value=0.01, value=0.06, step=0.01)
                mlss = st.number_input("MLSS (ملغم/لتر)", min_value=1000.0, value=3000.0, step=250.0)
                vss_ratio = st.number_input("نسبة VSS/MLSS", min_value=0.5, max_value=1.0, value=0.75, step=0.05)
                svi = st.number_input("SVI (مل/غم)", min_value=50.0, value=120.0, step=10.0)
                xr_f = st.number_input("Xr كنسبة من 10⁶/SVI", min_value=0.5, max_value=1.0, value=0.8, step=0.05)
                s_eff = st.number_input("BOD5 الذائب بالمخرج (ملغم/لتر)", min_value=1.0, value=20.0, step=1.0)
                bod_bodu = st.number_input("نسبة BOD5/BODu", min_value=0.5, max_value=0.9, value=0.68, step=0.01)
                sor_s = st.number_input("SOR للثانوي عند Q_avg (م/يوم)", min_value=5.0, value=20.0, step=1.0)
                n_s = st.number_input("عدد أحواض الثانوي", min_value=1, value=2, step=1)
                ras_pct = st.number_input("RAS الأولي (% من Q_avg، الأصل)", min_value=0.0, value=6.0, step=1.0) / 100
                was_pct = st.number_input("WAS الأولي (% من Q_avg، الأصل)", min_value=0.0, value=1.5, step=0.5) / 100

        submit_wwtp = st.form_submit_button(
            "📐 إجراء الحسابات الهيدروليكية والتصميمية"
        )

    # =================================================
    # 9. الحسابات الهيدروليكية (تُحفظ في الجلسة)
    # =================================================

    if submit_wwtp:

        try:

            st.session_state["ww"] = ww_compute(dict(
                population=population, water_consumption=water_consumption, peak_factor=peak_factor,
                V_velocity=V_velocity, retention_time=retention_time, well_depth=well_depth,
                H_static=H_static, L_length=L_length, pf_method=pf_method, ret_frac=ret_frac,
                infil=infil, qmin_ratio=qmin_ratio, bod_pc=bod_pc, tss_pc=tss_pc, C_hazen=C_hazen,
                minor_method=minor_method, K_sum=K_sum, h_res=h_res, dn_override=dn_override,
                n_duty=n_duty, n_standby=n_standby, eta_p=eta_p, sf=sf, pipe_mat=pipe_mat,
                t_cycle=t_cycle, h_ss=h_ss, hrt_p=hrt_p, depth_p=depth_p, n_p=n_p, bod_rem=bod_rem,
                tss_rem=tss_rem, theta_c=theta_c, Y=Y_yield, kd=kd, mlss=mlss, vss_ratio=vss_ratio,
                svi=svi, xr_f=xr_f, s_eff=s_eff, bod_bodu=bod_bodu, sor_s=sor_s, n_s=n_s,
                ras_pct=ras_pct, was_pct=was_pct
            ))

        except Exception as e:

            st.session_state.pop("ww", None)

            st.error(
                f"حدث خطأ أثناء إجراء الحسابات: {str(e)}"
            )

    # =================================================
    # 10. عرض النتائج
    # =================================================

    if "ww" in st.session_state:

        W = st.session_state["ww"]
        b = W["bio"]

        st.success(
            "🟢 تم تنفيذ الحسابات الأولية بنجاح."
        )

        st.divider()

        st.subheader(
            "📊 الحسابات التلقائية لمحطة الرفع وخط الضخ"
        )

        col_res1, col_res2, col_res3 = st.columns(3)

        with col_res1:

            st.metric(
                "التصريف اليومي المتوسط (Q_avg)",
                f"{W['q_avg']:,.2f} م³/يوم"
            )

            st.metric(
                "القطر الداخلي المحسوب (D_calc)",
                f"{W['D_calc']:.2f} ملم"
            )

        with col_res2:

            st.metric(
                "التصريف الذروي (Q_peak)",
                f"{W['q_peak_ls']:.3f} لتر/ثانية"
            )

            st.metric(
                "القطر التجاري الأولي",
                (
                    f"{W['D_com']:.0f} ملم"
                    if W["D_com"] is not None
                    else "غير متوفر"
                )
            )

        with col_res3:

            st.metric(
                "الضاغط الديناميكي الكلي (TDH)",
                (
                    f"{W['TDH']:.2f} متر"
                    if W["TDH"] is not None
                    else "غير محسوب"
                )
            )

            st.metric(
                "قدرة المضخة المطلوبة (BHP)",
                (
                    f"{W['BHP']:.2f} حصان"
                    if W["BHP"] is not None
                    else "غير محسوبة"
                )
            )

        t_pump, t_well, t_prim, t_bio, t_chk = st.tabs([
            "🔧 الرفع وخط الضخ", "🏗️ بئر الرفع", "🧱 الترسيب الابتدائي",
            "🌿 الحمأة المنشّطة والثانوي", "✅ الفحوص والملاحظات"
        ])

        # -----------------------------------------
        # الرفع وخط الضخ
        # -----------------------------------------

        with t_pump:

            h1, h2, h3 = st.columns(3)

            h1.metric("فاقد الاحتكاك", fmt(W["H_fr"], 2, "متر") if W["H_fr"] is not None else "غير محسوب")
            h2.metric("الفواقد الثانوية", fmt(W["H_minor"], 2, "متر") if W["H_minor"] is not None else "غير محسوبة")
            h3.metric("السرعة الفعلية بالأنبوب", fmt(W["v"], 2, "م/ث") if W["v"] is not None else "غير محسوبة")

            if W["TDH"] is not None:

                st.dataframe(
                    pd.DataFrame([
                        ("معامل الذروة المستخدم", fmt(W["pf"], 3), f"Harmon {W['pf_h']:.2f} | Babbitt {W['pf_b']:.2f}"),
                        ("القدرة الهيدروليكية", fmt(W["P_h"], 2, "kW"), ""),
                        ("قدرة العمود الكلية", fmt(W["P_shaft"], 2, "kW"), f"{W['n_duty']} عاملة + {W['n_stby']} احتياطية"),
                        ("قدرة العمود لكل مضخة", fmt(W["P_each"], 2, "kW"), ""),
                        ("قدرة المحرك المطلوبة (× معامل الخدمة)", fmt(W["P_req"], 2, "kW"), ""),
                        ("المحرك القياسي", f"{W['motor']} kW" if W["motor"] else "> 500 kW", ""),
                        ("TDH بأسوأ خشونة (C=100)", fmt(W["TDH_c100"], 2, "متر"), "لاختيار المضخة"),
                        ("سرعة الموجة a", fmt(W["a"], 0, "م/ث"), "حسب مادة الأنبوب"),
                        ("ارتفاع الصدمة (إغلاق لحظي)", fmt(W["dH"], 1, "متر"), "حد أعلى تقديري"),
                        ("الضغط الأقصى التقريبي (TDH + ΔH)", fmt(W["P_max"], 1, "متر"), f"≈ {W['P_max'] / 10.2:.1f} bar"),
                    ], columns=["المعلمة", "القيمة", "ملاحظة"]),
                    hide_index=True, use_container_width=True
                )

                st.line_chart(pd.DataFrame(W["curve"]).set_index("Q (لتر/ث)"))

                st.caption(
                    "منحنى النظام: يُطابَق مع منحنى المضخة المختارة لتحديد نقطة التشغيل؛ "
                    "غلاف C=100..140 يوضح عدم اليقين في الخشونة. "
                    "ارتفاع الصدمة حد أعلى للإغلاق اللحظي ولا يغني عن دراسة الصدمة المائية "
                    "لتحديد PN وصمامات الحماية."
                )

        # -----------------------------------------
        # بئر الرفع
        # -----------------------------------------

        with t_well:

            w1, w2, w3 = st.columns(3)

            w1.metric("حجم بئر الرفع (طريقة الأصل)", f"{W['V_orig']:.2f} م³")
            w2.metric("مساحة الحوض (طريقة الأصل)", f"{W['A_orig']:.2f} م²")
            w3.metric("العمق الفعال", f"{well_depth:.2f} متر")

            st.dataframe(
                pd.DataFrame([
                    ("حجم زمن الدورة V = Q·T/4", fmt(W["V_cycle"], 2, "م³"), "المعتمد هندسياً لعدد البدايات"),
                    ("مساحة الحوض (فرق التشغيل/الإيقاف)", fmt(W["A_ww"], 2, "م²"), ""),
                    ("القطر الدائري المكافئ", fmt(W["D_ww"], 2, "م"), ""),
                    ("أقصى حجم يحقق الاستبقاء عند Q_min", fmt(W["V_max"], 2, "م³"), "V = Q_min × زمن الاستبقاء"),
                    ("استبقاء حجم الأصل عند Q_min", fmt(W["ret_min_orig"], 1, "دقيقة"), "مقارنة بالحد الحرج"),
                    ("استبقاء حجم زمن الدورة عند Q_min", fmt(W["ret_min_cycle"], 1, "دقيقة"), ""),
                    ("بدايات/ساعة/مضخة (أسوأ حالة)", fmt(W["starts"], 2), "تعمل كل المضخات بالتناوب"),
                ], columns=["المعلمة", "القيمة", "ملاحظة"]),
                hide_index=True, use_container_width=True
            )

            if W["V_orig"] > W["V_max"]:
                st.warning(
                    f"حجم طريقة الأصل ({W['V_orig']:.1f} م³) يتجاوز أقصى حجم يحقق زمن الاستبقاء الحرج "
                    f"عند Q_min ({W['V_max']:.1f} م³)؛ خطر تعفن المياه في البئر. "
                    "العمق «الفعال» هنا يُفترض فرقاً بين منسوبي الإيقاف والتشغيل (عادة 0.6–2 م)، "
                    "أما العمق الكلي فيضاف إليه الغمر الأدنى والارتفاع الحر."
                )

        # -----------------------------------------
        # الترسيب الابتدائي
        # -----------------------------------------

        with t_prim:

            col_res4, col_res5 = st.columns(2)

            with col_res4:

                st.write(f"**الحجم الكلي للأحواض (V_primary):** {W['V_p']:.2f} م³")
                st.write(f"**المساحة السطحية الكلية:** {W['A_p']:.2f} م²")
                st.write(f"**مساحة الحوض الواحد:** {W['A_p1']:.2f} م²")
                st.write(f"**قطر الحوض الواحد:** {W['D1']:.2f} متر")
                st.write(f"**SOR عند Q_avg / Q_peak:** {W['sor']:.1f} / {W['sor_pk']:.1f} م/يوم")
                st.write(f"**حمل الهدّار:** {W['weir']:.1f} م³/م·يوم")

            with col_res5:

                st.write(f"**حمل BOD5 الداخل:** {W['bod_kg']:,.0f} كغم/يوم ({W['bod_mg']:.0f} ملغم/لتر)")
                st.write(f"**حمل TSS الداخل:** {W['tss_kg']:,.0f} كغم/يوم ({W['tss_mg']:.0f} ملغم/لتر)")
                st.write(f"**BOD5 بعد الترسيب:** {W['S0']:.0f} ملغم/لتر")
                st.write(f"**حمأة ابتدائية جافة:** {W['sludge']:,.0f} كغم/يوم ≈ {W['sludge_m3']:.1f} م³/يوم (4% جامدة)")

        # -----------------------------------------
        # الحمأة المنشطة والثانوي
        # -----------------------------------------

        with t_bio:

            st.subheader(
                "🔄 منظومة ضخ وتدوير الحمأة (Sludge Pumps)"
            )

            if b:

                st.dataframe(
                    pd.DataFrame([
                        ("RAS", fmt(W["q_ras_orig"] / 86.4, 3, "لتر/ث"), fmt(b["q_ras"] / 86.4, 3, "لتر/ث"), f"R = {b['R']:.2f}"),
                        ("WAS", fmt(W["q_was_orig"] / 86.4, 4, "لتر/ث"), fmt(b["q_was"] / 86.4, 4, "لتر/ث"), "V·MLSS/(SRT·Xr)"),
                    ], columns=["التدفق", "نسبة أولية (الأصل)", "حسب SRT وSVI", "أساس الحساب"]),
                    hide_index=True, use_container_width=True
                )

                st.dataframe(
                    pd.DataFrame([
                        ("حجم حوض التهوية", fmt(b["V_a"], 0, "م³")), ("HRT", fmt(b["hrt"], 1, "ساعة")),
                        ("F/M", fmt(b["fm"], 2, "1/يوم")), ("الحمل الحجمي", fmt(b["vl"], 2, "كغم BOD/م³·يوم")),
                        ("Xr", fmt(b["Xr"], 0, "ملغم/لتر")), ("إنتاج الكتلة الحيوية VSS", fmt(b["Px"], 0, "كغم/يوم")),
                        ("الأكسجين الكربوني المطلوب (دون نترجة)", fmt(b["O2"], 0, "كغم O₂/يوم")),
                        ("مساحة الترسيب الثانوي", fmt(b["A_sec"], 0, "م²")), ("المعيار الحاكم", b["gov"]),
                        ("قطر حوض الثانوي الواحد", fmt(b["D_sec"], 1, "م")),
                    ], columns=["المعلمة", "القيمة"]),
                    hide_index=True, use_container_width=True
                )

                st.caption(
                    "النسب الأولية (6% و1.5%) افتراضات بلا أساس؛ الحساب حسب SRT وSVI يربط الإرجاع "
                    "والفائض بتركيز المواد الصلبة وعمر الحمأة."
                )

            else:

                st.warning("BOD الداخل للهوائي أقل من أو يساوي BOD المخرج المطلوب؛ راجع المدخلات.")

        # -----------------------------------------
        # الفحوص والملاحظات
        # -----------------------------------------

        with t_chk:

            checks_df = pd.DataFrame(W["checks"])

            st.dataframe(checks_df, hide_index=True, use_container_width=True)

            st.metric("عدد التحذيرات", int((checks_df["الحالة"] == "⚠️").sum()))

            st.download_button(
                "تنزيل نتائج الفحص CSV",
                checks_df.to_csv(index=False).encode("utf-8-sig"),
                "wwtp_checks.csv",
                "text/csv"
            )

            st.warning("""
            النتائج أعلاه حسابات أولية وليست تصميماً تنفيذياً معتمداً.

            1. يجب التحقق من معامل الذروة وفق عدد السكان وطبيعة شبكة الصرف والمعيار المحلي.
            2. يجب اعتماد أقطار الأنابيب التجارية المتوفرة فعلاً (القطر الداخلي يختلف عن الاسمي).
            3. فاقد الاحتكاك بمعادلة Hazen-Williams؛ تحقق عند C الأدنى والأعلى (غلاف المنحنى).
            4. الفواقد الثانوية: استبدل نسبة 10% بـ ΣK الفعلي للقطع والصمامات.
            5. قدرة المضخة لا تغني عن اختيار منحنى المضخة ومراجعة نقطة التشغيل وNPSH.
            6. الصدمة المائية والضغط الأقصى يحتاجان دراسة انتقالية لتحديد PN ووسائل الحماية.
            7. أحواض الترسيب تحتاج مراجعة SOR وحمل الهدّار وزمن المكوث والحمل الصلب.
            8. RAS وWAS تُحدَّد من SRT وSVI وتركيز MLSS، لا من نسب ثابتة.
            9. الأكسجين المحسوب كربوني فقط؛ أضف النترجة ومعاملات α وβ وكفاءة النقل للتهوية.
            10. لا يشمل المصافي والحصى والتطهير ومعالجة الحمأة، ويجب التحقق من حدود التصريف المحلية.
            """)

