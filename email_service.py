import os
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from psycopg2.extras import RealDictCursor
from db import get_db_connection

SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.yandex.ru')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 465))
SMTP_USER = os.environ.get('SMTP_USER', 'farm3dcrm@yandex.ru')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', 'kddlpgxkbdqrfscn')
SMTP_FROM_NAME = os.environ.get('SMTP_FROM_NAME', 'PrintFarm 3D — Студия 3D-печати')


def build_order_email_html(order, items, event_type, base_url):
    """Формирует фирменное HTML-письмо с таблицей деталей и кнопкой перехода в трекер."""
    order_num = f"#ORD-{order['id']:04d}"
    track_url = f"{base_url.rstrip('/')}/track/{order['tracking_token']}"
    deadline_str = order['deadline'].strftime('%d.%m.%Y') if order.get('deadline') else '—'
    total_str = f"{float(order.get('total_price') or 0):,.2f}".replace(',', ' ') + ' ₽'

    if event_type == 'ready':
        badge_bg = '#059669'
        badge_text = 'ГОТОВ К ВЫДАЧЕ'
        headline = f'Ваш заказ {order_num} полностью напечатан и готов к получению!'
        subtext = (
            'Все 3D-детали вашего заказа успешно прошли послойную печать, очистку от поддержек, '
            'контроль качества (ОТК) и упакованы для выдачи.'
        )
    else:
        badge_bg = '#be123c'
        badge_text = 'ПРИНЯТ В ПРОИЗВОДСТВО'
        headline = f'Заказ {order_num} сформирован и передан в студию 3D-печати'
        subtext = (
            'Мы подготовили цифровые 3D-модели ваших изделий и поставили партию в производственную очередь. '
            'Вы можете отслеживать прогресс печати каждой детали в реальном времени по кнопке ниже.'
        )

    rows_html = ''
    for idx, it in enumerate(items, start=1):
        rows_html += f"""
        <tr>
            <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; color: #0f172a; font-size: 14px;">
                <strong>{idx}. {it['product_name']}</strong><br>
                <span style="color: #64748b; font-size: 12px;">Артикул: {it['sku']} • Материал: {it['material']}</span>
            </td>
            <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; text-align: center; color: #0f172a; font-weight: 600;">
                {it['quantity']} шт.
            </td>
            <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; text-align: right; color: #059669; font-size: 13px; font-weight: 600;">
                Упаковано: {it['packed_qty']} из {it['quantity']}
            </td>
        </tr>
        """

    subject = (
        f"PrintFarm 3D: Заказ {order_num} готов к выдаче!"
        if event_type == 'ready'
        else f"PrintFarm 3D: Заказ {order_num} принят в работу"
    )

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>{subject}</title>
</head>
<body style="margin: 0; padding: 24px; background-color: #f1f5f9; font-family: 'Segoe UI', Arial, sans-serif; color: #0f172a;">
    <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 640px; margin: 0 auto; background: #ffffff; border-radius: 14px; overflow: hidden; border: 1px solid #cbd5e1; box-shadow: 0 10px 25px rgba(15, 23, 42, 0.08);">
        <tr>
            <td style="background: #0f172a; padding: 22px 28px; color: #ffffff;">
                <table width="100%">
                    <tr>
                        <td>
                            <div style="font-size: 20px; font-weight: 700;">
                                PrintFarm<span style="color: #be123c;">.3D</span>
                            </div>
                            <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">
                                Автоматизированная система аддитивного производства
                            </div>
                        </td>
                        <td align="right">
                            <span style="background: {badge_bg}; color: #ffffff; padding: 6px 12px; border-radius: 20px; font-size: 11px; font-weight: 700;">
                                {badge_text}
                            </span>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
        <tr>
            <td style="padding: 28px;">
                <p style="margin: 0 0 8px 0; font-size: 14px; color: #64748b;">Здравствуйте, <strong>{order['client_name']}</strong>!</p>
                <h2 style="margin: 0 0 12px 0; font-size: 20px; color: #0f172a;">{headline}</h2>
                <p style="margin: 0 0 22px 0; font-size: 14px; line-height: 1.55; color: #334155;">{subtext}</p>

                <table width="100%" cellpadding="0" cellspacing="0" style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; margin-bottom: 22px;">
                    <tr>
                        <td style="font-size: 13px; color: #64748b;">Номер заказа:<br><strong style="color: #0f172a; font-size: 15px;">{order_num}</strong></td>
                        <td style="font-size: 13px; color: #64748b;">Плановый срок сдачи:<br><strong style="color: #0f172a; font-size: 15px;">{deadline_str}</strong></td>
                        <td style="font-size: 13px; color: #64748b;" align="right">Итоговая сумма:<br><strong style="color: #be123c; font-size: 15px;">{total_str}</strong></td>
                    </tr>
                </table>

                <div style="font-size: 12px; font-weight: 700; text-transform: uppercase; color: #64748b; margin-bottom: 8px;">
                    Состав заказа
                </div>
                <table width="100%" cellpadding="0" cellspacing="0" style="border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; margin-bottom: 26px;">
                    <thead>
                        <tr style="background: #f1f5f9;">
                            <th align="left" style="padding: 10px 12px; font-size: 12px; color: #475569;">Изделие</th>
                            <th align="center" style="padding: 10px 12px; font-size: 12px; color: #475569;">Кол-во</th>
                            <th align="right" style="padding: 10px 12px; font-size: 12px; color: #475569;">Статус ОТК</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>

                <div style="text-align: center; margin: 28px 0;">
                    <a href="{track_url}" target="_blank"
                       style="background: #be123c; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 700; font-size: 14px; display: inline-block;">
                        Отследить статус печати в реальном времени &rarr;
                    </a>
                    <div style="margin-top: 10px; font-size: 12px; color: #64748b;">
                        Прямая ссылка: <a href="{track_url}" style="color: #be123c;">{track_url}</a>
                    </div>
                </div>
            </td>
        </tr>
        <tr>
            <td style="background: #f8fafc; padding: 16px 28px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center;">
                Уведомление сформировано автоматически системой <strong>PrintFarm 3D</strong>.
            </td>
        </tr>
    </table>
