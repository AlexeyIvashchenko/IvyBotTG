import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.client.default import DefaultBotProperties
from datetime import datetime
import config
from keyboards import *
from google_sheets import GoogleSheets
from payments import PaymentManager
from database import Database
from reminders import ReminderSystem
from aiogram.types import WebAppInfo
import json
from aiogram.types import Update

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация
storage = MemoryStorage()
bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher(storage=storage)
db = Database()

# ИНИЦИАЛИЗИРУЕМ РАБОЧИЕ ДНИ ПРИ ПЕРВОМ ЗАПУСКЕ
db.initialize_work_days()

try:
    gsheets = GoogleSheets()
    if not gsheets.is_connected():
        logger.warning("Google Sheets не подключен, работаем только с локальной БД")
except Exception as e:
    logger.error(f"Ошибка инициализации Google Sheets: {e}")
    gsheets = None

payment_manager = PaymentManager()
reminder_system = ReminderSystem(gsheets)


# Состояния для FSM
class BookingState(StatesGroup):
    waiting_for_support = State()
    waiting_for_delivery = State()
    admin_support_reply = State()
    project_completed = State()
    specialist_chat_active = State()
    user_chat_active = State()


# Новые состояния для управления рабочими днями
class AdminWorkState(StatesGroup):
    waiting_for_month = State()
    waiting_for_day = State()
    waiting_for_remove_day = State()


def get_russian_month_name(date_obj):
    """Возвращает русское название месяца"""
    months_ru = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }
    return months_ru[date_obj.month]


# 📍 ОСНОВНЫЕ КОМАНДЫ

@dp.message(CommandStart())
async def cmd_start(message: Message):
    welcome_text = """
Привет! Я Айви. Через меня проходит 99% коммуникации.

Вам нужно создать адаптивный рабочий сайт и настроить рекламу в Яндексе? Специалист с 5-летним опытом в маркетинге и дизайне сделает это для Вас за 1 день! Без долгив переписок, подрядчиков и ожиданий.

С чего начнём?
    """
    photo = FSInputFile("photos/Lucid_Origin_A_stunning_Brazilian_model_with_unique_and_captiv_2.jpg")

    await message.answer_photo(
        photo=photo,
        caption=welcome_text,
        reply_markup=get_main_keyboard()
    )


@dp.message(F.text == "🗓️ Забронировать день")
async def book_day(message: Message):
    info_text = """
📅 <b>Бронирование дня</b>

Я работаю только по понедельникам, средам и пятницам. 
В неделю доступно всего 3 рабочих дней — бронируйте заранее!

Выберите месяц для просмотра доступных дат:
    """

    # Получаем забронированные даты из обоих источников
    booked_dates = []
    if gsheets:
        booked_dates = gsheets.get_booked_dates()

    # Также получаем забронированные даты из локальной базы
    from database import Database
    db = Database()

    # Получаем все активные бронирования с предоплатой
    all_bookings = db.conn.cursor().execute('''
        SELECT booking_date FROM bookings 
        WHERE deposit_paid = TRUE AND status = 'active'
    ''').fetchall()

    # Добавляем даты из базы в формате DD.MM.YYYY
    for booking in all_bookings:
        date_obj = datetime.strptime(booking[0], "%Y-%m-%d")
        booked_dates.append(date_obj.strftime("%d.%m.%Y"))

    keyboard = get_months_keyboard()

    if keyboard is None:
        await message.answer(
            "📅 <b>На данный момент нет доступных дат для бронирования</b>\n\n"
            "Все рабочие дни уже заняты или еще не настроены администратором.\n\n"
            "Пожалуйста, попробуйте позже или свяжитесь с поддержкой для уточнения доступных дат."
        )
    else:
        await message.answer(info_text, reply_markup=keyboard)


@dp.message(F.text == "❓ Как всё проходит?")
async def how_it_works(message: Message):
    text = """
Процесс простой и быстрый 👇

1️⃣ Вы бронируете день и вносите предоплату (4 000 ₽)
2️⃣ Заполняете бриф (если чего-то нет, создадим сами, потом сможете заменить.)
3️⃣ В выбранный день выполняется работа.
4️⃣ Вы оплачиваете оставшуюся сумму (11 000 ₽)
5️⃣ Отправляем вам весь проект + инструкции до 8 вечера по МСК

Весь процесс — 1 день. Без ожиданий и сложностей.

<b>НО! Есть несколько правил:</b>

- если специалист по любым причинам не выполнил проект вовремя — вся сумма в полном размере возвращается клиенту в ближашие 12 часов.

- если клиент не заполнил бриф до назначенного дня — проект закрывается, предоплата не возвращается.

- если клиент не оплатил вторую часть суммы в назначенный день — проект закрывается, предоплата не возвращается.
    """
    await message.answer(text)


@dp.message(F.text == "💰 Услуги/оплата")
async def services_payment(message: Message):
    text = """
<b>В проект входит:</b>

1️⃣ Сбор ключевых слов (для написания seo-текстов и рекламы в Яндексе)
2️⃣ Создание лендинга (одностраничного сайта). Сайт адаптирован под несколько разрешений экрана. 
3️⃣ Оформление сайта для поисковой выдачи + настройка аналитики/ подключение форм заявок
4️⃣ Создание 2-3 рекламных кампании в Яндекс.Директ. Продвижение рекламы по интересам пользователей и по ключевым словам.
5️⃣ Написание инструкции, если понадобится пополнить баланс в рекламе, изменить фото на сайте и другое

После запуска реклама начнёт работать, сайт будет полностью готов к приёму заявок, а аналитика — собираться автоматически. Никаких дополнительных действий не потребуется.

<b>ВАЖНО!</b> Реклама требует внимания. Да, мы создаем стартовую рекламу и подключаем аналитику. Но далее вы можете адаптироваться самостоятельно или обратиться к маркетологу. Без должного внимания реклама будет не качественной и вы будете сливать большой бюджет вникуда. 

💰 <b>Стоимость данного пакета — 15 000 ₽</b>

Предоплата 4 000 ₽ — это необходимо для того, чтобы специалист выделил день на ваш проект.

После оплаты появится ссылка на бриф и закрепится дата выполнения.
    """
    await message.answer(text)


@dp.message(F.text == "📊 Примеры работ")
async def examples(message: Message):
    text = """
🎨 <b>Примеры выполненных работ</b>

Выберите проект для просмотра готовых работ:

• 🎓 <b>Курсы английского</b> - лендинг для школы английского языка
• 💪 <b>Фитнес-центр</b> - сайт фитнес-центра с онлайн-записью  
• 💎 <b>Украшения ручной работы</b> - интернет-магазин украшений

Каждый проект включает адаптивный сайт и рекламные кампании.
    """
    await message.answer(text, reply_markup=get_projects_keyboard())


