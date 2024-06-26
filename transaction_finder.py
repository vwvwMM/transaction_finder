from telethon.sync import TelegramClient,events, Button
from telethon.tl.types import BotCommand
from telethon import functions, types
from datetime import datetime
import requests
import re
import os
from dotenv import load_dotenv

load_dotenv()

api_id = os.getenv('TXN_FINDER_API_ID')
api_hash = os.getenv('TXN_FINDER_API_HASH')
bot_token = os.getenv('TXN_FINDER_BOT_TOKEN')
GMGN_NEW_PAIR_URL = os.getenv('GMGN_NEW_PAIR_URL')
GMGN_WALLET_URL = os.getenv('GMGN_WALLET_URL')
GMGN_TRADE_URL = os.getenv('GMGN_TRADE_URL')
TOTAL_NUMBER_OF_TRADES = 15
FIRST_N_TXNS = 10
client = TelegramClient('bot_session', api_id, api_hash).start(bot_token=bot_token)
chat_ids = set()

user_data = {}
commands = [
    BotCommand(command='start', description='Start the bot'),
    BotCommand(command='finddur', description='Find transactions in a specific duration'),
    BotCommand(command='findtxn', description='Find transactions before/after a specific transaction'),
    BotCommand(command='findtokenopen', description=f'Find holdings of first {FIRST_N_TXNS} buyers of a token'),
    BotCommand(command='help', description='Show help message')
]

async def set_bot_commands():
    await client(functions.bots.SetBotCommandsRequest(
        scope=types.BotCommandScopeDefault(),
        lang_code='en',
        commands=commands
    ))
    
def get_time_menu(user_id):
    has_ca = user_data.get(user_id, {}).get('token_ca', False)
    token_ca_label = f"token {has_ca}" if has_ca else "Token mint address"
    has_start_time = user_data.get(user_id, {}).get('start_time', False)
    start_time_label = f"{has_start_time}" if has_start_time else "Start time"
    has_end_time = user_data.get(user_id, {}).get('end_time', False)
    end_time_label = f"{has_end_time}" if has_end_time else "End time (YYYY-MM-DD hh:mm:ss utc+8))"
    buysell = user_data.get(user_id, {}).get('buysell', 0)
    only_buy_label = "🟢 Only Buy" if buysell==1 else "🟠 Only Buy"
    only_sell_label = "🟢 Only Sell" if buysell==2 else "🟠 Only Sell"

    return [
        [Button.inline(token_ca_label, b"token_ca")],
        [Button.inline(start_time_label, b"start_time"), Button.inline(end_time_label, b"end_time")],
        [Button.inline(only_buy_label, b"only_buy"), Button.inline(only_sell_label, b"only_sell")],
        [Button.inline("Find", b"find")],
        [Button.inline("Back", b"back")],
    ]

def get_txn_menu(user_id):
    has_ca = user_data.get(user_id, {}).get('token_ca', False)
    token_ca_label = f"token {has_ca}" if has_ca else "Token mint address"
    has_signature = user_data.get(user_id, {}).get('signature', False)
    signature_label = f"Signature: {has_signature}" if has_signature else "Signature"
    before_after = user_data.get(user_id, {}).get('before_after', 'before')
    before_label = "🟢 Before" if before_after == 'before' else "🟠 Before"
    after_label = "🟢 After" if before_after == 'after' else "🟠 After"
    buysell = user_data.get(user_id, {}).get('buysell', 0)
    only_buy_label = "🟢 Only Buy" if buysell==1 else "🟠 Only Buy"
    only_sell_label = "🟢 Only Sell" if buysell==2 else "🟠 Only Sell"

    return [
        [Button.inline(token_ca_label, b"token_ca")],
        [Button.inline(signature_label, b"signature")],
        [Button.inline(before_label, b"before"), Button.inline(after_label, b"after")],
        [Button.inline(only_buy_label, b"only_buy"), Button.inline(only_sell_label, b"only_sell")],
        [Button.inline("Find", b"find")],
        [Button.inline("Back", b"back")],
    ]
    
def get_first_menu(user_id):
    use_default = user_data.get(user_id, {}).get('default_tokens', False)
    default_tokens_label = f"{'🟢' if use_default else '🟠'} Use latest completed tokens"
    has_ca = user_data.get(user_id, {}).get('token_ca', False)
    token_ca_label = f"token {has_ca}" if has_ca else "Token mint address"
    return [
        [Button.inline(default_tokens_label, b"default_tokens")],
        [Button.inline(token_ca_label, b"token_ca")],
        [Button.inline("Find", b"find")],
        [Button.inline("Back", b"back")],
    ]
    
