import os
import re
import csv
import io
import urllib.request
from psycopg2.extras import RealDictCursor
from db import get_db_connection

# Базовый онлайн-шаблон Google Таблицы для закупки филамента 3D-студии
DEFAULT_SHEET_URL = os.environ.get(
    'GOOGLE_SHEET_URL',
    'https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit'
)

# Резервные котировки на случай отсутствия интернета
FALLBACK_PRICES = {
    'PLA': {'price': 1290.00, 'brand': 'FDplast', 'source_sku': 'FDP-PLA-01'},
    'PETG': {'price': 1190.00, 'brand': 'FDplast', 'source_sku': 'FDP-PETG-02'},
    'ABS': {'price': 1250.00, 'brand': 'FDplast', 'source_sku': 'FDP-ABS-03'},
    'ASA': {'price': 2350.00, 'brand': 'BestFilament', 'source_sku': 'BF-ASA-04'},
    'PA-CF': {'price': 4950.00, 'brand': 'eSUN', 'source_sku': 'ESN-PACF-05'},
    'PC': {'price': 2850.00, 'brand': 'BestFilament', 'source_sku': 'BF-PC-06'},
    'PETG-CF': {'price': 3850.00, 'brand': 'eSUN', 'source_sku': 'ESN-PETGCF-07'},
    'PLA-CF': {'price': 3490.00, 'brand': 'Bambu Lab', 'source_sku': 'BL-PLACF-08'},
    'TPU 95A': {'price': 2200.00, 'brand': 'REC', 'source_sku': 'REC-TPU-09'},
}

