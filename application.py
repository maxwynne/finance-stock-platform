import os
import logging

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

app.debug = True

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

#db.execute("DROP TABLE transactions")
#db.execute("DROP TABLE portfolios")
#db.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id text, date int, type text, symbol text, shares int, price int)")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Query database for user's stocks
    db_transactions = db.execute("SELECT symbol, shares, price FROM transactions WHERE user_id = :user_id ORDER BY symbol DESC",
                    user_id = session["user_id"])

    # Ensure user has stocks
    if not db_transactions:
        return render_template("index.html", message = "Portfolio is empty.")

    # Set total at 0
    total = 0

    portfolios = {}


    # Add company name, current price and current stock value to stocks - adding stocks
    for transaction in db_transactions:
        symbol = transaction["symbol"]
        if symbol not in portfolios:
            stock_data = lookup(transaction["symbol"])
            name = stock_data["name"]
            price = stock_data["price"]
            value = price * transaction["shares"]
            total = total + value
            portfolios[symbol] = {"name": name, "price": price, "value": value, "shares": transaction["shares"]}
        else:
            portfolios[symbol]["shares"] += transaction["shares"]
            portfolios[symbol]["value"] += transaction["shares"] * portfolios[symbol]["price"]
            total += transaction["shares"] * portfolios[symbol]["price"]

    # Query database to get user's cash balance
    balance = get_cash(session["user_id"])

    # Calculate stocks value grand total
    total = total + balance

    # Render homepage
    return render_template("index.html", portfolios=portfolios, balance = usd(balance), value = usd(total), cash=usd(balance))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    logging.info('Buying Method')

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Assign inputs to variables
        input_symbol = request.form.get("symbol")
        input_shares = request.form.get("shares")

        # Ensure quote symbol exist in the stock data
        if not lookup(input_symbol):
            return apology("stock not found", 403)

        # Ensure user entered a positive integer
        elif int(input_shares) <= 0:
            return apology("number of shares must be a positive integer", 403)

        user_balance = get_cash(session["user_id"])

        # Calculate total price based on number of shares and stock's current price
        total_price = lookup(input_symbol)["price"] * int(input_shares);

        # Check if user has enough cash based on stock's current price
        if total_price > user_balance:

            # print(total_price, user_balance)

            # flash insufficient funds instead of returning apology
            flash(f"Insufficent funds")
            return render_template("buy.html")
            # return apology("insufficient funds", 403)

        # Query database to insert transaction
        db.execute("INSERT INTO transactions (user_id, date, symbol, shares, price) VALUES (:user_id, :date, :symbol, :shares, :price)",
            user_id = session["user_id"],
            date = datetime.datetime.now(), # python function to date transactions
            symbol = input_symbol,
            shares = int(input_shares),
            price = format(total_price,".2f"))

        # Calculate user's new cash balance after purchase
        user_balance = user_balance - total_price

        # Query database to update user's cash balance
        db.execute("UPDATE users SET cash = :balance WHERE id = :user_id",
            user_id = session["user_id"],
            balance = user_balance)

        # Query database for user's portfolio
        # portfolio = db.execute("SELECT shares FROM portfolios WHERE user_id = :user_id AND symbol = :symbol",
        #                 user_id = session["user_id"],
        #                 symbol = input_symbol)
        #
        # # In case user already does have shares for purchased stock
        # if len(portfolio) == 1:
        #
        #     # Calculate new number of shares based on current amount and purchased amount
        #     shares = portfolio[0]["shares"] + int(input_shares)
        #
        #     # Query database to update portfolios for newly purchased shares
        #     db.execute("UPDATE portfolios SET shares = :shares WHERE user_id = :user_id AND symbol = :symbol",
        #         user_id = session["user_id"],
        #         symbol = input_symbol,
        #         shares = shares)
        #
        # # In case user doesn't already have shares for purchased stock
        # else:
        #     # Query database to insert newly purchased shares info into portfolios
        #     db.execute("INSERT INTO portfolios (user_id, symbol, shares) VALUES (:user_id, :symbol, :shares)",
        #         user_id = session["user_id"],
        #         symbol = input_symbol,
        #         shares = int(input_shares))

        # Get company name
        name = lookup(input_symbol)["name"]

        # Flash info for the user
        flash(f"Purchased {input_shares} of {name}")

        # Redirect user to homepage
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


