import sqlite3
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure SQLite database connection
def get_db_connection():
    conn = sqlite3.connect("finance.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    conn = get_db_connection()
    stocks = conn.execute("SELECT symbol, quantity FROM stocks WHERE user_id=?", (session["user_id"],)).fetchall()

    cash_balance_row = conn.execute("SELECT cash FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    cash_balance = cash_balance_row["cash"] if cash_balance_row else 0
    total = cash_balance
    price_stock = {}
    total_price_stock = {}
    for stock in stocks:
        quote = lookup(stock["symbol"])
        price_stock[stock["symbol"]] = usd(quote["price"])
        total_price_stock[stock["symbol"]] = usd(quote["price"] * stock["quantity"])
        total = total + quote["price"] * stock["quantity"]

    conn.close()
    cash_balance = usd(cash_balance)
    total = usd(total)
    return render_template("index.html", stocks=stocks, price_stock=price_stock, total_price_stock=total_price_stock, cash_balance=cash_balance, total=total)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").lower()
        shares = request.form.get("shares")
        quote = lookup(symbol)
        if quote == None or not shares:
            return apology("Invalid Input")
        else:
            try:
                shares = int(shares)
                if shares <= 0:
                    return apology("Shares Invalid")
            except (ValueError, TypeError):
                return apology("Shares Invalid")

            now = datetime.now()
            conn = get_db_connection()
            cash = conn.execute("SELECT cash FROM users WHERE id = ?", (session["user_id"],)).fetchone()
            price = float(quote["price"]) * shares
            price = round(price, 2)
            if cash["cash"] < price:
                conn.close()
                return apology("Not enough money")
            else:
                current_price = cash["cash"] - price
                conn.execute("UPDATE users SET cash=? WHERE id=?", (current_price, session["user_id"]))
                conn.execute("INSERT INTO acquisition (user_id, shares, price, purpose, symbol, time) VALUES (?, ?, ?, ?, ?, ?)",
                            (session["user_id"], shares, price, "buy", symbol, now))

                existing_symbols = {stock["symbol"] for stock in conn.execute(
                    "SELECT symbol FROM stocks WHERE user_id=?", (session["user_id"],)).fetchall()}

                if symbol not in existing_symbols:
                    conn.execute("INSERT INTO stocks(user_id, symbol, quantity) VALUES(?, ?, ?)",
                                (session["user_id"], symbol, shares))
                else:
                    conn.execute("UPDATE stocks SET quantity = quantity + ? WHERE symbol = ? AND user_id= ? ",
                                (shares, symbol, session["user_id"]))
            conn.commit()
            conn.close()
            return redirect("/")

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    conn = get_db_connection()
    historys = conn.execute(
        "SELECT username, purpose, shares, price, UPPER(symbol) AS symbols, cash, time FROM acquisition JOIN users ON acquisition.user_id = users.id WHERE id = ? ORDER BY time DESC", (session["user_id"],)).fetchall()
    conn.close()
    return render_template("history.html", historys=historys)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        conn = get_db_connection()
        rows = conn.execute(
            "SELECT * FROM users WHERE username = ?", (request.form.get("username"),)).fetchall()
        conn.close()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        if quote != None:
            a = quote["price"]
            quote["price"] = usd(a)
            return render_template("quoted.html", quote=quote)
        else:
            return apology("Invalid Symbol")
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        if not username:
            return apology("must provide username")
        elif not password:
            return apology("must provide password")
        elif not confirmation:
            return apology("must provide confirmation of password")
        elif password != confirmation:
            return apology("password and confirmation do not match")

        password_hash = generate_password_hash(password)
        try:
            conn = get_db_connection()
            new_user = conn.execute(
                "INSERT INTO users(username, hash) VALUES (?, ?)", (username, password_hash))
            conn.commit()
            session["user_id"] = new_user.lastrowid
            conn.close()
        except:
            return apology("username already exists")
        return redirect("/")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    conn = get_db_connection()
    symbols = {stock["symbol"] for stock in conn.execute(
        "SELECT symbol FROM stocks WHERE user_id=?", (session["user_id"],)).fetchall()}
    conn.close()

    if request.method == "POST":
        now = datetime.now()
        symbol = request.form.get("symbol").lower()
        shares = request.form.get("shares")

        if not symbol or symbol not in symbols or not shares:
            return apology("Symbol Invalid")

        conn = get_db_connection()
        quantity = conn.execute(
            "SELECT quantity FROM stocks WHERE user_id=? AND symbol=?", (session["user_id"], symbol)).fetchone()

        try:
            shares = int(shares)
            if shares <= 0:
                conn.close()
                return apology("Shares Invalid")
        except (ValueError, TypeError):
            conn.close()
            return apology("Shares Invalid")

        remaining_quantity = quantity["quantity"] - int(shares)
        if remaining_quantity < 0:
            conn.close()
            return apology("Do not have enough shares")
        elif remaining_quantity == 0:
            conn.execute("DELETE FROM stocks WHERE symbol= ? AND user_id= ? ",
                        (symbol, session["user_id"]))
        else:
            conn.execute("UPDATE stocks SET quantity= ? WHERE user_id = ? AND symbol = ?",
                        (remaining_quantity, session["user_id"], symbol))

        quote = lookup(symbol)
        total_price = quote["price"] * int(shares)
        total_price = round(total_price, 2)

        conn.execute("UPDATE users SET cash = cash + ?  WHERE id = ?",
                    (total_price, session["user_id"]))
        conn.execute("INSERT INTO acquisition(user_id, shares, price, purpose, symbol, time) VALUES(?, ?, ?, ?, ?, ?)",
                    (session["user_id"], int(shares), total_price, "sell", symbol, now))
        conn.commit()
        conn.close()

        return redirect("/")

    return render_template("sell.html", symbols=symbols)

if __name__ == "__main__":
    app.run(debug=True)