def transform_number(num,type):
    if type == 'price':
        num_str = f"{num:.10f}"  # Use high precision to ensure small numbers are fully represented
        # Match the significant digits
        match = re.match(r"0\.(0+)(\d+)", num_str)
        if match:
            leading_zeros = len(match.group(1))
            significant_digits = match.group(2)
            return f"0.0{{{leading_zeros + 1}}}{significant_digits[:4]}"
        else:
            # In case the number does not match the pattern (which should not happen for positive small floats)
            return num_str
    elif type == 'amount':
        if num >= 1_000_000:
            return f"{round(num/1_000_000, 2)}M"
        elif num >= 1_000:
            return f"{round(num/1_000, 2)}K"
        else:
            return f"{round(num, 4)}"
    else:
        return num
    
def get_new_token():
    all_tokens = requests.get(GMGN_NEW_PAIR_URL).json()['data']['pairs']
    token = all_tokens[0]
    return {'address':token['base_address'], 'symbol':token['base_token_info']['symbol']}

def find_first_txns(token_address):
    ended = False
    limit = 200
    total_txns = []
    cursor = ''
    while not ended:
        response = requests.get(GMGN_TRADE_URL+f"/{token_address}", params={'limit': limit, 'cursror':cursor})
        if response.status_code != 200: 
            ended = True
            break
        data = response.json()
        total_txns += data['data']['history']
        if len(data) < limit:
            ended = True
        cursor = data['data']['next']
    
    if len(total_txns) < FIRST_N_TXNS:
        return total_txns
    return total_txns[-FIRST_N_TXNS:]

async def get_trades(token_address, sig='',start_timestamp=0, end_timestamp=0, before_after='before', buysell=0):
    limit = 100
    found = False
    total_trades = []
    start_ind = -1
    end_ind = -1
    cursor = ''
    while not found:
        response = requests.get(GMGN_TRADE_URL+f"/{token_address}", params={"limit":limit, "cursor":cursor})
        data = response.json()
        cursor = data['data'].get('next', '')
        data = data['data'].get('history', [])
        if buysell == 1:
            data = [trade for trade in data if trade['event']=='buy']
        elif buysell == 2:
            data = [trade for trade in data if trade['event']=='sell']
        prev_total_len = len(total_trades)
        total_trades += data
        if len(sig)!=0:
            for i in range(len(data)):
                # print(f'{data[i]['tx_hash']} {data[i]['timestamp']}')
                if data[i]['tx_hash'] == sig:
                    start_ind = i+prev_total_len
                    end_ind = i+prev_total_len
                    found = True
                    break
            if found:
                if before_after == 'before':
                    if len(total_trades)-end_ind <= TOTAL_NUMBER_OF_TRADES:
                        if cursor == '':
                            return total_trades[end_ind+1:]
                        res = requests.get(GMGN_TRADE_URL+f"/{token_address}", params={"limit":TOTAL_NUMBER_OF_TRADES,'cursor':cursor})
                        new_data = res.json()
                        cursor = new_data['data'].get('next', '')
                        new_data = new_data['data'].get('history', [])
                        total_trades += new_data
                        if len(total_trades) - end_ind < TOTAL_NUMBER_OF_TRADES:
                            return total_trades[end_ind+1:]
                    return total_trades[end_ind+1:end_ind+TOTAL_NUMBER_OF_TRADES+1]
                else:
                    if start_ind <TOTAL_NUMBER_OF_TRADES:
                        return total_trades[:start_ind]
                    else:
                        return total_trades[start_ind-TOTAL_NUMBER_OF_TRADES:start_ind]
        elif start_timestamp and end_timestamp:
            for i in range(len(data)):
                if data[i]['timestamp'] < end_timestamp and end_ind == -1:
                    end_ind = i+prev_total_len
                if data[i]['timestamp'] < start_timestamp:
                    start_ind = i+prev_total_len-1
                    found = True
                    break
            if found:
                if end_ind - start_ind < TOTAL_NUMBER_OF_TRADES:
                    return total_trades[end_ind:start_ind+1]
                else:
                    return total_trades[end_ind:start_ind+1]
        elif start_timestamp:
            for i in range(len(data)):
                if data[i]['timestamp'] < start_timestamp:
                    start_ind = i+prev_total_len-1
                    found = True
                    break
            if found:
                if start_ind < TOTAL_NUMBER_OF_TRADES:
                    return total_trades[:start_ind]
                else:
                    return total_trades[start_ind-TOTAL_NUMBER_OF_TRADES+1:start_ind+1]
        elif end_timestamp:
            for i in range(len(data)):
                if data[i]['timestamp'] < end_timestamp:
                    end_ind = i+prev_total_len
                    found = True
                    break
            if found:
                if len(total_trades)-end_ind < TOTAL_NUMBER_OF_TRADES:
                    if cursor == '':
                        return total_trades[end_ind:]
                    res = requests.get(GMGN_TRADE_URL+f"/{token_address}", params={"limit":TOTAL_NUMBER_OF_TRADES, 'cursor':cursor})
                    new_data = res.json()
                    cursor = new_data['data'].get('next', '')
                    new_data = new_data['data'].get('history', [])
                    total_trades += new_data
                return total_trades[end_ind:end_ind+TOTAL_NUMBER_OF_TRADES]
        if cursor == '':
            if start_timestamp:
                if len(total_trades) < TOTAL_NUMBER_OF_TRADES:
                    return total_trades 
                else:
                    return total_trades[-TOTAL_NUMBER_OF_TRADES:]
            else:
                return []
