from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
import requests
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace("postgres://", "postgresql://", 1)

db = SQLAlchemy(app)


class ConversionHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    from_curr = db.Column(db.String(3), nullable=False)
    to_curr = db.Column(db.String(3), nullable=False)
    result = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)


def get_currency_rates():
    """Получение курсов валют с кэшированием"""
    cached_data = getattr(app, 'cached_rates', None)

    if cached_data and (datetime.now() - cached_data['timestamp'] < timedelta(seconds=app.config['CACHE_TIMEOUT'])):
        return cached_data

    try:
        response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js")
        response.raise_for_status()
        data = response.json()

        app.cached_rates = {
            'date': datetime.now().strftime("%d.%m.%Y %H:%M"),
            'rates': data['Valute'],
            'timestamp': datetime.now()
        }
        return app.cached_rates

    except requests.exceptions.RequestException as e:
        return {'error': str(e)}

@app.route('/test-db')
def test_db():
    try:
        db.engine.connect()
        return "База данных подключена успешно!"
    except Exception as e:
        return f"Ошибка: {str(e)}"
@app.route('/', methods=['GET', 'POST'])
def index():
    currencies_data = get_currency_rates()
    result = None
    error = None
    history = ConversionHistory.query.order_by(ConversionHistory.timestamp.desc()).limit(10).all()
    sorted_currencies = []

    if 'error' not in currencies_data:
        currencies_dict = currencies_data['rates']
        sorted_currencies = sorted(
            currencies_dict.items(),
            key=lambda item: item[1]['Name']
        )

        if request.method == 'POST':
            try:
                amount = float(request.form['amount'])
                from_curr = request.form['from']
                to_curr = request.form['to']

                if from_curr == 'RUB':
                    rate = 1 / currencies_dict[to_curr]['Value']
                elif to_curr == 'RUB':
                    rate = currencies_dict[from_curr]['Value']
                else:
                    rate = currencies_dict[to_curr]['Value'] / currencies_dict[from_curr]['Value']

                converted = round(amount * rate, 2)
                result = {
                    'amount': amount,
                    'from': currencies_dict[from_curr]['Name'] if from_curr != 'RUB' else 'Российский рубль',
                    'to': currencies_dict[to_curr]['Name'] if to_curr != 'RUB' else 'Российский рубль',
                    'result': converted,
                    'rate': round(rate, 4)
                }

                # Сохранение в историю
                db.session.add(ConversionHistory(
                    amount=amount,
                    from_curr=from_curr,
                    to_curr=to_curr,
                    result=converted
                ))
                db.session.commit()

            except Exception as e:
                error = f"Ошибка: {str(e)}"
                db.session.rollback()

    return render_template(
        'index.html',
        currencies=sorted_currencies,
        result=result,
        error=error or currencies_data.get('error'),
        update_date=currencies_data.get('date', ''),
        history=history
    )


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)