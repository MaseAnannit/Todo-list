import os
import psycopg2
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# --- DATABASE CONNECTION ---
def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        database=os.environ.get("DB_NAME", "flaskdb"),
        user=os.environ.get("DB_USER", "flaskuser"),
        password=os.environ.get("DB_PASSWORD", "flaskpass")
    )

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
            done BOOLEAN DEFAULT FALSE
        )
    ''')

    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='todos' AND column_name='order_index'
    """)
    exists = cur.fetchone()
    if not exists:
        cur.execute("ALTER TABLE todos ADD COLUMN order_index INTEGER DEFAULT 0;")


    # Add due_date column if it doesn't exist
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='todos' AND column_name='due_date'
    """)
    if not cur.fetchone():
        cur.execute('ALTER TABLE todos ADD COLUMN due_date DATE')

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

# --- GET USER FROM DB ---
def get_user(username):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE username = %s', (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

# --- HOME REDIRECT ---
@app.route('/')
def home():
    if 'username' in session:
        return redirect(url_for('login'))
    return redirect('/login')

# --- REGISTER ---
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

# --- LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_user(username)

        if user and check_password_hash(user[2], password):
            session['username'] = username
            return redirect(url_for('todos'))
        else:
            error = 'Invalid username or password.'

    return render_template('login.html', error=error)

# --- LOGOUT ---
@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect('/login')

# --- TODO LIST ---
@app.route('/todos', methods=['GET', 'POST'])
def todos():
    if 'username' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cur = conn.cursor()

    # Get user ID
    cur.execute('SELECT id FROM users WHERE username = %s', (session['username'],))
    user_id = cur.fetchone()[0]

    # Handle new task
    if request.method == 'POST':
        task = request.form['task']
        due_date = request.form.get('due_date') or None

        if task:
            cur.execute(
                'INSERT INTO todos (user_id, content, due_date) VALUES (%s, %s, %s)',
                (user_id, task, due_date)
            )
            conn.commit()

    # Get tasks
    cur.execute(
        'SELECT id, content, done, due_date FROM todos WHERE user_id = %s ORDER BY due_date NULLS LAST, id DESC',
        (user_id,)
    )
    tasks = cur.fetchall()

    cur.close()
    conn.close()
    return render_template('todos.html', tasks=tasks)

# --- DELETE TODO ---
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

# --- TOGGLE TODO ---
@app.route('/todos/<int:todo_id>/toggle')
def toggle_todo(todo_id):
    if 'username' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        UPDATE todos
        SET done = NOT done
        WHERE id = %s AND user_id = (SELECT id FROM users WHERE username = %s)
    ''', (todo_id, session['username']))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/todos')

@app.route('/reorder', methods=['POST'])
def reorder():
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