def trades_to_messages(trades):
    message = ""
    for trade in trades[:TOTAL_NUMBER_OF_TRADES]:
        sol_amount = transform_number(trade['quote_amount'],'amount')
        token_amount = transform_number(trade['base_amount'],'amount')
        action = trade['event']
        price = transform_number(trade['quote_amount']/trade['base_amount'],'price')
        signer = trade['maker']
        signature = trade['tx_hash']
        message += f"<a href={'https://gmgn.ai/sol/address/'+signer} target='_blank'>{signer[:4]}...{signer[-4:]}</a> <b>{'🟢🟢BUY🟢🟢' if action =='buy' else '🔴🔴SELL🔴🔴'}</b> <a href={'https://solscan.io/tx/'+signature} target='_blank'>{token_amount} tokens {'with' if action=='buy' else 'for'} {sol_amount} SOL at price {price}</a>\n" 
    if len(trades) > TOTAL_NUMBER_OF_TRADES:
        message += "More transactions found..."
    if len(trades) == 0:
        message = "No transactions found..."
    return message

def trades_to_traders(trades):
    message = ""
    next_page = ''
    for trade in trades:
        signer = trade['maker']
        response = requests.get(GMGN_WALLET_URL+f"/{signer}", params={'orderby':'last_active_timestamp','direction':'desc','limit':FIRST_N_TXNS,'tx30d':'true','showsmall':'true','sellout':'true','cursor':next_page})
        holdings = response.json()['data']['holdings']
        message += f"<a href={'https://gmgn.ai/sol/address/'+signer} target='_blank'>{signer[:4]}...{signer[-4:]}</a> have:\n"
        for hold in holdings:
            nowtime = datetime.now().timestamp()
            duration = -1
            if hold['last_active_timestamp']:
                duration = str(round((nowtime - hold['last_active_timestamp'])/1000))
            message += f"{hold['symbol'].strip('$')}{' ('+duration+'s)' if duration!=-1 else ''}, "
        message = message[:-2]+'\n'
    if len(trades) == 0:
        message = "No transactions found..."
    return message

@client.on(events.NewMessage(pattern='/start'))
async def send_hello_message(event):
    chat_id = event.chat_id
    user_id = event.sender_id
    username = (await event.get_sender()).username
    
    if user_data.get(user_id):
        await event.reply("You have already started the bot.")
        return

    # Store user information
    user_data[user_id] = {
        'chat_id': chat_id,
        'username': username,
    }

    # Send a greeting message
    greeting_message = f'Hello {username} from your bot!'
    await client.send_message(chat_id, greeting_message)

    print(f"User {username} ({user_id}) started the bot.")

@client.on(events.NewMessage(pattern='/finddur'))
async def find_txn(event):
    user_id = event.sender_id
    message = (
        "Let's find some transactions associated with a token in a specific duration.\n"
    )
    msg = await client.send_message(
        user_id,
        message,
        buttons= get_time_menu(user_id)
    )
    user_data[user_id]['action'] = 'finddur'
    user_data[user_id]['step'] = 'token_ca'
    user_data[user_id]['msg_id'] = msg.id
    
    await client.send_message("Please enter the token mint address:")
    
@client.on(events.NewMessage(pattern='/findtxn'))
async def find_txn(event):
    user_id = event.sender_id
    message = (
        "Let's find transactions before/after a specific transaction.\n"
    )
    msg = await client.send_message(
        user_id,
        message,
        buttons= get_txn_menu(user_id)
    )
    user_data[user_id]['action'] = 'findtxn'
    user_data[user_id]['step'] = 'token_ca'
    user_data[user_id]['msg_id'] = msg.id
    
    await client.send_message("Please enter the token mint address:")
    
