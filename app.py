import os
import uuid
import io
from datetime import datetime, date
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify, send_file)
from werkzeug.security import check_password_hash, generate_password_hash
from psycopg2.extras import RealDictCursor
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from db import (
    get_db_connection, DB_CONFIG,
    PRINTER_STATUS_RU, ORDER_STATUS_RU, JOB_STATUS_RU,
    MAINT_PRIORITY_RU, MAINT_STATUS_RU, ROLE_RU, resolve_spool_hex
)
from simulator import PrintFarmSimulator, recalculate_order_status

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'printfarm_3d_college_project_2026_secret')

simulator = PrintFarmSimulator(DB_CONFIG, tick_interval=8)
simulator.start()

# ----------------- ИНЖЕНЕРНО-ЭКОНОМИЧЕСКАЯ МОДЕЛЬ СЕБЕСТОИМОСТИ -----------------
# Параметры расчёта:
# - Средняя стоимость 1 г пластика (если не найдена катушка материала): 2.15 ₽/г
# - Энергопотребление 3D-принтера: 0.35 кВт * тариф 7.50 ₽/кВт·ч = 2.625 ₽/час
# - Амортизация оборудования: 35.00 ₽/моточас
# - Технологический резерв на брак: 5% от стоимости пластика
POWER_KW = 0.35
ELECTRICITY_TARIFF = 7.50
AMORTIZATION_PER_HOUR = 35.00
SCRAP_RESERVE_RATE = 0.05

def calculate_item_economics(weight_g, print_time_min, unit_price, quantity=1, cost_per_gram=2.15):
    """Рассчитывает плановую себестоимость, чистую прибыль и маржинальность партии."""
    qty = max(1, int(quantity or 1))
    w_g = float(weight_g or 0)
    t_hours = float(print_time_min or 0) / 60.0
    price_total = float(unit_price or 0) * qty

    plastic_cost = (w_g * float(cost_per_gram)) * qty
    electricity_cost = (t_hours * POWER_KW * ELECTRICITY_TARIFF) * qty
    amortization_cost = (t_hours * AMORTIZATION_PER_HOUR) * qty
    scrap_reserve = plastic_cost * SCRAP_RESERVE_RATE

    planned_cost = round(plastic_cost + electricity_cost + amortization_cost + scrap_reserve, 2)
    net_profit = round(price_total - planned_cost, 2)
    margin_pct = round((net_profit / price_total) * 100.0, 1) if price_total > 0 else 0.0

    return {
        'plastic_cost': round(plastic_cost, 2),
        'electricity_cost': round(electricity_cost, 2),
        'amortization_cost': round(amortization_cost, 2),
        'scrap_reserve': round(scrap_reserve, 2),
        'planned_cost': planned_cost,
        'price_total': round(price_total, 2),
        'net_profit': net_profit,
        'margin_pct': margin_pct
    }

# ----------------- ФИЛЬТРЫ ШАБЛОНИЗАТОРА (ЛОКАЛИЗАЦИЯ И ФОРМАТИРОВАНИЕ) -----------------

@app.template_filter('printer_status_ru')
def printer_status_ru_filter(val):
    return PRINTER_STATUS_RU.get(val, val)

@app.template_filter('order_status_ru')
def order_status_ru_filter(val):
    return ORDER_STATUS_RU.get(val, val)

@app.template_filter('job_status_ru')
def job_status_ru_filter(val):
    return JOB_STATUS_RU.get(val, val)

@app.template_filter('maint_priority_ru')
def maint_priority_ru_filter(val):
    return MAINT_PRIORITY_RU.get(val, val)

@app.template_filter('maint_status_ru')
def maint_status_ru_filter(val):
    return MAINT_STATUS_RU.get(val, val)

@app.template_filter('role_ru')
def role_ru_filter(val):
    return ROLE_RU.get(val, val)

@app.template_filter('rub')
def rub_filter(val):
    try:
        num = float(val or 0)
        return f"{num:,.2f}".replace(",", " ") + " ₽"
    except Exception:
        return "0.00 ₽"

@app.template_filter('date_ru')
def date_ru_filter(val):
    if not val:
        return "—"
    if isinstance(val, (datetime, date)):
        return val.strftime('%d.%m.%Y')
    return str(val)

@app.template_filter('datetime_ru')
def datetime_ru_filter(val):
    if not val:
        return "—"
    if isinstance(val, (datetime, date)):
        return val.strftime('%d.%m.%Y %H:%M')
    return str(val)

@app.template_filter('duration_ru')
def duration_ru_filter(minutes):
    try:
        m = int(minutes or 0)
        if m <= 0:
            return "0 мин"
        if m < 60:
            return f"{m} мин"
        h = m // 60
        rem = m % 60
        return f"{h} ч {rem} мин" if rem > 0 else f"{h} ч"
    except Exception:
        return "—"

# ----------------- БЕЗОПАСНАЯ ФУНКЦИЯ ЗАПРОСОВ К БД -----------------

