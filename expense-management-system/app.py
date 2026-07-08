import sqlite3
import re
from flask import Flask, render_template, request, redirect, flash, session
from datetime import date
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

app = Flask(__name__)
app.secret_key = "expense_management_secret"

DATABASE = "database.db"

# Default categories given to every new user so they don't have to
# build their category list from scratch. These match the icon set
# already used on the Categories page.
DEFAULT_CATEGORIES = [
    "Food",
    "Transport",
    "Shopping",
    "Travel",
    "Rent",
    "Utilities",
    "Entertainment",
    "Medical",
]

def init_db():

    conn = sqlite3.connect(DATABASE)

    # If a previous migration attempt was interrupted after creating
    # categories_new but before it was renamed back to categories, resume
    # that here — before anything below gets a chance to silently create
    # a fresh empty `categories` table and orphan the real data.

    categories_exists = bool(conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='categories'
    """).fetchone())

    categories_new_exists = bool(conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='categories_new'
    """).fetchone())

    if categories_new_exists and not categories_exists:

        conn.execute("ALTER TABLE categories_new RENAME TO categories")

        conn.commit()

    # Categories
    # NOTE: category_name is no longer globally unique because each user
    # now has their own private set of categories.

    conn.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        category_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category_name TEXT NOT NULL,
        FOREIGN KEY(user_id)
        REFERENCES users(user_id)
    )
    """)

    # Expenses

    conn.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        expense_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        expense_date DATE NOT NULL,
        description TEXT,
        FOREIGN KEY(user_id)
        REFERENCES users(user_id)
    )
    """)
    
    conn.execute("""
    CREATE TABLE IF NOT EXISTS travel_requests (
        travel_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        destination TEXT NOT NULL,
        purpose TEXT NOT NULL,
        start_date DATE,
        end_date DATE,
        status TEXT DEFAULT 'Planned',
        FOREIGN KEY(user_id)
        REFERENCES users(user_id)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS travel_expenses (
        travel_expense_id
        INTEGER PRIMARY KEY AUTOINCREMENT,
        travel_id INTEGER,
        user_id INTEGER NOT NULL,
        category TEXT,
        amount REAL,
        expense_date DATE,
        description TEXT,
        FOREIGN KEY(travel_id)
        REFERENCES travel_requests(travel_id),

        FOREIGN KEY(user_id)
        REFERENCES users(user_id)

    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        budget REAL NOT NULL DEFAULT 30000
    )
    """)

    # ---- Migrations for databases created before this update ----

    user_columns = [
        row[1]
        for row in conn.execute("PRAGMA table_info(users)")
    ]

    if "budget" not in user_columns:
        conn.execute("""
            ALTER TABLE users
            ADD COLUMN budget REAL NOT NULL DEFAULT 30000
        """)

    travel_expense_columns = [
        row[1]
        for row in conn.execute("PRAGMA table_info(travel_expenses)")
    ]

    if "user_id" not in travel_expense_columns:

        conn.execute("""
            ALTER TABLE travel_expenses
            ADD COLUMN user_id INTEGER
            REFERENCES users(user_id)
        """)

        # Backfill user_id for existing rows from the parent trip, since
        # every travel expense belongs to whoever owns that trip.
        conn.execute("""
            UPDATE travel_expenses
            SET user_id = (
                SELECT tr.user_id
                FROM travel_requests tr
                WHERE tr.travel_id = travel_expenses.travel_id
            )
            WHERE user_id IS NULL
        """)

        conn.commit()

    category_columns = [
        row[1]
        for row in conn.execute("PRAGMA table_info(categories)")
    ]

    if "user_id" not in category_columns:

        # Old installs have a UNIQUE constraint on category_name, which
        # ALTER TABLE can't drop. Rebuild the table instead so different
        # users can each have a category with the same name.

        # Clear out any stale leftover from an earlier interrupted attempt.
        conn.execute("DROP TABLE IF EXISTS categories_new")

        conn.execute("""
            CREATE TABLE categories_new (
                category_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                category_name TEXT NOT NULL,
                FOREIGN KEY(user_id)
                REFERENCES users(user_id)
            )
        """)

        legacy_categories = conn.execute("""
            SELECT category_id, category_name
            FROM categories
        """).fetchall()

        # Any categories that existed before this update were shared by
        # every user. Give every existing user their own copy so nobody
        # loses access to categories they were already using.

        all_users = conn.execute(
            "SELECT user_id FROM users"
        ).fetchall()

        for category_id, category_name in legacy_categories:

            for (user_id,) in all_users:

                conn.execute("""
                    INSERT INTO categories_new(user_id, category_name)
                    VALUES(?, ?)
                """, (user_id, category_name))

        conn.execute("DROP TABLE categories")
        conn.execute("ALTER TABLE categories_new RENAME TO categories")

    conn.commit()

    user = conn.execute("""
    SELECT *
    FROM users
    WHERE username=?
    """, ("admin",)).fetchone()

    if not user:

        hashed_password = generate_password_hash(
            "admin123"
        )

        conn.execute("""
        INSERT INTO users
        (
            username,
            password
        )
        VALUES
        (?,?)
        """,
        (
            "admin",
            hashed_password
        ))

    conn.commit()

    # Give every existing user any default categories they don't already
    # have (case-insensitive match, so someone with "FOOD" doesn't also
    # get a separate "Food"). New signups already get these from the
    # signup route — this backfills accounts that existed before that.

    all_users = conn.execute(
        "SELECT user_id FROM users"
    ).fetchall()

    for (user_id,) in all_users:

        existing_names = {
            row[0].strip().lower()
            for row in conn.execute("""
                SELECT category_name
                FROM categories
                WHERE user_id=?
            """, (user_id,))
        }

        for category_name in DEFAULT_CATEGORIES:

            if category_name.lower() not in existing_names:

                conn.execute("""
                    INSERT INTO categories(user_id, category_name)
                    VALUES(?, ?)
                """, (user_id, category_name))

    conn.commit()

    conn.close()

