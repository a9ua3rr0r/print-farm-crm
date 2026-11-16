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
        return '#be123c'
    c = color_name.lower()
    if 'красн' in c or 'рубин' in c or 'кармин' in c or 'бордо' in c or 'гранат' in c:
        return '#be123c'
    if 'карбон' in c or 'чёрн' in c or 'черн' in c:
        return '#262f3e'
    if 'оранж' in c or 'неон' in c:
        return '#f97316'
    if 'сер' in c or 'графит' in c or 'сталь' in c:
        return '#64748b'
    if 'бел' in c:
        return '#f8fafc'
    if 'зел' in c or 'изумруд' in c:
        return '#10b981'
    if 'син' in c or 'кобальт' in c or 'сапфир' in c:
        return '#2563eb'
    if 'прозрач' in c or 'термо' in c or 'натурал' in c:
        return '#94a3b8'
    return '#be123c'

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

        # 2. Катушки с филаментом на складе
        cur.execute("""
            INSERT INTO spools (material, color, initial_weight_g, current_weight_g, cost) VALUES
            ('PLA', 'Чёрный Матовый', 1000, 840, 1890.00),
            ('PETG', 'Синий Кобальт', 1000, 910, 2150.00),
            ('ABS', 'Серый Графит', 1000, 420, 1790.00),
            ('PLA-CF', 'Карбон Чёрный', 1000, 760, 3490.00),
            ('TPU 95A', 'Оранжевый Неон', 500, 480, 2200.00),
            ('PA-CF', 'Углекомпозит Чёрный', 1000, 650, 4950.00),
            ('ASA', 'Белый УФ-стойкий', 1000, 820, 2350.00),
            ('PC', 'Прозрачный Термо', 1000, 900, 2850.00);
        """)

        # 3. Парк 3D-принтеров студии
        cur.execute("""
            INSERT INTO printers (name, model, status, current_spool_id, total_print_time_hours) VALUES
            ('Bambu-01', 'Bambu Lab X1-Carbon', 'printing', 6, 342.5),
            ('Bambu-02', 'Bambu Lab P1S Combo', 'printing', 2, 218.0),
            ('Creality-03', 'Creality K1 Max', 'idle', 1, 124.8),
            ('Voron-04', 'Voron 2.4 R2 Pro (350мм)', 'idle', 5, 412.0),
            ('Prusa-05', 'Original Prusa MK4', 'maintenance', 3, 189.4);
        """)

        # 4. Каталог изделий (гражданская оснастка, корпуса, детали механизмов)
        cur.execute("""
            INSERT INTO products (sku, name, material, weight_g, print_time_min, price) VALUES
            ('CASE-RPI5', 'Промышленный корпус Raspberry Pi 5 DIN', 'PLA', 82.0, 125, 950.00),
            ('GEAR-PLANET', 'Планетарный редуктор привода Z42', 'PETG', 48.0, 80, 680.00),
            ('DUCT-5015', 'Высокопоточный обдув экструдера 5015', 'ABS', 32.0, 55, 490.00),
            ('ROBO-ARM-Z', 'Несущий рычаг манипулятора учебного стенда', 'PLA-CF', 58.0, 105, 1350.00),
            ('SEAL-FLANGE', 'Демпферная муфта вала шагового двигателя', 'TPU 95A', 22.0, 45, 560.00),
            ('BRACKET-ROOF', 'Кронштейн внешнего погодного датчика (УФ-стойкий)', 'ASA', 42.0, 70, 780.00),
            ('GEAR-HEAVY', 'Силовая косозубая шестерня редуктора', 'PA-CF', 65.0, 115, 1650.00),
            ('DIFFUSER-PC', 'Термостойкий плафон светильника (до 115°C)', 'PC', 74.0, 130, 1180.00),
            ('STAND-PHONE', 'Эргономичная настольная подставка для смартфона', 'PETG', 36.0, 50, 450.00),
            ('AUTO-CLIP', 'Комплект монтажных клипс салона автомобиля (4 шт.)', 'PETG', 28.0, 40, 590.00);
        """)

        # 5. Клиенты (производственные компании, лаборатории, мастерские, автосервисы)
        cur.execute("""
            INSERT INTO clients (name, phone, email, notes) VALUES
            ('ООО «Форм-Технолоджи»', '+7 (916) 450-12-88', 'zakaz@form-tech.ru', 'Контрактное производство корпусов приборов и оснастки'),
            ('КБ «Робототехника и Автоматика»', '+7 (925) 780-33-19', 'kb@robo-auto.ru', 'Требуется строгое соблюдение инженерных допусков'),
            ('ИП Громов Д.А. (Мастерская Электроники)', '+7 (903) 112-90-45', 'gromov.dev@yandex.ru', 'Отгрузка через транспортную компанию СДЭК'),
            ('Технопарк «Кванториум»', '+7 (495) 800-55-10', 'lab@kvantorium.edu', 'Учебные стенды и комплекты образовательной робототехники'),
            ('Автосервис «РемАвто Моторс»', '+7 (908) 130-59-94', 'service@remauto.ru', 'Клипсы обшивки, кронштейны датчиков и кастомные переходники'),
            ('Студия интерьерного дизайна «Art-Space»', '+7 (999) 888-77-66', 'design@artspace.studio', 'Декоративные светорассеиватели и настольные аксессуары');
        """)

        # 6. Заказы и позиции (все ключевые статусы воронки: shipped, ready, in_progress, new)
        t1 = 'demo777formtech'
        t2 = uuid.uuid4().hex[:12]
        t3 = uuid.uuid4().hex[:12]
        t4 = uuid.uuid4().hex[:12]
        t5 = uuid.uuid4().hex[:12]
        t6 = uuid.uuid4().hex[:12]

        # Заказ 1: Выдан клиенту (ООО «Форм-Технолоджи»)
        cur.execute("""
            INSERT INTO orders (client_id, status, tracking_token, deadline, total_price, created_at)
            VALUES (1, 'shipped', %s, CURRENT_DATE - INTERVAL '1 day', 11940.00, NOW() - INTERVAL '4 days') RETURNING id;
        """, (t1,))
        o1_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, printed_qty, packed_qty) VALUES
            (%s, 4, 6, 6, 6),
            (%s, 2, 4, 4, 4),
            (%s, 5, 2, 2, 2);
        """, (o1_id, o1_id, o1_id))

        # Заказ 2: Выдан клиенту (ИП Громов Д.А.)
        cur.execute("""
            INSERT INTO orders (client_id, status, tracking_token, deadline, total_price, created_at)
            VALUES (3, 'shipped', %s, CURRENT_DATE - INTERVAL '2 days', 4750.00, NOW() - INTERVAL '5 days') RETURNING id;
        """, (t2,))
        o2_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, printed_qty, packed_qty) VALUES
            (%s, 1, 5, 5, 5);
        """, (o2_id,))

        # Заказ 3: В производстве (КБ «Робототехника и Автоматика»)
        cur.execute("""
            INSERT INTO orders (client_id, status, tracking_token, deadline, total_price, created_at)
            VALUES (2, 'in_progress', %s, CURRENT_DATE + INTERVAL '2 days', 7670.00, NOW() - INTERVAL '1 day') RETURNING id;
        """, (t3,))
        o3_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, printed_qty, packed_qty) VALUES
            (%s, 7, 3, 1, 0),
            (%s, 2, 4, 2, 1);
        """, (o3_id, o3_id))

        # Заказ 4: Готов к выдаче (Технопарк «Кванториум»)
        cur.execute("""
            INSERT INTO orders (client_id, status, tracking_token, deadline, total_price, created_at)
            VALUES (4, 'ready', %s, CURRENT_DATE + INTERVAL '1 day', 12200.00, NOW() - INTERVAL '2 days') RETURNING id;
        """, (t4,))
        o4_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, printed_qty, packed_qty) VALUES
            (%s, 1, 10, 10, 10),
            (%s, 4, 2, 2, 2);
        """, (o4_id, o4_id))

        # Заказ 5: Новый заказ (Автосервис «РемАвто Моторс»)
        cur.execute("""
            INSERT INTO orders (client_id, status, tracking_token, deadline, total_price, created_at)
            VALUES (5, 'new', %s, CURRENT_DATE + INTERVAL '4 days', 8640.00, NOW() - INTERVAL '3 hours') RETURNING id;
        """, (t5,))
        o5_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, printed_qty, packed_qty) VALUES
            (%s, 10, 12, 0, 0),
            (%s, 6, 2, 0, 0);
        """, (o5_id, o5_id))

        # Заказ 6: Выдан клиенту (Студия интерьерного дизайна «Art-Space»)
        cur.execute("""
            INSERT INTO orders (client_id, status, tracking_token, deadline, total_price, created_at)
            VALUES (6, 'shipped', %s, CURRENT_DATE - INTERVAL '3 days', 8320.00, NOW() - INTERVAL '7 days') RETURNING id;
        """, (t6,))
        o6_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO order_items (order_id, product_id, quantity, printed_qty, packed_qty) VALUES
            (%s, 8, 4, 4, 4),
            (%s, 9, 8, 8, 8);
        """, (o6_id, o6_id))

        # 7. Задания печати (активные и завершённые)
        cur.execute("""
            INSERT INTO print_jobs (printer_id, order_item_id, spool_id, quantity, status, progress, started_at) VALUES
            (1, 4, 6, 2, 'printing', 65, NOW() - INTERVAL '45 minutes'),
            (2, 5, 2, 2, 'printing', 40, NOW() - INTERVAL '25 minutes'),
            (3, 4, 6, 1, 'pending', 0, NULL);
        """)

        cur.execute("""
            INSERT INTO print_jobs (printer_id, order_item_id, spool_id, quantity, status, progress, started_at, finished_at, fail_reason) VALUES
            (1, 1, 4, 6, 'completed', 100, NOW() - INTERVAL '2 days', NOW() - INTERVAL '1 day', NULL),
            (2, 2, 2, 4, 'completed', 100, NOW() - INTERVAL '2 days', NOW() - INTERVAL '1 day', NULL),
            (3, 3, 1, 5, 'completed', 100, NOW() - INTERVAL '3 days', NOW() - INTERVAL '2 days', NULL),
            (4, 6, 1, 10, 'completed', 100, NOW() - INTERVAL '1 day', NOW() - INTERVAL '8 hours', NULL),
            (5, 5, 3, 1, 'failed', 35, NOW() - INTERVAL '12 hours', NOW() - INTERVAL '11 hours', 'Отрыв первого слоя от стола (потеря адгезии)');
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
            (1, 'Инициализация системы', 'Развёрнута демонстрационная база данных PrintFarm 3D', NOW() - INTERVAL '3 days'),
            (2, 'Создание заказа', 'Оформлен заказ #ORD-0001 для ООО «Форм-Технолоджи» на сумму 11 940.00 ₽', NOW() - INTERVAL '3 days'),
            (3, 'Запуск печати', 'Задание #1 назначено на принтер Bambu-01 (Bambu Lab X1-Carbon)', NOW() - INTERVAL '45 minutes'),
            (3, 'Фиксация брака', 'Задание #5 остановлено: Отрыв первого слоя от стола (потеря адгезии)', NOW() - INTERVAL '11 hours'),
            (2, 'Складской приход', 'Оприходована катушка филамента PA-CF (eSUN) на склад студии', NOW() - INTERVAL '6 hours');
        """)

    conn.commit()
    conn.close()
    print("[DB] Схема и демонстрационные данные PrintFarm 3D успешно загружены!")

if __name__ == '__main__':
    init_db()