def db_query(sql, params=(), fetchone=False, commit=False):
    """Безопасное выполнение SQL-запросов: читает курсор только при наличии возвращаемых столбцов."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            result = None
            if cur.description is not None:
                result = cur.fetchone() if fetchone else cur.fetchall()
            if commit:
                conn.commit()
            return result

# ----------------- ЦЕНТР ЖИВЫХ УВЕДОМЛЕНИЙ ЦЕХА (SMART NOTIFICATIONS) -----------------

@app.context_processor
def inject_notifications_and_state():
    notifications_list = []
    if 'user_id' in session:
        try:
            # 1. Катушки на исходе (< 200 г)
            low_spools = db_query("""
                SELECT id, material, color, current_weight_g
                FROM spools
                WHERE is_active = TRUE AND current_weight_g < 200
                ORDER BY current_weight_g ASC;
            """) or []
            for s in low_spools:
                notifications_list.append({
                    'type': 'warning',
                    'icon': 'bi-disc-fill text-warning',
                    'title': 'Низкий остаток пластика',
                    'text': f"Катушка {s['material']} ({s['color']}) — осталось {int(s['current_weight_g'])} г",
                    'url': url_for('warehouse')
                })

            # 2. Горящие дедлайны (<= 2 дня или просроченные)
            urgent_orders = db_query("""
                SELECT o.id, o.deadline, c.name AS client_name,
                       (o.deadline < CURRENT_DATE) AS is_overdue
                FROM orders o
                JOIN clients c ON o.client_id = c.id
                WHERE o.status NOT IN ('shipped', 'cancelled')
                  AND o.deadline <= CURRENT_DATE + INTERVAL '2 days'
                ORDER BY o.deadline ASC;
            """) or []
            for o in urgent_orders:
                if o['is_overdue']:
                    notifications_list.append({
                        'type': 'danger',
                        'icon': 'bi-alarm-fill text-danger',
                        'title': f"Просрочен заказ #ORD-{o['id']:04d}",
                        'text': f"Заказчик: {o['client_name']} (срок был {o['deadline'].strftime('%d.%m.%Y')})",
                        'url': url_for('orders')
                    })
                else:
                    notifications_list.append({
                        'type': 'info',
                        'icon': 'bi-clock-history text-info',
                        'title': f"Близкий срок сдачи #ORD-{o['id']:04d}",
                        'text': f"{o['client_name']} — сдача до {o['deadline'].strftime('%d.%m.%Y')}",
                        'url': url_for('orders')
                    })

            # 3. Партии, ожидающие постобработки и упаковки
            unpacked = db_query("""
                SELECT oi.order_id, pr.name AS product_name, (oi.printed_qty - oi.packed_qty) AS ready_cnt
                FROM order_items oi
                JOIN products pr ON oi.product_id = pr.id
                JOIN orders o ON oi.order_id = o.id
                WHERE (oi.printed_qty - oi.packed_qty) > 0
                  AND o.status NOT IN ('shipped', 'cancelled');
            """) or []
            for u in unpacked:
                notifications_list.append({
                    'type': 'success',
                    'icon': 'bi-box-seam-fill text-success',
                    'title': 'Ожидает упаковки',
                    'text': f"{u['product_name']} ({u['ready_cnt']} шт.) по заказу #ORD-{u['order_id']:04d}",
                    'url': url_for('queue')
                })

            # 4. Открытые заявки на ремонт и ТО
            open_maint = db_query("""
                SELECT m.id, m.priority, p.name AS printer_name, m.description
                FROM maintenance_requests m
                JOIN printers p ON m.printer_id = p.id
                WHERE m.status = 'open'
                ORDER BY m.id DESC;
            """) or []
            for m in open_maint:
                notifications_list.append({
                    'type': 'danger',
                    'icon': 'bi-wrench-adjustable-circle-fill text-danger',
                    'title': f"Станок {m['printer_name']} на ТО",
                    'text': m['description'],
                    'url': url_for('printers_view')
                })
        except Exception as e:
            print(f"[Notifications Context Error] {e}")

    return {
        'sim_auto_enabled': simulator.auto_enabled,
        'notifications_list': notifications_list,
        'notifications_count': len(notifications_list)
    }

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            user_role = session.get('role')
            if user_role not in roles and user_role != 'admin':
                flash('Доступ ограничен: у вашей роли нет прав на выполнение этой операции.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return wrapped
    return decorator

def log_action(action, details=""):
    uid = session.get('user_id')
    try:
        db_query(
            "INSERT INTO action_logs (user_id, action, details) VALUES (%s, %s, %s);",
            (uid, action, details),
            commit=True
        )
    except Exception as e:
        print(f"[Audit Log Error] {e}")

# ----------------- МАРШРУТЫ АВТОРИЗАЦИИ -----------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        uname = request.form.get('username', '').strip()
        pwd = request.form.get('password', '')
        user = db_query(
            "SELECT * FROM users WHERE username = %s;",
            (uname,), fetchone=True
        )
        if user and not user['is_active']:
            flash('Ваша учётная запись заблокирована администратором системы.', 'danger')
            return render_template('login.html')
        if user and check_password_hash(user['password_hash'], pwd):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            log_action("Вход в систему", f"Авторизован сотрудник {user['full_name']} ({ROLE_RU.get(user['role'])})")
            return redirect(url_for('dashboard'))
        flash('Неверный логин или пароль. Проверьте введённые данные.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'user_id' in session:
        log_action("Выход из системы", f"Завершение сеанса {session.get('full_name')}")
    session.clear()
    return redirect(url_for('login'))

# ----------------- УПРАВЛЕНИЕ ПЕРСОНАЛОМ (АДМИН-ПАНЕЛЬ СОТРУДНИКОВ) -----------------

@app.route('/users')
@role_required('admin')
def users_list():
    users = db_query("""
        SELECT u.*,
               (SELECT COUNT(*) FROM action_logs l WHERE l.user_id = u.id) AS actions_count
        FROM users u
        ORDER BY u.id ASC;
    """)
    return render_template('users.html', users=users)

@app.route('/users/create', methods=['POST'])
@role_required('admin')
def users_create():
    username = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    role = request.form.get('role', 'operator').strip()
    password = request.form.get('password', '12345').strip()

    if not username or not full_name or role not in ('admin', 'manager', 'operator'):
        flash('Заполните все обязательные поля корректно.', 'warning')
        return redirect(url_for('users_list'))

    existing = db_query("SELECT id FROM users WHERE username = %s;", (username,), fetchone=True)
    if existing:
        flash(f'Логин «{username}» уже занят другим сотрудником!', 'danger')
        return redirect(url_for('users_list'))

    pwd_hash = generate_password_hash(password)
    db_query("""
        INSERT INTO users (username, password_hash, full_name, role, is_active)
        VALUES (%s, %s, %s, %s, TRUE);
    """, (username, pwd_hash, full_name, role), commit=True)

    log_action("Создан пользователь", f"Добавлен сотрудник {full_name} (логин: {username}, роль: {ROLE_RU.get(role)})")
    flash(f'Сотрудник «{full_name}» успешно зарегистрирован в системе!', 'success')
    return redirect(url_for('users_list'))

@app.route('/users/<int:target_id>/toggle', methods=['POST'])
@role_required('admin')
def users_toggle(target_id):
    if target_id == session.get('user_id'):
        flash('Безопасность: вы не можете заблокировать собственную учётную запись!', 'warning')
        return redirect(url_for('users_list'))

    user = db_query("SELECT * FROM users WHERE id = %s;", (target_id,), fetchone=True)
    if user:
        new_state = not user['is_active']
        db_query("UPDATE users SET is_active = %s WHERE id = %s;", (new_state, target_id), commit=True)
        status_word = "разблокирован" if new_state else "заблокирован"
        log_action("Статус сотрудника", f"Аккаунт {user['full_name']} ({user['username']}) {status_word}")
        flash(f"Доступ сотрудника «{user['full_name']}» {status_word}.", 'info')
    return redirect(url_for('users_list'))

@app.route('/users/<int:target_id>/reset_password', methods=['POST'])
@role_required('admin')
def users_reset_password(target_id):
    new_password = request.form.get('new_password', '12345').strip() or '12345'
    user = db_query("SELECT * FROM users WHERE id = %s;", (target_id,), fetchone=True)
    if user:
        pwd_hash = generate_password_hash(new_password)
        db_query("UPDATE users SET password_hash = %s WHERE id = %s;", (pwd_hash, target_id), commit=True)
        log_action("Сброс пароля", f"Администратор обновил пароль для {user['full_name']} ({user['username']})")
        flash(f"Пароль для сотрудника «{user['full_name']}» успешно обновлён!", 'success')
    return redirect(url_for('users_list'))

# ----------------- СВОДКА ЦЕХА (ДАШБОРД) -----------------

@app.route('/')
@role_required('admin', 'manager', 'operator')
def dashboard():
    stats = {
        'orders_active': db_query("SELECT COUNT(*) AS c FROM orders WHERE status IN ('new', 'in_progress');", fetchone=True)['c'],
        'orders_ready': db_query("SELECT COUNT(*) AS c FROM orders WHERE status = 'ready';", fetchone=True)['c'],
        'printers_printing': db_query("SELECT COUNT(*) AS c FROM printers WHERE status = 'printing' AND is_active = TRUE;", fetchone=True)['c'],
        'printers_total': db_query("SELECT COUNT(*) AS c FROM printers WHERE is_active = TRUE;", fetchone=True)['c'],
        'queue_len': db_query("SELECT COUNT(*) AS c FROM print_jobs WHERE status = 'pending';", fetchone=True)['c'],
        'waiting_pack': db_query("SELECT COALESCE(SUM(printed_qty - packed_qty), 0) AS c FROM order_items WHERE printed_qty > packed_qty;", fetchone=True)['c'],
        'spools_warning': db_query("SELECT COUNT(*) AS c FROM spools WHERE current_weight_g < 200 AND is_active = TRUE;", fetchone=True)['c'],
        'maint_open': db_query("SELECT COUNT(*) AS c FROM maintenance_requests WHERE status = 'open';", fetchone=True)['c']
    }

    closest_job = db_query("""
        SELECT pj.*, pr.name AS product_name, pr.sku, pr.material AS product_material,
               pr.weight_g, pr.print_time_min,
               p.name AS printer_name, p.model AS printer_model, p.id AS printer_id,
               s.color AS spool_color, s.material AS spool_material,
               oi.order_id, c.name AS client_name
        FROM print_jobs pj
        JOIN printers p ON pj.printer_id = p.id
        JOIN order_items oi ON pj.order_item_id = oi.id
        JOIN orders o ON oi.order_id = o.id
        JOIN clients c ON o.client_id = c.id
        JOIN products pr ON oi.product_id = pr.id
        LEFT JOIN spools s ON pj.spool_id = s.id
        WHERE pj.status = 'printing'
        ORDER BY pj.progress DESC, pj.id ASC
        LIMIT 1;
    """, fetchone=True)

    if closest_job:
        closest_job['spool_hex'] = resolve_spool_hex(closest_job['spool_color'])
        total_time_min = closest_job['print_time_min'] * closest_job['quantity']
        rem_min = max(0, int(round(total_time_min * (1.0 - closest_job['progress'] / 100.0))))
        closest_job['remaining_ru'] = duration_ru_filter(rem_min)

    printers = db_query("""
        SELECT p.*, s.color AS spool_color, s.material AS spool_material,
               s.current_weight_g AS spool_weight, s.initial_weight_g AS spool_init_weight,
               active_job.job_id AS current_job_id,
               active_job.product_name AS current_task,
               active_job.sku AS current_sku,
               active_job.progress AS current_progress,
               active_job.quantity AS current_qty
        FROM printers p
        LEFT JOIN spools s ON p.current_spool_id = s.id
        LEFT JOIN LATERAL (
            SELECT pj.id AS job_id, pr.name AS product_name, pr.sku, pj.progress, pj.quantity
            FROM print_jobs pj
            JOIN order_items oi ON pj.order_item_id = oi.id
            JOIN products pr ON oi.product_id = pr.id
            WHERE pj.printer_id = p.id AND pj.status = 'printing'
            ORDER BY pj.id DESC LIMIT 1
        ) active_job ON TRUE
        WHERE p.is_active = TRUE
        ORDER BY p.id ASC;
    """)

    urgent_orders = db_query("""
        SELECT o.*, c.name AS client_name,
               COALESCE(SUM(oi.quantity), 0) AS total_qty,
               COALESCE(SUM(oi.printed_qty), 0) AS printed_qty,
               COALESCE(SUM(oi.packed_qty), 0) AS packed_qty,
               (o.deadline < CURRENT_DATE AND o.status NOT IN ('shipped', 'cancelled')) AS is_overdue
        FROM orders o
        JOIN clients c ON o.client_id = c.id
        LEFT JOIN order_items oi ON oi.order_id = o.id
        WHERE o.status NOT IN ('shipped', 'cancelled')
        GROUP BY o.id, c.name
        ORDER BY o.deadline ASC, o.id DESC
        LIMIT 6;
    """)

    recent_jobs = db_query("""
        SELECT pj.*, pr.name AS product_name, pr.material, p.name AS printer_name, oi.order_id
        FROM print_jobs pj
        JOIN order_items oi ON pj.order_item_id = oi.id
        JOIN products pr ON oi.product_id = pr.id
        LEFT JOIN printers p ON pj.printer_id = p.id
        ORDER BY pj.id DESC
        LIMIT 6;
    """)

    return render_template(
        'dashboard.html',
        stats=stats,
        closest_job=closest_job,
        printers=printers,
        orders=urgent_orders,
        recent_jobs=recent_jobs,
        now=datetime.now()
    )

# ----------------- API ТЕЛЕМЕТРИИ И 3D-ДВОЙНИКА СТАНКА -----------------

@app.route('/api/printer/<int:printer_id>/telemetry')
@role_required('admin', 'manager', 'operator')
def api_printer_telemetry(printer_id):
    p = db_query("""
        SELECT p.*, s.material AS spool_material, s.color AS spool_color,
               s.current_weight_g AS spool_weight, s.initial_weight_g AS spool_init_weight
        FROM printers p
        LEFT JOIN spools s ON p.current_spool_id = s.id
        WHERE p.id = %s;
    """, (printer_id,), fetchone=True)

    if not p:
        return jsonify({'error': 'Принтер не найден'}), 404

    job = db_query("""
        SELECT pj.id AS job_id, pj.progress, pj.quantity, pj.status AS job_status,
               pr.sku, pr.name AS product_name, pr.material AS product_material,
               pr.weight_g, pr.print_time_min,
               oi.order_id, c.name AS client_name
        FROM print_jobs pj
        JOIN order_items oi ON pj.order_item_id = oi.id
        JOIN orders o ON oi.order_id = o.id
        JOIN clients c ON o.client_id = c.id
        JOIN products pr ON oi.product_id = pr.id
        WHERE pj.printer_id = %s AND pj.status IN ('printing', 'pending')
        ORDER BY CASE WHEN pj.status = 'printing' THEN 0 ELSE 1 END, pj.id ASC
        LIMIT 1;
    """, (printer_id,), fetchone=True)

    is_printing = (p['status'] == 'printing' and job is not None)
    progress = int(job['progress']) if job else 0
    total_layers = int((job['print_time_min'] * 3.2)) if job else 240
    current_layer = int(round((progress / 100.0) * total_layers)) if is_printing else 0

    mat_str = (p['spool_material'] or (job['product_material'] if job else 'PLA')).upper()
    if 'ABS' in mat_str or 'CF' in mat_str:
        nozzle_target, bed_target = 255, 90
    elif 'PETG' in mat_str:
        nozzle_target, bed_target = 240, 75
    elif 'TPU' in mat_str:
        nozzle_target, bed_target = 225, 50
    else:
        nozzle_target, bed_target = 215, 60

    nozzle_temp = nozzle_target if is_printing else 26
    bed_temp = bed_target if is_printing else 24

    total_time_min = (job['print_time_min'] * job['quantity']) if job else 0
    remaining_min = max(0, int(round(total_time_min * (1.0 - progress / 100.0)))) if is_printing else 0

    return jsonify({
        'printer_id': p['id'],
        'printer_name': p['name'],
        'printer_model': p['model'],
        'status': p['status'],
        'status_ru': PRINTER_STATUS_RU.get(p['status'], p['status']),
        'total_hours': float(p['total_print_time_hours'] or 0),
        'spool_material': p['spool_material'] or 'Не установлена',
        'spool_color': p['spool_color'] or 'Стандартный',
        'spool_hex': resolve_spool_hex(p['spool_color']),
        'spool_weight': int(p['spool_weight'] or 0),
        'spool_init_weight': int(p['spool_init_weight'] or 1000),
        'has_active_job': job is not None,
        'job_id': job['job_id'] if job else None,
        'sku': job['sku'] if job else 'DEMO-PART',
        'product_name': job['product_name'] if job else 'Свободный стол (Ожидание задания)',
        'quantity': job['quantity'] if job else 0,
        'order_num': f"#ORD-{job['order_id']:04d}" if job else '—',
        'client_name': job['client_name'] if job else '—',
        'progress': progress,
        'current_layer': current_layer,
        'total_layers': total_layers,
        'nozzle_temp': nozzle_temp,
        'nozzle_target': nozzle_target if is_printing else 0,
        'bed_temp': bed_temp,
        'bed_target': bed_target if is_printing else 0,
        'print_speed': '160 мм/с' if is_printing else '0 мм/с',
        'fan_speed': '100%' if is_printing else '0%',
        'remaining_ru': duration_ru_filter(remaining_min) if is_printing else '—'
    })

# ----------------- УПРАВЛЕНИЕ ЗАКАЗАМИ, СЕБЕСТОИМОСТЬ И ПЕЧАТНЫЙ НАРЯД -----------------

@app.route('/orders', methods=['GET', 'POST'])
@role_required('admin', 'manager')
def orders():
    if request.method == 'POST':
        form_type = request.form.get('form_type', 'create_order')

        if form_type == 'create_client':
            c_name = request.form.get('name', '').strip()
            c_phone = request.form.get('phone', '').strip()
            c_email = request.form.get('email', '').strip()
            c_notes = request.form.get('notes', '').strip()
            if c_name and c_phone:
                db_query(
                    "INSERT INTO clients (name, phone, email, notes) VALUES (%s, %s, %s, %s);",
                    (c_name, c_phone, c_email, c_notes), commit=True
                )
                log_action("Добавлен клиент", f"Зарегистрирован заказчик {c_name} ({c_phone})")
                flash(f'Клиент «{c_name}» успешно добавлен в справочник!', 'success')
            return redirect(url_for('orders'))

        client_id = request.form.get('client_id')
        deadline = request.form.get('deadline')
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')

        token = uuid.uuid4().hex[:12]
        total_price = 0.0

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO orders (client_id, deadline, tracking_token, total_price)
                    VALUES (%s, %s, %s, 0.00) RETURNING id;
                """, (client_id, deadline, token))
                order_id = cur.fetchone()['id']

                for pid, qty_str in zip(product_ids, quantities):
                    if not pid or not qty_str:
                        continue
                    qty = max(1, int(qty_str))
                    cur.execute("SELECT price FROM products WHERE id = %s;", (pid,))
                    prod = cur.fetchone()
                    if prod:
                        total_price += float(prod['price']) * qty
                        cur.execute("""
                            INSERT INTO order_items (order_id, product_id, quantity)
                            VALUES (%s, %s, %s);
                        """, (order_id, pid, qty))

                cur.execute("UPDATE orders SET total_price = %s WHERE id = %s;", (total_price, order_id))
            conn.commit()

        log_action("Создан заказ", f"Оформлен заказ #ORD-{order_id:04d} на сумму {total_price:,.2f} ₽")
        flash(f'Заказ #ORD-{order_id:04d} успешно создан и передан в работу!', 'success')
        return redirect(url_for('orders'))

    status_filter = request.args.get('status', '')
    where_clause = "WHERE o.status = %s" if status_filter else ""
    params = (status_filter,) if status_filter else ()

    orders_list = db_query(f"""
        SELECT o.*, c.name AS client_name, c.phone AS client_phone,
               COALESCE(SUM(oi.quantity), 0) AS total_qty,
               COALESCE(SUM(oi.printed_qty), 0) AS printed_qty,
               COALESCE(SUM(oi.packed_qty), 0) AS packed_qty,
               (o.deadline < CURRENT_DATE AND o.status NOT IN ('shipped', 'cancelled')) AS is_overdue
        FROM orders o
        JOIN clients c ON o.client_id = c.id
        LEFT JOIN order_items oi ON oi.order_id = o.id
        {where_clause}
        GROUP BY o.id, c.name, c.phone
        ORDER BY o.id DESC;
    """, params)

    # Расчёт средней цены 1 г по типам пластика со склада
    spool_rates_rows = db_query("""
        SELECT material, AVG(cost / NULLIF(initial_weight_g, 0)) AS rate_per_g
        FROM spools
        GROUP BY material;
    """) or []
    material_rate_map = {r['material']: float(r['rate_per_g'] or 2.15) for r in spool_rates_rows}

    order_items_map = {}
    order_econ_map = {}
    all_items = db_query("""
        SELECT oi.*, pr.name AS product_name, pr.sku, pr.material,
               pr.weight_g, pr.print_time_min, pr.price
        FROM order_items oi
        JOIN products pr ON oi.product_id = pr.id
        ORDER BY oi.id ASC;
    """)
    for it in all_items:
        oid = it['order_id']
        order_items_map.setdefault(oid, []).append(it)
        rate_g = material_rate_map.get(it['material'], 2.15)
        econ = calculate_item_economics(it['weight_g'], it['print_time_min'], it['price'], it['quantity'], rate_g)
        acc = order_econ_map.setdefault(oid, {'planned_cost': 0.0, 'net_profit': 0.0, 'price_total': 0.0})
        acc['planned_cost'] = round(acc['planned_cost'] + econ['planned_cost'], 2)
        acc['net_profit'] = round(acc['net_profit'] + econ['net_profit'], 2)
        acc['price_total'] = round(acc['price_total'] + econ['price_total'], 2)

    for oid, acc in order_econ_map.items():
        acc['margin_pct'] = round((acc['net_profit'] / acc['price_total']) * 100.0, 1) if acc['price_total'] > 0 else 0.0

    clients = db_query("SELECT * FROM clients ORDER BY name ASC;")
    products = db_query("SELECT * FROM products WHERE is_active = TRUE ORDER BY name ASC;")
    for p in products:
        p['rate_per_g'] = round(material_rate_map.get(p['material'], 2.15), 2)

    return render_template(
        'orders.html',
        orders=orders_list,
        order_items_map=order_items_map,
        order_econ_map=order_econ_map,
        clients=clients,
        products=products,
        status_filter=status_filter,
        default_deadline=date.today().strftime('%Y-%m-%d')
    )

