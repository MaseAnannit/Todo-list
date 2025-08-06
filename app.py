import os
import time
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# --- DATABASE CONNECTION ---
def get_db_connection(retries=5, delay=2):  
    for i in range(retries):
        try:
            return psycopg2.connect(
                host=os.environ["DB_HOST"],
                dbname=os.environ["DB_NAME"],
                user=os.environ["DB_USER"],
                password=os.environ["DB_PASSWORD"]
            )
        except psycopg2.OperationalError as e:
            print(f"DB not ready yet (attempt {i+1}/{retries}): {e}")
            time.sleep(delay)
    raise Exception("Could not connect to DB after retries")

# --- INITIALIZE DATABASE ---
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    # Create users table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    # Create todos table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS todos (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            content TEXT NOT NULL,
            done BOOLEAN DEFAULT FALSE,
            due_date DATE,
            status TEXT DEFAULT 'Ongoing',
            order_index INTEGER DEFAULT 0
        )
    ''')

    # Ensure admin user exists
    cur.execute('SELECT * FROM users WHERE username = %s', ('admin',))
    if not cur.fetchone():
        cur.execute(
            'INSERT INTO users (username, password) VALUES (%s, %s)',
            ('admin', generate_password_hash('password123'))
        )

    conn.commit()
    cur.close()
    conn.close()
    print(":p Database initialized.")
#a
# --- GET USER FROM DB ---
def get_user(username):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE username = %s', (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

# --- ROUTES ---

@app.route('/')
def home():
    return redirect('/login') if 'username' not in session else redirect('/todos')

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    success = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if not username or not password:
            error = 'Both fields are required.'
        else:
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                hashed_pw = generate_password_hash(password)
                cur.execute('INSERT INTO users (username, password) VALUES (%s, %s)', (username, hashed_pw))
                conn.commit()
                success = 'Registration successful. You can now log in.'
            except psycopg2.errors.UniqueViolation:
                error = 'Username already exists.'
            except Exception as e:
                error = str(e)
            finally:
                conn.rollback()
                cur.close()
                conn.close()
    return render_template('register.html', error=error, success=success)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_user(username)
        if user and check_password_hash(user[2], password):
            session['username'] = username
            session['user_id'] = user[0]
            return redirect(url_for('todos'))
        else:
            error = 'Invalid username or password.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/todos', methods=['GET', 'POST'])
def todos():
    if 'user_id' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        content = request.form['task'].strip()
        due_date = request.form['due_date'] or None
        status = request.form['status']

        # Check if the task already exists for this user
        cur.execute('''
            SELECT 1 FROM todos 
            WHERE user_id = %s AND content = %s AND (due_date = %s OR (due_date IS NULL AND %s IS NULL))
        ''', (session['user_id'], content, due_date, due_date))
        
        if not cur.fetchone():
            cur.execute('''
                INSERT INTO todos (user_id, content, due_date, status)
                VALUES (%s, %s, %s, %s)
            ''', (session['user_id'], content, due_date, status))
            conn.commit()

    # Load tasks
    cur.execute('''
        SELECT id, content, done, due_date, status
        FROM todos
        WHERE user_id = %s
        ORDER BY due_date NULLS LAST, id DESC
    ''', (session['user_id'],))
    tasks = cur.fetchall()
    conn.close()

    # Group by status
    grouped = {'Planned': [], 'Ongoing': [], 'Completed': []}
    for task in tasks:
        grouped.get(task[4], []).append(task)

    return render_template('todos.html', grouped_tasks=grouped)

@app.route('/todos/<int:todo_id>/delete')
def delete_todo(todo_id):
    if 'username' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        DELETE FROM todos
        WHERE id = %s AND user_id = (SELECT id FROM users WHERE username = %s)
    ''', (todo_id, session['username']))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/todos')

@app.route('/todos/<int:task_id>/move', methods=['POST'])
def move_task(task_id):
    if 'user_id' not in session:
        return '', 403

    new_status = request.json.get('status')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        UPDATE todos
        SET status = %s
        WHERE id = %s AND user_id = %s
    ''', (new_status, task_id, session['user_id']))
    conn.commit()
    conn.close()
    return '', 204


@app.route('/reorder', methods=['POST'])
def reorder():
    if 'user_id' not in session:
        return redirect('/login')
    data = request.get_json()
    user_id = session['user_id']
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for item in data:
                cur.execute(
                    "UPDATE todos SET order_index = %s WHERE id = %s AND user_id = %s",
                    (item['position'], item['id'], user_id)
                )
        conn.commit()
    return '', 204

# --- MAIN ---
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
