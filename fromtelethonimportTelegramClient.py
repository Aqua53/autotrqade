from telethon import TelegramClient

api_id = '36075963'
api_hash = '8f80612a8520475f7ac55b6f9e1c4e54'

async def main():
    async with TelegramClient('sesi_cek_id', api_id, api_hash) as client:
        async for dialog in client.iter_dialogs():
            print(f'{dialog.name} has ID {dialog.id}')

import asyncio
asyncio.run(main())