@app.route('/orders/<int:order_id>/print')
@role_required('admin', 'manager', 'operator')
def order_print_sheet(order_id):
    """Печатная форма производственного наряда А4 и маркировочной этикетки с QR-кодом."""
    order = db_query("""
        SELECT o.*, c.name AS client_name, c.phone AS client_phone, c.email AS client_email, c.notes AS client_notes
        FROM orders o
        JOIN clients c ON o.client_id = c.id
        WHERE o.id = %s;
    """, (order_id,), fetchone=True)
    if not order:
        flash('Заказ не найден.', 'danger')
        return redirect(url_for('orders'))

    items = db_query("""
        SELECT oi.*, pr.sku, pr.name AS product_name, pr.material,
               pr.weight_g, pr.print_time_min, pr.price,
               (pr.weight_g * oi.quantity) AS batch_weight_g,
               (pr.print_time_min * oi.quantity) AS batch_time_min
        FROM order_items oi
        JOIN products pr ON oi.product_id = pr.id
        WHERE oi.order_id = %s
        ORDER BY oi.id ASC;
    """, (order_id,))

    total_weight_g = sum(float(i['batch_weight_g'] or 0) for i in items)
    total_time_min = sum(int(i['batch_time_min'] or 0) for i in items)
    total_qty = sum(int(i['quantity'] or 0) for i in items)

    return render_template(
        'order_print.html',
        order=order,
        items=items,
        total_weight_g=round(total_weight_g, 1),
        total_time_min=total_time_min,
        total_qty=total_qty,
        now=datetime.now()
    )

