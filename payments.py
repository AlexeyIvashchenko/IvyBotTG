import uuid
from yookassa import Payment, Configuration
import config
import logging
from database import Database

logger = logging.getLogger(__name__)
db = Database()

# Настройка ЮKassa
Configuration.account_id = config.YKASSA_SHOP_ID
Configuration.secret_key = config.YKASSA_SECRET_KEY


class PaymentManager:
    @staticmethod
    async def create_payment(amount, description, user_id, booking_date=None, is_final=False):
        """Создает платеж в ЮKassa"""
        try:
            idempotence_key = str(uuid.uuid4())

            payment_data = {
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"https://t.me/your_bot"
                },
                "capture": True,
                "description": description,
                "metadata": {
                    "user_id": user_id,
                    "booking_date": booking_date or "",
                    "is_final": str(is_final)
                }
            }

            payment = Payment.create(payment_data, idempotence_key)

            # Сохраняем в базу
            if booking_date and not is_final:
                db.save_payment_info(
                    user_id=user_id,
                    payment_id=payment.id,
                    amount=amount,
                    booking_date=booking_date,
                    payment_type="deposit"
                )
            elif is_final:
                db.save_payment_info(
                    user_id=user_id,
                    payment_id=payment.id,
                    amount=amount,
                    booking_date=booking_date,
                    payment_type="final"
                )

            logger.info(f"Создан платеж {payment.id} для пользователя {user_id}")
            return payment

        except Exception as e:
            logger.error(f"Ошибка создания платежа: {e}")
            return None

    @staticmethod
    async def check_payment_status(payment_id):
        """Проверяет статус платежа"""
        try:
            payment = Payment.find_one(payment_id)
            return payment.status
        except Exception as e:
            logger.error(f"Ошибка проверки статуса платежа: {e}")
            return None

    @staticmethod
    async def process_webhook(payment_data):
        """Обрабатывает вебхук от ЮKassa"""
        try:
            payment_id = payment_data['object']['id']
            status = payment_data['object']['status']

            logger.info(f"Вебхук от ЮKassa: payment_id={payment_id}, status={status}")

            if status == 'succeeded':
                # Получаем информацию о платеже из базы
                payment_info = db.get_payment_info(payment_id)

                if payment_info:
                    user_id, amount, payment_type, booking_date = payment_info[0], payment_info[2], payment_info[3], \
                    payment_info[4]

                    # Обновляем статус платежа в базе
                    db.update_payment_status(payment_id, status)

                    logger.info(f"Платеж подтвержден: user_id={user_id}, type={payment_type}, date={booking_date}")

                    return {
                        'success': True,
                        'user_id': user_id,
                        'payment_type': payment_type,
                        'booking_date': booking_date,
                        'amount': amount
                    }

            return {'success': False}

        except Exception as e:
            logger.error(f"Ошибка обработки вебхука: {e}")
            return {'success': False}

    @staticmethod
    async def process_refund(payment_id, amount=None):
        """Обрабатывает возврат средств"""
        try:
            from yookassa import Refund

            refund_data = {
                "payment_id": payment_id,
                "amount": {
                    "value": f"{amount:.2f}" if amount else None,
                    "currency": "RUB"
                }
            }

            refund = Refund.create(refund_data, str(uuid.uuid4()))

            if refund.status == 'succeeded':
                db.update_payment_status(payment_id, 'refunded')
                logger.info(f"Возврат успешен: {refund.id}")
                return True

        except Exception as e:
            logger.error(f"Ошибка возврата: {e}")
            return False
