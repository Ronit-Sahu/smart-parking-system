import os, math
from datetime import datetime
from functools import wraps
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-change-me')
ADM = os.getenv('ADMIN_EMAIL', '').lower()  # ye email wala user admin hoga


def db():
    return mysql.connector.connect(host=os.getenv('DB_HOST', 'localhost'), user=os.getenv('DB_USER', 'root'),
                                   password=os.getenv('DB_PASSWORD', ''), database=os.getenv('DB_NAME', 'smart_parking'))


def q(sql, p=(), one=False):
    c = db(); cur = c.cursor(dictionary=True)
    try:
        cur.execute(sql, p)
        return cur.fetchone() if one else cur.fetchall()
    finally:
        cur.close(); c.close()


def ex(sql, p=()):
    c = db(); cur = c.cursor()
    try:
        cur.execute(sql, p); c.commit()
    finally:
        cur.close(); c.close()


def login_req(f):
    @wraps(f)
    def w(*a, **k):
        if 'uid' not in session:
            return redirect(url_for('login'))
        return f(*a, **k)
    return w


def pdt(s):
    return datetime.strptime(s, '%Y-%m-%dT%H:%M')


@app.route('/')
def home():
    return redirect(url_for('search'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        f = request.form
        try:
            ex('INSERT INTO users (name, phone, email, password_hash) VALUES (%s,%s,%s,%s)',
               (f['name'], f.get('phone'), f['email'].lower(), generate_password_hash(f['password'])))
            flash('Registration ho gaya. Ab login karo.')
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError:
            flash('Ye email pehle se registered hai.')
    return render_template('auth.html', mode='register')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = q('SELECT * FROM users WHERE email = %s', (request.form['email'].lower(),), one=True)
        if u and check_password_hash(u['password_hash'], request.form['password']):
            session.update(uid=u['user_id'], name=u['name'], admin=u['email'] == ADM)
            return redirect(url_for('search'))
        flash('Galat email ya password.')
    return render_template('auth.html', mode='login')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/search')
@login_req
def search():
    f = request.args; rows = []
    if f.get('start') and f.get('end'):
        s, e = pdt(f['start']), pdt(f['end'])
        if e <= s:
            flash('End time start time se baad hona chahiye.')
        else:
            t, l = f.get('type', ''), f.get('lot', '0')
            rows = q("""SELECT s.slot_id, s.slot_no, s.slot_type, l.lot_name, l.rate_per_hour
                FROM parking_slot s JOIN parking_lot l ON l.lot_id = s.lot_id
                WHERE s.status <> 'MAINTENANCE' AND (%s = '' OR s.slot_type = %s) AND (%s = '0' OR l.lot_id = %s)
                AND NOT EXISTS (SELECT 1 FROM booking b WHERE b.slot_id = s.slot_id
                    AND b.status IN ('BOOKED','CHECKED_IN') AND %s < b.end_time AND %s > b.start_time)""",
                (t, t, l, l, s, e))
    return render_template('search.html', f=f, rows=rows, lots=q('SELECT * FROM parking_lot'),
                           veh=q('SELECT * FROM vehicle WHERE user_id = %s', (session['uid'],)))


@app.route('/book', methods=['POST'])
@login_req
def book():
    f = request.form
    s, e = pdt(f['start']), pdt(f['end'])
    c = db(); cur = c.cursor()
    try:
        c.start_transaction()
        cur.execute('SELECT 1 FROM vehicle WHERE vehicle_id = %s AND user_id = %s', (f['vehicle_id'], session['uid']))
        if not cur.fetchone():
            raise ValueError('Ye vehicle aapka nahi hai.')
        if e <= s:
            raise ValueError('End time start time se baad hona chahiye.')
        cur.execute('SELECT slot_id FROM parking_slot WHERE slot_id = %s FOR UPDATE', (f['slot_id'],))
        cur.fetchall()  # slot row lock ho gaya; concurrent bookings ruk jayengi
        cur.execute("""SELECT 1 FROM booking WHERE slot_id = %s AND status IN ('BOOKED','CHECKED_IN')
                       AND %s < end_time AND %s > start_time""", (f['slot_id'], s, e))
        if cur.fetchone():
            raise ValueError('Ye slot is time pe already booked hai.')
        cur.execute("INSERT INTO booking (start_time, end_time, status, vehicle_id, slot_id) VALUES (%s,%s,'BOOKED',%s,%s)",
                    (s, e, f['vehicle_id'], f['slot_id']))
        c.commit()
        flash('Booking confirm ho gayi!')
    except ValueError as x:
        c.rollback(); flash(str(x))
    except Exception:
        c.rollback(); flash('Booking fail hui. Dobara try karo.')
    finally:
        cur.close(); c.close()
    return redirect(url_for('dash'))


@app.route('/dash', methods=['GET', 'POST'])
@login_req
def dash():
    if request.method == 'POST':
        try:
            ex('INSERT INTO vehicle (reg_no, vehicle_type, user_id) VALUES (%s,%s,%s)',
               (request.form['reg_no'].strip().upper(), request.form['vehicle_type'], session['uid']))
            flash('Vehicle add ho gayi.')
        except mysql.connector.IntegrityError:
            flash('Ye registration number pehle se hai.')
    return render_template('dash.html',
        veh=q('SELECT * FROM vehicle WHERE user_id = %s', (session['uid'],)),
        bks=q("""SELECT b.booking_id, b.start_time, b.end_time, b.status, v.reg_no, s.slot_no, l.lot_name
            FROM booking b JOIN vehicle v ON v.vehicle_id = b.vehicle_id
            JOIN parking_slot s ON s.slot_id = b.slot_id JOIN parking_lot l ON l.lot_id = s.lot_id
            WHERE v.user_id = %s ORDER BY b.start_time DESC""", (session['uid'],)))


@app.route('/booking/<int:bid>/<a>', methods=['POST'])
@login_req
def bstat(bid, a):
    c = db(); cur = c.cursor(dictionary=True)
    try:
        c.start_transaction()
        cur.execute("""SELECT b.status, b.slot_id, b.start_time, b.end_time, l.rate_per_hour
            FROM booking b JOIN vehicle v ON v.vehicle_id = b.vehicle_id
            JOIN parking_slot s ON s.slot_id = b.slot_id JOIN parking_lot l ON l.lot_id = s.lot_id
            WHERE b.booking_id = %s AND v.user_id = %s FOR UPDATE""", (bid, session['uid']))
        b = cur.fetchone()
        if not b:
            raise ValueError('Booking nahi mili.')
        st = b['status']
        if a == 'cancel' and st == 'BOOKED':
            cur.execute("UPDATE booking SET status = 'CANCELLED' WHERE booking_id = %s", (bid,))
        elif a == 'checkin' and st == 'BOOKED':
            cur.execute("UPDATE booking SET status = 'CHECKED_IN' WHERE booking_id = %s", (bid,))
            cur.execute("UPDATE parking_slot SET status = 'OCCUPIED' WHERE slot_id = %s", (b['slot_id'],))
        elif a == 'checkout' and st == 'CHECKED_IN':
            hrs = max(1, math.ceil((b['end_time'] - b['start_time']).total_seconds() / 3600))
            cur.execute("INSERT INTO payment (amount, mode, paid_on, booking_id) VALUES (%s,%s,NOW(),%s)",
                        (hrs * b['rate_per_hour'], request.form.get('mode', 'CASH'), bid))
            cur.execute("UPDATE booking SET status = 'COMPLETED' WHERE booking_id = %s", (bid,))
            cur.execute("UPDATE parking_slot SET status = 'AVAILABLE' WHERE slot_id = %s", (b['slot_id'],))
        else:
            raise ValueError('Ye action abhi allowed nahi hai.')
        c.commit()
        flash('Status update ho gaya.')
    except ValueError as x:
        c.rollback(); flash(str(x))
    except Exception:
        c.rollback(); flash('Kuch galat hua.')
    finally:
        cur.close(); c.close()
    return redirect(url_for('dash'))


@app.route('/admin', methods=['GET', 'POST'])
@login_req
def admin():
    if not session.get('admin'):
        abort(403)
    if request.method == 'POST':
        ex('UPDATE parking_slot SET status = %s WHERE slot_id = %s',
           (request.form['status'], request.form['slot_id']))
        flash('Slot status update ho gaya.')
        return redirect(url_for('admin'))
    return render_template('admin.html',
        rev=q('SELECT COALESCE(SUM(amount), 0) AS t, COUNT(*) AS n FROM payment', one=True),
        occ=q("""SELECT l.lot_name, COUNT(s.slot_id) AS total, SUM(s.status = 'OCCUPIED') AS occupied,
            SUM(s.status = 'MAINTENANCE') AS maint FROM parking_lot l
            LEFT JOIN parking_slot s ON s.lot_id = l.lot_id GROUP BY l.lot_id, l.lot_name"""),
        slots=q("""SELECT s.slot_id, s.slot_no, s.status, l.lot_name FROM parking_slot s
            JOIN parking_lot l ON l.lot_id = s.lot_id ORDER BY l.lot_id, s.slot_no"""),
        logs=q("""SELECT g.changed_on, g.old_status, g.new_status, s.slot_no FROM slot_log g
            JOIN parking_slot s ON s.slot_id = g.slot_id ORDER BY g.changed_on DESC LIMIT 20"""))


if __name__ == '__main__':
    app.run(debug=True)
