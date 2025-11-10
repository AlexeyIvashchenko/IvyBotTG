from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton,
                           InlineKeyboardMarkup, InlineKeyboardButton)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
import calendar
import config


def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🗓️ Забронировать день")],
            [KeyboardButton(text="❓ Как всё проходит?"), KeyboardButton(text="💰 Услуги/оплата")],
            [KeyboardButton(text="📊 Примеры работ"), KeyboardButton(text="👨‍💼 Поддержка")]
        ],
        resize_keyboard=True
    )


def get_russian_month_name(date_obj):
    """Возвращает русское название месяца"""
    months_ru = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }
    return months_ru[date_obj.month]


def get_months_keyboard():
    """Клавиатура выбора месяцев - теперь только доступные месяцы с рабочими днями"""
    builder = InlineKeyboardBuilder()
    today = datetime.now()

    # Получаем все рабочие дни
    from database import Database
    db = Database()
    work_days = db.get_available_work_days()

    # Собираем уникальные месяцы из рабочих дней
    available_months = set()
    for work_day in work_days:
        date_obj = datetime.strptime(work_day, "%Y-%m-%d")
        month_key = date_obj.strftime("%Y-%m")
        available_months.add(month_key)

    # Добавляем кнопки для доступных месяцев
    for month_key in sorted(available_months):
        year, month = map(int, month_key.split('-'))
        month_date = datetime(year, month, 1)
        month_name = f"{get_russian_month_name(month_date)} {year}"

        builder.button(
            text=month_name,
            callback_data=f"month_{month_key}"
        )

    # Если нет доступных месяцев, возвращаем None
    if not available_months:
        return None

    builder.adjust(2)
    return builder.as_markup()


def get_days_keyboard(year_month, booked_dates):
    """Клавиатура выбора дней для конкретного месяца"""
    builder = InlineKeyboardBuilder()
    year, month = map(int, year_month.split('-'))

    # Получаем рабочие дни из базы
    from database import Database
    db = Database()
    work_days = db.get_available_work_days()

    # Получаем календарь месяца
    cal = calendar.monthcalendar(year, month)

    for week in cal:
        for day in week:
            if day != 0:
                date_obj = datetime(year, month, day)
                date_iso = date_obj.strftime("%Y-%m-%d")  # Формат для callback
                date_str = date_obj.strftime("%d.%m.%Y")  # Формат для сравнения с booked_dates
                weekday_ru = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"][date_obj.weekday()]

                # Проверяем, является ли день рабочим
                if date_iso in work_days:
                    if date_str in booked_dates:
                        builder.button(
                            text=f"❌ {day:02d} ({weekday_ru})",
                            callback_data="occupied"
                        )
                    else:
                        builder.button(
                            text=f"✅ {day:02d} ({weekday_ru})",
                            callback_data=f"book_{date_iso}"
                        )

    builder.button(text="🔙 Назад к месяцам", callback_data="back_to_months")
    builder.adjust(3)
    return builder.as_markup()


def get_payment_keyboard(amount, booking_date=None, is_final=False):
    """Клавиатура для оплаты - БЕЗ кнопки 'Я оплатил'"""
    builder = InlineKeyboardBuilder()

    if booking_date and not is_final:
        builder.button(
            text=f"💳 Оплатить {amount} ₽",
            callback_data=f"pay_deposit_{booking_date}"
        )
    elif is_final:
        builder.button(
            text=f"💳 Оплатить {amount} ₽",
            callback_data="pay_final"
        )

    builder.button(text="❌ Отмена", callback_data="cancel_payment")
    builder.adjust(1)
    return builder.as_markup()


def get_projects_keyboard():
    """Клавиатура для выбора проекта"""
    builder = InlineKeyboardBuilder()

    for project_key, project_data in config.PROJECTS.items():
        builder.button(
            text=project_data["name"],
            callback_data=f"show_project_{project_key}"
        )

    builder.adjust(1)
    return builder.as_markup()


def get_back_to_projects_keyboard():
    """Клавиатура для возврата к выбору проекта"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад к проектам", callback_data="back_to_projects")
    builder.adjust(1)
    return builder.as_markup()


def get_examples_keyboard():
    """Клавиатура для примеров работ"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📱 Примеры рекламы", callback_data="show_ads")
    builder.adjust(1)
    return builder.as_markup()