@app.route('/orders/<int:order_id>/ship', methods=['POST'])
@role_required('admin', 'manager')
def ship_order(order_id):
    order = db_query("SELECT status FROM orders WHERE id = %s;", (order_id,), fetchone=True)
    if not order or order['status'] != 'ready':
        flash('Отгрузка невозможна: не все позиции заказа напечатаны и упакованы!', 'warning')
        return redirect(url_for('orders'))

    db_query("UPDATE orders SET status = 'shipped' WHERE id = %s;", (order_id,), commit=True)
    log_action("Отгрузка заказа", f"Заказ #ORD-{order_id:04d} выдан клиенту")
    flash(f'Заказ #ORD-{order_id:04d} успешно выдан клиенту!', 'success')
    return redirect(url_for('orders'))

@app.route('/orders/<int:order_id>/cancel', methods=['POST'])
@role_required('admin', 'manager')
def cancel_order(order_id):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("UPDATE orders SET status = 'cancelled' WHERE id = %s;", (order_id,))
            cur.execute("""
                SELECT pj.id, pj.printer_id
                FROM print_jobs pj
                JOIN order_items oi ON pj.order_item_id = oi.id
                WHERE oi.order_id = %s AND pj.status IN ('pending', 'printing');
            """, (order_id,))
            active_jobs = cur.fetchall()
            for j in active_jobs:
                cur.execute("UPDATE print_jobs SET status = 'cancelled', finished_at = NOW() WHERE id = %s;", (j['id'],))
                if j['printer_id']:
                    cur.execute("UPDATE printers SET status = 'idle' WHERE id = %s;", (j['printer_id'],))
        conn.commit()
    log_action("Отмена заказа", f"Заказ #ORD-{order_id:04d} отменён, связанные задания остановлены")
    flash(f'Заказ #ORD-{order_id:04d} отменён.', 'info')
    return redirect(url_for('orders'))

