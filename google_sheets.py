import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import config
import logging

logger = logging.getLogger(__name__)

# Импортируем db здесь чтобы избежать циклического импорта
from database import Database

db = Database()


class GoogleSheets:
    def __init__(self):
        try:
            scope = ['https://spreadsheets.google.com/feeds',
                     'https://www.googleapis.com/auth/drive']

            creds = Credentials.from_service_account_info(config.GOOGLE_SHEETS_CREDENTIALS, scopes=scope)

            # НОВЫЙ СПОСОБ: создаем клиент без устаревших параметров
            self.client = gspread.auth.authorize(creds)

            # Открываем таблицу
            self.sheet = self.client.open_by_key(config.SPREADSHEET_ID).sheet1

            # Инициализируем заголовки если таблица пустая
            self._initialize_headers()

        except Exception as e:
            logger.error(f"Ошибка инициализации Google Sheets: {e}")
            # Создаем заглушку чтобы бот мог работать
            self.sheet = None

    def _initialize_headers(self):
        """Инициализирует заголовки если таблица пустая"""
        try:
            # Пробуем прочитать данные
            data = self.sheet.get_all_values()

            # Если таблица пустая или нет данных
            if not data or len(data) == 0:
                headers = [
                    'Дата создания', 'ID пользователя', 'Username', 'Имя',
                    'Дата брони', 'Статус брифа', 'Статус оплаты', 'ID платежа',
                    'Сумма предоплаты', 'Сумма финальная', 'Заполнен бриф', 'Телефон', 'Email'
                ]
                self.sheet.append_row(headers)
                logger.info("Заголовки таблицы инициализированы")
            else:
                logger.info("Таблица уже содержит данные")

        except Exception as e:
            logger.error(f"Ошибка инициализации заголовков: {e}")
            # Создаем заголовки в любом случае
            try:
                headers = [
                    'Дата создания', 'ID пользователя', 'Username', 'Имя',
                    'Дата брони', 'Статус брифа', 'Статус оплаты', 'ID платежа',
                    'Сумма предоплаты', 'Сумма финальная', 'Заполнен бриф', 'Телефон', 'Email'
                ]
                self.sheet.append_row(headers)
            except:
                pass

    # Все остальные методы остаются без изменений...
    def is_connected(self):
        """Проверяет подключение к Google Sheets"""
        return self.sheet is not None

    def find_booking_row(self, booking_date, user_id=None):
        """Находит строку с бронированием по дате или пользователю"""
        if not self.is_connected():
            return None

        try:
            records = self.sheet.get_all_records()
            for i, record in enumerate(records, start=2):
                if user_id and str(record.get('ID пользователя', '')) == str(user_id):
                    return i
                # Преобразуем дату к формату таблицы (dd.mm.yyyy)
                record_date = record.get('Дата брони', '')
                if record_date == booking_date:
                    return i
            return None
        except Exception as e:
            logger.error(f"Ошибка поиска бронирования: {e}")
            return None

    def add_booking(self, user_data, booking_date, payment_id=None):
        """Добавляет бронирование в таблицу"""
        if not self.is_connected():
            logger.warning("Google Sheets не подключен, бронирование не сохранено")
            return False

        try:
            # Преобразуем дату к формату dd.mm.yyyy для Google Sheets
            booking_date_str = booking_date.strftime("%d.%m.%Y")

            row = [
                datetime.now().strftime("%d.%m.%Y %H:%M"),
                user_data['user_id'],
                user_data.get('username', ''),
                user_data.get('full_name', ''),
                booking_date_str,  # Используем отформатированную дату
                "Ожидает заполнения брифа",
                "Предоплата ожидается",
                payment_id or "",
                config.DEPOSIT_AMOUNT,
                config.FINAL_AMOUNT,
                "Нет",  # Заполнен бриф
                "", "",  # Телефон, Email
            ]
            self.sheet.append_row(row)
            logger.info(f"Бронирование добавлено: {booking_date_str} для пользователя {user_data['user_id']}")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления бронирования: {e}")
            return False

    def get_booked_dates(self):
        """Получает все забронированные даты"""
        if not self.is_connected():
            return []

        try:
            records = self.sheet.get_all_records()
            booked_dates = []

            # Пропускаем первую строку (заголовки)
            for i, record in enumerate(records):
                # Проверяем что запись не пустая и содержит нужные поля
                if record and isinstance(record, dict):
                    date_str = record.get('Дата брони', '')
                    status = record.get('Статус оплаты', '')

                    # Проверяем что date_str не пустой и статус подходящий
                    if date_str and date_str.strip() and status in ['Предоплата получена', 'Полная оплата']:
                        # Убедимся, что дата в правильном формате
                        try:
                            # Проверяем формат даты (должен быть DD.MM.YYYY)
                            datetime.strptime(date_str.strip(), "%d.%m.%Y")
                            booked_dates.append(date_str.strip())
                        except ValueError:
                            logger.warning(f"Некорректный формат даты в таблице: {date_str}")
                            continue

            logger.info(f"Забронированные даты из Google Sheets: {booked_dates}")
            return booked_dates
        except Exception as e:
            logger.error(f"Ошибка получения забронированных дат: {e}")
            return []

    def update_booking_status(self, user_id, booking_date, status="Предоплата получена"):
        """Обновляет статус бронирования в Google Sheets"""
        if not self.is_connected():
            logger.warning("Google Sheets не подключен")
            return False

        try:
            # Преобразуем дату к формату dd.mm.yyyy для поиска
            if isinstance(booking_date, str) and '-' in booking_date:
                # Если дата в формате YYYY-MM-DD, преобразуем в DD.MM.YYYY
                date_obj = datetime.strptime(booking_date, "%Y-%m-%d")
                booking_date_search = date_obj.strftime("%d.%m.%Y")
            else:
                booking_date_search = booking_date

            # Ищем строку по user_id и booking_date
            records = self.sheet.get_all_records()
            logger.info(f"Всего записей в таблице: {len(records)}")

            for i, record in enumerate(records, start=2):  # start=2 потому что первая строка - заголовки
                record_user_id = str(record.get('ID пользователя', ''))
                record_booking_date = record.get('Дата брони', '')

                logger.info(f"Запись {i}: user_id={record_user_id}, date={record_booking_date}")

                if (record_user_id == str(user_id) and
                        record_booking_date == booking_date_search):

                    # Обновляем статус в зависимости от типа статуса
                    if status == "Проект завершен":
                        # При завершении проекта обновляем несколько полей
                        self.sheet.update_cell(i, 7, "Проект завершен")  # Колонка 7 - Статус оплаты
                        self.sheet.update_cell(i, 6, "Проект завершен")  # Колонка 6 - Статус брифа
                        self.sheet.update_cell(i, 11, "Да")  # Колонка 11 - Заполнен бриф
                        logger.info(f"Проект отмечен завершенным для строки {i}")

                    elif status == "Предоплата получена":
                        # Обновляем только статус оплаты для предоплаты
                        self.sheet.update_cell(i, 7, status)  # Колонка 7 - Статус оплаты
                        logger.info(f"Статус обновлен для строки {i}: {status}")

                    elif status == "Полная оплата":
                        # Обновляем статус для финальной оплаты
                        self.sheet.update_cell(i, 7, status)  # Колонка 7 - Статус оплаты
                        logger.info(f"Статус обновлен для строки {i}: {status}")

                    else:
                        # Для других статусов обновляем только статус оплаты
                        self.sheet.update_cell(i, 7, status)
                        logger.info(f"Статус обновлен для строки {i}: {status}")

                    return True

            logger.warning(f"Не найдена запись для user_id={user_id}, date={booking_date_search}")
            return False

        except Exception as e:
            logger.error(f"Ошибка обновления статуса бронирования: {e}")
            return False

    def update_payment_status(self, user_id, status="Предоплата получена", final_payment=False):
        """Обновляет статус оплаты по ID пользователя"""
        if not self.is_connected():
            logger.warning("Google Sheets не подключен")
            return False

        try:
            # Получаем booking_date из базы данных
            booking = db.get_user_active_booking(user_id)
            if not booking:
                logger.warning(f"Не найдено активных бронирований для пользователя {user_id}")
                return False

            booking_date = booking[4]  # booking_date field
            logger.info(f"Обновление статуса для пользователя {user_id}, дата {booking_date}")

            return self.update_booking_status(user_id, booking_date, status)

        except Exception as e:
            logger.error(f"Ошибка обновления статуса оплаты: {e}")
            return False

    def mark_brief_completed(self, user_id):
        """Отмечает что бриф заполнен"""
        if not self.is_connected():
            return False

        try:
            row_index = self.find_booking_row(None, user_id)
            if row_index:
                self.sheet.update_cell(row_index, 6, "Бриф заполнен")
                self.sheet.update_cell(row_index, 11, "Да")
                logger.info(f"Бриф отмечен заполненным для пользователя {user_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка отметки брифа: {e}")
            return False

    def get_today_bookings(self):
        """Получает бронирования на сегодня"""
        if not self.is_connected():
            return []

        try:
            today = datetime.now().strftime("%d.%m.%Y")
            records = self.sheet.get_all_records()
            today_bookings = []

            for record in records:
                if record.get('Дата брони') == today and record.get('Статус оплаты') == 'Предоплата получена':
                    today_bookings.append(record)

            return today_bookings
        except Exception as e:
            logger.error(f"Ошибка получения сегодняшних бронирований: {e}")
            return []