import os
import uuid
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash

DB_CONFIG = {
    'dbname': os.environ.get('PGDATABASE', 'printfarm_db'),
    'user': os.environ.get('PGUSER', 'postgres'),
    'password': os.environ.get('PGPASSWORD', '1234'),
    'host': os.environ.get('PGHOST', 'localhost'),
    'port': int(os.environ.get('PGPORT', 5432))
}

# Словари локализации для отображения всех ключей БД на русском языке
PRINTER_STATUS_RU = {
    'idle': 'Свободен',
    'printing': 'Идёт печать',
    'maintenance': 'На обслуживании',
    'offline': 'Недоступен'
}

ORDER_STATUS_RU = {
    'new': 'Новый заказ',
    'in_progress': 'В производстве',
    'ready': 'Готов к отгрузке',
    'shipped': 'Выдан клиенту',
    'cancelled': 'Отменён'
}

JOB_STATUS_RU = {
    'pending': 'В очереди',
    'printing': 'Печать детали',
    'completed': 'Успешно напечатано',
    'failed': 'Брак / Сбой',
    'cancelled': 'Отменено'
}

MAINT_PRIORITY_RU = {
    'low': 'Низкий',
    'normal': 'Плановый',
    'urgent': 'Срочный ремонт'
}

MAINT_STATUS_RU = {
    'open': 'В работе',
    'closed': 'Выполнено'
}