def get_admin_delivery_keyboard(user_id, booking_date, is_final_paid=False):
    """Клавиатура для отправки проекта клиенту"""
    builder = InlineKeyboardBuilder()

    if is_final_paid:
        builder.button(
            text="📤 Отправить проект клиенту",
            callback_data=f"deliver_{user_id}_{booking_date}"
        )
    else:
        builder.button(
            text="⏳ Ожидание финальной оплаты",
            callback_data="waiting_final_payment"
        )

    builder.adjust(1)
    return builder.as_markup()


# НОВЫЕ КЛАВИАТУРЫ ДЛЯ АДМИН-ПАНЕЛИ

def get_admin_work_keyboard():
    """Клавиатура управления рабочими днями"""
    builder = InlineKeyboardBuilder()

    builder.button(text="📅 Добавить месяц полностью", callback_data="admin_add_month")
    builder.button(text="➕ Добавить день работы", callback_data="admin_add_day")
    builder.button(text="🗑️ Удалить день работы", callback_data="admin_remove_day_menu")
    builder.button(text="🔙 Назад в админку", callback_data="admin_back")

    builder.adjust(1)
    return builder.as_markup()


def get_admin_months_keyboard(action="add"):
    """Клавиатура выбора месяцев для админа"""
    builder = InlineKeyboardBuilder()
    today = datetime.now()

    # Показываем 12 месяцев вперед для админа
    for i in range(12):
        month_date = today.replace(day=1) + timedelta(days=32 * i)
        month_date = month_date.replace(day=1)
        month_name = f"{get_russian_month_name(month_date)} {month_date.year}"

        if action == "add":
            callback_data = f"admin_month_{month_date.strftime('%Y-%m')}"
        else:
            callback_data = f"admin_remove_month_{month_date.strftime('%Y-%m')}"

        builder.button(
            text=month_name,
            callback_data=callback_data
        )

    builder.button(text="🔙 Назад", callback_data="admin_work_back")
    builder.adjust(2)
    return builder.as_markup()


def get_admin_days_keyboard(year_month):
    """Клавиатура выбора дней для удаления (для админа)"""
    builder = InlineKeyboardBuilder()
    year, month = map(int, year_month.split('-'))

    # Получаем рабочие дни и забронированные даты
    from database import Database
    db = Database()
    work_days = db.get_all_work_days()

    # Получаем забронированные даты
    booked_dates = db.conn.cursor().execute('''
        SELECT booking_date FROM bookings 
        WHERE deposit_paid = TRUE AND status = 'active'
    ''').fetchall()
    booked_dates_set = {row[0] for row in booked_dates}  # Используем формат YYYY-MM-DD

    # Получаем календарь месяца
    cal = calendar.monthcalendar(year, month)

    for week in cal:
        for day in week:
            if day != 0:
                date_obj = datetime(year, month, day)
                date_iso = date_obj.strftime("%Y-%m-%d")
                weekday_ru = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"][date_obj.weekday()]

                # Проверяем, является ли день рабочим
                if date_iso in work_days:
                    if date_iso in booked_dates_set:  # Используем тот же формат для сравнения
                        builder.button(
                            text=f"❌ {day:02d} ({weekday_ru})",
                            callback_data="admin_occupied"
                        )
                    else:
                        builder.button(
                            text=f"✅ {day:02d} ({weekday_ru})",
                            callback_data=f"admin_remove_{date_iso}"  # ТОЛЬКО даты в формате YYYY-MM-DD
                        )

    builder.button(text="🔙 Назад к месяцам", callback_data="admin_remove_back")
    builder.adjust(3)
    return builder.as_markup()


def get_admin_chat_keyboard(user_id, booking_date):
    """Клавиатура для администратора во время диалога"""
    builder = InlineKeyboardBuilder()

    builder.button(
        text="📞 Связаться с пользователем",
        callback_data=f"start_chat_{user_id}_{booking_date}"
    )

    builder.adjust(1)
    return builder.as_markup()


def get_admin_chat_active_keyboard(user_id):
    """Клавиатура когда диалог активен"""
    builder = InlineKeyboardBuilder()

    builder.button(
        text="🔒 Завершить диалог",
        callback_data=f"end_chat_{user_id}"
    )

    builder.adjust(1)
    return builder.as_markup()


def get_user_chat_notification_keyboard():
    """Клавиатура для уведомления пользователя о начале диалога"""
    builder = InlineKeyboardBuilder()

    builder.button(
        text="💬 Ответить специалисту",
        callback_data="reply_to_specialist"
    )

    builder.adjust(1)
    return builder.as_markup()