@dp.message(F.text == "👨‍💼 Поддержка")
async def support(message: Message, state: FSMContext):
    # Проверяем, завершен ли проект у пользователя
    user_id = message.from_user.id
    cursor = db.conn.cursor()
    cursor.execute('''
        SELECT status FROM bookings 
        WHERE user_id = ? AND status = 'completed'
        ORDER BY created_at DESC LIMIT 1
    ''', (user_id,))

    completed_project = cursor.fetchone()

    if completed_project:
        text = """
💬 <b>Связь с поддержкой</b>

Напишите ваш вопрос ниже, и я передам его специалисту. Он ответит вам в ближайшее время.

<i>Пожалуйста, опишите вопрос максимально подробно.</i>
        """
    else:
        text = """
💬 <b>Связь с поддержкой</b>

Напишите ваш вопрос ниже, и я передам его специалисту. Он ответит вам в ближайшее время.

<i>Пожалуйста, опишите вопрос максимально подробно.</i>
        """

    await message.answer(text)
    await state.set_state(BookingState.waiting_for_support)


# 📍 НОВЫЕ ОБРАБОТЧИКИ ДЛЯ ПРОЕКТОВ

@dp.callback_query(F.data == "back_to_projects")
async def back_to_projects(callback: CallbackQuery):
    """Возврат к выбору проекта"""
    text = """
🎨 <b>Примеры выполненных работ</b>

Выберите проект для просмотра готовых работ:

• 🎓 <b>Курсы английского</b> - лендинг для школы английского языка
• 💪 <b>Фитнес-центр</b> - сайт фитнес-центра с онлайн-записью  
• 💎 <b>Украшения ручной работы</b> - интернет-магазин украшений

Каждый проект включает адаптивный сайт и рекламные кампании.
    """

    # Удаляем предыдущее сообщение с кнопкой "Назад"
    await callback.message.delete()

    # Отправляем новое сообщение с выбором проектов
    await callback.message.answer(text, reply_markup=get_projects_keyboard())
    await callback.answer()


@dp.callback_query(F.data.startswith("show_project_"))
async def show_project(callback: CallbackQuery):
    """Показывает фото выбранного проекта"""
    project_key = callback.data.split("_")[2]

    if project_key not in config.PROJECTS:
        await callback.answer("❌ Проект не найден")
        return

    project_data = config.PROJECTS[project_key]
    project_name = project_data["name"]
    folder_name = project_data["folder"]

    try:
        # Получаем список фото из папки проекта
        project_folder = f"photos/{folder_name}"
        if not os.path.exists(project_folder):
            await callback.message.answer(
                f"❌ Фотографии проекта временно недоступны",
                reply_markup=get_back_to_projects_keyboard()
            )
            await callback.answer()
            return

        photo_files = []
        for file in os.listdir(project_folder):
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                photo_files.append(file)

        if not photo_files:
            await callback.message.answer(
                f"❌ В папке проекта нет фотографий",
                reply_markup=get_back_to_projects_keyboard()
            )
            await callback.answer()
            return

        # Сортируем файлы для последовательного отображения
        photo_files.sort()

        # Создаем медиагруппу
        media_group = []

        for i, photo_file in enumerate(photo_files):
            try:
                photo_path = f"{project_folder}/{photo_file}"

                # Для первого фото добавляем подпись с описанием проекта
                if i == 0:
                    caption = f"🖼️ <b>{project_name}</b>\n\n{project_data['description']}\n\nФото {i + 1}/{len(photo_files)}"
                else:
                    caption = f"🖼️ <b>{project_name}</b>\n\nФото {i + 1}/{len(photo_files)}"

                media_group.append(types.InputMediaPhoto(
                    media=FSInputFile(photo_path),
                    caption=caption,
                    parse_mode="HTML"
                ))

            except Exception as e:
                logger.error(f"Ошибка загрузки фото {photo_file}: {e}")
                continue

        if media_group:
            # Удаляем предыдущее сообщение с выбором проектов
            await callback.message.delete()

            # Отправляем всю медиагруппу одним сообщением
            await callback.message.answer_media_group(media_group)

            # Отправляем отдельное сообщение с кнопкой "Назад"
            await callback.message.answer(
                "🔙 <b>Вернуться к выбору проектов</b>",
                reply_markup=get_back_to_projects_keyboard()
            )
        else:
            await callback.message.answer(
                "❌ Не удалось загрузить фотографии проекта",
                reply_markup=get_back_to_projects_keyboard()
            )

    except Exception as e:
        logger.error(f"Ошибка показа проекта {project_key}: {e}")
        await callback.message.answer(
            "❌ Ошибка загрузки проекта",
            reply_markup=get_back_to_projects_keyboard()
        )

    await callback.answer()


# 📍 ИНЛАЙН КНОПКИ