</body>
</html>"""
    return subject, html, track_url


def _fetch_order_and_items(order_id):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT o.*, c.name AS client_name, c.email AS client_email, c.phone AS client_phone
                FROM orders o
                JOIN clients c ON o.client_id = c.id
                WHERE o.id = %s;
            """, (order_id,))
            order = cur.fetchone()
            if not order:
                return None, []

            cur.execute("""
                SELECT oi.*, pr.name AS product_name, pr.sku, pr.material
                FROM order_items oi
                JOIN products pr ON oi.product_id = pr.id
                WHERE oi.order_id = %s
                ORDER BY oi.id ASC;
            """, (order_id,))
            items = cur.fetchall()
            return order, items


def _log_email_event(user_id, action, details):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO action_logs (user_id, action, details) VALUES (%s, %s, %s);",
                    (user_id, action, details)
                )
            conn.commit()
    except Exception as e:
        print(f"[Email Audit Error] {e}")


def _send_email_background_worker(order_id, event_type, base_url, user_id=None):
    order, items = _fetch_order_and_items(order_id)
    if not order:
        return

    recipient = (order.get('client_email') or '').strip()
    subject, html_body, track_url = build_order_email_html(order, items, event_type, base_url)

    if not recipient:
        _log_email_event(
            user_id,
            "Email-уведомление (без адреса)",
            f"Для заказа #ORD-{order_id:04d} сформировано письмо «{subject}» (трекер: {track_url})"
        )
        return

    if SMTP_USER and SMTP_PASSWORD:
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = Header(subject, 'utf-8')
            msg['From'] = formataddr((str(Header(SMTP_FROM_NAME, 'utf-8')), SMTP_USER))
            msg['To'] = recipient
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            if SMTP_PORT == 465:
                with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                    server.sendmail(SMTP_USER, [recipient], msg.as_string())
            else:
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                    server.starttls()
                    server.login(SMTP_USER, SMTP_PASSWORD)
                    server.sendmail(SMTP_USER, [recipient], msg.as_string())

            _log_email_event(
                user_id,
                "Отправлено Email-письмо",
                f"Письмо «{subject}» отправлено клиенту на {recipient} (трекер: {track_url})"
            )
        except Exception as e:
            _log_email_event(
                user_id,
                "Ошибка SMTP (сохранена копия письма)",
                f"Попытка отправки на {recipient}: {e}. Письмо доступно в предпросмотре заказа #ORD-{order_id:04d}."
            )
    else:
        _log_email_event(
            user_id,
            "Сформировано Email-письмо клиенту",
            f"Получатель: {recipient} | Тема: «{subject}» | Ссылка отслеживания: {track_url}"
        )


def send_order_email(order_id, event_type='created', base_url='http://127.0.0.1:5003', user_id=None):
    """Асинхронная отправка письма в отдельном потоке без зависания интерфейса."""
    t = threading.Thread(
        target=_send_email_background_worker,
        args=(order_id, event_type, base_url, user_id),
        daemon=True
    )
    t.start()


def get_order_email_preview(order_id, event_type=None, base_url='http://127.0.0.1:5003'):
    order, items = _fetch_order_and_items(order_id)
    if not order:
        return None
    if not event_type:
        event_type = 'ready' if order['status'] in ('ready', 'shipped') else 'created'
    subject, html_body, track_url = build_order_email_html(order, items, event_type, base_url)
    return {
        'subject': subject,
        'recipient': order.get('client_email') or 'Не указан',
        'html': html_body,
        'track_url': track_url
    }