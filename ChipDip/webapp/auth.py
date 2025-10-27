# webapp/auth.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
from chipdip_parser.config_loader import get_config

auth_bp = Blueprint('auth', __name__)
login_manager = LoginManager()

class User:
    def __init__(self, id, username, email=None):
        self.id = id
        self.username = username
        self.email = email
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False

    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    config = get_config()
    try:
        conn = psycopg2.connect(
            dbname=config['db_name'],
            user=config['db_user'],
            password=config['db_password'],
            host=config['db_host'],
            port=config['db_port']
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, username, email FROM users WHERE id = %s AND is_active = TRUE", (user_id,))
            user_data = cur.fetchone()
            if user_data:
                return User(user_data['id'], user_data['username'], user_data['email'])
    except Exception as e:
        print(f"Ошибка загрузки пользователя: {e}")
    finally:
        if conn:
            conn.close()
    return None

def get_db_connection():
    """Получает соединение с БД"""
    config = get_config()
    try:
        conn = psycopg2.connect(
            dbname=config['db_name'],
            user=config['db_user'],
            password=config['db_password'],
            host=config['db_host'],
            port=config['db_port']
        )
        return conn
    except psycopg2.Error as e:
        print(f"Ошибка подключения к БД: {e}")
        return None

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Введите логин и пароль', 'error')
            return redirect(url_for('main.index'))
        
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        "SELECT id, username, password_hash, email FROM users WHERE username = %s AND is_active = TRUE",
                        (username,)
                    )
                    user_data = cur.fetchone()
                    
                    if user_data and check_password_hash(user_data['password_hash'], password):
                        user = User(user_data['id'], user_data['username'], user_data['email'])
                        login_user(user)
                        flash(f'Добро пожаловать, {username}!', 'success')
                        return redirect(url_for('main.index'))
                    else:
                        flash('Неверный логин или пароль', 'error')
            except Exception as e:
                flash(f'Ошибка входа: {e}', 'error')
            finally:
                conn.close()
        else:
            flash('Ошибка подключения к базе данных', 'error')
    
    return redirect(url_for('main.index'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        email = request.form.get('email')
        
        # Валидация
        if not username or not password:
            flash('Логин и пароль обязательны', 'error')
            return redirect(url_for('main.index'))
        
        if password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return redirect(url_for('main.index'))
        
        if len(password) < 6:
            flash('Пароль должен содержать минимум 6 символов', 'error')
            return redirect(url_for('main.index'))
        
        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    # Проверяем, не занят ли логин
                    cur.execute("SELECT id FROM users WHERE username = %s", (username,))
                    if cur.fetchone():
                        flash('Пользователь с таким логином уже существует', 'error')
                        return redirect(url_for('main.index'))
                    
                    # Создаем пользователя
                    password_hash = generate_password_hash(password)
                    cur.execute(
                        "INSERT INTO users (username, password_hash, email) VALUES (%s, %s, %s)",
                        (username, password_hash, email)
                    )
                    conn.commit()
                    flash('Регистрация успешна! Теперь вы можете войти.', 'success')
                    return redirect(url_for('main.index'))
            except Exception as e:
                conn.rollback()
                flash(f'Ошибка регистрации: {e}', 'error')
            finally:
                conn.close()
        else:
            flash('Ошибка подключения к базе данных', 'error')
    
    return redirect(url_for('main.index'))

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('main.index'))

@auth_bp.route('/profile')
@login_required
def profile():
    return render_template('profile.html')
