import asyncio
from datetime import datetime, timedelta
import logging
from database import Database
import config
from payments import PaymentManager

logger = logging.getLogger(__name__)
db = Database()


class ReminderSystem:
    def __init__(self, gsheets=None):
        self.gsheets = gsheets

    async def send_booking_reminders(self, bot):
        """Отправляет напоминания о бронированиях"""
        try:
            # Используем локальную базу данных вместо Google Sheets для напоминаний
            today_bookings = db.get_today_bookings()

            for booking in today_bookings:
                user_id = booking[1]  # user_id field from database
                booking_date = booking[4]  # booking_date field
                final_paid = booking[7]  # final_paid field

                try:
                    # Если финальная оплата еще не произведена
                    if not final_paid:
                        from keyboards import get_payment_keyboard
                        await bot.send_message(
                            user_id,
                            f"🔄 <b>Ваш проект в разработке!</b>\n\n"
                            f"Сегодня ({booking_date}) мы работаем над вашим проектом. "
                            f"Пожалуйста, оплатите оставшуюся сумму <b>11 000 ₽</b> до 20:00 по МСК, "
                            f"чтобы мы могли отправить вам готовый проект.\n\n"
                            f"<i>После оплаты вы получите:</i>\n"
                            f"• Ссылку на готовый сайт\n"
                            f"• Рекламные объявления\n"
                            f"• Инструкцию по работе",
                            parse_mode="HTML",
                            reply_markup=get_payment_keyboard(config.FINAL_AMOUNT, is_final=True)
                        )
                        logger.info(f"Напоминание о финальной оплате отправлено пользователю {user_id}")
                    else:
                        logger.info(f"Пользователь {user_id} уже оплатил финальную часть")

                except Exception as e:
                    logger.error(f"Ошибка отправки напоминания пользователю {user_id}: {e}")

            logger.info(f"Отправлены напоминания для {len(today_bookings)} бронирований")

        except Exception as e:
            logger.error(f"Ошибка отправки напоминаний: {e}")

    async def check_pending_payments(self, bot):
        """Проверяет статусы ожидающих платежей каждые 2 минуты"""
        try:
            logger.info("Проверка статусов ожидающих платежей...")

            # Получаем ожидающие платежи
            cursor = db.conn.cursor()
            cursor.execute('''
                SELECT payment_id, user_id, payment_type, booking_date, amount 
                FROM payments WHERE status = 'pending'
            ''')

            pending_payments = cursor.fetchall()
            logger.info(f"Найдено {len(pending_payments)} ожидающих платежей")

            for payment in pending_payments:
                payment_id, user_id, payment_type, booking_date, amount = payment

                try:
                    # Проверяем статус в ЮKassa
                    status = await PaymentManager.check_payment_status(payment_id)
                    logger.info(f"Платеж {payment_id}: статус {status}")

                    if status == 'succeeded':
                        # Обновляем статус платежа
                        db.update_payment_status(payment_id, status)

                        # Обновляем Google Sheets
                        if self.gsheets:
                            if payment_type == 'deposit':
                                self.gsheets.update_booking_status(user_id, booking_date, "Предоплата получена")
                            elif payment_type == 'final':
                                self.gsheets.update_booking_status(user_id, booking_date, "Полная оплата")

                        # Отправляем уведомление пользователю
                        if payment_type == 'deposit':
                            await bot.send_message(
                                user_id,
                                f"✅ <b>Платеж подтвержден!</b>\n\n"
                                f"Сумма: {amount} ₽\n"
                                f"Дата брони: {booking_date}\n\n"
                                f"📝 <b>Теперь заполните бриф:</b>\n{config.BRIEF_FORM_URL}\n\n"
                                f"<i>Важно: бриф нужно заполнить до назначенной даты.</i>"
                            )

                            # Уведомляем админа
                            from keyboards import get_admin_delivery_keyboard
                            await bot.send_message(
                                config.ADMIN_ID,
                                f"🎉 <b>Новое бронирование!</b>\n\n"
                                f"👤 Пользователь: {user_id}\n"
                                f"📅 Дата: {booking_date}\n"
                                f"💰 Предоплата: {config.DEPOSIT_AMOUNT} ₽",
                                reply_markup=get_admin_delivery_keyboard(user_id, booking_date, is_final_paid=False)
                            )

                        elif payment_type == 'final':
                            await bot.send_message(
                                user_id,
                                f"✅ <b>Финальная оплата подтверждена!</b>\n\n"
                                f"Сумма: {amount} ₽\n\n"
                                f"Спасибо за оплату! Теперь мы можем отправить вам готовый проект.\n\n"
                                f"<i>Ожидайте материалы в течение дня.</i>"
                            )

                            # Уведомляем админа о готовности к отправке проекта
                            from keyboards import get_admin_delivery_keyboard, get_admin_chat_keyboard
                            await bot.send_message(
                                config.ADMIN_ID,
                                f"🎉 <b>Финальная оплата получена!</b>\n\n"
                                f"👤 Пользователь: {user_id}\n"
                                f"📅 Дата: {booking_date}\n"
                                f"💰 Финальная оплата: {config.FINAL_AMOUNT} ₽\n\n"
                                f"<i>Теперь можно отправить клиенту готовый проект.</i>",
                                reply_markup=get_admin_delivery_keyboard(user_id, booking_date, is_final_paid=True)
                            )

                            # ДОБАВЛЯЕМ кнопку для связи с пользователем
                            await bot.send_message(
                                config.ADMIN_ID,
                                f"💬 <b>Можно связаться с пользователем</b>\n\n"
                                f"👤 Пользователь: {user_id}\n"
                                f"📅 Дата проекта: {booking_date}\n\n"
                                f"<i>Если требуется уточнить детали для завершения проекта, вы можете начать диалог с пользователем.</i>",
                                reply_markup=get_admin_chat_keyboard(user_id, booking_date)
                            )

                        logger.info(f"Платеж {payment_id} успешно обработан для пользователя {user_id}")

                    elif status in ['canceled', 'failed']:
                        # Обновляем статус отмененного/неудачного платежа
                        db.update_payment_status(payment_id, status)
                        logger.info(f"Платеж {payment_id} отменен/неудачен")

                except Exception as e:
                    logger.error(f"Ошибка проверки платежа {payment_id}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Ошибка проверки ожидающих платежей: {e}")

    async def start_reminder_scheduler(self, bot):
        """Запускает планировщик напоминаний и проверки платежей"""
        while True:
            now = datetime.now()

            # Проверяем каждый день в указанное время для напоминаний
            if now.hour == config.REMINDER_HOUR and now.minute == 00:
                await self.send_booking_reminders(bot)
                await asyncio.sleep(60)  # Ждем 1 минуту чтобы не запускать повторно

            # Проверяем платежи каждые 2 минуты
            if now.minute % 2 == 0:  # Каждые 2 минуты
                await self.check_pending_payments(bot)
                await asyncio.sleep(60)  # Ждем 1 минуту

            await asyncio.sleep(60)  # Проверяем каждую минуту