# Каталог для выпадающих списков при оприходовании катушек (актуальные рыночные цены РФ)
MARKETPLACE_CATALOG = [
    # PLA
    {'code': 'GS-PLA-FDP', 'material': 'PLA', 'brand': 'FDplast', 'default_color': 'Чёрный Матовый', 'weight_g': 1000, 'price': 1290.00, 'source_type': 'Google Таблица', 'source_sku': 'FDP-PLA-BLK'},
    {'code': 'GS-PLA-BF', 'material': 'PLA', 'brand': 'BestFilament', 'default_color': 'Белый Базовый', 'weight_g': 1000, 'price': 1890.00, 'source_type': 'Google Таблица', 'source_sku': 'BF-PLA-WHT'},
    {'code': 'GS-PLA-BL', 'material': 'PLA', 'brand': 'Bambu Lab', 'default_color': 'Серый Металлик', 'weight_g': 1000, 'price': 2490.00, 'source_type': 'Google Таблица', 'source_sku': 'BL-PLA-GRY'},

    # PETG
    {'code': 'GS-PETG-FDP', 'material': 'PETG', 'brand': 'FDplast', 'default_color': 'Синий Сапфир', 'weight_g': 1000, 'price': 1190.00, 'source_type': 'Google Таблица', 'source_sku': 'FDP-PETG-BLU'},
    {'code': 'GS-PETG-BF', 'material': 'PETG', 'brand': 'BestFilament', 'default_color': 'Красный Рубин', 'weight_g': 1000, 'price': 1950.00, 'source_type': 'Google Таблица', 'source_sku': 'BF-PETG-RED'},
    {'code': 'GS-PETG-ESN', 'material': 'PETG', 'brand': 'eSUN', 'default_color': 'Зелёный Изумруд', 'weight_g': 1000, 'price': 2190.00, 'source_type': 'Google Таблица', 'source_sku': 'ESN-PETG-GRN'},

    # ABS
    {'code': 'GS-ABS-FDP', 'material': 'ABS', 'brand': 'FDplast', 'default_color': 'Чёрный Стандарт', 'weight_g': 1000, 'price': 1250.00, 'source_type': 'Google Таблица', 'source_sku': 'FDP-ABS-BLK'},
    {'code': 'GS-ABS-ESN', 'material': 'ABS', 'brand': 'eSUN', 'default_color': 'Серый Графит', 'weight_g': 1000, 'price': 1850.00, 'source_type': 'Google Таблица', 'source_sku': 'ESN-ABS-GRY'},
    {'code': 'GS-ABS-BF', 'material': 'ABS', 'brand': 'BestFilament', 'default_color': 'Натуральный Белый', 'weight_g': 1000, 'price': 1790.00, 'source_type': 'Google Таблица', 'source_sku': 'BF-ABS-NAT'},

    # ASA (Стойкий к УФ и атмосферным осадкам)
    {'code': 'GS-ASA-BF', 'material': 'ASA', 'brand': 'BestFilament', 'default_color': 'Белый УФ-стойкий', 'weight_g': 1000, 'price': 2350.00, 'source_type': 'Google Таблица', 'source_sku': 'BF-ASA-WHT'},
    {'code': 'GS-ASA-BL', 'material': 'ASA', 'brand': 'Bambu Lab', 'default_color': 'Оранжевый Сигнал', 'weight_g': 1000, 'price': 2890.00, 'source_type': 'Google Таблица', 'source_sku': 'BL-ASA-ORG'},

    # PA-CF (Карбоновый Нейлон высокой прочности и жесткости)
    {'code': 'GS-PACF-ESN', 'material': 'PA-CF', 'brand': 'eSUN', 'default_color': 'Карбон Чёрный', 'weight_g': 1000, 'price': 4950.00, 'source_type': 'Google Таблица', 'source_sku': 'ESN-PACF-BLK'},
    {'code': 'GS-PACF-BL', 'material': 'PA-CF', 'brand': 'Bambu Lab', 'default_color': 'Антрацит Карбон', 'weight_g': 1000, 'price': 5490.00, 'source_type': 'Google Таблица', 'source_sku': 'BL-PAHT-CF'},

    # PC (Поликарбонат сверхтермостойкий до 115°C)
    {'code': 'GS-PC-BF', 'material': 'PC', 'brand': 'BestFilament', 'default_color': 'Прозрачный Термо', 'weight_g': 1000, 'price': 2850.00, 'source_type': 'Google Таблица', 'source_sku': 'BF-PC-CLR'},

    # PLA-CF / PETG-CF (Углекомпозиты)
    {'code': 'GS-PLACF-BL', 'material': 'PLA-CF', 'brand': 'Bambu Lab', 'default_color': 'Карбон Чёрный', 'weight_g': 1000, 'price': 3490.00, 'source_type': 'Google Таблица', 'source_sku': 'BL-PLACF-01'},
    {'code': 'GS-PETGCF-ESN', 'material': 'PETG-CF', 'brand': 'eSUN', 'default_color': 'Тёмно-Серый Карбон', 'weight_g': 1000, 'price': 3850.00, 'source_type': 'Google Таблица', 'source_sku': 'ESN-PETGCF-01'},

    # TPU 95A / Flex (Эластомеры и полиуретаны)
    {'code': 'GS-TPU-REC', 'material': 'TPU 95A', 'brand': 'REC', 'default_color': 'Оранжевый Неон', 'weight_g': 500, 'price': 2200.00, 'source_type': 'Google Таблица', 'source_sku': 'REC-TPU-ORG'},
    {'code': 'GS-TPU-BF', 'material': 'TPU 95A', 'brand': 'BestFilament', 'default_color': 'Красный Эласт', 'weight_g': 500, 'price': 1990.00, 'source_type': 'Google Таблица', 'source_sku': 'BF-TPU-RED'},
    {'code': 'GS-TPU-BL', 'material': 'TPU 95A', 'brand': 'Bambu Lab', 'default_color': 'Чёрный Эластичный', 'weight_g': 1000, 'price': 3200.00, 'source_type': 'Google Таблица', 'source_sku': 'BL-TPU-BLK'},
]