@dp.callback_query(F.data.startswith("month_"))
async def select_month(callback: CallbackQuery):
    month_key = callback.data.split("_")[1]

    # Получаем забронированные даты только из Google Sheets
    booked_dates = []
    if gsheets:
        booked_dates = gsheets.get_booked_dates()

    # Логируем для отладки
    logger.info(f"Отображение календаря для {month_key}, забронированные даты: {booked_dates}")

    await callback.message.edit_text(
        "📅 Выберите доступную дату:",
        reply_markup=get_days_keyboard(month_key, booked_dates)
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_months")
async def back_to_months(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выберите месяц для просмотра доступных дат:",
        reply_markup=get_months_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "occupied")
async def date_occupied(callback: CallbackQuery):
    await callback.answer("❌ Эта дата уже занята. Выберите другую.", show_alert=True)


@dp.callback_query(F.data.startswith("book_"))
async def select_date(callback: CallbackQuery):
    date_str = callback.data.split("_")[1]
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")

    text = f"""
📅 <b>Вы выбрали дату:</b> {date_obj.strftime('%d.%m.%Y')}

Для бронирования необходимо внести предоплату <b>4 000 ₽</b>

После оплаты:
• Дата будет закреплена за вами
• Вы получите ссылку на бриф для заполнения
• Мы приступим к работе в выбранный день

Нажмите "💳 Оплатить 4000 ₽" чтобы перейти к оплате.
    """

    await callback.message.edit_text(
        text,
        # Показываем только кнопку оплаты, без кнопки "Я оплатил"
        reply_markup=get_payment_keyboard(config.DEPOSIT_AMOUNT, date_str)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("pay_deposit_"))
async def process_deposit_payment(callback: CallbackQuery):
    date_str = callback.data.split("_")[2]
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")

    # Создаем платеж
    payment = await payment_manager.create_payment(
        amount=config.DEPOSIT_AMOUNT,
        description=f"Предоплата за бронирование {date_str}",
        user_id=callback.from_user.id,
        booking_date=date_str
    )

    if payment:
        # Сохраняем в базу
        db.add_booking(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name,
            booking_date=date_str
        )

        # Добавляем в Google Sheets
        if gsheets:
            user_data = {
                'user_id': callback.from_user.id,
                'username': callback.from_user.username,
                'full_name': callback.from_user.full_name
            }
            gsheets.add_booking(user_data, date_obj, payment.id)

        # РЕДАКТИРУЕМ текущее сообщение - УБИРАЕМ кнопку "Я оплатил"
        await callback.message.edit_text(
            f"💳 <b>Оплата предоплаты</b>\n\n"
            f"Сумма: {config.DEPOSIT_AMOUNT} ₽\n"
            f"Дата брони: {date_obj.strftime('%d.%m.%Y')}\n\n"
            f"Для оплаты перейдите по ссылке:\n{payment.confirmation.confirmation_url}\n\n"
            f"<i>После успешной оплаты бот автоматически подтвердит бронирование и отправит ссылку на бриф.</i>\n\n"
            f"<b>Ожидаем подтверждения оплаты...</b> ⏳",
            reply_markup=get_payment_keyboard(config.DEPOSIT_AMOUNT, date_str)
        )
    else:
        await callback.message.edit_text("❌ Ошибка создания платежа. Попробуйте позже.")

    await callback.answer()


@dp.message(Command("project_status"))
async def check_project_status(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        return

    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("Использование: /project_status user_id")
            return

        user_id = int(parts[1])

        cursor = db.conn.cursor()
        cursor.execute('''
            SELECT booking_date, status, deposit_paid, final_paid, brief_completed
            FROM bookings WHERE user_id = ? ORDER BY created_at DESC LIMIT 1
        ''', (user_id,))

        project = cursor.fetchone()

        if project:
            status_text = {
                'active': 'Активный',
                'completed': 'Завершен',
                'cancelled': 'Отменен'
            }

            await message.answer(
                f"📊 <b>Статус проекта пользователя {user_id}</b>\n\n"
                f"📅 Дата брони: {project[0]}\n"
                f"📋 Статус: {status_text.get(project[1], project[1])}\n"
                f"💰 Предоплата: {'✅ Оплачена' if project[2] else '❌ Не оплачена'}\n"
                f"💰 Финальная оплата: {'✅ Оплачена' if project[3] else '❌ Не оплачена'}\n"
                f"📝 Бриф: {'✅ Заполнен' if project[4] else '❌ Не заполнен'}\n"
            )
        else:
            await message.answer("❌ Проект не найден")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@dp.update()
async def handle_webhook(update: Update):
    """Обрабатывает вебхуки от ЮKassa"""
    # Проверяем, это вебхук от ЮKassa
    if hasattr(update, 'web_app_data') or (
            hasattr(update, 'message') and update.message and update.message.web_app_data):
        try:
            # Получаем данные вебхука
            webhook_data = update.web_app_data.data if hasattr(update,
                                                               'web_app_data') else update.message.web_app_data.data
            payment_data = json.loads(webhook_data)

            # Обрабатываем платеж
            result = await payment_manager.process_webhook(payment_data)

            if result['success']:
                user_id = result['user_id']
                payment_type = result['payment_type']
                booking_date = result['booking_date']
                amount = result['amount']

                # Отправляем уведомление пользователю
                if payment_type == 'deposit':
                    success_message = (
                        f"✅ <b>Платеж подтвержден!</b>\n\n"
                        f"Сумма: {amount} ₽\n"
                        f"Дата брони: {booking_date}\n\n"
                        f"📝 <b>Теперь заполните бриф:</b>\n{config.BRIEF_FORM_URL}\n\n"
                        f"<i>Важно: бриф нужно заполнить до назначенной даты.</i>"
                    )

                    # Уведомляем админа
                    await bot.send_message(
                        config.ADMIN_ID,
                        f"🎉 <b>Новое бронирование!</b>\n\n"
                        f"👤 Пользователь: {user_id}\n"
                        f"📅 Дата: {booking_date}\n"
                        f"💰 Предоплата: {config.DEPOSIT_AMOUNT} ₽",
                        reply_markup=get_admin_delivery_keyboard(user_id, booking_date, is_final_paid=False)
                    )

                elif payment_type == 'final':
                    success_message = (
                        f"✅ <b>Финальная оплата подтверждена!</b>\n\n"
                        f"Сумма: {amount} ₽\n\n"
                        f"Спасибо за оплату! Теперь мы можем отправить вам готовый проект.\n\n"
                        f"<i>Ожидайте материалы в течение дня.</i>"
                    )

                    # Уведомляем админа о готовности к отправке проекта
                    await bot.send_message(
                        config.ADMIN_ID,
                        f"🎉 <b>Финальная оплата получена!</b>\n\n"
                        f"👤 Пользователь: {user_id}\n"
                        f"📅 Дата: {booking_date}\n"
                        f"💰 Финальная оплата: {config.FINAL_AMOUNT} ₽\n\n"
                        f"<i>Теперь можно отправить клиенту готовый проект.</i>",
                        reply_markup=get_admin_delivery_keyboard(user_id, booking_date, is_final_paid=True)
                    )

                # Отправляем сообщение пользователю
                await bot.send_message(user_id, success_message)

        except Exception as e:
            logger.error(f"Ошибка обработки вебхука: {e}")



@dp.callback_query(F.data == "cancel_payment")
async def cancel_booking(callback: CallbackQuery):
    """Отменяет бронирование"""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} отменил бронирование")

    # Удаляем последнее бронирование пользователя
    bookings = db.get_user_bookings(user_id)
    if bookings:
        latest_booking = bookings[0]
        booking_date = latest_booking[4]

        # Удаляем бронирование из базы
        cursor = db.conn.cursor()
        cursor.execute('DELETE FROM bookings WHERE user_id = ? AND booking_date = ?',
                       (user_id, booking_date))
        db.conn.commit()

        logger.info(f"Бронирование {booking_date} удалено для пользователя {user_id}")

    # Редактируем сообщение
    await callback.message.edit_text(
        "❌ <b>Ваша бронь отменена</b>\n\n"
        "Может быть, выберете другую дату?",
        reply_markup=get_months_keyboard()  # Возвращаем к выбору месяца
    )
    await callback.answer()


@dp.callback_query(F.data == "pay_final")
async def process_final_payment(callback: CallbackQuery):
    """Обработка финальной оплаты"""
    user_id = callback.from_user.id
    bookings = db.get_user_bookings(user_id)

    if bookings:
        latest_booking = bookings[0]
        booking_date = latest_booking[4]

        payment = await payment_manager.create_payment(
            amount=config.FINAL_AMOUNT,
            description=f"Финальная оплата за проект {booking_date}",
            user_id=user_id,
            booking_date=booking_date,
            is_final=True
        )

        if payment:
            # РЕДАКТИРУЕМ текущее сообщение - УБИРАЕМ кнопку "Я оплатил"
            await callback.message.edit_text(
                f"💳 <b>Финальная оплата</b>\n\n"
                f"Сумма: {config.FINAL_AMOUNT} ₽\n\n"
                f"Для оплаты перейдите по ссылке:\n{payment.confirmation.confirmation_url}\n\n"
                f"<i>После успешной оплаты бот автоматически подтвердит получение средств и уведомит администратора о готовности проекта к отправке.</i>\n\n"
                f"<b>Ожидаем подтверждения оплаты...</b> ⏳",
                reply_markup=get_payment_keyboard(config.FINAL_AMOUNT, is_final=True)
            )
        else:
            await callback.message.edit_text("❌ Ошибка создания платежа.")
    else:
        await callback.message.edit_text("❌ Не найдено активных бронирований.")

    await callback.answer()


@dp.callback_query(F.data == "show_ads")
async def show_ads_examples(callback: CallbackQuery):
    """Показывает примеры рекламы"""
    try:
        media_group = []
        for i, photo_path in enumerate(config.EXAMPLES['ads']):
            try:
                photo = FSInputFile(photo_path)
                media_group.append(types.InputMediaPhoto(
                    media=photo,
                    caption="Пример рекламного объявления" if i == 0 else ""
                ))
            except FileNotFoundError:
                logger.warning(f"Файл не найден: {photo_path}")

        if media_group:
            await callback.message.answer_media_group(media_group)
        else:
            await callback.message.answer("❌ Фотографии примеров временно недоступны.")

    except Exception as e:
        logger.error(f"Ошибка отправки медиагруппы: {e}")
        await callback.message.answer("❌ Ошибка загрузки примеров рекламы.")

    await callback.answer()


@dp.callback_query(F.data.startswith("deliver_"))
async def deliver_project(callback: CallbackQuery, state: FSMContext):
    """Начало процесса отправки проекта клиенту"""
    parts = callback.data.split("_")
    user_id = int(parts[1])
    booking_date = parts[2]

    # Проверяем, оплачена ли финальная часть
    cursor = db.conn.cursor()
    cursor.execute('''
        SELECT final_paid FROM bookings 
        WHERE user_id = ? AND booking_date = ?
    ''', (user_id, booking_date))

    result = cursor.fetchone()

    if not result or not result[0]:
        await callback.answer("❌ Финальная оплата еще не получена!", show_alert=True)
        return

    await state.update_data(
        target_user_id=user_id,
        booking_date=booking_date,
        delivered_parts=0,  # Счетчик отправленных частей
        total_parts=4  # Всего нужно отправить 4 части
    )

    await callback.message.answer(
        f"📤 <b>Отправка проекта клиенту</b>\n\n"
        f"👤 Пользователь: {user_id}\n"
        f"📅 Дата: {booking_date}\n\n"
        f"Отправьте по порядку:\n"
        f"1. Ссылку на готовый сайт\n"
        f"2. Фото рекламных объявлений (до 3 шт)\n"
        f"3. Инструкцию (текст или документ)\n"
        f"4. Финальное сообщение для клиента\n\n"
        f"<i>Отправляйте материалы по одному сообщению.</i>\n"
        f"<b>Прогресс: 0/4</b>"
    )

    await state.set_state(BookingState.waiting_for_delivery)
    await callback.answer()


# 📍 ПОДДЕРЖКА

@dp.message(BookingState.waiting_for_support)
async def handle_support_message(message: Message, state: FSMContext):
    # Сохраняем ID пользователя для ответа
    await state.update_data(support_user_id=message.from_user.id)

    # Пересылаем сообщение владельцу с кнопкой ответа
    support_text = f"""
💬 <b>Новый вопрос от клиента</b>

👤 <b>Пользователь:</b> {message.from_user.full_name}
📱 <b>Username:</b> @{message.from_user.username}
🆔 <b>ID:</b> {message.from_user.id}

<b>Вопрос:</b>
{message.text}
    """

    # Создаем клавиатуру для ответа
    reply_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_support_{message.from_user.id}")]
    ])

    await bot.send_message(config.ADMIN_ID, support_text, reply_markup=reply_keyboard)
    await message.answer("✅ Ваш вопрос отправлен специалисту. Ответим в ближайшее время!")

    # Возвращаем в главное меню
    await message.answer("Чем ещё могу помочь?", reply_markup=get_main_keyboard())
    await state.clear()


