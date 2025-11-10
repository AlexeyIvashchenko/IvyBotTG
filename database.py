import sqlite3
from datetime import datetime
import logging
import config  # ДОБАВИЛИ ИМПОРТ CONFIG

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.conn = sqlite3.connect('bookings.db', check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        """Создает таблицы в базе данных"""
        cursor = self.conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                booking_date TEXT,
                status TEXT DEFAULT 'active',
                deposit_paid BOOLEAN DEFAULT FALSE,
                final_paid BOOLEAN DEFAULT FALSE,
                brief_completed BOOLEAN DEFAULT FALSE,
                payment_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                payment_id TEXT UNIQUE,
                amount REAL,
                payment_type TEXT,
                status TEXT DEFAULT 'pending',
                booking_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS support_chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Новая таблица для рабочих дней
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS work_days (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_date TEXT UNIQUE,
                is_available BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
                CREATE TABLE IF NOT EXISTS active_chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    admin_id INTEGER,
                    booking_date TEXT,
                    chat_started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (user_id) REFERENCES bookings (user_id)
                )
            ''')

        self.conn.commit()

    def add_booking(self, user_id, username, full_name, booking_date):
        """Добавляет бронирование в базу"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO bookings (user_id, username, full_name, booking_date, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, full_name, booking_date, "active"))
        self.conn.commit()
        return cursor.lastrowid

    def save_payment_info(self, user_id, payment_id, amount, booking_date, payment_type):
        """Сохраняет информацию о платеже"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO payments (user_id, payment_id, amount, payment_type, booking_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, payment_id, amount, payment_type, booking_date))
        self.conn.commit()

    def update_payment_status(self, payment_id, status):
        """Обновляет статус платежа"""
        cursor = self.conn.cursor()

        # Сначала обновляем статус в таблице payments
        cursor.execute('''
            UPDATE payments SET status = ? WHERE payment_id = ?
        ''', (status, payment_id))

        if status == 'succeeded':
            # Ищем соответствующее бронирование
            payment_info = self.get_payment_info(payment_id)
            if payment_info:
                user_id, payment_type, booking_date = payment_info[0], payment_info[3], payment_info[4]
                logger.info(f"Обновление бронирования: user_id={user_id}, type={payment_type}, date={booking_date}")

                if payment_type == 'deposit':
                    # Обновляем статус предоплаты
                    cursor.execute('''
                        UPDATE bookings SET deposit_paid = TRUE 
                        WHERE user_id = ? AND booking_date = ?
                    ''', (user_id, booking_date))
                    logger.info(f"Предоплата подтверждена для user_id={user_id}, date={booking_date}")
                elif payment_type == 'final':
                    # Обновляем статус финальной оплаты
                    cursor.execute('''
                        UPDATE bookings SET final_paid = TRUE 
                        WHERE user_id = ? AND booking_date = ?
                    ''', (user_id, booking_date))
                    logger.info(f"Финальная оплата подтверждена для user_id={user_id}, date={booking_date}")

        self.conn.commit()

    def get_payment_info(self, payment_id):
        """Получает информацию о платеже"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT user_id, payment_id, amount, payment_type, booking_date 
            FROM payments WHERE payment_id = ?
        ''', (payment_id,))
        return cursor.fetchone()

    def get_user_bookings(self, user_id):
        """Получает бронирования пользователя"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM bookings WHERE user_id = ? ORDER BY booking_date DESC
        ''', (user_id,))
        return cursor.fetchall()

    def is_date_available(self, booking_date):
        """Проверяет доступна ли дата в формате YYYY-MM-DD"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM bookings 
            WHERE booking_date = ? AND status = 'active' AND deposit_paid = TRUE
        ''', (booking_date,))
        count = cursor.fetchone()[0]

        # Также проверяем в Google Sheets через локальную логику
        # (это дополнительная проверка, основная - через booked_dates)
        logger.info(f"Проверка даты {booking_date}: найдено {count} оплаченных бронирований")
        return count == 0

    def mark_project_completed(self, user_id, booking_date):
        """Отмечает проект как завершенный"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE bookings SET status = 'completed' 
            WHERE user_id = ? AND booking_date = ?
        ''', (user_id, booking_date))
        self.conn.commit()
        logger.info(f"Проект отмечен завершенным: user_id={user_id}, date={booking_date}")

    def mark_brief_completed(self, user_id):
        """Отмечает бриф как заполненный"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE bookings SET brief_completed = TRUE WHERE user_id = ?
        ''', (user_id,))
        self.conn.commit()

    def get_today_bookings(self):
        """Получает бронирования на сегодня с предоплатой но без финальной оплаты"""
        cursor = self.conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute('''
            SELECT * FROM bookings 
            WHERE booking_date = ? AND deposit_paid = TRUE AND final_paid = FALSE
        ''', (today,))
        return cursor.fetchall()

    def get_upcoming_bookings(self, days=7):
        """Получает предстоящие бронирования"""
        cursor = self.conn.cursor()
        from datetime import datetime, timedelta

        upcoming_bookings = []
        for i in range(days + 1):
            target_date = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
            cursor.execute('''
                SELECT * FROM bookings 
                WHERE booking_date = ? AND deposit_paid = TRUE AND brief_completed = FALSE
            ''', (target_date,))
            upcoming_bookings.extend(cursor.fetchall())

        return upcoming_bookings

    def mark_date_as_booked(self, booking_date):
        """Отмечает дату как забронированную в базе данных"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE bookings SET status = 'booked' 
            WHERE booking_date = ? AND deposit_paid = TRUE
        ''', (booking_date,))
        self.conn.commit()

    def get_user_booking_date(self, user_id):
        """Получает дату бронирования пользователя"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT booking_date FROM bookings 
            WHERE user_id = ? AND deposit_paid = TRUE 
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else None

    def get_user_active_booking(self, user_id):
        """Получает активное бронирование пользователя (без проверки оплаты)"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM bookings 
            WHERE user_id = ? AND status = 'active'
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id,))
        return cursor.fetchone()

    def get_all_user_bookings(self, user_id):
        """Получает все бронирования пользователя (для отладки)"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM bookings WHERE user_id = ? ORDER BY created_at DESC
        ''', (user_id,))
        return cursor.fetchall()

    # НОВЫЕ МЕТОДЫ ДЛЯ РАБОЧИХ ДНЕЙ

    def add_work_day(self, work_date):
        """Добавляет рабочий день"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO work_days (work_date) VALUES (?)
            ''', (work_date,))
            self.conn.commit()
            logger.info(f"Добавлен рабочий день: {work_date}")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления рабочего дня {work_date}: {e}")
            return False

    def add_work_days_for_month(self, year, month):
        """Добавляет все рабочие дни для указанного месяца"""
        cursor = self.conn.cursor()
        try:
            import calendar
            cal = calendar.monthcalendar(year, month)

            work_days_added = 0
            for week in cal:
                for i, day in enumerate(week):
                    if day != 0 and i in config.WORK_DAYS:  # Проверяем день недели
                        work_date = f"{year}-{month:02d}-{day:02d}"
                        cursor.execute('''
                            INSERT OR IGNORE INTO work_days (work_date) VALUES (?)
                        ''', (work_date,))
                        work_days_added += 1

            self.conn.commit()
            logger.info(f"Добавлено {work_days_added} рабочих дней для {year}-{month:02d}")
            return work_days_added
        except Exception as e:
            logger.error(f"Ошибка добавления рабочих дней для месяца {year}-{month:02d}: {e}")
            return 0

    def remove_work_day(self, work_date):
        """Удаляет рабочий день"""
        cursor = self.conn.cursor()
        try:
            # Проверяем, нет ли активных бронирований на эту дату
            cursor.execute('''
                SELECT COUNT(*) FROM bookings 
                WHERE booking_date = ? AND deposit_paid = TRUE AND status = 'active'
            ''', (work_date,))
            active_bookings = cursor.fetchone()[0]

            if active_bookings > 0:
                return False, "На эту дату есть активные бронирования"

            cursor.execute('''
                DELETE FROM work_days WHERE work_date = ?
            ''', (work_date,))
            self.conn.commit()
            logger.info(f"Удален рабочий день: {work_date}")
            return True, "Рабочий день удален"
        except Exception as e:
            logger.error(f"Ошибка удаления рабочего дня {work_date}: {e}")
            return False, f"Ошибка: {e}"

    def get_available_work_days(self):
        """Получает все доступные рабочие дни"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT work_date FROM work_days 
            WHERE is_available = TRUE 
            ORDER BY work_date
        ''')
        return [row[0] for row in cursor.fetchall()]

    def get_all_work_days(self):
        """Получает все рабочие дни (для админки)"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT work_date FROM work_days 
            ORDER BY work_date
        ''')
        return [row[0] for row in cursor.fetchall()]

    def is_work_day(self, date_str):
        """Проверяет, является ли день рабочим"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM work_days WHERE work_date = ? AND is_available = TRUE
        ''', (date_str,))
        return cursor.fetchone()[0] > 0

    # В класс Database добавим:

    def start_chat_session(self, user_id, admin_id, booking_date):
        """Начинает сессию чата между специалистом и пользователем"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO active_chats (user_id, admin_id, booking_date, is_active)
                VALUES (?, ?, ?, TRUE)
            ''', (user_id, admin_id, booking_date))
            self.conn.commit()
            logger.info(f"Начат чат с пользователем {user_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка начала чата: {e}")
            return False

    def end_chat_session(self, user_id):
        """Завершает сессию чата"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                UPDATE active_chats SET is_active = FALSE WHERE user_id = ?
            ''', (user_id,))
            self.conn.commit()
            logger.info(f"Чат с пользователем {user_id} завершен")
            return True
        except Exception as e:
            logger.error(f"Ошибка завершения чата: {e}")
            return False

    def get_active_chat(self, user_id):
        """Получает активный чат пользователя"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM active_chats WHERE user_id = ? AND is_active = TRUE
        ''', (user_id,))
        return cursor.fetchone()

    def is_chat_active(self, user_id):
        """Проверяет, активен ли чат с пользователем"""
        return self.get_active_chat(user_id) is not None

    def initialize_work_days(self):
        """Инициализирует рабочие дни для ближайших 3 месяцев при первом запуске"""
        cursor = self.conn.cursor()

        # Проверяем, есть ли уже рабочие дни
        cursor.execute('SELECT COUNT(*) FROM work_days')
        count = cursor.fetchone()[0]

        if count == 0:
            logger.info("Инициализация рабочих дней для ближайших 3 месяцев...")

            from datetime import datetime, timedelta
            import calendar

            today = datetime.now()
            work_days_added = 0

            # Добавляем рабочие дни для ближайших 3 месяцев
            for i in range(config.MONTHS_TO_SHOW):
                month_date = today.replace(day=1) + timedelta(days=32 * i)
                month_date = month_date.replace(day=1)
                year = month_date.year
                month = month_date.month

                # Получаем календарь месяца
                cal = calendar.monthcalendar(year, month)

                for week in cal:
                    for day_idx, day in enumerate(week):
                        if day != 0 and day_idx in config.WORK_DAYS:  # Проверяем день недели
                            # Проверяем, что дата не в прошлом
                            date_obj = datetime(year, month, day)
                            if date_obj >= today.replace(hour=0, minute=0, second=0, microsecond=0):
                                work_date = f"{year}-{month:02d}-{day:02d}"
                                cursor.execute('''
                                    INSERT OR IGNORE INTO work_days (work_date) VALUES (?)
                                ''', (work_date,))
                                work_days_added += 1

            self.conn.commit()
            logger.info(f"Добавлено {work_days_added} рабочих дней для ближайших {config.MONTHS_TO_SHOW} месяцев")

        return count