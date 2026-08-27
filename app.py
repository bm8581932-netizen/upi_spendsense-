import csv
import io
import re
from datetime import datetime
from flask import Flask, jsonify, request, render_template
import pymysql
from config import Config

app = Flask(__name__)

# System Constants
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB Limit to prevent server crashes
MICRO_TRANSACTION_THRESHOLD = 100.00 # Anything <= 100 is a micro-transaction

def get_db_connection():
    """Establishes and returns a database connection using PyMySQL."""
    return pymysql.connect(
        host=Config.DB_HOST,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

def clean_and_normalize_merchant(note):
    """
    Cleans raw transaction notes to extract a normalized merchant name.
    Example: 'UPI/SWIGGY/12847' -> 'Swiggy'
    """
    if not note or not note.strip():
        return "Unknown"

    text = note.strip()
    lower = text.lower()

    # Known merchant dictionary
    merchants = {
        'swiggy': 'Swiggy', 'zomato': 'Zomato', 'canteen': 'Canteen', 
        'chai': 'Tea Stall', 'tea': 'Tea Stall', 'coffee': 'Coffee Shop',
        'uber': 'Uber', 'ola': 'Ola', 'rapido': 'Rapido', 'metro': 'Metro Rail',
        'petrol': 'Fuel Station', 'fuel': 'Fuel Station', 'blinkit': 'Blinkit', 
        'zepto': 'Zepto', 'recharge': 'Mobile Recharge', 'movie': 'Cinema / Theatre',
        'theatre': 'Cinema / Theatre'
    }

    # 1. Check if we know the merchant
    for key, normalized in merchants.items():
        if key in lower:
            return normalized

    # 2. If unknown, clean up the UPI garbage using Regex
    cleaned = re.sub(r'(?i)^(upi|paytm|gpay|phonepe)[-\s:/]*', '', text)
    cleaned = re.sub(r'[-_/\d]+', ' ', cleaned).strip()
    return cleaned.title() if cleaned else "General Merchant"

def categorize_transaction(note, merchant):
    """Rule-based categorization based on note and cleaned merchant."""
    combined = f"{note} {merchant}".lower()
    
    if any(k in combined for k in ['zomato', 'swiggy', 'canteen', 'tea', 'chai', 'coffee', 'snacks', 'food']):
        return 'Food'
    elif any(k in combined for k in ['uber', 'ola', 'rapido', 'auto', 'metro', 'petrol', 'fuel', 'bus']):
        return 'Travel'
    elif any(k in combined for k in ['movie', 'cinema', 'theatre', 'show', 'netflix']):
        return 'Entertainment'
    elif any(k in combined for k in ['recharge', 'wifi', 'electricity', 'bill']):
        return 'Utilities'
    elif any(k in combined for k in ['blinkit', 'zepto', 'amazon', 'flipkart', 'grocery']):
        return 'Shopping'
        
    return 'Uncategorized'
# =========================================================================
# ROUTES: FRONTEND & TRANSACTIONS
# =========================================================================

@app.route('/')
def home():
    """Serves the main dashboard application."""
    return render_template('index.html')

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Retrieves recent transactions for the dashboard table."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Fetch the latest 100 transactions
        cursor.execute("SELECT * FROM transactions ORDER BY txn_date DESC, id DESC LIMIT 100")
        records = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({"status": "success", "count": len(records), "data": records}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/transactions/import', methods=['POST'])
def import_csv():
    """Ingests, validates, normalizes, deduplicates, and commits CSV bank statements."""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded."}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"status": "error", "message": "Empty filename selected."}), 400

    # 1. Security Check: File Size Limit (Prevents Server Overload)
    file_bytes = file.stream.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        return jsonify({"status": "error", "message": "File exceeds maximum allowed size of 2MB."}), 400

    try:
        # decode('utf-8-sig') automatically removes the hidden BOM character some Excel CSVs have
        content = file_bytes.decode('utf-8-sig') 
    except UnicodeDecodeError:
        return jsonify({"status": "error", "message": "Invalid encoding. Please upload UTF-8 CSV."}), 400

    reader = csv.DictReader(io.StringIO(content))
    
    if not reader.fieldnames:
        return jsonify({"status": "error", "message": "The uploaded CSV file is empty."}), 400

    # 2. Validation: Ensure required columns exist
    headers = {h.strip().lower(): h for h in reader.fieldnames}
    if 'date' not in headers or 'amount' not in headers:
        return jsonify({"status": "error", "message": "Missing required columns: 'date' and 'amount'."}), 400

    date_col = headers['date']
    amount_col = headers['amount']
    note_col = headers.get('note') or headers.get('description')
    source_col = headers.get('source')

    imported_count, duplicate_count, invalid_count = 0, 0, 0

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        for row in reader:
            raw_date = row.get(date_col, '').strip()
            raw_amount = row.get(amount_col, '').strip()
            note = row.get(note_col, '').strip() if note_col else 'Direct Transfer'
            source = row.get(source_col, '').strip() if source_col else 'CSV Statement'

            # Parse Date Safely
            parsed_date = None
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'):
                try:
                    parsed_date = datetime.strptime(raw_date, fmt).strftime('%Y-%m-%d')
                    break
                except ValueError:
                    continue

            if not parsed_date:
                invalid_count += 1
                continue

            # Parse Amount Safely (stripping currency symbols)
            try:
                amount = float(re.sub(r'[^\d.]', '', raw_amount))
                if amount <= 0:
                    invalid_count += 1
                    continue
            except (ValueError, TypeError):
                invalid_count += 1
                continue

            # 3. Apply Core Intelligence
            merchant = clean_and_normalize_merchant(note)
            category = categorize_transaction(note, merchant)

            # 4. Prevent Duplicates seamlessly
            check_sql = "SELECT id FROM transactions WHERE txn_date=%s AND amount=%s AND note=%s LIMIT 1"
            cursor.execute(check_sql, (parsed_date, amount, note))
            if cursor.fetchone():
                duplicate_count += 1
                continue

            # 5. Insert Valid Record
            insert_sql = """
                INSERT INTO transactions (txn_date, amount, note, merchant, category, source)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_sql, (parsed_date, amount, note, merchant, category, source))
            imported_count += 1

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return jsonify({
        "status": "success",
        "imported": imported_count,
        "duplicates_skipped": duplicate_count,
        "invalid_rows": invalid_count
    }), 200
# =========================================================================
# ROUTES: ANALYTICS, HABITS, LEAKAGE SCORE, ANOMALIES
# =========================================================================

@app.route('/api/analytics/summary', methods=['GET'])
def get_analytics_summary():
    """Computes overall spending, micro-spending, and leakage overview."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Total spend & count
        cursor.execute("SELECT COUNT(*) as total_count, COALESCE(SUM(amount), 0) as total_spent FROM transactions")
        total_res = cursor.fetchone()
        total_spent = float(total_res['total_spent'])
        total_count = int(total_res['total_count'])

        # Micro spend & count
        cursor.execute("""
            SELECT COUNT(*) as micro_count, COALESCE(SUM(amount), 0) as micro_spent 
            FROM transactions WHERE amount <= %s
        """, (MICRO_TRANSACTION_THRESHOLD,))
        micro_res = cursor.fetchone()
        micro_spent = float(micro_res['micro_spent'])
        micro_count = int(micro_res['micro_count'])

        cursor.close()
        conn.close()

        leakage_pct = round((micro_spent / total_spent * 100), 2) if total_spent > 0 else 0.0

        return jsonify({
            "status": "success", "threshold": MICRO_TRANSACTION_THRESHOLD,
            "total_spent": total_spent, "total_count": total_count,
            "micro_spent": micro_spent, "micro_count": micro_count,
            "leakage_percentage": leakage_pct
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/analytics/categories', methods=['GET'])
def get_category_breakdown():
    """Computes categorical aggregations."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            SELECT 
                category, 
                COALESCE(SUM(amount), 0) as total_spent, 
                COUNT(*) as transaction_count
            FROM transactions 
            GROUP BY category 
            ORDER BY total_spent DESC
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Format decimals for JSON safety
        for r in rows:
            r['total_spent'] = float(r['total_spent'])

        return jsonify({"status": "success", "data": rows}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/analytics/habits', methods=['GET'])
def get_recurring_habits():
    """Identifies recurring micro-spending patterns (Vampire Habits)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            SELECT 
                merchant, amount, COUNT(*) as frequency, SUM(amount) as total_cost
            FROM transactions
            WHERE amount <= %s
            GROUP BY merchant, amount
            HAVING COUNT(*) >= 3
            ORDER BY frequency DESC, total_cost DESC
        """
        cursor.execute(sql, (MICRO_TRANSACTION_THRESHOLD,))
        habits = cursor.fetchall()
        cursor.close()
        conn.close()

        for h in habits:
            h['amount'] = float(h['amount'])
            h['total_cost'] = float(h['total_cost'])

        return jsonify({"status": "success", "count": len(habits), "data": habits}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/analytics/monthly', methods=['GET'])
def get_monthly_analysis():
    """Computes Month-over-Month spending dynamics."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            SELECT 
                DATE_FORMAT(txn_date, '%%Y-%%m') as month_key,
                COALESCE(SUM(amount), 0) as total_spent,
                COALESCE(SUM(CASE WHEN amount <= %s THEN amount ELSE 0 END), 0) as micro_spent
            FROM transactions
            GROUP BY month_key
            ORDER BY month_key ASC
        """
        cursor.execute(sql, (MICRO_TRANSACTION_THRESHOLD,))
        months = cursor.fetchall()
        cursor.close()
        conn.close()

        formatted_months = []
        for m in months:
            formatted_months.append({
                "month": m['month_key'],
                "total_spent": float(m['total_spent']),
                "micro_spent": float(m['micro_spent'])
            })

        return jsonify({"status": "success", "data": formatted_months}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/analytics/leakage-score', methods=['GET'])
def get_leakage_score():
    """Computes a transparent Spending Leakage Score (0 - 100)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get overall metrics
        cursor.execute("""
            SELECT COUNT(*) as total_count, COALESCE(SUM(amount), 0) as total_spent,
            SUM(CASE WHEN amount <= %s THEN 1 ELSE 0 END) as micro_count,
            COALESCE(SUM(CASE WHEN amount <= %s THEN amount ELSE 0 END), 0) as micro_spent
            FROM transactions
        """, (MICRO_TRANSACTION_THRESHOLD, MICRO_TRANSACTION_THRESHOLD))
        stats = cursor.fetchone()
        cursor.close()
        conn.close()

        total_spent = float(stats['total_spent'])
        total_count = int(stats['total_count'])
        micro_spent = float(stats['micro_spent'])
        micro_count = int(stats['micro_count'] or 0)

        if total_spent == 0:
            return jsonify({"status": "success", "score": 0, "rating": "No Data", "reasons": []}), 200

        # Calculate Score Rules
        score_val = (micro_spent / total_spent) * 50  # Up to 50 points for money leaked
        score_freq = (micro_count / total_count) * 50 # Up to 50 points for transaction frequency
        
        final_score = int(min(100.0, score_val + score_freq))
        
        rating = "Low Leakage"
        if final_score >= 70:
            rating = "Severe Leakage"
        elif final_score >= 40:
            rating = "Moderate Leakage"
            
        reasons = [f"Micro-spend ratio accounts for {int(score_val)} points.", 
                   f"Transaction frequency accounts for {int(score_freq)} points."]

        return jsonify({
            "status": "success", "score": final_score, "rating": rating, "reasons": reasons
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/analytics/anomalies', methods=['GET'])
def get_spending_anomalies():
    """Detects statistical category anomalies based on historical bounds."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Calculate Average and Standard Deviation per category
        cursor.execute("""
            SELECT category, AVG(amount) as avg_amount, STDDEV(amount) as std_amount
            FROM transactions GROUP BY category HAVING COUNT(*) >= 3
        """)
        benchmarks = {row['category']: row for row in cursor.fetchall()}

        cursor.execute("SELECT * FROM transactions ORDER BY txn_date DESC")
        all_tx = cursor.fetchall()
        cursor.close()
        conn.close()

        anomalies = []
        for tx in all_tx:
            cat = tx['category']
            amt = float(tx['amount'])
            if cat in benchmarks:
                b = benchmarks[cat]
                avg = float(b['avg_amount'])
                std = float(b['std_amount'] or 0)
                # Anomaly Rule: Must be > Average + (2.5 * StdDev) AND at least 500 above average
                threshold = max(avg + (2.5 * std), avg + 500.0)

                if amt > threshold:
                    anomalies.append({
                        "id": tx['id'], "merchant": tx['merchant'], "amount": amt, "category": cat,
                        "explanation": f"Amount ₹{amt:.2f} is exceptionally higher than your {cat} average (₹{avg:.2f})."
                    })

        return jsonify({"status": "success", "count": len(anomalies), "data": anomalies}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/analytics/what-if', methods=['POST'])
def calculate_what_if():
    """Simulates monthly and annual savings by curbing micro-transactions."""
    try:
        data = request.json or {}
        reduction_pct = float(data.get('reduction_percentage', 25))
        micro_spent = float(data.get('micro_spent', 0))

        monthly_savings = (reduction_pct / 100.0) * micro_spent
        annual_savings = monthly_savings * 12

        return jsonify({
            "status": "success", 
            "monthly_savings": round(monthly_savings, 2), 
            "annual_savings": round(annual_savings, 2)
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)