# ----------------- ОЧЕРЕДЬ ПЕЧАТИ И ПОСТОБРАБОТКА (ОПЕРАТОР) -----------------

@app.route('/queue', methods=['GET', 'POST'])
@role_required('admin', 'operator', 'manager')
def queue():
    if request.method == 'POST':
        item_id = int(request.form.get('order_item_id'))
        printer_id = int(request.form.get('printer_id'))
        qty = max(1, int(request.form.get('quantity', 1)))

        printer = db_query("SELECT * FROM printers WHERE id = %s;", (printer_id,), fetchone=True)
        item = db_query("SELECT * FROM order_items WHERE id = %s;", (item_id,), fetchone=True)

        if not printer or not item:
            flash('Ошибка выбора принтера или позиции заказа.', 'danger')
            return redirect(url_for('queue'))

        job_status = 'printing' if printer['status'] == 'idle' else 'pending'
        init_progress = 10 if job_status == 'printing' else 0

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO print_jobs (printer_id, order_item_id, spool_id, quantity, status, progress, started_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CASE WHEN %s = 'printing' THEN NOW() ELSE NULL END)
                    RETURNING id;
                """, (printer_id, item_id, printer['current_spool_id'], qty, job_status, init_progress, job_status))
                new_job_id = cur.fetchone()['id']

                if job_status == 'printing':
                    cur.execute("UPDATE printers SET status = 'printing' WHERE id = %s;", (printer_id,))
                    cur.execute("UPDATE orders SET status = 'in_progress' WHERE id = %s AND status = 'new';", (item['order_id'],))
            conn.commit()

        log_action("Задание на печать", f"Создано задание #{new_job_id} на {printer['name']} ({JOB_STATUS_RU[job_status]})")
        flash(f"Задание #{new_job_id} назначено на станок {printer['name']} ({JOB_STATUS_RU[job_status]})!", 'success')
        return redirect(url_for('queue'))

    jobs = db_query("""
        SELECT pj.*, pr.name AS product_name, pr.sku, pr.material, pr.weight_g, pr.print_time_min,
               p.name AS printer_name, p.model AS printer_model,
               s.color AS spool_color, s.material AS spool_material,
               oi.order_id, c.name AS client_name
        FROM print_jobs pj
        JOIN order_items oi ON pj.order_item_id = oi.id
        JOIN orders o ON oi.order_id = o.id
        JOIN clients c ON o.client_id = c.id
        JOIN products pr ON oi.product_id = pr.id
        LEFT JOIN printers p ON pj.printer_id = p.id
        LEFT JOIN spools s ON pj.spool_id = s.id
        ORDER BY CASE
            WHEN pj.status = 'printing' THEN 1
            WHEN pj.status = 'pending' THEN 2
            ELSE 3
        END, pj.id DESC;
    """)

    available_items = db_query("""
        SELECT oi.id, oi.order_id, pr.name AS product_name, pr.sku, pr.material,
               c.name AS client_name,
               (oi.quantity - oi.printed_qty) AS remaining_qty
        FROM order_items oi
        JOIN products pr ON oi.product_id = pr.id
        JOIN orders o ON oi.order_id = o.id
        JOIN clients c ON o.client_id = c.id
        WHERE (oi.quantity - oi.printed_qty) > 0
          AND o.status NOT IN ('cancelled', 'shipped')
        ORDER BY o.deadline ASC;
    """)

    printers = db_query("""
        SELECT p.*, s.material AS spool_material, s.color AS spool_color
        FROM printers p
        LEFT JOIN spools s ON p.current_spool_id = s.id
        WHERE p.is_active = TRUE AND p.status NOT IN ('maintenance', 'offline')
        ORDER BY p.id ASC;
    """)

    pack_items = db_query("""
        SELECT oi.id, oi.order_id, pr.name AS product_name, pr.sku,
               c.name AS client_name,
               oi.printed_qty, oi.packed_qty,
               (oi.printed_qty - oi.packed_qty) AS ready_to_pack
        FROM order_items oi
        JOIN products pr ON oi.product_id = pr.id
        JOIN orders o ON oi.order_id = o.id
        JOIN clients c ON o.client_id = c.id
        WHERE (oi.printed_qty - oi.packed_qty) > 0
          AND o.status NOT IN ('cancelled', 'shipped')
        ORDER BY o.deadline ASC;
    """)

    return render_template(
        'queue.html',
        jobs=jobs,
        items=available_items,
        printers=printers,
        pack_items=pack_items
    )

@app.route('/queue/<int:job_id>/fail', methods=['POST'])
@role_required('admin', 'operator', 'manager')
def fail_job(job_id):
    reason = request.form.get('reason', 'Отрыв детали от стола (потеря адгезии)')
    job = db_query("SELECT * FROM print_jobs WHERE id = %s;", (job_id,), fetchone=True)
    if job:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    UPDATE print_jobs
                    SET status = 'failed', fail_reason = %s, finished_at = NOW()
                    WHERE id = %s;
                """, (reason, job_id))
                if job['printer_id']:
                    cur.execute("UPDATE printers SET status = 'idle' WHERE id = %s;", (job['printer_id'],))
            conn.commit()
        log_action("Фиксация брака", f"Задание #{job_id} остановлено. Причина: {reason}")
        flash(f'Задание #{job_id} переведено в брак ({reason}). Станок освобождён.', 'warning')
    return redirect(request.referrer or url_for('queue'))

