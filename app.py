import csv
import io
from flask import Flask, jsonify, request, render_template
import pymysql
from config import Config

app = Flask(__name__)

# Helper function to establish a secure database connection
def get_db_connection():
    return pymysql.connect(
        host=Config.DB_HOST,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

# 1. Base UI Route (NOW SERVES HTML)
@app.route('/')
def home():
    return render_template('index.html')

# 2. Database Connection Test Route
@app.route('/test-db')
def test_db():
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({"status": "success", "message": "Database connected successfully!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 3. Project Overview Route
@app.route('/about')
def about():
    return "This is the Micro-Transaction Analytics Engine."

# 4. Fetch All Transactions (GET API)
@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        sql_query = "SELECT * FROM transactions ORDER BY txn_date DESC"
        cursor.execute(sql_query)
        transactions = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "count": len(transactions),
            "data": transactions
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 5. Add Transaction Manually (POST API)
@app.route('/api/transactions', methods=['POST'])
def add_transaction():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No JSON payload provided"}), 400
        
        amount = data.get('amount')
        txn_date = data.get('txn_date')
        note = data.get('note', '')
        category = data.get('category', 'Uncategorized')
        source = data.get('source', 'Manual')

        if amount is None or float(amount) <= 0:
            return jsonify({"status": "error", "message": "Amount must be greater than zero"}), 400
        if not txn_date:
            return jsonify({"status": "error", "message": "Transaction date is required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        
        sql_query = """
            INSERT INTO transactions (txn_date, amount, note, category, source)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(sql_query, (txn_date, amount, note, category, source))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({"status": "success", "message": "Transaction securely added!"}), 201
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 6. CSV Batch Ingestion & Auto-Categorization (POST API)
@app.route('/api/import-csv', methods=['POST'])
def import_csv():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Empty filename provided"}), 400

    imported_count = 0
    rejected_count = 0

    try:
        file_content = file.stream.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(file_content))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for row in reader:
            txn_date = row.get('date', '').strip()
            amount_str = row.get('amount', '').strip()
            note = row.get('note', '').strip()
            source = row.get('source', 'CSV Import').strip()

            if not txn_date or not amount_str:
                rejected_count += 1
                continue
            
            try:
                amount = float(amount_str)
                if amount <= 0:
                    rejected_count += 1
                    continue
            except ValueError:
                rejected_count += 1
                continue

            category = 'Uncategorized'
            lower_note = note.lower()
            if any(k in lower_note for k in ['zomato', 'swiggy', 'canteen', 'tea', 'coffee', 'snacks']):
                category = 'Food'
            elif any(k in lower_note for k in ['uber', 'ola', 'auto', 'metro', 'petrol', 'fuel', 'chetak', 'scooter']):
                category = 'Travel'
            elif any(k in lower_note for k in ['movie', 'cinema', 'theatre', 'show']):
                category = 'Entertainment'
            elif any(k in lower_note for k in ['recharge', 'wifi', 'electricity', 'bill']):
                category = 'Utilities'

            check_sql = """
                SELECT COUNT(*) as count FROM transactions 
                WHERE txn_date = %s AND amount = %s AND note = %s AND source = %s
            """
            cursor.execute(check_sql, (txn_date, amount, note, source))
            result = cursor.fetchone()
            
            if result['count'] > 0:
                rejected_count += 1
                continue

            sql = """
                INSERT INTO transactions (txn_date, amount, note, category, source)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (txn_date, amount, note, category, source))
            imported_count += 1

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "status": "success",
            "imported": imported_count,
            "rejected": rejected_count
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 7. Micro-Transaction Analytics (GET API)
@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    try:
        MICRO_THRESHOLD = 100.00 
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT SUM(amount) as total_spent FROM transactions")
        total_result = cursor.fetchone()
        total_spent = float(total_result['total_spent'] or 0)
        
        micro_sql = """
            SELECT SUM(amount) as micro_spent, COUNT(*) as micro_count 
            FROM transactions 
            WHERE amount <= %s
        """
        cursor.execute(micro_sql, (MICRO_THRESHOLD,))
        micro_result = cursor.fetchone()
        
        micro_spent = float(micro_result['micro_spent'] or 0)
        micro_count = int(micro_result['micro_count'] or 0)
        
        cursor.close()
        conn.close()
        
        leakage_percentage = 0
        if total_spent > 0:
            leakage_percentage = round((micro_spent / total_spent) * 100, 2)
            
        return jsonify({
            "status": "success",
            "threshold": MICRO_THRESHOLD,
            "total_spent": total_spent,
            "micro_spent": micro_spent,
            "micro_count": micro_count,
            "leakage_percentage": leakage_percentage
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 8. Category Breakdown Analysis (GET API)
@app.route('/api/analytics/categories', methods=['GET'])
def get_category_analytics():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        sql = """
            SELECT category, SUM(amount) as total_spent, COUNT(*) as transaction_count 
            FROM transactions 
            GROUP BY category 
            ORDER BY total_spent DESC
        """
        cursor.execute(sql)
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        formatted_results = []
        for row in results:
            formatted_results.append({
                "category": row['category'],
                "total_spent": float(row['total_spent'] or 0),
                "transaction_count": row['transaction_count']
            })
            
        return jsonify({
            "status": "success",
            "data": formatted_results
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)