@client.on(events.NewMessage(pattern='/findtokenopen'))
async def find_token_open(event):
    user_id = event.sender_id
    message = (
        f"Let's find first {FIRST_N_TXNS} transactions of a specific transaction.\n"
    )
    msg = await client.send_message(
        user_id,
        message,
        buttons= get_first_menu(user_id)
    )
    user_data[user_id]['action'] = 'findtokenopen'
    user_data[user_id]['step'] = 'token_ca'
    user_data[user_id]['msg_id'] = msg.id
    
    await client.send_message("Please enter the token mint address:")
    
@client.on(events.CallbackQuery)
async def callback_query_handler(event):
    user_id = event.sender_id
    data = event.data.decode('utf-8')

    if user_id not in user_data:
        user_data[user_id] = {}

    user_data[user_id]['msg_id'] = event.message_id
    
    if data == "token_ca":
        user_data[user_id]['step'] = 'token_ca'
        await event.respond("Please enter the token mint address:")
    elif data == "default_tokens":
        if user_data[user_id].get('default_tokens', False):
            user_data[user_id]['default_tokens'] = False
        else:
            user_data[user_id]['default_tokens'] = True
        user_data[user_id]['token_ca'] = None
        await client.edit_message(event.chat_id, event.message_id, buttons=get_first_menu(user_id))
    elif data == "signature":
        user_data[user_id]['step'] = 'signature'
        await event.respond("Please enter the signature:")
    elif data == "start_time":
        user_data[user_id]['step'] = 'start_time'
        await event.respond("Please enter the start date (YYYY-MM-DD hh:mm:ss):")
    elif data == "end_time":
        user_data[user_id]['step'] = 'end_time'
        await event.respond("Please enter the end date (YYYY-MM-DD) hh:mm:ss):")
    elif data == "only_buy":
        if user_data[user_id].get('buysell', 0) == 1:
            user_data[user_id]['buysell'] = 0
        else:
            user_data[user_id]['buysell'] = 1
        if user_data[user_id].get('action', '') == 'finddur':
            await client.edit_message(event.chat_id, event.message_id, buttons=get_time_menu(user_id))
        elif user_data[user_id].get('action', '') == 'findtxn':
            await client.edit_message(event.chat_id, event.message_id, buttons=get_txn_menu(user_id))
    elif data == "only_sell":
        if user_data[user_id].get('buysell', 0) == 2:
            user_data[user_id]['buysell'] = 0
        else: 
            user_data[user_id]['buysell'] = 2
        if user_data[user_id].get('action', '') == 'finddur':
            await client.edit_message(event.chat_id, event.message_id, buttons=get_time_menu(user_id))
        elif user_data[user_id].get('action', '') == 'findtxn':
            await client.edit_message(event.chat_id, event.message_id, buttons=get_txn_menu(user_id))
    elif data == "before":
        user_data[user_id]['before_after'] = 'before'
        await client.edit_message(event.chat_id, event.message_id, buttons=get_txn_menu(user_id))   
    elif data == "after":
        user_data[user_id]['before_after'] = 'after'
        await client.edit_message(event.chat_id, event.message_id, buttons=get_txn_menu(user_id))
    elif data == "find":
        print(user_data[user_id])
        if user_data[user_id].get('action', '') == 'finddur':
            await event.respond("Finding transactions...")
            token_ca = user_data[user_id].get('token_ca')
            start_time = user_data[user_id].get('start_time',None)
            if start_time: start_time = int(datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S').timestamp())
            end_time = user_data[user_id].get('end_time',None)
            if end_time: end_time = int(datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S').timestamp())
            buysell = user_data[user_id].get('buysell', 0)
            before_after = user_data[user_id].get('before_after', 'after')
            signature = user_data[user_id].get('signature', '')
            if token_ca and (start_time or end_time):
                print(token_ca, start_time, end_time)
                response = await get_trades(token_ca, start_timestamp=start_time, end_timestamp=end_time, buysell=buysell)
                message = trades_to_messages(response)
                await event.respond(message, parse_mode='html')
            elif token_ca and signature:
                response = await get_trades(token_ca, sig=signature, before_after=before_after, buysell=buysell)
                message = trades_to_messages(response)
                await event.respond(message, parse_mode='html')
            else:
                await event.respond("Please provide all required information (token mint address, start date or end date).")
        elif user_data[user_id].get('action', '') == 'findtxn':
            await event.respond("Finding transactions...")
            token_ca = user_data[user_id].get('token_ca')
            signature = user_data[user_id].get('signature', '')
            buysell = user_data[user_id].get('buysell', 0)
            before_after = user_data[user_id].get('before_after', 'before')
            if token_ca and signature:
                response = await get_trades(token_ca, sig=signature, before_after=before_after, buysell=buysell)
                message = trades_to_messages(response)
                await event.respond(message, parse_mode='html')
            else:
                await event.respond("Please provide all required information (token mint address, signature).")
        elif user_data[user_id].get('action', '') == 'findtokenopen':
            await event.respond("Finding transactions...")
            if user_data[user_id].get('token_ca'):
                token_ca = user_data[user_id].get('token_ca')
                response = find_first_txns(token_ca)
                message = trades_to_traders(response)
                await event.respond(message, parse_mode='html')
            elif user_data[user_id].get('default_tokens', False):
                token = get_new_token()
                await event.respond(f"Using {token['symbol']}...")
                response = find_first_txns(token['address'])
                message = trades_to_traders(response)
                await event.respond(message, parse_mode='html')
            else:
                await event.respond("Please provide the token mint address.")
        message = (
            'Oldest txns from bottom to top, max 15 txns\n'
        )
        msg = await client.send_message(
            user_id,
            message=message,
            buttons= get_time_menu(user_id) if user_data[user_id].get('action', '') == 'finddur' else get_txn_menu(user_id) if user_data[user_id].get('action', '') == 'findtxn' else get_first_menu(user_id)
        )
        user_data[user_id]['msg_id'] = msg.id
    elif data == "back":
        user_data[user_id] = {'step': 'init'}
        user_data[user_id]['action'] = ''
        await client.edit_message(event.chat_id, event.message_id, buttons=[])
    
@client.on(events.NewMessage)
async def text_message_handler(event):
    user_id = event.sender_id
    text = event.text.strip()

    if user_id not in user_data or text=='/finddur' or text=='/findtxn' or text=='/findtokenopen':
        return

    current_step = user_data[user_id].get('step')

    if user_data[user_id].get('action', '') == 'finddur':
        if current_step == 'token_ca':
            user_data[user_id]['token_ca'] = text
            await client.edit_message(event.chat_id, user_data[user_id]['msg_id'], buttons=get_time_menu(user_id))
            user_data[user_id]['step'] = 'start_time'
        elif current_step == 'start_time':
            try:
                #check text format
                datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
                user_data[user_id]['start_time'] = text
                await client.edit_message(event.chat_id, user_data[user_id]['msg_id'], buttons=get_time_menu(user_id))
                user_data[user_id]['step'] = 'end_time'
            except ValueError:
                await event.respond("Invalid date format. Please enter the date in YYYY-MM-DD hh:mm:ss format.")
                user_data[user_id]['start_time'] = None
                await client.edit_message(event.chat_id, user_data[user_id]['msg_id'], buttons=get_time_menu(user_id))
        elif current_step == 'end_time':
            try:
                datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
                user_data[user_id]['end_time'] = text
                await client.edit_message(event.chat_id, user_data[user_id]['msg_id'], buttons=get_time_menu(user_id))
            except ValueError:
                await event.respond("Invalid date format. Please enter the date in YYYY-MM-DD hh:mm:ss format.")
                user_data[user_id]['end_time'] = None
                await client.edit_message(event.chat_id, user_data[user_id]['msg_id'], buttons=get_time_menu(user_id))
    elif user_data[user_id].get('action', '') == 'findtxn':
        if current_step == 'token_ca':
            user_data[user_id]['token_ca'] = text
            await client.edit_message(event.chat_id, user_data[user_id]['msg_id'], buttons=get_txn_menu(user_id))
            user_data[user_id]['step'] = 'signature'
        elif current_step == 'signature':
            user_data[user_id]['signature'] = text
            await client.edit_message(event.chat_id, user_data[user_id]['msg_id'], buttons=get_txn_menu(user_id))
    elif user_data[user_id].get('action', '') == 'findtokenopen':
        if current_step == 'token_ca':
            user_data[user_id]['token_ca'] = text
            user_data[user_id]['default_tokens'] = False
            await client.edit_message(event.chat_id, user_data[user_id]['msg_id'], buttons=get_first_menu(user_id))
    
    

async def main():
    await set_bot_commands()
    await client.run_until_disconnected()
    
if __name__ == '__main__':
    print("Bot is running...")
    # find_transaction('1','DrPTyHhkYmTaz4JqjRbNnhfb9NFN4fU8h6QfC4ATS8GD','2024-06-19 18:50:23','2024-06-19 21:56:23', 'asc', False)
    client.loop.run_until_complete(main())