@app.route('/items/<int:item_id>/pack', methods=['POST'])
@role_required('admin', 'operator', 'manager')
def pack_item(item_id):
    qty = max(1, int(request.form.get('pack_qty', 1)))
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT order_id, printed_qty, packed_qty FROM order_items WHERE id = %s;", (item_id,))
            item = cur.fetchone()
            if item:
                new_packed = min(item['printed_qty'], item['packed_qty'] + qty)
                cur.execute("UPDATE order_items SET packed_qty = %s WHERE id = %s;", (new_packed, item_id))
                recalculate_order_status(cur, item['order_id'])
        conn.commit()
    log_action("Упаковка изделий", f"Позиция #{item_id}: упаковано {qty} шт.")
    flash('Партия изделий прошла постобработку и упакована! Готовность заказа обновлена.', 'success')
    return redirect(url_for('queue'))

# ----------------- ПАРК ПРИНТЕРОВ И СТЕЛЛАЖНЫЙ ВИД ФЕРМЫ -----------------

@app.route('/printers', methods=['GET', 'POST'])
@role_required('admin', 'manager', 'operator')
def printers_view():
    if request.method == 'POST':
        action = request.form.get('action_type')

        if action == 'create_maintenance':
            printer_id = int(request.form.get('printer_id'))
            desc = request.form.get('description', '').strip()
            priority = request.form.get('priority', 'normal')
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO maintenance_requests (printer_id, description, priority, status)
                        VALUES (%s, %s, %s, 'open');
                    """, (printer_id, desc, priority))
                    cur.execute("UPDATE printers SET status = 'maintenance' WHERE id = %s;", (printer_id,))
                conn.commit()
            log_action("Заявка на ТО", f"Принтер #{printer_id} переведён на обслуживание: {desc}")
            flash('Заявка на ТО создана, принтер переведён в статус «На обслуживании».', 'warning')

        elif action == 'close_maintenance':
            req_id = int(request.form.get('request_id'))
            notes = request.form.get('resolution_notes', 'Регламентные работы выполнены').strip()
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        UPDATE maintenance_requests
                        SET status = 'closed', resolved_at = NOW(), resolution_notes = %s
                        WHERE id = %s RETURNING printer_id;
                    """, (notes, req_id))
                    row = cur.fetchone()
                    if row:
                        cur.execute("UPDATE printers SET status = 'idle' WHERE id = %s;", (row['printer_id'],))
                conn.commit()
            log_action("Завершение ТО", f"Заявка #{req_id} закрыта, станок возвращён в строй")
            flash('Обслуживание завершено! Принтер снова свободен и готов к печати.', 'success')

        elif action == 'add_printer':
            name = request.form.get('name', '').strip()
            model = request.form.get('model', '').strip()
            spool_id = request.form.get('spool_id') or None
            db_query("""
                INSERT INTO printers (name, model, status, current_spool_id)
                VALUES (%s, %s, 'idle', %s);
            """, (name, model, spool_id), commit=True)
            log_action("Добавлен принтер", f"Введён в эксплуатацию станок {name} ({model})")
            flash(f'Принтер {name} добавлен в парк оборудования!', 'success')

        return redirect(url_for('printers_view'))

    printers = db_query("""
        SELECT p.*, s.material, s.color, s.current_weight_g, s.initial_weight_g,
               (SELECT COUNT(*) FROM print_jobs pj WHERE pj.printer_id = p.id AND pj.status = 'completed') AS completed_jobs,
               (SELECT COUNT(*) FROM print_jobs pj WHERE pj.printer_id = p.id AND pj.status = 'failed') AS failed_jobs,
               active_job.product_name AS current_task,
               active_job.sku AS current_sku,
               active_job.progress AS current_progress,
               active_job.quantity AS current_qty
        FROM printers p
        LEFT JOIN spools s ON p.current_spool_id = s.id
        LEFT JOIN LATERAL (
            SELECT pr.name AS product_name, pr.sku, pj.progress, pj.quantity
            FROM print_jobs pj
            JOIN order_items oi ON pj.order_item_id = oi.id
            JOIN products pr ON oi.product_id = pr.id
            WHERE pj.printer_id = p.id AND pj.status = 'printing'
            ORDER BY pj.id DESC LIMIT 1
        ) active_job ON TRUE
        WHERE p.is_active = TRUE
        ORDER BY p.id ASC;
    """)
    spools = db_query("SELECT * FROM spools WHERE is_active = TRUE AND current_weight_g > 0 ORDER BY id ASC;")
    maint_reqs = db_query("""
        SELECT m.*, p.name AS printer_name, p.model AS printer_model
        FROM maintenance_requests m
        JOIN printers p ON m.printer_id = p.id
        ORDER BY CASE WHEN m.status = 'open' THEN 0 ELSE 1 END, m.id DESC;
    """)
    return render_template('printers.html', printers=printers, spools=spools, maintenance=maint_reqs)

