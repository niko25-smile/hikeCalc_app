from flask import Flask, render_template, request, redirect, url_for, session
from datetime import timedelta

app = Flask(__name__)
app.secret_key = "your_secret_key"
app.permanent_session_lifetime = timedelta(minutes=30)

# === 追加: 補正係数テーブル ===
AGE_FACTOR = {
    "male":   {"15-29": 1.00, "30-39": 0.96, "40-49": 0.94, "50-59": 0.92, "60-": 0.91},
    "female": {"15-29": 0.95, "30-39": 0.87, "40-49": 0.85, "50-59": 0.84, "60-": 0.84},
}
MUSCLE_FACTOR = {
    "male":   {"muscular": 1.06, "normal": 1.00, "cultural": 0.94},
    "female": {"muscular": 1.03, "normal": 1.00, "cultural": 0.97},
}


@app.route("/")
def index():
    return redirect(url_for("home_step1"))


@app.route("/user", methods=["GET", "POST"])
def user():
    if request.method == "POST":
        session.permanent = True
        # 基本情報を保存
        session["weight"] = float(request.form["weight"])
        session["gender"] = request.form.get("gender", "male")         # male / female
        session["age_group"] = request.form.get("age_group", "30-39")  # 15-29 / 30-39 / 40-49 / 50-59 / 60-
        session["muscle"] = request.form.get("muscle", "normal")       # muscular / normal / cultural
        return redirect(url_for("home_step1"))

    # GET のときは既存値を初期表示に使う
    ctx = {
        "css_file": "user.css",
        "weight": session.get("weight", ""),
        "gender": session.get("gender", "male"),
        "age_group": session.get("age_group", "30-39"),
        "muscle": session.get("muscle", "normal"),
    }
    return render_template("user.html", **ctx)


@app.route("/home/step1", methods=["GET", "POST"])
def home_step1():
    if request.method == "POST":
        if "weight" not in session:
            session["weight"] = 60.0

        session["days"] = int(request.form["days"])
        session["luggage_weight"] = float(request.form["luggage"])
        return redirect(url_for("home_step2"))

    if "weight" not in session:
        session["weight"] = 60.0

    return render_template("home_step1.html", css_file="home_step1.css")


@app.route("/home/step2", methods=["GET", "POST"])
def home_step2():
    days = session.get("days", 1)
    if request.method == "POST":
        course_details = []
        for i in range(1, days + 1):
            course_time = float(request.form[f"course_{i}"])
            meals = request.form.getlist(f"meals_{i}")
            hut = f"hut_{i}" in request.form
            water = f"water_{i}" in request.form
            course_details.append({
                "course_time": course_time,
                "meals": meals,
                "hut": hut,
                "water": water
            })
        session["course_details"] = course_details
        return redirect(url_for("home_step3"))

    return render_template("home_step2.html", days=days, css_file="home_step2.css")


@app.route("/home/step3")
def home_step3():
    weight = session.get("weight", 60.0)
    luggage = session.get("luggage_weight", 0.0)
    course_details = session.get("course_details", [])

    # 新式に必要な属性（未設定なら既定）
    gender = session.get("gender", "male")            # "male" / "female"
    age_group = session.get("age_group", "30-39")     # "15-29" / "30-39" / "40-49" / "50-59" / "60-"
    muscle = session.get("muscle", "normal")          # "muscular" / "normal" / "cultural"

    # Biglobe式: 体重 × 0.155 × 60分 × 時間 × 補正1 × 補正2
    BASE = 0.155 * 60.0  # = 9.3

    result = []
    total_meal_kcal = 0.0
    total_intake_needed = 0.0
    total_water_needed = 0.0
    total_dinner_to_prepare = 0

    breakfast_count = 0
    lunch_count = 0
    dinner_count = 0

    previous_day_water_source = False

    # 係数の取得（性別に紐づく）
    factor1 = AGE_FACTOR.get(gender, AGE_FACTOR["male"]).get(age_group, 1.0)
    factor2 = MUSCLE_FACTOR.get(gender, MUSCLE_FACTOR["male"]).get(muscle, 1.0)

    # effective_weight = weight
    effective_weight = weight + luggage

    for idx, day in enumerate(course_details, start=1):
        course_time = day["course_time"]
        meals = day["meals"]
        hut = day.get("hut", False)
        water_source = day.get("water", False)

        # === 消費カロリー（新式） ===
        consumed = effective_weight * BASE * course_time * factor1 * factor2

        # === 摂取目標（既存ロジックは踏襲） ===
        if idx == 1:
            intake_target = max(consumed * 0.8 - 400, 0)
        else:
            intake_target = max(consumed * 0.8, 0)

        # === 食事カロリー ===
        meal_kcal = 0
        if "breakfast" in meals:
            meal_kcal += 400
            breakfast_count += 1
        if "lunch" in meals:
            meal_kcal += 400
            lunch_count += 1
        if "dinner" in meals:
            meal_kcal += 500
            dinner_count += 1
            if not hut:
                total_dinner_to_prepare += 1

        intake_needed = max(intake_target - meal_kcal, 0)

        # === 水分 ===
        required_water = effective_weight * course_time * 5 * 0.8
        if idx == 1:
            water_needed = effective_weight * course_time * 5 * 0.8
        else:
            water_needed = 0 if previous_day_water_source else effective_weight * course_time * 5 * 0.8

        previous_day_water_source = water_source

        total_meal_kcal += max(meal_kcal, 0)
        total_intake_needed += intake_needed
        total_water_needed += water_needed

        result.append({
            "course_time": course_time,
            "intake_target": round(intake_target, 1),
            "meal_kcal": round(meal_kcal, 1),
            "intake_needed": round(intake_needed, 1),
            "required_water": round(required_water, 1), 
            "water_needed": round(water_needed, 1),
            "meals": meals,
            "hut": hut,
            "water": water_source,
            "total_dinner_to_prepare": total_dinner_to_prepare
        })

    return render_template(
        "home_step3.html",
        result=result,
        total_meal_kcal=round(total_meal_kcal, 1),
        total_intake_needed=round(total_intake_needed, 1),
        total_water_needed=round(total_water_needed, 1),
        total_dinner_to_prepare=total_dinner_to_prepare,
        breakfast_count=breakfast_count,
        lunch_count=lunch_count,
        dinner_count=dinner_count,
        css_file="home_step3.css"
    )


if __name__ == "__main__":
    app.run(debug=True)