def get_cash(user_id) :
    # Query database for how much cash user currently has
    user_balance = db.execute("SELECT cash FROM users WHERE id = :user_id",
                              user_id=user_id)[0]["cash"]
    return user_balance


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Query database for user's stocks
    db_transactions = db.execute(
        "SELECT symbol, shares, price, date FROM transactions WHERE user_id = :user_id ORDER BY date DESC",
        user_id=session["user_id"])

    # Ensure user has stocks
    if not db_transactions :
        return render_template("index.html", message="Portfolio is empty.")

    # Set total at 0
    total = 0

    # get list of stock names and transactions
    stock_names = {}
    transactions = []

    # db.transactions - go through transactions and store the names of each stock (no need to re-look up stock names)
    #
    for transaction in db_transactions:
        symbol = transaction["symbol"]
        if symbol not in stock_names: # if stock not found, store it
            stock_data = lookup(transaction["symbol"])
            name = stock_data["name"]
            stock_names[symbol] = name
        else:
            name = stock_names[symbol] # if stock is found, use stocks

        # type section for transactions in trans history table. Buy transactions if it's over 0; if not, type to sell.
        type = "Buy" if transaction["shares"] > 0 else "Sell"

        # abs (abs(transaction["shares"]) returns a whole/abs value for number for each transaction
        transactions.append(
            {"name": name, "price": transaction["price"], "value": transaction["price"] * abs(transaction["shares"]),
             "shares": abs(transaction["shares"]), "symbol": symbol, "date": transaction["date"], "type": type})

    print(transactions)

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Assign inputs to variables
        input_username = request.form.get("username")
        input_password = request.form.get("password")

        # Ensure username was submitted
        if not input_username:
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not input_password:
            return apology("must provide password", 403)

        # Query database for username
        username = db.execute("SELECT * FROM users WHERE username = :username",
                username = input_username)

        # Ensure username exists and password is correct
        if len(username) != 1 or not check_password_hash(username[0]["hash"], input_password):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = username[0]["id"]

        # Flash info for the user
        flash(f"Logged in as {input_username}")

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

    # User reached route via POST (submitting form by post)
    if request.method == "POST":

        # Assign inputs to variables
        input_symbol = request.form.get("symbol")

        # Ensure quote symbol was submitted
        if not input_symbol:
            return apology("must provide symbol", 403)

        # Ensure quote symbol exists in the stock data
        elif not lookup(input_symbol):
            return apology("stock not found", 403)

        # get quote info
        quote = lookup(input_symbol)

        # format price to usd
        quote["price"] = usd(quote["price"])

        return render_template("quoted.html", quote=quote)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Assign inputs to variables
        input_username = request.form.get("username")
        input_password = request.form.get("password")
        input_confirmation = request.form.get("confirmation")

        # Ensure username was submitted
        if not input_username:
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not input_password:
            return apology("must provide password", 403)

        # Ensure password confirmation was submitted
        elif not input_confirmation:
            return apology("must provide password confirmation", 418)

        elif not input_password == input_confirmation:
            return apology("passwords must match", 418)

        # Query database for username
        username = db.execute("SELECT username FROM users WHERE username = :username",
                          username = input_username)

        # Ensure username is not already taken
        if len(username) == 1:
            return apology("sorry, username is already taken", 403)

        # Query database to insert new user
        else:
            new_user = db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)",
                            username = input_username,
                            password = generate_password_hash(input_password, method="pbkdf2:sha256", salt_length=8))

            if new_user:
                # Keep newly registered user logged in
                session["user_id"] = new_user

            # Flash info for the user
            flash(f"Registered as {input_username}")

            # Redirect user to homepage
            return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Assign inputs to variables
        input_symbol = request.form.get("symbol")
        input_shares = request.form.get("shares")

        # Ensure quote symbol was submitted
        if not input_symbol:
            return apology("must provide symbol", 403)

        # Ensure user entered a positive integer for number of shares
        elif int(input_shares) <= 0:
            return apology("number of shares must be a positive integer", 403)

        # Query database for user's portfolio
        transactions = db.execute("SELECT shares FROM transactions WHERE user_id = :user_id AND symbol = :symbol",
                        user_id = session["user_id"],
                        symbol = input_symbol)

        num_shares_owned = 0
        print(transactions, input_symbol)
        for transaction in transactions:
            num_shares_owned += transaction["shares"]

        # Ensure user has enough shares for selected symbol
        print(num_shares_owned, input_shares)
        if num_shares_owned < int(input_shares):
            return apology("not enough shares", 403)

        # Calculate total price based on number of shares and stock's current price
        price = lookup(input_symbol)["price"] * int(input_shares)

        # Query database to insert transaction
        db.execute("INSERT INTO transactions (user_id, date, symbol, shares, price) VALUES (:user_id, :date, :symbol, :shares, :price)",
            user_id = session["user_id"],
            date = 0,
            symbol = input_symbol,
            shares = -int(input_shares),
            price = format(price,".2f"))

    # # Query database for how much cash user currently has
    #     balance = db.execute("SELECT cash FROM users WHERE id = :user_id",
    #                     user_id = session["user_id"])[0]["cash"]
    #
    #     # Calculate user's new cash balance after purchase
    #     balance = balance + price
    #
    #     # Query database to update user's cash balance
    #     db.execute("UPDATE users SET cash = :balance WHERE id = :user_id",
    #         user_id = session["user_id"],
    #         balance = balance)
    #
    #     # Calculate new share amount
    #     shares = stocks[0]["shares"] - int(input_shares)
    #
    #     # Query database to update user's portfolio
    #     db.execute("UPDATE portfolios SET shares = :shares WHERE user_id = :user_id AND symbol = :symbol",
    #         user_id = session["user_id"],
    #         symbol = input_symbol,
    #         shares = shares)

        # Get company name
        name = lookup(input_symbol)["name"]

        # Flash info for the user
        flash(f"Sold {input_shares} of {name}")

        # Redirect user to homepage
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        # Query database for stocks where user_id is equal to logged in user id
        transactions = db.execute(
            "SELECT symbol, shares FROM transactions WHERE user_id =:user_id ORDER BY symbol ASC",
                        user_id = session["user_id"])

        symbols = set()
        for transaction in transactions:
            symbols.add(transaction["symbol"])


        return render_template("sell.html", symbols = symbols)


@app.route("/addcash", methods=["GET", "POST"])
@login_required
def addcash():
    """Add more cash."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        try:
            # Assign input to variable
            input_amount = float(request.form.get("cash"))
        except ValueError:
            # Ensure cash amount was submitted
            flash("must provide amount of cash to add")
            return redirect("/")

        if input_amount <= 0:
            flash("Added amount must be positive")
            return redirect("/")

        # Query database to update user's cash amount
        print(input_amount, type(input_amount))
        db.execute("UPDATE users SET cash = cash + :amount WHERE id = :user_id",
            user_id = session["user_id"],
            amount = input_amount)

        # Flash info for the user
        flash(f"Added {usd(int(input_amount))} to your account")

        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
