from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin
import stripe

app = Flask(__name__)
app.secret_key = 'replace_with_a_random_secret_key'

# Configure Stripe
stripe.api_key = 'sk_test_your_secret_key_here'  # replace with your key

login_manager = LoginManager(app)

# In-memory user store (for demonstration only)
users = {"demo@example.com": {"password": "password"}}

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id)
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if email in users and users[email]['password'] == password:
            user = User(email)
            login_user(user)
            return redirect(url_for('shop'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/shop')
@login_required
def shop():
    # Example item to purchase
    item = {
        'name': 'Handmade Scarf',
        'price': 2500,  # price in cents
        'currency': 'eur',
    }
    return render_template('shop.html', item=item)

@app.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': 'Handmade Scarf',
                    },
                    'unit_amount': 2500,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('shop', _external=True),
        )
        return redirect(session.url, code=303)
    except Exception as e:
        return str(e)

@app.route('/success')
@login_required
def success():
    return render_template('success.html')

if __name__ == '__main__':
    app.run(debug=True)