init_db()

@app.before_request
def require_login():
    if request.endpoint is None:
        return

    allowed_routes = {
        "login",
        "signup",
        "logout",
        "static"
    }

    if request.endpoint in allowed_routes:
        return

    if "user_id" not in session:

        return redirect("/login")

@app.route("/")
def dashboard():

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    # Total expenses (regular + travel expenses from Ongoing/Completed trips)
    total_expenses = conn.execute("""
        SELECT
            IFNULL(SUM(amount), 0)
        FROM (
            SELECT amount
            FROM expenses
            WHERE user_id=?

            UNION ALL

            SELECT te.amount
            FROM travel_expenses te
            JOIN travel_requests tr
                ON te.travel_id = tr.travel_id
            WHERE te.user_id=?
            AND tr.status IN ('Ongoing', 'Completed')
        )
    """,(session["user_id"], session["user_id"])).fetchone()[0]

    # Total trips
    trip_count = conn.execute("""
        SELECT
            COUNT(*)
        FROM travel_requests WHERE user_id=?
    """,(session["user_id"],)).fetchone()[0]

    # Total categories
    category_count = conn.execute("""
        SELECT
            COUNT(*)
        FROM categories
        WHERE user_id=?
    """,(session["user_id"],)).fetchone()[0]

    # Monthly budget
    budget = conn.execute("""
        SELECT budget
        FROM users
        WHERE user_id=?
    """,(session["user_id"],)).fetchone()[0]

    # Current month expenses (regular + travel expenses from Ongoing/Completed trips)
    monthly_total = conn.execute("""
        SELECT
            IFNULL(SUM(amount), 0)
        FROM (
            SELECT amount, expense_date
            FROM expenses
            WHERE user_id=?

            UNION ALL

            SELECT te.amount, te.expense_date
            FROM travel_expenses te
            JOIN travel_requests tr
                ON te.travel_id = tr.travel_id
            WHERE te.user_id=?
            AND tr.status IN ('Ongoing', 'Completed')
        )
        WHERE strftime('%Y-%m', expense_date) = strftime('%Y-%m', 'now')
    """,(session["user_id"], session["user_id"])).fetchone()[0]

    # Recent expenses
    recent_expenses = conn.execute("""
        SELECT *
        FROM expenses
        WHERE user_id=?
        ORDER BY expense_id DESC
        LIMIT 5
    """,(session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        total_expenses=total_expenses,
        trip_count=trip_count,
        category_count=category_count,
        monthly_total=monthly_total,
        recent_expenses=recent_expenses,
        budget=budget
    )

@app.route("/budget/update", methods=["POST"])
def update_budget():

    budget = request.form["budget"]

    try:
        budget = float(budget)
    except ValueError:
        flash("Please enter a valid budget amount.")
        return redirect("/")

    if budget < 0:
        flash("Budget cannot be negative.")
        return redirect("/")

    conn = sqlite3.connect(DATABASE)

    conn.execute("""
        UPDATE users
        SET budget=?
        WHERE user_id=?
    """, (budget, session["user_id"]))

    conn.commit()
    conn.close()

    flash("Budget updated successfully!")

    return redirect("/")

@app.route("/categories")
def categories():

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    categories = conn.execute(
        "SELECT * FROM categories WHERE user_id=?",
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "categories.html",
        categories=categories
    )

@app.route("/category/add", methods=["GET", "POST"])
def add_category():

    if request.method == "POST":

        category_name = request.form["category_name"]

        if not category_name.strip():
            flash("Category name cannot be empty")
            return redirect("/category/add")

        conn = sqlite3.connect(DATABASE)

        conn.execute(
            """
            INSERT INTO categories(user_id, category_name)
            VALUES(?, ?)
            """,
            (session["user_id"], category_name)
        )

        conn.commit()
        conn.close()

        flash("Category added successfully!")

        return redirect("/categories")

    return render_template("add_category.html")

@app.route("/expense/add", methods=["GET", "POST"])
def add_expense():

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    categories = conn.execute(
        "SELECT * FROM categories WHERE user_id=?",
        (session["user_id"],)
    ).fetchall()

    if request.method == "POST":

        category = request.form["category"]
        amount = request.form["amount"]
        expense_date = request.form["expense_date"]
        description = request.form["description"]

        conn.execute("""
            INSERT INTO expenses
            (user_id,category, amount, expense_date, description)
            VALUES (?, ?, ?, ?,?)
        """,
        (
            session["user_id"],
            category,
            amount,
            expense_date,
            description
        ))

        conn.commit()
        conn.close()

        flash("Expense added successfully!")

        return redirect("/expenses")

    return render_template(
        "add_expense.html",
        categories=categories,
        today=date.today().isoformat()
    )

@app.route("/expenses")
def expenses():

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    expenses = conn.execute("""
        SELECT *
        FROM expenses
        WHERE user_id=?
        ORDER BY expense_date DESC
    """,(session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "expenses.html",
        expenses=expenses
    )

@app.route("/expense/delete/<int:id>")
def delete_expense(id):

    conn = sqlite3.connect(DATABASE)

    conn.execute(
        "DELETE FROM expenses WHERE expense_id=? AND user_id=?",
        (id,session["user_id"])
    )

    conn.commit()
    conn.close()

    flash("Expense deleted successfully!")

    return redirect("/expenses")

@app.route("/expense/edit/<int:id>", methods=["GET", "POST"])
def edit_expense(id):

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    if request.method == "POST":

        category = request.form["category"]
        amount = request.form["amount"]
        expense_date = request.form["expense_date"]
        description = request.form["description"]

        conn.execute("""
            UPDATE expenses
            SET category=?,
                amount=?,
                expense_date=?,
                description=?
            WHERE expense_id=?
            AND user_id=?
        """,
        (
            category,
            amount,
            expense_date,
            description,
            id,
            session["user_id"]
        ))

        conn.commit()

        flash("Expense updated!")

        return redirect("/expenses")

    expense = conn.execute(
        "SELECT * FROM expenses WHERE expense_id=? AND user_id=?",
        (id,session["user_id"])
    ).fetchone()

    if expense is None:
        flash("Expense not found.")
        return redirect("/expenses")
    
    categories = conn.execute(
        "SELECT * FROM categories WHERE user_id=?",
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return render_template(
        "edit_expense.html",
        expense=expense,
        categories=categories
    )

@app.route("/travel")
def travel():

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    trips = conn.execute("""
    SELECT *
    FROM travel_requests
    WHERE user_id=?
    ORDER BY travel_id DESC
    """,(session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "travel.html",
        trips=trips
    )

@app.route(
    "/travel/add",
    methods=["GET", "POST"]
)
def add_travel():

    if request.method == "POST":

        destination = request.form[
            "destination"
        ]

        purpose = request.form[
            "purpose"
        ]

        start_date = request.form[
            "start_date"
        ]

        end_date = request.form[
            "end_date"
        ]

        conn = sqlite3.connect(DATABASE)

        conn.execute("""
            INSERT INTO travel_requests
            (
                user_id,
                destination,
                purpose,
                start_date,
                end_date
            )
            VALUES
            (?, ?, ?, ?, ?)
        """,
        (
            session["user_id"],
            destination,
            purpose,
            start_date,
            end_date
        ))

        conn.commit()
        conn.close()

        flash(
            "Travel request created!"
        )

        return redirect("/travel")

    return render_template(
        "add_travel.html"
    )

@app.route("/reports")
def reports():

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    total = conn.execute("""
        SELECT IFNULL(SUM(amount), 0)
        FROM (
            SELECT amount
            FROM expenses
            WHERE user_id=?

            UNION ALL

            SELECT te.amount
            FROM travel_expenses te
            JOIN travel_requests tr
                ON te.travel_id = tr.travel_id
            WHERE te.user_id=?
            AND tr.status IN ('Ongoing', 'Completed')
        )
    """,(session["user_id"], session["user_id"])).fetchone()[0]

    categories = conn.execute("""
        SELECT
            category,
            SUM(amount) AS total
        FROM (
            SELECT category, amount
            FROM expenses
            WHERE user_id=?

            UNION ALL

            SELECT te.category, te.amount
            FROM travel_expenses te
            JOIN travel_requests tr
                ON te.travel_id = tr.travel_id
            WHERE te.user_id=?
            AND tr.status IN ('Ongoing', 'Completed')
        )
        GROUP BY category
        ORDER BY total DESC
    """,(session["user_id"], session["user_id"])).fetchall()

    monthly = conn.execute("""
        SELECT
            strftime('%Y-%m', expense_date) AS month,
            SUM(amount) AS total
        FROM (
            SELECT amount, expense_date
            FROM expenses
            WHERE user_id=?

            UNION ALL

            SELECT te.amount, te.expense_date
            FROM travel_expenses te
            JOIN travel_requests tr
                ON te.travel_id = tr.travel_id
            WHERE te.user_id=?
            AND tr.status IN ('Ongoing', 'Completed')
        )
        GROUP BY month
        ORDER BY month
    """,(session["user_id"], session["user_id"])).fetchall()

    conn.close()

    return render_template(
        "reports.html",
        total=total,
        categories=categories,
        monthly=monthly
    )

@app.route(
    "/travel/<int:id>/expenses"
)
def travel_expenses(id):

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    trip = conn.execute(
        """
        SELECT *
        FROM travel_requests
        WHERE travel_id=?
        AND user_id=?
        """,
        (id,session["user_id"])
    ).fetchone()

    if trip is None:

        flash("Trip not found.")
        return redirect("/travel")

    expenses = conn.execute(
        """
        SELECT *
        FROM travel_expenses
        WHERE travel_id=?
        AND user_id=?
        """,
        (id,session["user_id"])
    ).fetchall()

    total = conn.execute(
        """
        SELECT
        IFNULL(
            SUM(amount),
            0
        )
        FROM travel_expenses
        WHERE travel_id=?
        AND user_id=?
        """,
        (id,session["user_id"])
    ).fetchone()[0]

    conn.close()

    return render_template(
        "travel_expenses.html",
        trip=trip,
        expenses=expenses,
        total=total
    )

@app.route(
    "/travel/edit/<int:id>",
    methods=["GET", "POST"]
)
def edit_travel(id):

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    if request.method == "POST":

        destination = request.form["destination"]
        purpose = request.form["purpose"]
        start_date = request.form["start_date"]
        end_date = request.form["end_date"]
        status = request.form.get("status", "Planned")

        if status not in ("Planned", "Ongoing", "Completed"):
            status = "Planned"

        conn.execute("""
            UPDATE travel_requests
            SET
                destination=?,
                purpose=?,
                start_date=?,
                end_date=?,
                status=?
            WHERE travel_id=? AND user_id=?
        """,
        (
            destination,
            purpose,
            start_date,
            end_date,
            status,
            id,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        flash(
            "Trip updated successfully!"
        )

        return redirect("/travel")

    trip = conn.execute("""
        SELECT *
        FROM travel_requests
        WHERE travel_id=? AND user_id=?
    """, (id,session["user_id"])).fetchone()

    if trip is None:
        flash("Trip not found.")
        return redirect("/travel")

    conn.close()

    return render_template(
        "edit_travel.html",
        trip=trip
    )

@app.route(
    "/travel/delete/<int:id>"
)
def delete_travel(id):

    conn = sqlite3.connect(DATABASE)

    conn.execute("""
        DELETE FROM travel_requests
        WHERE travel_id=? AND user_id=?
    """, (id,session["user_id"]))

    conn.commit()
    conn.close()

    flash(
        "Trip deleted successfully!"
    )

    return redirect("/travel")

@app.route(
    "/travel/<int:id>/expense/add",
    methods=["GET","POST"]
)
def add_travel_expense(id):

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    trip = conn.execute("""
    SELECT *
    FROM travel_requests
    WHERE travel_id=?
    AND user_id=?
    """,
    (
        id,
        session["user_id"]
    )
    ).fetchone()

    if trip is None:
        conn.close()
        flash("Trip not found.")
        return redirect("/travel")

    if request.method == "POST":

        category = request.form["category"]
        amount = request.form["amount"]
        expense_date = request.form["expense_date"]
        description = request.form["description"]

        conn = sqlite3.connect(DATABASE)

        conn.execute("""
            INSERT INTO travel_expenses
            (
                travel_id,
                user_id,
                category,
                amount,
                expense_date,
                description
            )
            VALUES
            (?, ?, ?, ?, ?, ?)
        """,
        (
            id,
            session["user_id"],
            category,
            amount,
            expense_date,
            description
        ))

        conn.commit()
        conn.close()

        flash(
            "Travel expense added!"
        )

        return redirect(
            f"/travel/{id}/expenses"
        )

    return render_template(
        "add_travel_expense.html",
        travel_id=id
    )

@app.route("/travel/start/<int:id>")
def start_trip(id):

    conn = sqlite3.connect(DATABASE)

    conn.execute("""
        UPDATE travel_requests
        SET status='Ongoing'
        WHERE travel_id=? AND user_id=?
    """, (id,session["user_id"]))

    conn.commit()
    conn.close()

    flash("Trip marked as Ongoing!")

    return redirect("/travel")

@app.route("/travel/complete/<int:id>")
def complete_trip(id):

    conn = sqlite3.connect(DATABASE)

    conn.execute("""
        UPDATE travel_requests
        SET status='Completed'
        WHERE travel_id=? AND user_id=?
    """, (id,session["user_id"]))

    conn.commit()
    conn.close()

    flash("Trip marked as Completed!")

    return redirect("/travel")

@app.route(
    "/login",
    methods=["GET","POST"]
)
def login():

    if request.method=="POST":

        username=request.form["username"]
        password=request.form["password"]

        conn=sqlite3.connect(DATABASE)
        conn.row_factory=sqlite3.Row

        user=conn.execute("""
            SELECT *
            FROM users
            WHERE username=?
        """,(username,)).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"]=user["user_id"]
            session["username"]=user["username"]

            flash("Welcome back!")

            return redirect("/")

        flash("Invalid username or password")

    return render_template(
        "login.html"
    )

@app.route("/logout")
def logout():

    session.clear()

    flash("Logged out successfully.")

    return redirect("/login")

@app.route(
    "/settings",
    methods=["GET", "POST"]
)
def settings():

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    if request.method == "POST":

        form_type = request.form.get("form_type")

        # ---- Update username ----

        if form_type == "username":

            new_username = request.form["username"].strip()

            if len(new_username) < 4:

                flash("Username must be at least 4 characters.")

                conn.close()
                return redirect("/settings")

            existing = conn.execute("""
                SELECT *
                FROM users
                WHERE username=?
                AND user_id!=?
            """, (new_username, session["user_id"])).fetchone()

            if existing:

                flash("That username is already taken.")

                conn.close()
                return redirect("/settings")

            conn.execute("""
                UPDATE users
                SET username=?
                WHERE user_id=?
            """, (new_username, session["user_id"]))

            conn.commit()
            conn.close()

            session["username"] = new_username

            flash("Username updated successfully!")

            return redirect("/settings")

        # ---- Update password ----

        if form_type == "password":

            current_password = request.form["current_password"]
            new_password = request.form["new_password"]
            confirm_password = request.form["confirm_password"]

            user = conn.execute("""
                SELECT *
                FROM users
                WHERE user_id=?
            """, (session["user_id"],)).fetchone()

            if not user or not check_password_hash(
                user["password"],
                current_password
            ):

                flash("Current password is incorrect.")

                conn.close()
                return redirect("/settings")

            if new_password != confirm_password:

                flash("New passwords do not match.")

                conn.close()
                return redirect("/settings")

            if len(new_password) < 8:

                flash("Password must be at least 8 characters.")

                conn.close()
                return redirect("/settings")

            if not re.search(r"[A-Z]", new_password):

                flash("Password must contain an uppercase letter.")

                conn.close()
                return redirect("/settings")

            if not re.search(r"[a-z]", new_password):

                flash("Password must contain a lowercase letter.")

                conn.close()
                return redirect("/settings")

            if not re.search(r"\d", new_password):

                flash("Password must contain a number.")

                conn.close()
                return redirect("/settings")

            if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", new_password):

                flash("Password must contain a special character.")

                conn.close()
                return redirect("/settings")

            hashed_password = generate_password_hash(new_password)

            conn.execute("""
                UPDATE users
                SET password=?
                WHERE user_id=?
            """, (hashed_password, session["user_id"]))

            conn.commit()
            conn.close()

            flash("Password updated successfully!")

            return redirect("/settings")

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE user_id=?
    """, (session["user_id"],)).fetchone()

    conn.close()

    return render_template(
        "settings.html",
        user=user
    )

@app.route(
    "/signup",
    methods=["GET", "POST"]
)
def signup():

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # Password confirmation

        if password != confirm_password:

            flash("Passwords do not match.")

            return redirect("/signup")

        # Username validation

        if len(username) < 4:

            flash("Username must be at least 4 characters.")

            return redirect("/signup")

        # Password validation

        if len(password) < 8:

            flash("Password must be at least 8 characters.")

            return redirect("/signup")

        if not re.search(r"[A-Z]", password):

            flash("Password must contain an uppercase letter.")

            return redirect("/signup")

        if not re.search(r"[a-z]", password):

            flash("Password must contain a lowercase letter.")

            return redirect("/signup")

        if not re.search(r"\d", password):

            flash("Password must contain a number.")

            return redirect("/signup")

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):

            flash("Password must contain a special character.")

            return redirect("/signup")

        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row

        existing = conn.execute("""
            SELECT *
            FROM users
            WHERE username=?
        """, (username,)).fetchone()

        if existing:

            conn.close()

            flash("Username already exists.")

            return redirect("/signup")

        hashed_password = generate_password_hash(password)

        cursor = conn.execute("""
            INSERT INTO users
            (
                username,
                password
            )
            VALUES
            (?,?)
        """,
        (
            username,
            hashed_password
        ))

        new_user_id = cursor.lastrowid

        for category_name in DEFAULT_CATEGORIES:
            conn.execute("""
                INSERT INTO categories(user_id, category_name)
                VALUES(?, ?)
            """, (new_user_id, category_name))

        conn.commit()
        conn.close()

        flash("Account created successfully. Please log in.")

        return redirect("/login")

    return render_template("signup.html")

@app.route("/category/delete/<int:id>")
def delete_category(id):

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    category = conn.execute("""
        SELECT *
        FROM categories
        WHERE category_id=?
        AND user_id=?
    """, (id, session["user_id"])).fetchone()

    if category is None:

        conn.close()

        flash("Category not found.")

        return redirect("/categories")

    # Check if any of this user's expenses use this category

    used = conn.execute("""
        SELECT COUNT(*)
        FROM expenses
        WHERE category=?
        AND user_id=?
    """, (category["category_name"], session["user_id"])).fetchone()[0]

    if used > 0:

        conn.close()

        flash("This category is being used by expenses and cannot be deleted.")

        return redirect("/categories")

    # Safe to delete

    conn.execute("""
        DELETE FROM categories
        WHERE category_id=?
        AND user_id=?
    """, (id, session["user_id"]))

    conn.commit()
    conn.close()

    flash("Category deleted successfully!")

    return redirect("/categories")

@app.route(
    "/category/edit/<int:id>",
    methods=["GET", "POST"]
)
def edit_category(id):

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    if request.method == "POST":

        category_name = request.form["category_name"]

        conn.execute("""
            UPDATE categories
            SET category_name=?
            WHERE category_id=?
            AND user_id=?
        """,
        (
            category_name,
            id,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        flash("Category updated successfully!")

        return redirect("/categories")

    category = conn.execute("""
        SELECT *
        FROM categories
        WHERE category_id=?
        AND user_id=?
    """, (id, session["user_id"])).fetchone()

    conn.close()

    if category is None:

        flash("Category not found.")

        return redirect("/categories")

    return render_template(
        "edit_category.html",
        category=category
    )

if __name__ == "__main__":
    app.run(debug=True)