ROLE_RU = {
    'admin': 'Администратор',
    'manager': 'Менеджер заказов',
    'operator': 'Оператор ЧПУ / 3D'
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def resolve_spool_hex(color_name):
    """Преобразует русское название цвета катушки в HEX-код для 3D-рендера."""
    if not color_name:
        return '#3b82f6'
    c = color_name.lower()
    if 'карбон' in c or 'чёрн' in c or 'черн' in c:
        return '#334155'
    if 'син' in c or 'кобальт' in c:
        return '#2563eb'
    if 'оранж' in c or 'неон' in c:
        return '#f97316'
    if 'сер' in c or 'графит' in c or 'сталь' in c:
        return '#64748b'
    if 'бел' in c:
        return '#f8fafc'
    if 'зел' in c or 'изумруд' in c:
        return '#10b981'
    if 'красн' in c or 'рубин' in c:
        return '#ef4444'
    return '#3b82f6'

def ensure_database_exists():
    """Автоматически создаёт базу данных printfarm_db, если она ещё не создана."""
    try:
        conn = psycopg2.connect(
            dbname='postgres',
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port']
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (DB_CONFIG['dbname'],))
            if not cur.fetchone():
                cur.execute(f"CREATE DATABASE {DB_CONFIG['dbname']} ENCODING 'UTF8';")
                print(f"[DB] База данных '{DB_CONFIG['dbname']}' успешно создана.")
        conn.close()
    except Exception as e:
        print(f"[DB Warning] Не удалось проверить/создать БД автоматически: {e}")

def init_db():
    ensure_database_exists()
    conn = get_db_connection()
    with conn.cursor() as cur:
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        with open(schema_path, 'r', encoding='utf-8') as f:
            cur.execute(f.read())

        # 1. Пользователи (пароль для всех: 12345)
        default_pwd = generate_password_hash('12345')
        users = [
            ('admin', default_pwd, 'Марков Иван Александрович', 'admin'),
            ('manager', default_pwd, 'Смирнова Анна Сергеевна', 'manager'),
            ('operator', default_pwd, 'Кузнецов Олег Викторович', 'operator')
        ]
        for u, p, name, role in users:
            cur.execute("""
                INSERT INTO users (username, password_hash, full_name, role)
                VALUES (%s, %s, %s, %s);
            """, (u, p, name, role))

        # 2. Катушки с филаментом
        cur.execute("""
            INSERT INTO spools (material, color, initial_weight_g, current_weight_g, cost) VALUES
            ('PLA', 'Чёрный Матовый', 1000, 840, 1890.00),
            ('PETG', 'Синий Кобальт', 1000, 910, 2150.00),
            ('ABS', 'Серый Графит', 1000, 165, 1790.00),
            ('PLA-CF', 'Карбон Чёрный', 1000, 760, 3490.00),
            ('TPU 95A', 'Оранжевый Неон', 500, 480, 2200.00);
        """)

        # 3. Парк 3D-принтеров
        cur.execute("""
            INSERT INTO printers (name, model, status, current_spool_id, total_print_time_hours) VALUES
            ('Bambu-01', 'Bambu Lab X1-Carbon', 'printing', 4, 342.5),
            ('Bambu-02', 'Bambu Lab P1S Combo', 'printing', 2, 218.0),
            ('Creality-03', 'Creality K1 Max', 'idle', 1, 124.8),
            ('Voron-04', 'Voron 2.4 R2 Pro (350мм)', 'idle', 5, 412.0),
            ('Prusa-05', 'Original Prusa MK4', 'maintenance', 3, 189.4);
        """)

        # 4. Каталог изделий
        cur.execute("""
            INSERT INTO products (sku, name, material, weight_g, print_time_min, price) VALUES
            ('DRN-ARM-7', 'Силовой луч квадрокоптера 7 дюймов', 'PLA-CF', 55.0, 95, 1250.00),
            ('GEAR-PLANET', 'Планетарный редуктор привода Z42', 'PETG', 48.0, 80, 680.00),
            ('CASE-RPI5', 'Промышленный корпус Raspberry Pi 5 DIN', 'PLA', 82.0, 125, 950.00),
            ('DUCT-5015', 'Высокопоточный обдув экструдера 5015', 'ABS', 32.0, 55, 490.00),
            ('MOUNT-CAM', 'Виброгасящее крепление курсовой камеры', 'TPU 95A', 18.0, 40, 520.00);
        """)

        # 5. Клиенты
        cur.execute("""
            INSERT INTO clients (name, phone, email, notes) VALUES
            ('ООО «АэроТех Системы»', '+7 (916) 450-12-88', 'procurement@aerotech.ru', 'Постоянный корпоративный заказчик БПЛА'),
            ('КБ «Робототехника и Автоматика»', '+7 (925) 780-33-19', 'kb@robo-auto.ru', 'Требуется точное соблюдение допусков'),
            ('ИП Громов Д.А. (Мастерская Электроники)', '+7 (903) 112-90-45', 'gromov.dev@yandex.ru', 'Отгрузка через СДЭК'),
            ('Технопарк «Кванториум»', '+7 (495) 800-55-10', 'lab@kvantorium.edu', 'Учебные комплекты робототехники');
        """)

        # 6. Заказы и позиции
        t1 = 'demo777aerotech'
        t2 = uuid.uuid4().hex[:12]
        t3 = uuid.uuid4().hex[:12]
        t4 = uuid.uuid4().hex[:12]

        # Заказ 1: В производстве
        cur.execute("""
            INSERT INTO orders (client_id, status, tracking_token, deadline, total_price, created_at)
            VALUES (1, 'in_progress', %s, CURRENT_DATE + INTERVAL '2 days', 11060.00, NOW() - INTERVAL '2 days') RETURNING id;
        """, (t1,))
        o1_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, printed_qty, packed_qty) VALUES
            (%s, 1, 6, 3, 2),
            (%s, 2, 4, 4, 2),
            (%s, 5, 2, 0, 0);
        """, (o1_id, o1_id, o1_id))

        # Заказ 2: Готов к отгрузке
        cur.execute("""
            INSERT INTO orders (client_id, status, tracking_token, deadline, total_price, created_at)
            VALUES (3, 'ready', %s, CURRENT_DATE + INTERVAL '1 day', 4750.00, NOW() - INTERVAL '3 days') RETURNING id;
        """, (t2,))
        o2_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, printed_qty, packed_qty) VALUES
            (%s, 3, 5, 5, 5);
        """, (o2_id,))

        # Заказ 3: Новый заказ
        cur.execute("""
            INSERT INTO orders (client_id, status, tracking_token, deadline, total_price, created_at)
            VALUES (2, 'new', %s, CURRENT_DATE + INTERVAL '5 days', 6320.00, NOW() - INTERVAL '5 hours') RETURNING id;
        """, (t3,))
        o3_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, printed_qty, packed_qty) VALUES
            (%s, 2, 6, 0, 0),
            (%s, 4, 4, 0, 0);
        """, (o3_id, o3_id))

        # Заказ 4: Выдан клиенту (для статистики выручки)
        cur.execute("""
            INSERT INTO orders (client_id, status, tracking_token, deadline, total_price, created_at)
            VALUES (4, 'shipped', %s, CURRENT_DATE - INTERVAL '1 day', 14250.00, NOW() - INTERVAL '6 days') RETURNING id;
        """, (t4,))
        o4_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, printed_qty, packed_qty) VALUES
            (%s, 3, 15, 15, 15);
        """, (o4_id,))

        # 7. Задания печати
        cur.execute("""
            INSERT INTO print_jobs (printer_id, order_item_id, spool_id, quantity, status, progress, started_at) VALUES
            (1, 1, 4, 2, 'printing', 65, NOW() - INTERVAL '45 minutes'),
            (2, 3, 2, 2, 'printing', 40, NOW() - INTERVAL '25 minutes'),
            (3, 1, 4, 1, 'pending', 0, NULL);
        """)

        # История выполненных и отбракованных заданий
        cur.execute("""
            INSERT INTO print_jobs (printer_id, order_item_id, spool_id, quantity, status, progress, started_at, finished_at, fail_reason) VALUES
            (1, 1, 4, 3, 'completed', 100, NOW() - INTERVAL '1 day', NOW() - INTERVAL '20 hours', NULL),
            (2, 2, 2, 4, 'completed', 100, NOW() - INTERVAL '1 day', NOW() - INTERVAL '18 hours', NULL),
            (3, 4, 1, 5, 'completed', 100, NOW() - INTERVAL '2 days', NOW() - INTERVAL '1 day', NULL),
            (5, 2, 3, 1, 'failed', 35, NOW() - INTERVAL '12 hours', NOW() - INTERVAL '11 hours', 'Отрыв детали от стола (потеря адгезии)');
        """)

        # 8. Заявки на обслуживание
        cur.execute("""
            INSERT INTO maintenance_requests (printer_id, description, priority, status, created_at) VALUES
            (5, 'Замена латунного сопла 0.4 мм и калибровка первого слоя (Z-offset)', 'urgent', 'open', NOW() - INTERVAL '4 hours');
        """)
        cur.execute("""
            INSERT INTO maintenance_requests (printer_id, description, priority, status, created_at, resolved_at, resolution_notes) VALUES
            (1, 'Плановая смазка направляющих рельс и натяжение ремней XY', 'normal', 'closed', NOW() - INTERVAL '5 days', NOW() - INTERVAL '4 days', 'Смазка выполнена, тест резонансов пройден успешно');
        """)

        # 9. Журнал аудита
        cur.execute("""
            INSERT INTO action_logs (user_id, action, details, created_at) VALUES
            (1, 'Инициализация системы', 'Развёрнута демонстрационная база данных PrintFarm 3D', NOW() - INTERVAL '2 days'),
            (2, 'Создание заказа', 'Оформлен заказ #ORD-0001 для ООО «АэроТех Системы» на сумму 11 060.00 ₽', NOW() - INTERVAL '2 days'),
            (3, 'Запуск печати', 'Задание #1 назначено на принтер Bambu-01 (Bambu Lab X1-Carbon)', NOW() - INTERVAL '45 minutes'),
            (3, 'Фиксация брака', 'Задание #7 остановлено: Отрыв детали от стола (потеря адгезии)', NOW() - INTERVAL '11 hours');
        """)

    conn.commit()
    conn.close()
    print("[DB] Схема и демонстрационные данные PrintFarm 3D успешно загружены!")

if __name__ == '__main__':
    init_db()