def ensure_spool_price_columns():
    """Создаёт таблицу настроек и добавляет поля привязки к Google Таблице в таблицу spools."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    key VARCHAR(100) PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cur.execute("""
                ALTER TABLE spools
                ADD COLUMN IF NOT EXISTS source_type VARCHAR(50) DEFAULT 'Google Таблица',
                ADD COLUMN IF NOT EXISTS source_sku VARCHAR(100),
                ADD COLUMN IF NOT EXISTS brand VARCHAR(100) DEFAULT 'FDplast',
                ADD COLUMN IF NOT EXISTS price_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
            """)

            cur.execute("""
                ALTER TABLE clients
                ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
            """)
        conn.commit()


def get_google_sheet_url():
    """Возвращает сохранённый в БД или дефолтный URL Google Таблицы."""
    ensure_spool_price_columns()
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT value FROM system_settings WHERE key = 'google_sheet_url';")
            row = cur.fetchone()
            if row and row['value']:
                return row['value'].strip()
    return DEFAULT_SHEET_URL


def set_google_sheet_url(url):
    """Сохраняет пользовательский URL Google Таблицы в БД."""
    ensure_spool_price_columns()
    clean_url = (url or '').strip()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO system_settings (key, value, updated_at)
                VALUES ('google_sheet_url', %s, NOW())
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = NOW();
            """, (clean_url,))
        conn.commit()
    return clean_url


def convert_sheet_url_to_csv_export(sheet_url):
    """Преобразует любую ссылку на Google Таблицу или CSV в прямой URL скачивания данных."""
    if not sheet_url:
        return None
    url = sheet_url.strip()

    # Если это опубликованная в веб таблица Google: .../pub?output=csv
    if '/spreadsheets/d/e/' in url:
        if 'output=csv' in url:
            return url
        base = url.split('?')[0].rstrip('/')
        return f"{base}?output=csv"

    # Стандартная ссылка на Google Таблицу: /spreadsheets/d/{ID}/edit...
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    if match:
        sheet_id = match.group(1)
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

    # Если ссылка уже является прямой ссылкой на CSV или эндпоинт
    if 'format=csv' in url or url.endswith('.csv') or 'output=csv' in url:
        return url

    return url


def parse_numeric_price(raw_str):
    """Очищает строку от пробелов и валют, корректно обрабатывая разделители тысяч и копеек."""
    clean = re.sub(r'[^\d.,]', '', str(raw_str))
    if not clean:
        return 0.0
    if ',' in clean and '.' in clean:
        if clean.rfind(',') > clean.rfind('.'):
            # 1.890,50
            clean = clean.replace('.', '').replace(',', '.')
        else:
            # 1,890.50
            clean = clean.replace(',', '')
    else:
        clean = clean.replace(',', '.')
    try:
        return float(clean)
    except Exception:
        return 0.0


def fetch_prices_from_sheet(sheet_url):
    """
    Скачивает онлайн CSV из Google Таблицы и парсит котировки материалов.
    Поддерживает разделители запятая, точка с запятой и табуляция.
    Возвращает dict { 'PLA': {'price': 1850.0, 'brand': 'FDplast', 'source_sku': '...'}, ... }
    """
    csv_url = convert_sheet_url_to_csv_export(sheet_url)
    if not csv_url:
        raise ValueError("Некорректный формат ссылки на Google Таблицу.")

    req = urllib.request.Request(
        csv_url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) PrintFarm-CRM/2.0'}
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        content = resp.read().decode('utf-8', errors='ignore')

    if not content.strip():
        raise ValueError("Google Таблица пуста.")

    # Автоопределение разделителя (запятая, точка с запятой, таб)
    try:
        sample = content[:2048]
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample, delimiters=',;\t')
        reader = csv.reader(io.StringIO(content), dialect)
    except Exception:
        reader = csv.reader(io.StringIO(content))

    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        raise ValueError("Google Таблица не содержит данных.")

    headers = [h.strip().lower() for h in rows[0]]
    mat_idx = -1
    price_idx = -1
    brand_idx = -1
    sku_idx = -1
    color_idx = -1
    weight_idx = -1

    for idx, h in enumerate(headers):
        # Материал: 'материал', 'полимер', 'material', 'пластик' или отдельное слово 'тип' (но НЕ 'типичный')
        if any(k in h for k in ['материал', 'полимер', 'material', 'пластик']) or (('тип' in h) and ('типич' not in h)):
            if mat_idx == -1:
                mat_idx = idx
        elif any(k in h for k in ['цена', 'стоимость', 'price', 'cost', 'прайс', 'руб']):
            if price_idx == -1:
                price_idx = idx
        elif any(k in h for k in ['бренд', 'brand', 'производитель', 'марка', 'завод']):
            if brand_idx == -1:
                brand_idx = idx
        elif any(k in h for k in ['оттенок', 'цвет', 'color']):
            if color_idx == -1:
                color_idx = idx
        elif any(k in h for k in ['фасовка', 'вес', 'weight', 'нетто']):
            if weight_idx == -1:
                weight_idx = idx
        elif any(k in h for k in ['артикул', 'sku', 'код', 'code']):
            if sku_idx == -1:
                sku_idx = idx

    # Если заголовки не распознаны по ключевым словам, используем порядок по умолчанию
    if mat_idx == -1:
        mat_idx = 0
    if price_idx == -1 and len(headers) > 1:
        price_idx = 1
    if brand_idx == -1 and len(headers) > 2:
        brand_idx = 2

    parsed_prices = {}
    for row in rows[1:]:
        if len(row) <= mat_idx:
            continue
        raw_mat = row[mat_idx].strip()
        if not raw_mat:
            continue
        mat_key = raw_mat.upper()

        raw_price = row[price_idx] if (price_idx != -1 and price_idx < len(row)) else '0'
        price_val = parse_numeric_price(raw_price)

        brand_val = row[brand_idx].strip() if (brand_idx != -1 and brand_idx < len(row)) else 'FDplast'
        brand_key = brand_val.upper()

        sku_val = row[sku_idx].strip() if (sku_idx != -1 and sku_idx < len(row)) else f"GS-{mat_key}"

        if price_val > 0:
            item = {
                'price': price_val,
                'brand': brand_val or 'FDplast',
                'source_sku': sku_val
            }
            # Точная связка (Материал, Бренд)
            parsed_prices[(mat_key, brand_key)] = item
            # Общий фолбэк по названию материала
            if mat_key not in parsed_prices:
                parsed_prices[mat_key] = item

    return parsed_prices


