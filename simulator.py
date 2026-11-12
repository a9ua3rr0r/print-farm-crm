import time
import threading
import random
import psycopg2
from psycopg2.extras import RealDictCursor

def recalculate_order_status(cur, order_id):
    """Единая функция пересчёта жизненного цикла заказа по состоянию его позиций."""
    cur.execute("""
        SELECT COALESCE(SUM(quantity), 0) AS total_qty,
               COALESCE(SUM(printed_qty), 0) AS total_printed,
               COALESCE(SUM(packed_qty), 0) AS total_packed
        FROM order_items
        WHERE order_id = %s;
    """, (order_id,))
    stats = cur.fetchone()
    if not stats or stats['total_qty'] == 0:
        return

    if stats['total_packed'] >= stats['total_qty']:
        new_status = 'ready'
    elif stats['total_printed'] > 0 or stats['total_packed'] > 0:
        new_status = 'in_progress'
    else:
        new_status = 'new'

    cur.execute("""
        UPDATE orders
        SET status = %s
        WHERE id = %s AND status NOT IN ('shipped', 'cancelled');
    """, (new_status, order_id))


class PrintFarmSimulator:
    def __init__(self, db_config, min_interval=20, max_interval=30, tick_interval=None):
        self.db_config = db_config
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.tick_interval = tick_interval or ((min_interval + max_interval) // 2)
        self.auto_enabled = False  # Флаг автоматической фоновой печати
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    def get_connection(self):
        return psycopg2.connect(**self.db_config)

    def start(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self):
        self._running = False

    def toggle_auto(self):
        """Переключает режим автоматической печати (ВКЛ / ВЫКЛ)."""
        self.auto_enabled = not self.auto_enabled
        return self.auto_enabled

    def _run_loop(self):
        while self._running:
            if self.auto_enabled:
                wait_sec = random.uniform(self.min_interval, self.max_interval)
                # Посекундный сон для мгновенной реакции при выключении тумблера
                slept = 0.0
                while slept < wait_sec and self._running and self.auto_enabled:
                    time.sleep(1.0)
                    slept += 1.0
                if self._running and self.auto_enabled:
                    try:
                        self.tick()
                    except Exception as e:
                        print(f"[Simulator Background Error] {e}")
            else:
                time.sleep(1.0)

    def tick(self, target_printer_id=None):
        """Выполняет один шаг симуляции (+20% к прогрессу) для всех или выбранного станка."""
        with self._lock:
            changes = {'started': 0, 'progressed': 0, 'completed': 0}
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. Автозапуск заданий из очереди, если назначенный принтер свободен
                    cur.execute("""
                        SELECT pj.id AS job_id, pj.printer_id, pj.order_item_id, p.current_spool_id
                        FROM print_jobs pj
                        JOIN printers p ON pj.printer_id = p.id
                        WHERE pj.status = 'pending' AND p.status = 'idle' AND p.is_active = TRUE
                        ORDER BY pj.id ASC;
                    """)
                    pending_jobs = cur.fetchall()
                    busy_printers = set()

                    for job in pending_jobs:
                        if target_printer_id and job['printer_id'] != target_printer_id:
                            continue
                        if job['printer_id'] in busy_printers:
                            continue
                        busy_printers.add(job['printer_id'])
                        cur.execute("""
                            UPDATE print_jobs
                            SET status = 'printing', progress = 10, started_at = NOW(),
                                spool_id = COALESCE(spool_id, %s)
                            WHERE id = %s;
                        """, (job['current_spool_id'], job['job_id']))
                        cur.execute("UPDATE printers SET status = 'printing' WHERE id = %s;", (job['printer_id'],))

                        cur.execute("SELECT order_id FROM order_items WHERE id = %s;", (job['order_item_id'],))
                        oi = cur.fetchone()
                        if oi:
                            cur.execute("""
                                UPDATE orders SET status = 'in_progress'
                                WHERE id = %s AND status = 'new';
                            """, (oi['order_id'],))
                        changes['started'] += 1

                    # 2. Продвижение активных заданий печати (+20% за шаг)
                    filter_sql = "AND pj.printer_id = %s" if target_printer_id else ""
                    params = (target_printer_id,) if target_printer_id else ()

                    cur.execute(f"""
                        SELECT pj.id, pj.printer_id, pj.order_item_id, pj.progress, pj.quantity,
                               pj.spool_id, pr.weight_g, pr.print_time_min, oi.order_id
                        FROM print_jobs pj
                        JOIN order_items oi ON pj.order_item_id = oi.id
                        JOIN products pr ON oi.product_id = pr.id
                        WHERE pj.status = 'printing' {filter_sql}
                        ORDER BY pj.id ASC;
                    """, params)
                    active_jobs = cur.fetchall()

                    for job in active_jobs:
                        new_progress = min(100, job['progress'] + 20)
                        if new_progress >= 100:
                            cur.execute("""
                                UPDATE print_jobs
                                SET status = 'completed', progress = 100, finished_at = NOW()
                                WHERE id = %s;
                            """, (job['id'],))

                            hours_added = round((job['print_time_min'] * job['quantity']) / 60.0, 2)
                            if job['printer_id']:
                                cur.execute("""
                                    UPDATE printers
                                    SET status = 'idle',
                                        total_print_time_hours = total_print_time_hours + %s
                                    WHERE id = %s;
                                """, (hours_added, job['printer_id']))

                            weight_used = float(job['weight_g']) * job['quantity']
                            if job['spool_id']:
                                cur.execute("""
                                    UPDATE spools
                                    SET current_weight_g = GREATEST(0, current_weight_g - %s)
                                    WHERE id = %s;
                                """, (weight_used, job['spool_id']))

                            cur.execute("""
                                UPDATE order_items
                                SET printed_qty = LEAST(quantity, printed_qty + %s)
                                WHERE id = %s;
                            """, (job['quantity'], job['order_item_id']))

                            recalculate_order_status(cur, job['order_id'])
                            changes['completed'] += 1
                        else:
                            cur.execute("""
                                UPDATE print_jobs SET progress = %s WHERE id = %s;
                            """, (new_progress, job['id']))
                            changes['progressed'] += 1

                conn.commit()
            return changes