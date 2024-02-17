import asyncio
import json
import os
import threading
import uuid
from urllib.parse import quote_plus

import requests
import websockets


class Item:
    def __init__(self, notifier: uuid.UUID, remoter: uuid.UUID, currencies: str, display: str):
        self.notifier = notifier
        self.remoter = remoter
        self.currencies = currencies
        self.display = display

    def __str__(self):
        return f'{self.notifier};{self.remoter};{self.currencies};{self.display}'


class Trade:
    def __init__(self, id: uuid.UUID, remoter: uuid.UUID, state: str):
        self.id = id
        self.remoter = remoter
        self.state = state

    def __str__(self):
        return f'{self.id};{self.remoter};{self.state}'


def parse_uuid(value: str):
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


token: uuid.UUID
if not os.path.exists(os.path.join('./', 'token.txt')):
    print('嗨！您似乎是第一次執行此腳本！')
    print('請先在遊戲內輸入：/token Payment LandNotify')
    token = parse_uuid(input('然後把令牌貼在此處並按下 Enter：'))
    while token is None:
        token = parse_uuid(input('您輸入的令牌不正確，請重新輸入後按下 Enter：'))
    with open('token.txt', 'w', encoding='utf-8') as file:
        file.write(str(token))
else:
    with open('token.txt', 'r', encoding='utf-8') as file:
        token = parse_uuid(file.read())

assert (token is not None), "無法讀取先前存取的令牌！"

running = True
gateway: websockets.WebSocketClientProtocol | None
items: dict[uuid.UUID, Item] = {}
trades: dict[uuid.UUID, Trade] = {}

if os.path.exists(os.path.join('./', 'items.txt')):
    with open('items.txt', 'r', encoding='utf-8') as file:
        for line in file.readlines():
            split = line.split(';', 4)
            if len(split) == 4:
                notifier = parse_uuid(split[0])
                if notifier is not None:
                    items[notifier] = Item(notifier, parse_uuid(split[1]), split[2], split[3])

if os.path.exists(os.path.join('./', 'trades.txt')):
    with open('trades.txt', 'r', encoding='utf-8') as file:
        for line in file.readlines():
            split = line.split(';', 3)
            if len(split) == 2:
                id = parse_uuid(split[0])
                if id is not None:
                    trades[id] = Trade(id, parse_uuid(split[1]), split[2])


def save_items():
    with open('items.txt', 'w', encoding='utf-8') as file:
        for item in items.values():
            file.write(str(item))


def save_trades():
    with open('trades.txt', 'w', encoding='utf-8') as file:
        for item in trades.values():
            file.write(str(item))


def request_trade(message: dict):
    if message['data']['powered'] is not True:
        return
    key = parse_uuid(message['data']['key'])
    if key not in items:
        return
    item = items[key]
    try:
        requests.get(f'https://catbud.net/api/remote/{item.remoter}/false')
        players = requests.get(f'https://catbud.net/api/range?env={message['data']['env']}&x={message['data']['x']}&y={message['data']['y'] + 1.}&z={message['data']['z']}&range=1.25').json()
        if len(players) == 0:
            return
        payment = requests.get(f'https://catbud.net/api/payment/request?token={token}&player={players[0]['player']}&display={item.display}&prices={item.currencies}').json()
        id = parse_uuid(payment['id'])
        trades[id] = Trade(id, item.remoter, payment['state'])
        save_trades()
    except requests.exceptions.JSONDecodeError as ex:
        print(f'無法建立交易：{key}')


def finish_trade(message: dict):
    if message['data']['state'] != 'finish':
        return
    id = parse_uuid(message['data']['id'])
    if id not in trades:
        return
    trade = trades[id]
    if trade.state != 'wait':
        return
    trade.state = 'finish'
    try:
        requests.get(f'https://catbud.net/api/remote/{trade.remoter}/true')
        save_trades()
    except requests.exceptions.JSONDecodeError as ex:
        print(f'無法完成交易：{id}')


async def connect_gateway():
    global running
    global gateway
    while running:
        try:
            async with websockets.connect(f'wss://catbud.net/api//gateway?token={token}') as websocket:
                gateway = websocket
                while running:
                    message = json.loads(await websocket.recv())
                    match message['type']:
                        case 'land_notify':
                            request_trade(message)
                        case 'payment':
                            finish_trade(message)
        except RuntimeError as ex:
            pass
        except websockets.exceptions.ConnectionClosedError as ex:
            print('無法連線伺服器，重新嘗試中...')
        except websockets.InvalidStatusCode as ex:
            print('無法連線伺服器，重新嘗試中...')
        await asyncio.sleep(10)


asyncio.set_event_loop(asyncio.new_event_loop())
thread_gateway = threading.Thread(target=(lambda: asyncio.run(connect_gateway())))
thread_gateway.start()


def cmd_qu():
    global running
    print('正在關閉腳本...')
    running = False
    thread_gateway.join()
    print('成功結束腳本')


def cmd_ad(args: list[str]):
    if len(args) < 5:
        print('命令需要至少 4 個參數')
        return
    notifier = parse_uuid(args[1])
    if notifier is None:
        print('通知器密鑰不正確')
        return
    remoter = parse_uuid(args[2])
    if remoter is None:
        print('遙控器密鑰不正確')
        return
    currencies = args[3]
    if len(currencies) == 0:
        print('貨幣與價錢不能為空')
        return
    for entry in currencies.split(','):
        if len(entry.split(':')) != 2:
            print('貨幣與價錢格式不正確')
    display = ''
    for index in range(4, len(args) - 1):
        if len(display) != 0:
            display += ' '
        display += args[index]
    if notifier in items:
        print(f'商店 {notifier} 已經存在')
        return
    items[notifier] = Item(notifier, remoter, currencies, quote_plus(display))
    save_items()
    print(f'商店 {notifier} 新增成功！')


def cmd_rm(args: list[str]):
    if len(args) < 2:
        print('命令需要至少 1 個參數')
        return
    notifier = parse_uuid(args[1])
    if notifier is None:
        print('通知器密鑰不正確')
        return
    if notifier not in items:
        print(f'商店 {notifier} 不存在')
        return
    del items[notifier]
    save_items()
    print(f'商店 {notifier} 移除成功！')


while running:
    coms = input('→ qu 退出腳本\n→ ad <通知器密鑰> <遙控器密鑰> <貨幣:金額,貨幣:金額,...> <商品說明> 加入商店配置\n→ rm <通知器密鑰> 移除商店配置\n').split(' ')
    match coms[0]:
        case 'qu':
            cmd_qu()
        case 'ad':
            cmd_ad(coms)
        case 'rm':
            cmd_rm(coms)
        case _:
            print('未知的命令前軸')