# 📍 ОТВЕТЫ АДМИНА НА ВОПРОСЫ ПОДДЕРЖКИ

@dp.callback_query(F.data.startswith("reply_support_"))
async def start_support_reply(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс ответа на вопрос поддержки"""
    user_id = int(callback.data.split("_")[2])

    await state.update_data(support_target_user_id=user_id)
    await callback.message.answer(
        f"💬 <b>Ответ клиенту</b>\n\n"
        f"ID пользователя: {user_id}\n\n"
        f"Напишите ваш ответ:"
    )

    await state.set_state(BookingState.admin_support_reply)
    await callback.answer()


@dp.message(BookingState.admin_support_reply)
async def handle_support_reply(message: Message, state: FSMContext):
    """Обрабатывает ответ админа и отправляет клиенту"""
    data = await state.get_data()
    user_id = data.get('support_target_user_id')

    if not user_id:
        await message.answer("❌ Ошибка: не найден пользователь для ответа")
        await state.clear()
        return

    try:
        # Отправляем ответ клиенту
        await bot.send_message(
            user_id,
            f"💬 <b>Ответ от поддержки:</b>\n\n{message.text}\n\n"
            f"<i>Если у вас есть дополнительные вопросы, напишите нам снова.</i>"
        )

        await message.answer("✅ Ответ отправлен клиенту!")

    except Exception as e:
        logger.error(f"Ошибка отправки ответа поддержки: {e}")
        await message.answer("❌ Ошибка отправки ответа. Пользователь可能 заблокировал бота.")

    await state.clear()


# 📍 ОБРАБОТКА ДОСТАВКИ ПРОЕКТА

@dp.message(BookingState.waiting_for_delivery)
async def handle_project_delivery(message: Message, state: FSMContext):
    data = await state.get_data()
    target_user_id = data.get('target_user_id')
    booking_date = data.get('booking_date')
    delivered_parts = data.get('delivered_parts', 0)
    total_parts = data.get('total_parts', 4)

    if not target_user_id:
        await message.answer("❌ Ошибка: не найден пользователь для отправки")
        await state.clear()
        return

    try:
        # Увеличиваем счетчик отправленных частей
        delivered_parts += 1
        await state.update_data(delivered_parts=delivered_parts)

        # Пересылаем сообщение клиенту
        if message.text:
            caption = ""
            if delivered_parts == 1:
                caption = "🌐 <b>Ссылка на готовый сайт</b>"
            elif delivered_parts == 2:
                caption = "📱 <b>Рекламные объявления</b>"
            elif delivered_parts == 3:
                caption = "📄 <b>Инструкция по работе</b>"
            elif delivered_parts == 4:
                caption = "💬 <b>Финальное сообщение</b>"

            await bot.send_message(target_user_id, f"{caption}\n\n{message.text}")

        elif message.photo:
            await bot.send_photo(
                target_user_id,
                message.photo[-1].file_id,
                caption="📱 <b>Рекламное объявление</b>"
            )
        elif message.document:
            await bot.send_document(
                target_user_id,
                message.document.file_id,
                caption="📄 <b>Инструкция по работе</b>"
            )

        # Проверяем, все ли части доставлены
        if delivered_parts >= total_parts:
            # Отправляем финальное сообщение клиенту
            await bot.send_message(
                target_user_id,
                "🎉 <b>Проект полностью доставлен!</b>\n\n"
                "Все материалы были отправлены. Ваш проект завершен!\n\n"
                "Если у вас есть вопросы, вы можете обратиться в поддержку через меню бота.\n\n"
                "<i>Спасибо, что выбрали наши услуги! 🚀</i>"
            )

            # Уведомляем админа
            await message.answer(
                "✅ <b>Проект полностью доставлен клиенту!</b>\n\n"
                f"👤 Пользователь: {target_user_id}\n"
                f"📅 Дата: {booking_date}\n\n"
                "<i>Все материалы отправлены, проект завершен.</i>"
            )

            # Обновляем статус в базе данных
            cursor = db.conn.cursor()
            cursor.execute('''
                UPDATE bookings SET status = 'completed' 
                WHERE user_id = ? AND booking_date = ?
            ''', (target_user_id, booking_date))
            db.conn.commit()

            # Обновляем Google Sheets
            if gsheets:
                gsheets.update_booking_status(target_user_id, booking_date, "Проект завершен")

            await state.clear()
        else:
            # Показываем прогресс админу
            progress_text = f"✅ Материал {delivered_parts}/{total_parts} отправлен клиенту!"
            if delivered_parts == 1:
                progress_text += "\n\nОжидаю ссылку на рекламные объявления..."
            elif delivered_parts == 2:
                progress_text += "\n\nОжидаю инструкцию..."
            elif delivered_parts == 3:
                progress_text += "\n\nОжидаю финальное сообщение для клиента..."

            await message.answer(progress_text)

    except Exception as e:
        logger.error(f"Ошибка отправки проекта: {e}")
        await message.answer("❌ Ошибка отправки материала")


@dp.callback_query(F.data.startswith("start_chat_"))
async def start_specialist_chat(callback: CallbackQuery, state: FSMContext):
    """Специалист начинает диалог с пользователем"""
    parts = callback.data.split("_")
    user_id = int(parts[2])
    booking_date = parts[3]

    # Начинаем сессию чата
    success = db.start_chat_session(user_id, callback.from_user.id, booking_date)

    if success:
        # Уведомляем пользователя
        await bot.send_message(
            user_id,
            "💬 <b>Специалист хочет связаться с вами</b>\n\n"
            "Для завершения работы над проектом специалисту требуется уточнить некоторые детали. "
            "Пожалуйста, ответьте на его сообщения в этом чате.\n\n"
            "<i>Весь диалог будет происходить здесь. После завершения общения специалист закроет диалог.</i>",
            reply_markup=get_user_chat_notification_keyboard()
        )

        # Обновляем сообщение специалисту
        await callback.message.edit_text(
            f"💬 <b>Диалог с пользователем начат</b>\n\n"
            f"👤 Пользователь: {user_id}\n"
            f"📅 Дата проекта: {booking_date}\n\n"
            f"<i>Теперь вы можете общаться с пользователем напрямую в этом чате. "
            f"Все ваши сообщения будут пересылаться пользователю.</i>\n\n"
            f"Когда закончите, нажмите 'Завершить диалог'",
            reply_markup=get_admin_chat_active_keyboard(user_id)
        )

        # Сохраняем состояние
        await state.update_data(chat_user_id=user_id)
        await state.set_state(BookingState.specialist_chat_active)

    else:
        await callback.answer("❌ Ошибка начала диалога")

    await callback.answer()


@dp.callback_query(F.data.startswith("end_chat_"))
async def end_specialist_chat(callback: CallbackQuery, state: FSMContext):
    """Специалист завершает диалог"""
    user_id = int(callback.data.split("_")[2])

    # Завершаем сессию чата
    success = db.end_chat_session(user_id)

    if success:
        # Уведомляем пользователя
        await bot.send_message(
            user_id,
            "✅ <b>Диалог со специалистом завершен</b>\n\n"
            "Спасибо за общение! Теперь вы можете продолжать пользоваться ботом в обычном режиме.\n\n"
            "<i>Если у вас возникнут вопросы, вы всегда можете обратиться в поддержку через меню.</i>"
        )

        # Обновляем сообщение специалисту
        await callback.message.edit_text(
            f"✅ <b>Диалог с пользователем завершен</b>\n\n"
            f"👤 Пользователь: {user_id}\n\n"
            f"<i>Пользователь снова может пользоваться ботом в обычном режиме.</i>"
        )

        # Очищаем состояние
        await state.clear()

    else:
        await callback.answer("❌ Ошибка завершения диалога")

    await callback.answer()


@dp.callback_query(F.data == "reply_to_specialist")
async def user_reply_to_specialist(callback: CallbackQuery, state: FSMContext):
    """Пользователь готов общаться со специалистом"""
    user_id = callback.from_user.id

    # Проверяем, активен ли чат
    chat_session = db.get_active_chat(user_id)

    if chat_session:
        await callback.message.answer(
            "💬 <b>Вы в диалоге со специалистом</b>\n\n"
            "Теперь все ваши сообщения в этом чате будут пересылаться специалисту. "
            "Пожалуйста, отвечайте на его вопросы.\n\n"
            "<i>Диалог будет продолжаться до тех пор, пока специалист его не завершит.</i>"
        )
        await state.set_state(BookingState.user_chat_active)
    else:
        await callback.message.answer("❌ Диалог со специалистом не активен")

    await callback.answer()


# Обработчики сообщений во время активного диалога

@dp.message(BookingState.specialist_chat_active)
async def handle_specialist_message(message: Message, state: FSMContext):
    """Обрабатывает сообщения специалиста во время диалога"""
    data = await state.get_data()
    user_id = data.get('chat_user_id')

    if user_id:
        try:
            # Пересылаем сообщение пользователю
            await bot.send_message(
                user_id,
                f"👨‍💼 <b>Сообщение от специалиста:</b>\n\n{message.text}"
            )
            await message.answer("✅ Сообщение отправлено пользователю")
        except Exception as e:
            await message.answer("❌ Не удалось отправить сообщение пользователю")
            logger.error(f"Ошибка отправки сообщения пользователю: {e}")
    else:
        await message.answer("❌ Ошибка: не найден пользователь для диалога")
        await state.clear()


@dp.message(BookingState.user_chat_active)
async def handle_user_message_to_specialist(message: Message):
    """Обрабатывает сообщения пользователя во время диалога"""
    user_id = message.from_user.id

    # Получаем информацию о активном чате
    chat_session = db.get_active_chat(user_id)

    if chat_session:
        admin_id = chat_session[2]  # admin_id field
        try:
            # Пересылаем сообщение специалисту
            await bot.send_message(
                admin_id,
                f"👤 <b>Сообщение от пользователя:</b>\n\n"
                f"ID: {user_id}\n"
                f"Сообщение: {message.text}"
            )
            await message.answer("✅ Сообщение отправлено специалисту")
        except Exception as e:
            await message.answer("❌ Не удалось отправить сообщение специалисту")
            logger.error(f"Ошибка отправки сообщения специалисту: {e}")
    else:
        await message.answer("❌ Диалог со специалистом не активен")


@dp.callback_query(F.data.startswith("start_chat_"))
async def start_specialist_chat(callback: CallbackQuery, state: FSMContext):
    """Специалист начинает диалог с пользователем"""
    parts = callback.data.split("_")
    user_id = int(parts[2])
    booking_date = parts[3]

    # Начинаем сессию чата
    success = db.start_chat_session(user_id, callback.from_user.id, booking_date)

    if success:
        # Уведомляем пользователя
        await bot.send_message(
            user_id,
            "💬 <b>Специалист хочет связаться с вами</b>\n\n"
            "Для завершения работы над проектом специалисту требуется уточнить некоторые детали. "
            "Пожалуйста, ответьте на его сообщения в этом чате.\n\n"
            "<i>Весь диалог будет происходить здесь. После завершения общения специалист закроет диалог.</i>",
            reply_markup=get_user_chat_notification_keyboard()
        )

        # Обновляем сообщение специалисту
        await callback.message.edit_text(
            f"💬 <b>Диалог с пользователем начат</b>\n\n"
            f"👤 Пользователь: {user_id}\n"
            f"📅 Дата проекта: {booking_date}\n\n"
            f"<i>Теперь вы можете общаться с пользователем напрямую в этом чате. "
            f"Все ваши сообщения будут пересылаться пользователю.</i>\n\n"
            f"Когда закончите, нажмите 'Завершить диалог'",
            reply_markup=get_admin_chat_active_keyboard(user_id)
        )

        # Сохраняем состояние
        await state.update_data(chat_user_id=user_id)
        await state.set_state(BookingState.specialist_chat_active)

    else:
        await callback.answer("❌ Ошибка начала диалога")

    await callback.answer()


@dp.callback_query(F.data.startswith("end_chat_"))
async def end_specialist_chat(callback: CallbackQuery, state: FSMContext):
    """Специалист завершает диалог"""
    user_id = int(callback.data.split("_")[2])

    # Завершаем сессию чата
    success = db.end_chat_session(user_id)

    if success:
        # Уведомляем пользователя
        await bot.send_message(
            user_id,
            "✅ <b>Диалог со специалистом завершен</b>\n\n"
            "Спасибо за общение! Теперь вы можете продолжать пользоваться ботом в обычном режиме.\n\n"
            "<i>Если у вас возникнут вопросы, вы всегда можете обратиться в поддержку через меню.</i>"
        )

        # Обновляем сообщение специалисту
        await callback.message.edit_text(
            f"✅ <b>Диалог с пользователем завершен</b>\n\n"
            f"👤 Пользователь: {user_id}\n\n"
            f"<i>Пользователь снова может пользоваться ботом в обычном режиме.</i>"
        )

        # Очищаем состояние
        await state.clear()

    else:
        await callback.answer("❌ Ошибка завершения диалога")

    await callback.answer()


@dp.callback_query(F.data == "reply_to_specialist")
async def user_reply_to_specialist(callback: CallbackQuery, state: FSMContext):
    """Пользователь готов общаться со специалистом"""
    user_id = callback.from_user.id

    # Проверяем, активен ли чат
    chat_session = db.get_active_chat(user_id)

    if chat_session:
        await callback.message.answer(
            "💬 <b>Вы в диалоге со специалистом</b>\n\n"
            "Теперь все ваши сообщения в этом чате будут пересылаться специалисту. "
            "Пожалуйста, отвечайте на его вопросы.\n\n"
            "<i>Диалог будет продолжаться до тех пор, пока специалист его не завершит.</i>"
        )
        await state.set_state(BookingState.user_chat_active)
    else:
        await callback.message.answer("❌ Диалог со специалистом не активен")

    await callback.answer()


# Обработчики сообщений во время активного диалога

@dp.message(BookingState.specialist_chat_active)
async def handle_specialist_message(message: Message, state: FSMContext):
    """Обрабатывает сообщения специалиста во время диалога"""
    data = await state.get_data()
    user_id = data.get('chat_user_id')

    if user_id:
        try:
            # Пересылаем сообщение пользователю
            await bot.send_message(
                user_id,
                f"👨‍💼 <b>Сообщение от специалиста:</b>\n\n{message.text}"
            )
            await message.answer("✅ Сообщение отправлено пользователю")
        except Exception as e:
            await message.answer("❌ Не удалось отправить сообщение пользователю")
            logger.error(f"Ошибка отправки сообщения пользователю: {e}")
    else:
        await message.answer("❌ Ошибка: не найден пользователь для диалога")
        await state.clear()


@dp.message(BookingState.user_chat_active)
async def handle_user_message_to_specialist(message: Message):
    """Обрабатывает сообщения пользователя во время диалога"""
    user_id = message.from_user.id

    # Получаем информацию о активном чате
    chat_session = db.get_active_chat(user_id)

    if chat_session:
        admin_id = chat_session[2]  # admin_id field
        try:
            # Пересылаем сообщение специалисту
            await bot.send_message(
                admin_id,
                f"👤 <b>Сообщение от пользователя:</b>\n\n"
                f"ID: {user_id}\n"
                f"Сообщение: {message.text}"
            )
            await message.answer("✅ Сообщение отправлено специалисту")
        except Exception as e:
            await message.answer("❌ Не удалось отправить сообщение специалисту")
            logger.error(f"Ошибка отправки сообщения специалисту: {e}")
    else:
        await message.answer("❌ Диалог со специалистом не активен")


async def check_chat_active(message: Message) -> bool:
    """Проверяет, активен ли чат с пользователем"""
    return db.is_chat_active(message.from_user.id)


# Для пользователя - блокируем основные команды во время диалога
@dp.message(
    F.text.in_(["🗓️ Забронировать день", "❓ Как всё проходит?", "💰 Услуги/оплата", "📊 Примеры работ", "👨‍💼 Поддержка"]))
async def handle_commands_during_chat(message: Message):
    """Блокирует основные команды во время активного диалога"""
    if await check_chat_active(message):
        await message.answer(
            "⏸️ <b>Команды временно недоступны</b>\n\n"
            "В настоящее время вы находитесь в диалоге со специалистом. "
            "Пожалуйста, завершите общение прежде чем пользоваться другими функциями бота.\n\n"
            "<i>Специалист скоро завершит диалог.</i>"
        )
        return
    # Если чат не активен, пропускаем обработку дальше к другим обработчикам


# Также добавим проверку для команды /start
@dp.message(CommandStart())
async def cmd_start_with_chat_check(message: Message):
    """Обработчик /start с проверкой активного чата"""
    if await check_chat_active(message):
        await message.answer(
            "⏸️ <b>Команды временно недоступны</b>\n\n"
            "В настоящее время вы находитесь в диалоге со специалистом. "
            "Пожалуйста, завершите общение прежде чем пользоваться другими функциями бота.\n\n"
            "<i>Специалист скоро завершит диалог.</i>"
        )
        return

    # Если чат не активен, выполняем обычный /start
    welcome_text = """
Привет! Я Айви. Через меня проходит 99% коммуникации.

Вам нужно создать адаптивный рабочий сайт и настроить рекламу в Яндексе? Специалист с 5-летним опытом в маркетинге и дизайне сделает это для Вас за 1 день! Без долгив переписок, подрядчиков и ожиданий.

С чего начнём?
    """
    photo = FSInputFile("photos/Lucid_Origin_A_stunning_Brazilian_model_with_unique_and_captiv_2.jpg")

    await message.answer_photo(
        photo=photo,
        caption=welcome_text,
        reply_markup=get_main_keyboard()
    )

# 📍 АДМИН ПАНЕЛЬ

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        return

    text = """
👨‍💼 <b>Админ панель</b>

<b>Команды управления:</b>
/bookings - Показать все активные бронирования
/stats - Статистика по бронированиям
/remind - Отправить напоминания о финальной оплате
/project_status [user_id] - Статус проекта пользователя
/add_work - Управление рабочими днями

<b>Команды для клиентов:</b>
/start - Главное меню
"""
    await message.answer(text)


@dp.message(Command("bookings"))
async def show_bookings(message: Message):
    """Показывает все активные бронирования"""
    if message.from_user.id != config.ADMIN_ID:
        return

    from database import Database
    db = Database()

    # Получаем все активные бронирования с предоплатой
    cursor = db.conn.cursor()
    cursor.execute('''
        SELECT user_id, username, full_name, booking_date, deposit_paid, final_paid, brief_completed
        FROM bookings 
        WHERE status = 'active' AND deposit_paid = TRUE
        ORDER BY booking_date
    ''')

    bookings = cursor.fetchall()

    if not bookings:
        await message.answer("📭 <b>Активных бронирований нет</b>")
        return

    text = "📋 <b>Активные бронирования:</b>\n\n"

    for booking in bookings:
        user_id, username, full_name, booking_date, deposit_paid, final_paid, brief_completed = booking
        date_obj = datetime.strptime(booking_date, "%Y-%m-%d")
        date_str = date_obj.strftime("%d.%m.%Y")

        text += f"👤 <b>{full_name}</b>\n"
        text += f"📱 @{username or 'нет'}\n"
        text += f"🆔 {user_id}\n"
        text += f"📅 {date_str}\n"
        text += f"💰 Предоплата: {'✅' if deposit_paid else '❌'}\n"
        text += f"💰 Финальная: {'✅' if final_paid else '❌'}\n"
        text += f"📝 Бриф: {'✅' if brief_completed else '❌'}\n"
        text += "─" * 30 + "\n"

    await message.answer(text)


@dp.message(Command("stats"))
async def show_stats(message: Message):
    """Показывает статистику по бронированиям"""
    if message.from_user.id != config.ADMIN_ID:
        return

    from database import Database
    db = Database()

    cursor = db.conn.cursor()

    # Общее количество бронирований
    cursor.execute('SELECT COUNT(*) FROM bookings')
    total_bookings = cursor.fetchone()[0]

    # Активные бронирования
    cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "active" AND deposit_paid = TRUE')
    active_bookings = cursor.fetchone()[0]

    # Завершенные проекты
    cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "completed"')
    completed_bookings = cursor.fetchone()[0]

    # Бронирования с предоплатой
    cursor.execute('SELECT COUNT(*) FROM bookings WHERE deposit_paid = TRUE')
    paid_deposit = cursor.fetchone()[0]

    # Бронирования с финальной оплатой
    cursor.execute('SELECT COUNT(*) FROM bookings WHERE final_paid = TRUE')
    paid_final = cursor.fetchone()[0]

    text = f"""
📊 <b>Статистика бота</b>

📋 Всего бронирований: {total_bookings}
🟢 Активных: {active_bookings}
✅ Завершенных: {completed_bookings}
💰 С предоплатой: {paid_deposit}
💰 С финальной оплатой: {paid_final}

💼 Рабочих дней в системе: {len(db.get_all_work_days())}
    """

    await message.answer(text)


@dp.message(Command("add_work"))
async def admin_work_panel(message: Message):
    """Панель управления рабочими днями"""
    if message.from_user.id != config.ADMIN_ID:
        return

    text = """
🛠️ <b>Управление рабочими днями</b>

Выберите действие:

• <b>Добавить месяц полностью</b> - все понедельники, среды и пятницы месяца станут рабочими
• <b>Добавить день работы</b> - добавить конкретную дату как рабочий день
• <b>Удалить день работы</b> - удалить рабочий день (нельзя удалить дни с активными бронированиями)
    """
    await message.answer(text, reply_markup=get_admin_work_keyboard())


# Обработчики для управления рабочими днями
@dp.callback_query(F.data == "admin_work_back")
async def admin_work_back(callback: CallbackQuery):
    """Возврат к панели управления рабочими днями"""
    text = """
🛠️ <b>Управление рабочими днями</b>

Выберите действие:

• <b>Добавить месяц полностью</b> - все понедельники, среды и пятницы месяца станут рабочими
• <b>Добавить день работы</b> - добавить конкретную дату как рабочий день
• <b>Удалить день работы</b> - удалить рабочий день (нельзя удалить дни с активными бронированиями)
    """
    await callback.message.edit_text(text, reply_markup=get_admin_work_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "admin_back")
async def admin_back_to_panel(callback: CallbackQuery):
    """Возврат в главную админ-панель"""
    text = """
👨‍💼 <b>Админ панель</b>

Доступные команды:
/bookings - Посмотреть бронирования
/stats - Статистика
/remind - Отправить напоминания
/project_status user_id - Статус проекта
/add_work - Управление рабочими днями

Также используйте кнопки доставки проекта из уведомлений о бронированиях.
    """
    await callback.message.edit_text(text)
    await callback.answer()


@dp.callback_query(F.data == "admin_add_month")
async def admin_add_month(callback: CallbackQuery):
    """Добавление месяца полностью"""
    text = """
📅 <b>Добавление месяца</b>

Выберите месяц, для которого добавить все понедельники, среды и пятницы как рабочие дни:
    """
    await callback.message.edit_text(text, reply_markup=get_admin_months_keyboard(action="add"))
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_month_"))
async def admin_process_month(callback: CallbackQuery):
    """Обработка выбранного месяца для добавления"""
    month_key = callback.data.split("_")[2]
    year, month = map(int, month_key.split('-'))
    month_date = datetime(year, month, 1)
    month_name = f"{get_russian_month_name(month_date)} {year}"

    from database import Database
    db = Database()

    work_days_added = db.add_work_days_for_month(year, month)

    if work_days_added > 0:
        await callback.message.edit_text(
            f"✅ <b>Месяц добавлен!</b>\n\n"
            f"Месяц: {month_name}\n"
            f"Добавлено рабочих дней: {work_days_added}\n\n"
            f"Теперь эти дни доступны для бронирования клиентами.",
            reply_markup=get_admin_work_keyboard()
        )
    else:
        await callback.message.edit_text(
            f"❌ <b>Ошибка добавления месяца</b>\n\n"
            f"Месяц: {month_name}\n\n"
            f"Не удалось добавить рабочие дни.",
            reply_markup=get_admin_work_keyboard()
        )

    await callback.answer()


@dp.callback_query(F.data == "admin_add_day")
async def admin_add_day(callback: CallbackQuery, state: FSMContext):
    """Добавление конкретного дня"""
    text = """
📝 <b>Добавление рабочего дня</b>

Введите дату в формате <b>ДД.ММ.ГГГГ</b> (например: 25.12.2024)

Эта дата станет доступна для бронирования клиентами.
    """
    await callback.message.edit_text(text)
    await state.set_state(AdminWorkState.waiting_for_day)
    await callback.answer()


@dp.message(AdminWorkState.waiting_for_day)
async def admin_process_day(message: Message, state: FSMContext):
    """Обработка введенной даты"""
    try:
        # Парсим дату
        date_obj = datetime.strptime(message.text, "%d.%m.%Y")
        date_iso = date_obj.strftime("%Y-%m-%d")

        from database import Database
        db = Database()

        success = db.add_work_day(date_iso)

        if success:
            await message.answer(
                f"✅ <b>Рабочий день добавлен!</b>\n\n"
                f"Дата: {message.text}\n\n"
                f"Теперь этот день доступен для бронирования клиентами.",
                reply_markup=get_admin_work_keyboard()
            )
        else:
            await message.answer(
                f"❌ <b>Ошибка добавления дня</b>\n\n"
                f"Не удалось добавить дату {message.text}",
                reply_markup=get_admin_work_keyboard()
            )

    except ValueError:
        await message.answer(
            "❌ <b>Неверный формат даты!</b>\n\n"
            "Пожалуйста, введите дату в формате <b>ДД.ММ.ГГГГ</b> (например: 25.12.2024)",
            reply_markup=get_admin_work_keyboard()
        )

    await state.clear()


@dp.callback_query(F.data == "admin_remove_day_menu")
async def admin_remove_day_menu(callback: CallbackQuery):
    """Меню удаления рабочего дня"""
    text = """
🗑️ <b>Удаление рабочего дня</b>

Выберите месяц, из которого хотите удалить рабочий день:

<i>Примечание: нельзя удалить дни с активными бронированиями (они отмечены ❌)</i>
    """
    await callback.message.edit_text(text, reply_markup=get_admin_months_keyboard(action="remove"))
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_remove_month_"))
async def admin_select_month_for_remove(callback: CallbackQuery):
    """Выбор месяца для удаления дней"""
    month_key = callback.data.split("_")[3]  # admin_remove_month_2025-01
    year, month = map(int, month_key.split('-'))
    month_date = datetime(year, month, 1)
    month_name = f"{get_russian_month_name(month_date)} {year}"

    # Проверяем, есть ли рабочие дни в этом месяце
    from database import Database
    db = Database()
    work_days = db.get_all_work_days()
    month_work_days = [d for d in work_days if d.startswith(month_key)]

    if not month_work_days:
        await callback.message.edit_text(
            f"❌ <b>В этом месяце нет рабочих дней</b>\n\n"
            f"Месяц: {month_name}\n\n"
            f"Нечего удалять.",
            reply_markup=get_admin_work_keyboard()
        )
        await callback.answer()
        return

    text = f"""
🗑️ <b>Удаление рабочих дней</b>

Месяц: {month_name}

Выберите день для удаления:

• <b>✅</b> - доступен для удаления
• <b>❌</b> - есть активные бронирования (удалить нельзя)
    """
    await callback.message.edit_text(text, reply_markup=get_admin_days_keyboard(month_key))
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_remove_"))
async def admin_process_remove_day(callback: CallbackQuery):
    """Обработка удаления дня - ТОЛЬКО для дат, не для месяцев"""
    # Проверяем, что это кнопка "назад"
    if callback.data == "admin_remove_back":
        await admin_remove_day_menu(callback)
        await callback.answer()
        return

    # Проверяем, что это НЕ месяц (не содержит "month")
    if "month" in callback.data:
        # Это выбор месяца для удаления, а не сама дата - игнорируем
        await callback.answer()
        return

    # Извлекаем дату из callback_data (формат: admin_remove_2026-02-01)
    try:
        date_iso = callback.data.replace("admin_remove_", "")
        date_obj = datetime.strptime(date_iso, "%Y-%m-%d")
        date_str = date_obj.strftime("%d.%m.%Y")

        from database import Database
        db = Database()

        success, message_text = db.remove_work_day(date_iso)

        if success:
            await callback.message.edit_text(
                f"✅ <b>Рабочий день удален!</b>\n\n"
                f"Дата: {date_str}\n\n"
                f"{message_text}",
                reply_markup=get_admin_work_keyboard()
            )
        else:
            await callback.message.edit_text(
                f"❌ <b>Не удалось удалить день</b>\n\n"
                f"Дата: {date_str}\n\n"
                f"{message_text}",
                reply_markup=get_admin_work_keyboard()
            )

    except ValueError as e:
        logger.error(f"Ошибка парсинга даты {callback.data}: {e}")
        await callback.answer("❌ Ошибка обработки даты")
        await callback.message.edit_text(
            "❌ <b>Ошибка удаления дня</b>\n\n"
            "Произошла ошибка при обработке даты. Попробуйте еще раз.",
            reply_markup=get_admin_work_keyboard()
        )

    await callback.answer()


@dp.callback_query(F.data == "admin_remove_back")
async def admin_remove_back(callback: CallbackQuery):
    """Возврат из удаления дней к выбору месяца"""
    text = """
🗑️ <b>Удаление рабочего дня</b>

Выберите месяц, из которого хотите удалить рабочий день:

<i>Примечание: нельзя удалить дни с активными бронированиями (они отмечены ❌)</i>
    """
    await callback.message.edit_text(text, reply_markup=get_admin_months_keyboard(action="remove"))
    await callback.answer()


@dp.callback_query(F.data == "admin_occupied")
async def admin_date_occupied(callback: CallbackQuery):
    """Обработчик для занятых дней в админке"""
    await callback.answer("❌ Этот день имеет активные бронирования и не может быть удален", show_alert=True)


@dp.message(Command("remind"))
async def send_manual_reminders(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        return

    await reminder_system.send_booking_reminders(bot)
    await message.answer("✅ Напоминания отправлены")


@dp.message(Command("refund"))
async def process_refund(message: Message):
    """Обработка возврата средств (только для админа)"""
    if message.from_user.id != config.ADMIN_ID:
        return

    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("Использование: /refund payment_id [amount]")
            return

        payment_id = parts[1]
        amount = float(parts[2]) if len(parts) > 2 else None

        success = await PaymentManager.process_refund(payment_id, amount)
        if success:
            await message.answer("✅ Возврат успешно обработан")
        else:
            await message.answer("❌ Ошибка возврата")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# 📍 ЗАПУСК БОТА

async def start_schedulers():
    """Запускает все планировщики"""
    asyncio.create_task(reminder_system.start_reminder_scheduler(bot))


async def main():
    logger.info("Бот Айви запущен!")
    await start_schedulers()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())