@app.route('/printers/<int:printer_id>/mount_spool', methods=['POST'])
@role_required('admin', 'operator', 'manager')
def mount_spool(printer_id):
    spool_id = request.form.get('spool_id') or None
    db_query("UPDATE printers SET current_spool_id = %s WHERE id = %s;", (spool_id, printer_id), commit=True)
    log_action("Замена катушки", f"На принтере #{printer_id} установлена катушка #{spool_id}")
    flash('Катушка с пластиком успешно установлена на принтер!', 'info')
    return redirect(url_for('printers_view'))

# ----------------- СКЛАД И КАТАЛОГ ИЗДЕЛИЙ -----------------

@app.route('/warehouse', methods=['GET', 'POST'])
@role_required('admin', 'manager', 'operator')
def warehouse():
    if request.method == 'POST':
        action = request.form.get('action_type')
        if action == 'add_spool':
            mat = request.form.get('material', '').strip()
            color = request.form.get('color', '').strip()
            weight = float(request.form.get('weight', 1000))
            cost = float(request.form.get('cost', 1900))
            db_query("""
                INSERT INTO spools (material, color, initial_weight_g, current_weight_g, cost)
                VALUES (%s, %s, %s, %s, %s);
            """, (mat, color, weight, weight, cost), commit=True)
            log_action("Приход пластика", f"Добавлена катушка {mat} ({color}), {weight:.0f} г")
            flash(f'Катушка {mat} ({color}) оприходована на склад!', 'success')

        elif action == 'add_product':
            sku = request.form.get('sku', '').strip().upper()
            name = request.form.get('name', '').strip()
            mat = request.form.get('material', '').strip()
            w = float(request.form.get('weight_g', 50))
            t = int(request.form.get('print_time_min', 60))
            price = float(request.form.get('price', 500))
            db_query("""
                INSERT INTO products (sku, name, material, weight_g, print_time_min, price)
                VALUES (%s, %s, %s, %s, %s, %s);
            """, (sku, name, mat, w, t, price), commit=True)
            log_action("Новое изделие", f"В каталог добавлена 3D-модель {sku} — {name}")
            flash(f'Изделие «{name}» ({sku}) добавлено в каталог!', 'success')

        return redirect(url_for('warehouse'))

    spools = db_query("""
        SELECT s.*,
               (SELECT string_agg(p.name, ', ') FROM printers p WHERE p.current_spool_id = s.id) AS mounted_on
        FROM spools s
        WHERE s.is_active = TRUE
        ORDER BY s.id ASC;
    """)
    products = db_query("SELECT * FROM products WHERE is_active = TRUE ORDER BY id ASC;")
    return render_template('warehouse.html', spools=spools, products=products)

# ----------------- АНАЛИТИКА, МАРЖИНАЛЬНОСТЬ И ЭКСПОРТ В EXCEL -----------------