def sync_all_spools(user_id=None, custom_url=None):
    """
    Массовая синхронизация цен катушек склада с Google Таблицей.
    Учитывает как материал, так и производителя (бренд) катушки.
    При сбое связи использует резервные котировки и возвращает детальный отчёт.
    """
    ensure_spool_price_columns()
    sheet_url = custom_url or get_google_sheet_url()
    updated_count = 0
    source_name = 'Google Таблица'
    error_note = None

    try:
        sheet_prices = fetch_prices_from_sheet(sheet_url)
    except Exception as e:
        error_note = str(e)
        sheet_prices = {}

    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, material, color, source_sku, brand FROM spools WHERE is_active = TRUE ORDER BY id ASC;")
            spools = cur.fetchall()

            for s in spools:
                mat = (s['material'] or 'PLA').strip().upper()
                brand_s = (s.get('brand') or '').strip().upper()

                # 1. Сначала ищем по связке (Материал, Бренд), например ('PLA', 'FDPLAST')
                info = sheet_prices.get((mat, brand_s))

                # 2. Если по бренду не найдено, ищем по общему материалу 'PLA'
                if not info:
                    info = sheet_prices.get(mat)

                # 3. Если таблицы нет или материал новый — берём из резервной матрицы
                if not info:
                    info = FALLBACK_PRICES.get(mat, {'price': 1950.00, 'brand': 'FDplast', 'source_sku': f"GS-{mat}"})

                new_price = round(float(info['price']), 2)
                brand = info.get('brand', s.get('brand') or 'FDplast')
                sku = s.get('source_sku') or info.get('source_sku', f"GS-{mat}")

                cur.execute("""
                    UPDATE spools
                    SET cost = %s,
                        source_type = %s,
                        source_sku = %s,
                        brand = %s,
                        price_updated_at = NOW()
                    WHERE id = %s;
                """, (new_price, source_name, sku, brand, s['id']))
                updated_count += 1

            detail_log = f"Актуализированы цены из Google Таблицы для {updated_count} катушек"
            if error_note:
                detail_log += f" (Резервный режим: {error_note})"

            cur.execute("""
                INSERT INTO action_logs (user_id, action, details)
                VALUES (%s, %s, %s);
            """, (
                user_id,
                'Синхронизация Google Таблицы',
                detail_log
            ))
        conn.commit()

    return updated_count, error_note


def get_catalog_item_by_code(code):
    for item in MARKETPLACE_CATALOG:
        if item['code'] == code:
            return item
    return MARKETPLACE_CATALOG[0]
