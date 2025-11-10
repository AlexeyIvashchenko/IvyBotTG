import asyncio
from aiogram import Bot
import config

async def delete_webhook():
    bot = Bot(token=config.BOT_TOKEN)
    await bot.delete_webhook()
    print("✅ Вебхук удален!")
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(delete_webhook())