@app.route('/analytics')
@role_required('admin', 'manager')
def analytics():
    revenue_shipped = db_query("SELECT COALESCE(SUM(total_price), 0) AS total FROM orders WHERE status = 'shipped';", fetchone=True)['total']
    revenue_pipeline = db_query("SELECT COALESCE(SUM(total_price), 0) AS total FROM orders WHERE status IN ('new', 'in_progress', 'ready');", fetchone=True)['total']

    total_printed_weight = db_query("""
        SELECT COALESCE(SUM(pr.weight_g * pj.quantity), 0) / 1000.0 AS kg
        FROM print_jobs pj
        JOIN order_items oi ON pj.order_item_id = oi.id
        JOIN products pr ON oi.product_id = pr.id
        WHERE pj.status = 'completed';
    """, fetchone=True)['kg']

    scrap_rate = db_query("""
        SELECT ROUND(COUNT(CASE WHEN status = 'failed' THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 1) AS rate
        FROM print_jobs;
    """, fetchone=True)['rate'] or 0.0

    # Расчёт общей себестоимости, чистой прибыли и рентабельности по всем не отменённым заказам
    spool_rates_rows = db_query("SELECT material, AVG(cost / NULLIF(initial_weight_g, 0)) AS rate_per_g FROM spools GROUP BY material;") or []
    material_rate_map = {r['material']: float(r['rate_per_g'] or 2.15) for r in spool_rates_rows}

    active_items = db_query("""
        SELECT oi.quantity, pr.weight_g, pr.print_time_min, pr.price, pr.material
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        JOIN products pr ON oi.product_id = pr.id
        WHERE o.status != 'cancelled';
    """) or []

    total_planned_cost = 0.0
    total_sales_value = 0.0
    for it in active_items:
        rate_g = material_rate_map.get(it['material'], 2.15)
        ec = calculate_item_economics(it['weight_g'], it['print_time_min'], it['price'], it['quantity'], rate_g)
        total_planned_cost += ec['planned_cost']
        total_sales_value += ec['price_total']

    total_net_profit = round(total_sales_value - total_planned_cost, 2)
    avg_margin_pct = round((total_net_profit / total_sales_value) * 100.0, 1) if total_sales_value > 0 else 0.0

    status_counts = db_query("""
        SELECT status, COUNT(*) AS cnt
        FROM orders
        GROUP BY status;
    """)
    status_chart_labels = [ORDER_STATUS_RU.get(r['status'], r['status']) for r in status_counts]
    status_chart_values = [r['cnt'] for r in status_counts]

    logs = db_query("""
        SELECT l.*, u.full_name, u.role
        FROM action_logs l
        LEFT JOIN users u ON l.user_id = u.id
        ORDER BY l.id DESC
        LIMIT 25;
    """)

    return render_template(
        'analytics.html',
        revenue_shipped=revenue_shipped,
        revenue_pipeline=revenue_pipeline,
        total_planned_cost=round(total_planned_cost, 2),
        total_net_profit=total_net_profit,
        avg_margin_pct=avg_margin_pct,
        weight_kg=round(float(total_printed_weight or 0), 2),
        scrap_rate=scrap_rate,
        status_chart_labels=status_chart_labels,
        status_chart_values=status_chart_values,
        logs=logs
    )

@app.route('/analytics/export/orders')
@role_required('admin', 'manager')
def export_orders_excel():
    orders = db_query("""
        SELECT o.id, c.name AS client_name, c.phone AS client_phone,
               o.deadline, o.status, o.total_price, o.created_at,
               COALESCE(SUM(oi.quantity), 0) AS total_qty,
               COALESCE(SUM(oi.printed_qty), 0) AS printed_qty,
               COALESCE(SUM(oi.packed_qty), 0) AS packed_qty
        FROM orders o
        JOIN clients c ON o.client_id = c.id
        LEFT JOIN order_items oi ON oi.order_id = o.id
        GROUP BY o.id, c.name, c.phone
        ORDER BY o.id DESC;
    """)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Реестр заказов"

    headers = [
        "Номер заказа", "Заказчик", "Телефон", "Дата оформления",
        "Срок сдачи", "Статус заказа", "Всего деталей (шт)",
        "Напечатано (шт)", "Упаковано (шт)", "Стоимость (руб.)"
    ]
    ws.append(headers)

    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, o in enumerate(orders, start=2):
        ws.append([
            f"ORD-{o['id']:04d}",
            o['client_name'],
            o['client_phone'],
            o['created_at'].strftime('%d.%m.%Y %H:%M') if o['created_at'] else '',
            o['deadline'].strftime('%d.%m.%Y') if o['deadline'] else '',
            ORDER_STATUS_RU.get(o['status'], o['status']),
            int(o['total_qty']),
            int(o['printed_qty']),
            int(o['packed_qty']),
            float(o['total_price'])
        ])
        for col_num in range(1, len(headers) + 1):
            c = ws.cell(row=row_idx, column=col_num)
            c.border = thin_border
            if col_num == 10:
                c.number_format = '#,##0.00" ₽"'

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    log_action("Экспорт в Excel", "Выгружен отчёт по заказам (printfarm_orders.xlsx)")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"PrintFarm_Orders_{date.today().strftime('%d_%m_%Y')}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ----------------- ПУБЛИЧНЫЙ ТРЕКЕР ЗАКАЗА ДЛЯ КЛИЕНТА -----------------

@app.route('/track/<token>')
def track(token):
    order = db_query("""
        SELECT o.id, o.status, o.deadline, o.created_at, c.name AS client_name
        FROM orders o
        JOIN clients c ON o.client_id = c.id
        WHERE o.tracking_token = %s;
    """, (token,), fetchone=True)
    if not order:
        return render_template('track.html', order=None, items=[]), 404

    items = db_query("""
        SELECT pr.name, pr.sku, pr.material, oi.quantity, oi.printed_qty, oi.packed_qty
        FROM order_items oi
        JOIN products pr ON oi.product_id = pr.id
        WHERE oi.order_id = %s
        ORDER BY oi.id ASC;
    """, (order['id'],))
    return render_template('track.html', order=order, items=items)

# ----------------- API СИМУЛЯТОРА -----------------

@app.route('/api/simulator/tick', methods=['POST'])
def sim_tick():
    payload = request.get_json(silent=True) or {}
    printer_id = payload.get('printer_id')
    changes = simulator.tick(target_printer_id=int(printer_id) if printer_id else None)
    return jsonify({
        'success': True,
        'changes': changes,
        'auto_enabled': simulator.auto_enabled,
        'message': f"Шаг выполнен: запущено {changes['started']}, в печати {changes['progressed']}, завершено {changes['completed']}"
    })

@app.route('/api/simulator/toggle', methods=['POST'])
def sim_toggle():
    state = simulator.toggle_auto()
    return jsonify({'success': True, 'auto_enabled': state})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=True)
