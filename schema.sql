DROP TABLE IF EXISTS action_logs CASCADE;
DROP TABLE IF EXISTS maintenance_requests CASCADE;
DROP TABLE IF EXISTS print_jobs CASCADE;
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS printers CASCADE;
DROP TABLE IF EXISTS spools CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS clients CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- 1. Пользователи системы
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'manager', 'operator')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Клиенты
CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(30) NOT NULL,
    email VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Каталог изделий (3D-моделей)
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(150) NOT NULL,
    material VARCHAR(50) NOT NULL,
    weight_g NUMERIC(8, 2) NOT NULL CHECK (weight_g > 0),
    print_time_min INTEGER NOT NULL CHECK (print_time_min > 0),
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    is_active BOOLEAN DEFAULT TRUE
);

-- 4. Склад пластика (катушки филамента)
CREATE TABLE spools (
    id SERIAL PRIMARY KEY,
    material VARCHAR(50) NOT NULL,
    color VARCHAR(50) NOT NULL,
    initial_weight_g NUMERIC(8, 2) NOT NULL CHECK (initial_weight_g > 0),
    current_weight_g NUMERIC(8, 2) NOT NULL CHECK (current_weight_g >= 0),
    cost NUMERIC(10, 2) DEFAULT 0.00 CHECK (cost >= 0),
    is_active BOOLEAN DEFAULT TRUE
);

-- 5. Парк 3D-принтеров
CREATE TABLE printers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    model VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'idle' CHECK (status IN ('idle', 'printing', 'maintenance', 'offline')),
    current_spool_id INTEGER REFERENCES spools(id) ON DELETE SET NULL,
    total_print_time_hours NUMERIC(10, 2) DEFAULT 0.00,
    is_active BOOLEAN DEFAULT TRUE
);

-- 6. Заказы клиентов
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    status VARCHAR(20) DEFAULT 'new' CHECK (status IN ('new', 'in_progress', 'ready', 'shipped', 'cancelled')),
    tracking_token VARCHAR(64) UNIQUE NOT NULL,
    deadline DATE NOT NULL,
    total_price NUMERIC(10, 2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Позиции заказа
CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    printed_qty INTEGER DEFAULT 0 CHECK (printed_qty >= 0),
    packed_qty INTEGER DEFAULT 0 CHECK (packed_qty >= 0)
);

-- 8. Очередь печати (производственные задания)
CREATE TABLE print_jobs (
    id SERIAL PRIMARY KEY,
    printer_id INTEGER REFERENCES printers(id) ON DELETE SET NULL,
    order_item_id INTEGER NOT NULL REFERENCES order_items(id) ON DELETE CASCADE,
    spool_id INTEGER REFERENCES spools(id) ON DELETE SET NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'printing', 'completed', 'failed', 'cancelled')),
    progress INTEGER DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    fail_reason TEXT
);

-- 9. Журнал технического обслуживания оборудования
CREATE TABLE maintenance_requests (
    id SERIAL PRIMARY KEY,
    printer_id INTEGER NOT NULL REFERENCES printers(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    priority VARCHAR(20) DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'urgent')),
    status VARCHAR(20) DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution_notes TEXT
);

-- 10. Журнал аудита действий пользователей
CREATE TABLE action_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(255) NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
