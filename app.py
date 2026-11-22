import os
import json
import mysql.connector
from functools import wraps
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from flask import jsonify
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

# ---------------- FLASK CONFIGURATION ----------------
app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")

# ---------------- DATABASE CONNECTION ----------------
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "db"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "bloom_glow")
    )
# ---------------- SELLER AUTHENTICATION ----------------
def seller_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("user_id"):
            flash("Please sign in with your seller account.")
            return redirect(url_for("login"))

        if session.get("role") != "seller":
            flash("Access denied. Seller account required.")
            return redirect(url_for("home"))

        return function(*args, **kwargs)

    return wrapper


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT * FROM users WHERE email = %s",
                (email,)
            )

            user = cursor.fetchone()

        finally:
            cursor.close()
            connection.close()

        if user and check_password_hash(
            user["password_hash"], password
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            flash("Login successful!")

            if user["role"] == "seller":
                return redirect(url_for("seller_requests"))

            next_page = request.form.get("next", "")

            if next_page.startswith("/") and not next_page.startswith("//"):
                return redirect(next_page)

            return redirect(url_for("home"))

        flash("Invalid email or password.")

    next_page = request.args.get("next", "")

    return render_template(
        "login.html",
        next_page=next_page
    )

# ---------------- SYNC CART ----------------

@app.route("/sync-cart", methods=["POST"])
def sync_cart():

    if "user_id" not in session:
        return jsonify({"success": False, "message": "Please log in"}), 401

    if session.get("role") != "customer":
        return jsonify({"success": False, "message": "Customer account required"}), 403

    data = request.get_json(silent=True) or {}
    items = data.get("cart", [])

    if not isinstance(items, list):
        return jsonify({"success": False, "message": "Invalid cart"}), 400

    clean_cart = []

    try:
        for item in items:
            name = str(item.get("name", "")).strip()
            price = float(item.get("price", 0))
            quantity = int(item.get("quantity", 0))
            image = str(item.get("image", ""))

            if not name or price < 0 or quantity < 1:
                return jsonify({"success": False, "message": "Invalid product"}), 400

            clean_cart.append({
                "name": name,
                "price": price,
                "quantity": quantity,
                "image": image
            })

    except (TypeError, ValueError, AttributeError):
        return jsonify({"success": False, "message": "Invalid cart data"}), 400

    session["cart"] = clean_cart

    return jsonify({"success": True})

# ---------------- SIGNUP ----------------

@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Please fill in all fields.")
            return redirect(url_for("signup"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.")
            return redirect(url_for("signup"))

        password_hash = generate_password_hash(password)

        connection = get_db_connection()
        cursor = connection.cursor()

        try:
            cursor.execute("""
                INSERT INTO users
                (name, email, password_hash, role)
                VALUES (%s, %s, %s, 'customer')
            """, (name, email, password_hash))

            connection.commit()

            flash("Account created successfully! Please sign in.")
            return redirect(url_for("login"))

        except mysql.connector.IntegrityError:
            flash("This email is already registered.")

        finally:
            cursor.close()
            connection.close()

    return render_template("signup.html")


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():

    session.clear()

    flash("You have successfully signed out.")

    return redirect(url_for("home"))


# ---------------- SELLER REQUESTS ----------------

@app.route("/seller-requests")
@seller_required
def seller_requests():

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT *
            FROM seller_requests
            ORDER BY id DESC
        """)

        requests_list = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "seller_requests.html",
        requests=requests_list
    )

# ---------------- GET FULL ADDRESS FROM GPS ----------------

@app.route("/reverse-geocode", methods=["POST"])
def reverse_geocode():

    data = request.get_json(silent=True) or {}

    try:
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))

        if not (-90 <= latitude <= 90):
            raise ValueError("Invalid latitude")

        if not (-180 <= longitude <= 180):
            raise ValueError("Invalid longitude")

    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Invalid GPS coordinates."
        }), 400

    params = urlencode({
        "format": "jsonv2",
        "lat": latitude,
        "lon": longitude,
        "addressdetails": 1
    })

    url = "https://nominatim.openstreetmap.org/reverse?" + params

    req = Request(
        url,
        headers={
            "User-Agent": "BloomAndGlowStore/1.0"
        }
    )

    try:
        with urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))

        full_address = result.get("display_name")

        if not full_address:
            return jsonify({
                "success": False,
                "message": "No address was found for this location."
            }), 404

        return jsonify({
            "success": True,
            "full_address": full_address,
            "latitude": latitude,
            "longitude": longitude
        })

    except Exception as error:
        app.logger.error("Reverse geocoding failed: %s", error)

        return jsonify({
            "success": False,
            "message": "Unable to find the address. Please enter it manually."
        }), 502
    
# ---------------- HOME PAGE ----------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------- PRODUCT PAGES ----------------

@app.route("/flowers")
def flowers():
    return render_template("flowers.html")


@app.route("/candles")
def candles():
    return render_template("candles.html")


@app.route("/bouquets")
def bouquets():
    return render_template("Bouquets.html")


# ---------------- CART ----------------

@app.route("/cart")
def cart():
    return render_template("cart.html")


# ---------------- CHECKOUT ----------------
@app.route('/checkout')
def checkout():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'customer':
        return redirect(url_for('home'))

    cart_items = session.get('cart', [])

    total = sum(
        float(item['price']) * int(item['quantity'])
        for item in cart_items
    )
    upi_link = "upi://pay?" + urlencode({
        "pa": "maheshsudha794@oksbi",
        "pn": "Bloom and Glow",
        "am": f"{total:.2f}",
        "cu": "INR",
        "tn": "Bloom and Glow Order"
    })

    return render_template(
        'checkout.html',
        cart_items=cart_items,
        total=total,
        upi_link=upi_link
    )

# ---------------- PLACE ORDER ----------------
@app.route('/place-order', methods=['POST'])
def place_order():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'customer':
        flash("Only customers can place orders.")
        return redirect(url_for('home'))

    customer_name = request.form.get('customer_name')
    phone = request.form.get('phone')
    address = request.form.get('address')
    city = request.form.get('city')
    pincode = request.form.get('pincode')
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    payment_method = request.form.get('payment_method')

    if not all([customer_name, phone, address, city, pincode, payment_method]):
        flash("Please complete all delivery details.")
        return redirect(url_for('checkout'))

    if payment_method not in ['COD', 'UPI']:
        flash("Invalid payment method.")
        return redirect(url_for('checkout'))
    if payment_method == "UPI":
        payment_status = "Pending Verification"
    else:
        payment_status = "Cash on Delivery"

    # For now, display order confirmation.
    # Database order saving will be added next.
    return render_template(
        'order_success.html',
        customer_name=customer_name,
        payment_method=payment_method,
        payment_status=payment_status 
    )

# ---------------- VIDEOS ----------------

@app.route("/videos")
def videos():
    return render_template("videos.html")


# ---------------- REVIEWS ----------------

@app.route("/reviews")
def reviews():
    return render_template("reviews.html")


# ---------------- ABOUT ----------------

@app.route("/about")
def about():
    return render_template("about.html")


# ---------------- CONTACT ----------------

@app.route("/contact")
def contact():
    return render_template("contact.html")


# ---------------- CUSTOMIZATION REQUEST ----------------

@app.route("/customization-request", methods=["POST"])
def customization_request():

    order_id = request.form.get("order_id", "").strip()
    product = request.form.get("product", "").strip()
    colours = request.form.get("colours", "").strip()
    details = request.form.get("details", "").strip()

    if not order_id or not product or not colours:
        flash("Please fill in all required fields.")
        return redirect(url_for("contact"))

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO customization_requests
            (order_id, product, colours, details)
            VALUES (%s, %s, %s, %s)
        """, (order_id, product, colours, details))

        connection.commit()

        flash("Your customization request has been submitted!")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("contact"))

# ---------------- RUN APPLICATION ----------------
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
