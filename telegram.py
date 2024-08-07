#  StatusServer by jimchen5209
#  Copyright (C) 2019-2019
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
import asyncio
import json
import logging
import time
from enum import Enum

from aiogram import Bot, Dispatcher, executor, types

from app import Main


class ServerStatus(Enum):
    online = "✅ {name} is up"
    server_online = "Server {name} is online:"
    server_unknown = "Service without server association:"
    online_list = "✅ {name} is online"
    online_sub = "✅ {name} is currently online"
    offline = "❌ {name} is down"
    server_offline = "Server {name} is offline:\nLast Error: {reason}"
    offline_list = "❌ {name} is offline"
    offline_sub = "❌ {name} is currently offline"
    unknown = "❔ {name} returned a unknown status"
    new_online = "🆕✅ {name} just popped up and indicates online"
    new_offline = "🆕❌ {name} showed up but it is offline"
    deleted = "🗑 {name} has been deleted"
    service_type = "✅ Service running in {lang}:"
    service_type_offline = "❌ Service offline:"
    service_type_unknown = "❔ Service with unknown status/type:"
    service_empty = "❔ No service running on this server"
    node_down = "🚫 Errored when fetching status from node `{ip}`: {message}"


class Telegram:
    def __init__(self, main: Main):
        self.__logger = logging.getLogger("Telegram")
        logging.basicConfig(level=logging.INFO)
        self.__logger.info("Loading Telegram...")
        self.__main = main
        self.__config = main.config
        self.bot = Bot(token=self.__config.telegram_token)
        self.dispatcher = Dispatcher(self.bot)
        self.loop = asyncio.get_event_loop()

        @self.dispatcher.message_handler(commands=['start'])
        async def start(message: types.Message):
            await message.reply("Jim's Bot Status")

        @self.dispatcher.message_handler(commands=['status'])
        async def get_status(message: types.Message):
            args = message.get_args().split()
            if len(args) == 0:
                status = self.__main.status.get_status()
                msg = self.__status_to_string(status)
                refresh_button = types.inline_keyboard.InlineKeyboardButton(
                    text="🔄 Refresh Now",
                    callback_data=json.dumps({'t': 'refresh', 'o': message.from_user.id})
                )
                markup = types.inline_keyboard.InlineKeyboardMarkup().add(refresh_button)
                await message.reply(msg if len(msg) != 0 else 'No services available.', reply_markup=markup)
            elif args[0] == '-d':
                if message.from_user.id != self.__config.telegram_admin:
                    await message.reply('Permission denied')
                    return
                status = self.__main.status.get_detailed_status()
                msg = self.__detailed_status_to_string(status)
                refresh_button = types.inline_keyboard.InlineKeyboardButton(
                    text="🔄 Refresh Now",
                    callback_data=json.dumps(
                        {'t': 'refresh-detail', 'o': message.from_user.id})
                )
                markup = types.inline_keyboard.InlineKeyboardMarkup().add(refresh_button)
                await message.reply(msg if len(msg) != 0 else 'No services available.', reply_markup=markup)
            else:
                await message.reply('Invalid command')

        @self.dispatcher.message_handler(commands=['privacy'])
        async def reply(message: types.Message):
            await message.reply(
                'Jim\'s Bot Status is just a simple bot that shows the status of my servers, it does not store any data.\nBut some data need to be used for command and refresh button to work, for more information, please refer to the [Telegram\'s Privacy Policy](https://telegram.org/privacy#6-2-how-bots-can-receive-data).', 
                parse_mode='Markdown',
                disable_web_page_preview=True
            )

        @self.dispatcher.callback_query_handler()
        async def on_callback_query(callback_query: types.CallbackQuery):
            data = json.loads(callback_query.data)
            if 't' not in data or 'o' not in data:
                await callback_query.answer("Invalid Button!")
                await callback_query.message.edit_reply_markup(None)
                return
            if data['t'] == 'refresh' or data['t'] == 'refresh-detail':
                if data['o'] != callback_query.message.reply_to_message.from_user.id:
                    await callback_query.answer("This button is not yours!!", show_alert=True)
                    return
                refreshing = types.inline_keyboard.InlineKeyboardButton(
                    text="🔄 Refreshing...",
                    callback_data=json.dumps({'t': 'none', 'o': data['o']})
                )
                markup = types.inline_keyboard.InlineKeyboardMarkup().add(refreshing)
                await callback_query.message.edit_reply_markup(markup)
                self.__main.status.update_status(True)
                if data['t'] == 'refresh':
                    status = self.__main.status.get_status()
                    msg = self.__status_to_string(status)
                elif data['t'] == 'refresh-detail':
                    status = self.__main.status.get_detailed_status()
                    msg = self.__detailed_status_to_string(status)
                msg += '\nUpdated: {time}'.format(time=time.strftime("%Y/%m/%d %H:%M:%S"))
                if callback_query.message.text != msg:
                    await callback_query.message.edit_text(msg, reply_markup=callback_query.message.reply_markup)
                await callback_query.answer("Updated!")

    def send_status_message(self, message: str):
        execute = asyncio.run_coroutine_threadsafe(self.bot.send_message(
            self.__config.telegram_admin,
            message,
            parse_mode="Markdown"
        ), self.loop)
        execute.result()

    @staticmethod
    def __status_to_string(status: dict) -> str:
        msg = ""
        for name in status:
            if status[name]['online']:
                msg += ServerStatus.online_list.value.format(name=name) + '\n'
            else:
                msg += ServerStatus.offline_list.value.format(name=name) + '\n'
        return msg

    def __detailed_status_to_string(self, status: dict) -> str:
        temp_data = {
            'local': {},
            'none': {}
        }
        for name in self.__config.nodes:
            temp_data[name] = {}
        msg = ""
        for name in status:
            if status[name]['online']:
                if status[name]['type'] not in temp_data[status[name]['server']]:
                    temp_data[status[name]['server']][status[name]['type']] = []
                temp_data[status[name]['server']][status[name]['type']].append(name)
            else:
                if 'offline' not in temp_data[status[name]['server']]:
                    temp_data[status[name]['server']]['offline'] = []
                temp_data[status[name]['server']]['offline'].append(name)
        last_error = self.__main.status.get_down_server()
        for server in last_error:
            temp_data[server]['error'] = last_error[server]

        for server in temp_data:
            if server == 'none':
                continue
            if 'error' in temp_data[server]:
                msg += ServerStatus.server_offline.value.format(name=server, reason=temp_data[server]['error']) + '\n'
            else:
                msg += ServerStatus.server_online.value.format(name=server) + '\n'
                if temp_data[server] == {}:
                    msg += '  ' + ServerStatus.service_empty.value + '\n\n'
                else:
                    for lang in temp_data[server]:
                        if lang == 'python':
                            msg += '  ' + ServerStatus.service_type.value.format(lang='Python') + '\n'
                        elif lang == 'node':
                            msg += '  ' + ServerStatus.service_type.value.format(lang='Node.JS') + '\n'
                        elif lang == 'node-pm2':
                            msg += '  ' + ServerStatus.service_type.value.format(lang='Node.JS with PM2') + '\n'
                        elif lang == 'offline':
                            continue
                        else:
                            msg += '  ' + ServerStatus.service_type_unknown.value + '\n'
                        for i in temp_data[server][lang]:
                            msg += '  - ' + i + '\n'
                        msg += '\n'
                    if 'offline' in temp_data[server]:
                        msg += '  ' + ServerStatus.service_type_offline.value + '\n'
                        for i in temp_data[server]['offline']:
                            msg += '  - ' + i + '\n'
                        msg += '\n'
        
        if 'offline' in temp_data['none']:
            msg += ServerStatus.server_unknown.value + '\n  ' + ServerStatus.service_type_offline.value + '\n'
            for i in temp_data['none']['offline']:
                msg += '  - ' + i + '\n'
            msg += '\n'

        return msg

    def start(self):
        executor.start_polling(self.dispatcher, skip_updates=True)
