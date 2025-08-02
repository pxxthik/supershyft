from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from datetime import datetime, timedelta, date
import sqlite3
import json
from typing import Dict, List, Tuple
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'

# Admin Configuration
ADMIN_PASSWORD = 'admin123'  # Change this to your desired password

# Configuration
BLOOD_TEST_START_TIME = '09:00'
BLOOD_TEST_END_TIME = '13:00'
CONSULTATION_START_TIME = '10:00'
CONSULTATION_END_TIME = '18:00'
SLOT_DURATION_BLOOD = 15  # minutes
SLOT_DURATION_CONSULTATION = 30  # minutes
BLOOD_TEST_CABINS_COUNT = 4
CONSULTATION_CABINS_COUNT = 4
PEOPLE_PER_BLOOD_CABIN = 4
PEOPLE_PER_CONSULTATION_CABIN = 1

def admin_required(f):
    """Decorator to require admin authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_authenticated'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect('bookings.db')
    cursor = conn.cursor()
    
    # Create bookings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            age INTEGER NOT NULL,
            gender TEXT NOT NULL,
            phone TEXT NOT NULL,
            blood_test_date TEXT,
            blood_test_time TEXT,
            blood_test_cabin INTEGER,
            consultation_date TEXT,
            consultation_time TEXT,
            consultation_cabin INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def is_valid_date(date_string: str) -> bool:
    """Check if the date string is valid and not in the past"""
    try:
        input_date = datetime.strptime(date_string, '%Y-%m-%d').date()
        today = date.today()
        return input_date >= today
    except ValueError:
        return False

def is_weekend(date_string: str) -> bool:
    """Check if the date falls on a weekend"""
    try:
        input_date = datetime.strptime(date_string, '%Y-%m-%d').date()
        return input_date.weekday() >= 5  # Saturday = 5, Sunday = 6
    except ValueError:
        return True  # If invalid date, treat as weekend (not available)

def generate_time_slots(start_time: str, end_time: str, duration: int) -> List[str]:
    """Generate time slots between start and end time with given duration"""
    slots = []
    start = datetime.strptime(start_time, '%H:%M')
    end = datetime.strptime(end_time, '%H:%M')
    
    current = start
    while current + timedelta(minutes=duration) <= end:
        slots.append(current.strftime('%H:%M'))
        current += timedelta(minutes=duration)
    
    return slots

def get_blood_test_cabin_availability(date: str) -> Dict:
    """Get available slots per cabin for blood tests on a given date"""
    if not is_valid_date(date):
        return {}
    
    conn = sqlite3.connect('bookings.db')
    cursor = conn.cursor()
    
    # Get total time slots available for the day
    total_slots = len(generate_time_slots(BLOOD_TEST_START_TIME, BLOOD_TEST_END_TIME, SLOT_DURATION_BLOOD))
    
    # Get booked slots per cabin
    cursor.execute('''
        SELECT blood_test_cabin, COUNT(*) as booked_count
        FROM bookings 
        WHERE blood_test_date = ? AND blood_test_cabin IS NOT NULL
        GROUP BY blood_test_cabin
    ''', (date,))
    
    booked_per_cabin = dict(cursor.fetchall())
    
    # Calculate available slots per cabin
    cabin_availability = {}
    for cabin in range(1, BLOOD_TEST_CABINS_COUNT + 1):
        booked_count = booked_per_cabin.get(cabin, 0)
        available_slots = (total_slots * PEOPLE_PER_BLOOD_CABIN) - booked_count
        cabin_availability[cabin] = max(0, available_slots)
    
    conn.close()
    return cabin_availability

def get_blood_test_available_slots(date: str, cabin: int) -> List[str]:
    """Get available time slots for a specific cabin on a given date"""
    if not is_valid_date(date):
        return []
    
    conn = sqlite3.connect('bookings.db')
    cursor = conn.cursor()
    
    # Get all possible time slots
    all_slots = generate_time_slots(BLOOD_TEST_START_TIME, BLOOD_TEST_END_TIME, SLOT_DURATION_BLOOD)
    
    # Get booked slots for this cabin
    cursor.execute('''
        SELECT blood_test_time, COUNT(*) as booked_count
        FROM bookings 
        WHERE blood_test_date = ? AND blood_test_cabin = ?
        GROUP BY blood_test_time
    ''', (date, cabin))
    
    booked_slots = dict(cursor.fetchall())
    
    # Filter available slots
    available_slots = []
    for slot in all_slots:
        booked_count = booked_slots.get(slot, 0)
        if booked_count < PEOPLE_PER_BLOOD_CABIN:
            available_slots.append(slot)
    
    conn.close()
    return available_slots

def get_blood_test_slots_with_availability(date: str, cabin: int) -> Dict[str, int]:
    """Get time slots with availability count for a specific cabin on a given date"""
    if not is_valid_date(date):
        return {}
    
    conn = sqlite3.connect('bookings.db')
    cursor = conn.cursor()
    
    # Get all possible time slots
    all_slots = generate_time_slots(BLOOD_TEST_START_TIME, BLOOD_TEST_END_TIME, SLOT_DURATION_BLOOD)
    
    # Get booked slots for this cabin
    cursor.execute('''
        SELECT blood_test_time, COUNT(*) as booked_count
        FROM bookings 
        WHERE blood_test_date = ? AND blood_test_cabin = ?
        GROUP BY blood_test_time
    ''', (date, cabin))
    
    booked_slots = dict(cursor.fetchall())
    
    # Create slots with availability
    slots_with_availability = {}
    for slot in all_slots:
        booked_count = booked_slots.get(slot, 0)
        available_count = PEOPLE_PER_BLOOD_CABIN - booked_count
        slots_with_availability[slot] = max(0, available_count)
    
    conn.close()
    return slots_with_availability

def get_consultation_cabin_availability(date: str) -> Dict:
    """Get available slots per cabin for consultations on a given date"""
    if not is_valid_date(date):
        return {}
    
    conn = sqlite3.connect('bookings.db')
    cursor = conn.cursor()
    
    # Get total time slots available for the day
    total_slots = len(generate_time_slots(CONSULTATION_START_TIME, CONSULTATION_END_TIME, SLOT_DURATION_CONSULTATION))
    
    # Get booked slots per cabin
    cursor.execute('''
        SELECT consultation_cabin, COUNT(*) as booked_count
        FROM bookings 
        WHERE consultation_date = ? AND consultation_cabin IS NOT NULL
        GROUP BY consultation_cabin
    ''', (date,))
    
    booked_per_cabin = dict(cursor.fetchall())
    
    # Calculate available slots per cabin (1 person per slot for consultations)
    cabin_availability = {}
    for cabin in range(1, CONSULTATION_CABINS_COUNT + 1):
        booked_count = booked_per_cabin.get(cabin, 0)
        available_slots = total_slots - booked_count
        cabin_availability[cabin] = max(0, available_slots)
    
    conn.close()
    return cabin_availability

def get_consultation_available_slots(date: str, cabin: int) -> List[str]:
    """Get available time slots for a specific consultation cabin on a given date"""
    if not is_valid_date(date):
        return []
    
    conn = sqlite3.connect('bookings.db')
    cursor = conn.cursor()
    
    # Get all possible time slots
    all_slots = generate_time_slots(CONSULTATION_START_TIME, CONSULTATION_END_TIME, SLOT_DURATION_CONSULTATION)
    
    # Get booked slots for this cabin
    cursor.execute('''
        SELECT consultation_time
        FROM bookings 
        WHERE consultation_date = ? AND consultation_cabin = ?
    ''', (date, cabin))
    
    booked_slots = [row[0] for row in cursor.fetchall()]
    
    # Filter available slots (only 1 person per consultation slot)
    available_slots = [slot for slot in all_slots if slot not in booked_slots]
    
    conn.close()
    return available_slots

@app.route('/')
def index():
    """Main registration form"""
    return render_template('index.html')

@app.route('/get_blood_test_cabins')
def get_blood_test_cabins():
    """API endpoint to get available cabins for blood tests"""
    date_param = request.args.get('date')
    if not date_param:
        return jsonify({'error': 'Date parameter is required'})
    
    if not is_valid_date(date_param):
        return jsonify({'error': 'Invalid date or date is in the past'})
    
    cabin_availability = get_blood_test_cabin_availability(date_param)
    return jsonify(cabin_availability)

@app.route('/get_blood_test_slots')
def get_blood_test_slots():
    """API endpoint to get available time slots for a specific blood test cabin"""
    date_param = request.args.get('date')
    cabin_param = request.args.get('cabin')
    
    if not date_param or not cabin_param:
        return jsonify({'error': 'Date and cabin parameters are required'})
    
    try:
        cabin = int(cabin_param)
    except ValueError:
        return jsonify({'error': 'Invalid cabin number'})
    
    if not is_valid_date(date_param):
        return jsonify({'error': 'Invalid date or date is in the past'})
    
    # Return slots with availability count
    slots_with_availability = get_blood_test_slots_with_availability(date_param, cabin)
    return jsonify(slots_with_availability)

@app.route('/get_consultation_cabins_availability')
def get_consultation_cabins_availability():
    """API endpoint to get available cabins for consultations"""
    date_param = request.args.get('date')
    if not date_param:
        return jsonify({'error': 'Date parameter is required'})
    
    if not is_valid_date(date_param):
        return jsonify({'error': 'Invalid date or date is in the past'})
    
    cabin_availability = get_consultation_cabin_availability(date_param)
    return jsonify(cabin_availability)

@app.route('/get_consultation_slots')
def get_consultation_slots():
    """API endpoint to get available time slots for a specific consultation cabin"""
    date_param = request.args.get('date')
    cabin_param = request.args.get('cabin')
    
    if not date_param or not cabin_param:
        return jsonify({'error': 'Date and cabin parameters are required'})
    
    try:
        cabin = int(cabin_param)
    except ValueError:
        return jsonify({'error': 'Invalid cabin number'})
    
    if not is_valid_date(date_param):
        return jsonify({'error': 'Invalid date or date is in the past'})
    
    available_slots = get_consultation_available_slots(date_param, cabin)
    return jsonify(available_slots)

@app.route('/submit_booking', methods=['POST'])
def submit_booking():
    """Handle form submission and create booking"""
    try:
        # Get form data
        name = request.form.get('name')
        email = request.form.get('email')
        age = int(request.form.get('age'))
        gender = request.form.get('gender')
        phone = request.form.get('phone')
        blood_test_date = request.form.get('blood_test_date')
        blood_test_time = request.form.get('blood_test_time')
        blood_test_cabin = int(request.form.get('blood_test_cabin'))
        consultation_date = request.form.get('consultation_date')
        consultation_time = request.form.get('consultation_time')
        consultation_cabin = request.form.get('consultation_cabin')
        
        # Convert consultation_cabin to int if provided
        if consultation_cabin:
            consultation_cabin = int(consultation_cabin)
        else:
            consultation_cabin = None
        
        # Validate required fields
        if not all([name, email, age, gender, phone, blood_test_date, blood_test_time, blood_test_cabin]):
            flash('Please fill in all required fields')
            return redirect(url_for('index'))
        
        # Validate blood test date
        if not is_valid_date(blood_test_date):
            flash('Invalid blood test date or date is in the past')
            return redirect(url_for('index'))
        
        # Check if blood test slot is still available
        available_slots = get_blood_test_available_slots(blood_test_date, blood_test_cabin)
        if blood_test_time not in available_slots:
            flash('Selected blood test slot is no longer available')
            return redirect(url_for('index'))
        
        # Validate consultation slot if provided
        if consultation_date and consultation_time and consultation_cabin:
            if not is_valid_date(consultation_date):
                flash('Invalid consultation date or date is in the past')
                return redirect(url_for('index'))
            
            consultation_available = get_consultation_available_slots(consultation_date, consultation_cabin)
            if consultation_time not in consultation_available:
                flash('Selected consultation slot is no longer available')
                return redirect(url_for('index'))
        
        # Save booking to database
        conn = sqlite3.connect('bookings.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO bookings (
                name, email, age, gender, phone, 
                blood_test_date, blood_test_time, blood_test_cabin,
                consultation_date, consultation_time, consultation_cabin
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            name, email, age, gender, phone,
            blood_test_date, blood_test_time, blood_test_cabin,
            consultation_date, consultation_time, consultation_cabin
        ))
        
        conn.commit()
        booking_id = cursor.lastrowid
        conn.close()
        
        success_message = f'Booking confirmed! Your booking ID is {booking_id}. Blood test assigned to Cabin {blood_test_cabin}.'
        if consultation_cabin:
            success_message += f' Consultation assigned to Cabin {consultation_cabin}.'
        
        flash(success_message)
        return redirect(url_for('booking_success', booking_id=booking_id))
        
    except Exception as e:
        flash(f'Error processing booking: {str(e)}')
        return redirect(url_for('index'))

@app.route('/booking_success/<int:booking_id>')
def booking_success(booking_id):
    """Display booking confirmation"""
    conn = sqlite3.connect('bookings.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM bookings WHERE id = ?', (booking_id,))
    booking = cursor.fetchone()
    conn.close()
    
    if not booking:
        flash('Booking not found')
        return redirect(url_for('index'))
    
    return render_template('success.html', booking=booking)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['admin_authenticated'] = True
            flash('Login successful!')
            return redirect(url_for('admin'))
        else:
            flash('Invalid password. Please try again.')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin_authenticated', None)
    flash('You have been logged out.')
    return redirect(url_for('admin_login'))

@app.route('/admin')
@admin_required
def admin():
    """Admin panel to view all bookings"""
    conn = sqlite3.connect('bookings.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, email, age, gender, phone, 
               blood_test_date, blood_test_time, blood_test_cabin,
               consultation_date, consultation_time, consultation_cabin,
               created_at
        FROM bookings 
        ORDER BY created_at DESC
    ''')
    bookings = cursor.fetchall()
    conn.close()
    
    return render_template('admin.html', bookings=bookings)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
