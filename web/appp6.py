from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'super_secret_key'

DB_PATH = os.path.join(os.path.dirname(__file__), 'study_var.db')

def query_db(query, args=(), one=False):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.execute(query, args)
    rv = cur.fetchall()
    con.close()
    return rv[0] if rv and one else rv

def execute_db(query, args=()):
    con = sqlite3.connect(DB_PATH)
    cur = con.execute(query, args)
    con.commit()
    con.close()

def get_columns(table):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.execute(f"SELECT * FROM {table} LIMIT 1")
    return [desc[0] for desc in cur.description]

def get_primary_key(table):
    con = sqlite3.connect(DB_PATH)
    cur = con.execute(f"PRAGMA table_info({table})")
    for row in cur.fetchall():
        if row[5]:
            return row[1]
    return 'id'

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    wait_time = 0
    now = datetime.now()

    session.setdefault('failed_attempts', 0)
    session.setdefault('lock_until', None)

    if session['lock_until']:
        lock_until = datetime.fromisoformat(session['lock_until'])
        if now < lock_until:
            wait_time = int((lock_until - now).total_seconds())
            return render_template('login.html', error="Слишком много попыток. Подождите.", wait_time=wait_time)

    if request.method == 'POST':
        login = request.form['login']
        password = request.form['password']
        admin = query_db("SELECT * FROM admin WHERE login = ? AND password = ?", (login, password), one=True)

        if admin:
            session['user'] = login
            session['failed_attempts'] = 0
            session['lock_until'] = None
            return redirect(url_for('index'))
        else:
            session['failed_attempts'] += 1
            error = "Неверный логин или пароль"

            if session['failed_attempts'] >= 5:
                minutes = session['failed_attempts'] // 5
                lock_time = timedelta(minutes=minutes)
                session['lock_until'] = (now + lock_time).isoformat()
                wait_time = int(lock_time.total_seconds())
                error = "Слишком много попыток. Подождите."

    return render_template('login.html', error=error, wait_time=wait_time)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    tables = query_db("SELECT name FROM sqlite_master WHERE type='table'")
    visible_tables = [t['name'] for t in tables if t['name'] != 'admin']
    return render_template('index.html', tables=visible_tables)

@app.route('/table/<table>')
def show_table(table):
    if 'user' not in session:
        return redirect(url_for('login'))
    if table == 'admin':
        return "Доступ запрещён", 403

    search = request.args.get('search', '').strip()
    columns = get_columns(table)

    if search:
        search_query = f"SELECT * FROM {table} WHERE " + " OR ".join([f"{col} LIKE ?" for col in columns])
        search_args = [f"%{search}%"] * len(columns)
        data = query_db(search_query, search_args)
    else:
        data = query_db(f"SELECT * FROM {table}")

    return render_template('table.html', table=table, data=data, columns=columns, search=search)

@app.route('/table/<table>/add', methods=['GET', 'POST'])
def add_record(table):
    if 'user' not in session or table == 'admin':
        return redirect(url_for('login'))
    columns = get_columns(table)
    pk = get_primary_key(table)
    if request.method == 'POST':
        values = [request.form.get(col) for col in columns if col != pk]
        placeholders = ','.join(['?'] * len(values))
        cols = ','.join([col for col in columns if col != pk])
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        execute_db(sql, values)
        return redirect(url_for('show_table', table=table))
    return render_template('form.html', table=table, columns=[col for col in columns if col != pk], values=None, action='Добавить')

@app.route('/table/<table>/edit/<row_id>', methods=['GET', 'POST'])
def edit_record(table, row_id):
    if 'user' not in session or table == 'admin':
        return redirect(url_for('login'))
    pk = get_primary_key(table)
    columns = get_columns(table)
    if request.method == 'POST':
        values = [request.form.get(col) for col in columns if col != pk]
        updates = ', '.join([f"{col}=?" for col in columns if col != pk])
        sql = f"UPDATE {table} SET {updates} WHERE {pk}=?"
        execute_db(sql, values + [row_id])
        return redirect(url_for('show_table', table=table))
    row = query_db(f"SELECT * FROM {table} WHERE {pk}=?", (row_id,), one=True)
    return render_template('form.html', table=table, columns=[col for col in columns if col != pk], values=row, action='Редактировать')

@app.route('/table/<table>/delete/<row_id>', methods=['POST'])
def delete_record(table, row_id):
    if 'user' not in session or table == 'admin':
        return redirect(url_for('login'))
    pk = get_primary_key(table)
    sql = f"DELETE FROM {table} WHERE {pk}=?"
    execute_db(sql, (row_id,))
    return redirect(url_for('show_table', table=table))

if __name__ == '__main__':
    app.run(debug=True)