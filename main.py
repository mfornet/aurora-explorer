"""
All data is saved in an sqlite database
"""
import io
from dotmap import DotMap
from flask import Flask
import base64
import hashlib
import json
import os
import pickle
import psycopg2
import requests
import rlp
from functools import partial


QUERY = """
SELECT public.receipts.receipt_id, public.receipts.originated_from_transaction_hash, public.action_receipt_actions.index_in_action_receipt, public.action_receipt_actions.action_kind, public.action_receipt_actions.args
FROM public.receipts
JOIN public.action_receipt_actions
ON public.action_receipt_actions.receipt_id = public.receipts.receipt_id
where
receiver_account_id = 'aurora'
"""


FOLDER = '.cache'

URL = "https://archival-rpc.mainnet.near.org/"
os.makedirs(FOLDER, exist_ok=True)

BODY = """
<!doctype html>
<html lang="en">
  <head>
    <!-- Required meta tags -->
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">

    <!-- Bootstrap CSS -->
    <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css" integrity="sha384-Gn5384xqQ1aoWXA+058RXPxPg6fy4IWvTNh0E263XmFcJlSAwiGgFAW/dAiS6JXm" crossorigin="anonymous">

    <title>Hello, world!</title>
  </head>
  <body>

    {}

    <!-- Optional JavaScript -->
    <!-- jQuery first, then Popper.js, then Bootstrap JS -->
    <script src="https://code.jquery.com/jquery-3.2.1.slim.min.js" integrity="sha384-KJ3o2DKtIkvYIK3UENzmM7KCkRr/rE9/Qpg6aAZGJwFDMVNA/GpGFF93hXpG5KkN" crossorigin="anonymous"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/popper.js/1.12.9/umd/popper.min.js" integrity="sha384-ApNbgh9B+Y1QKtv3Rn7W3mgPxhU9K/ScQsAP7hUibX39j7fakFPskvXusvfa0b4Q" crossorigin="anonymous"></script>
    <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/js/bootstrap.min.js" integrity="sha384-JZR6Spejh4U02d8jOt6vLEHfe/JQGiRRSQQxSfFWpi1MquVdAyjUar5+76PVCmYl" crossorigin="anonymous"></script>
  </body>
</html>
""".format


def cache(function):
    """
    Cache the result of a function in disk
    """
    def modified(*args):
        args_id = hashlib.sha256(str(args).encode()).hexdigest()[:16]
        name = str(function.__name__) + '.' + args_id + '.pickle'
        path = os.path.join(FOLDER, name)
        if os.path.exists(path):
            with open(path, 'rb') as f:
                data = pickle.load(f)
                return data
        else:
            data = function(*args)
            with open(path, 'wb') as f:
                pickle.dump(data, f)
            return data
    return modified


@cache
def get_receipt(receipt_id):
    """
    Get a receipt data from the RPC (each query is done only one time)
    """
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": "dontcare",
        "method": "EXPERIMENTAL_receipt",
        "params": {
            "receipt_id": receipt_id
        }
    })
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request("POST", URL, headers=headers, data=payload)
    return response.json()


@cache
def get_tx(tx_id):
    """
    Get a Transaction data from the RPC (each query is done only one time)
    """
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": "dontcare",
        "method": "tx",
        "params":  [tx_id, "dontcare"]
    })
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request("POST", URL, headers=headers, data=payload)
    return response.json()


app = Flask(__name__)


def decode_uint(ser):
    """
    Convert bytes to int
    """
    res = 0
    for v in ser:
        res = res * 256 + v
    return res


def flatten(dic, prefix=''):
    res = {}
    for key, value in dic.items():
        if isinstance(value, dict):
            if prefix != '':
                n_prefix = prefix + '_' + key
            else:
                n_prefix = key

            cur = flatten(value, n_prefix)
            res.update(cur)
        else:
            res[key] = value

    return res


def parse_info(data: bytes):
    # TODO: Use proper rlp deserialization
    _data = rlp.decode(data)

    nonce = decode_uint(_data[0])
    gas_price = decode_uint(_data[1])
    gas = decode_uint(_data[2])

    if len(_data[3]) == 0:
        # Deploy transaction
        to = None
    elif len(_data[3]) == 20:
        # Call transaction
        to = '0x' + _data[3].hex()
    else:
        raise ValueError(f'Invalid rlp (to): {_data[3].hex()}')

    value = decode_uint(_data[4])
    data = _data[5]

    v = decode_uint(_data[6])
    r = _data[7]
    s = _data[8]

    # TODO: Recover the sender using ecrecover

    return {
        'sender': 'TODO',
        'nonce': nonce,
        'gas_price': gas_price,
        'gas': gas,
        'to': to,
        'value': value,
        'data': data,
        'signature': {
            'v': v,
            'r': r,
            's': s
        }
    }


def update(record):
    """
    Convert a database ra
    """
    receipt_id, tx_id, _, action_kind, args = record

    if action_kind != 'FUNCTION_CALL':
        # TODO: Show a row for every record
        return None

    transaction = get_tx(tx_id)
    transaction = DotMap(transaction)

    tx_outcome = None

    for outcome in transaction.result.receipts_outcome:
        if outcome.id == receipt_id:
            tx_outcome = outcome
            break

    success_receipt_id = None
    success_value = None

    if 'SuccessValue' in tx_outcome.outcome.status:
        success_value = tx_outcome.outcome.status.SuccessValue
        success_value = '0x' + base64.b64decode(success_value.encode()).hex()

    if 'SuccessReceiptId' in tx_outcome.outcome.status:
        success_receipt_id = tx_outcome.outcome.status.SuccessReceiptId

    input = base64.b64decode(args['args_base64'].encode())

    if args['method_name'] == 'submit':
        input = parse_info(input)
    else:
        input = input.hex()

    return {
        'receipt_id': receipt_id,
        'tx_id': tx_id,
        'near_gas': args['gas'],
        'near_deposit': args['deposit'],
        'input': input,
        'method': args['method_name'],
        'success_value': success_value,
        'success_receipt_id': success_receipt_id,
    }

# Main functions


async def fetch_data():
    """
    This function downloads all records from the indexer and updates sqlite database
    It should only fetch data starting from the last downloaded data
    """
    conn = psycopg2.connect(database='mainnet_explorer',
                            user='public_readonly', password='nearprotocol', host='104.199.89.51')
    cur = conn.cursor()
    cur.execute(QUERY)
    records = cur.fetchall()
    return records


def create_table(data):
    """
    Return rows with all the data
    """
    keys = ['#']

    rows = []
    for row in map(update, data):
        if row is None:
            continue
        row = flatten(row)

        for key in row:
            if key not in keys:
                keys.append(key)

        rows.append(row)

    table = [keys]

    for ix, row in enumerate(rows):
        n_row = [None] * len(keys)
        n_row[0] = ix

        for key, value in row.items():
            index = keys.index(key)
            n_row[index] = value

        table.append(n_row)

    return table


def proc(index, value, head_row, value_row):
    if value is None:
        value = '-'

    if isinstance(value, bytes):
        value = value.hex()

    value = str(value)

    if head_row[index] == 'near_deposit':
        near = int(value)
        if near == 0:
            value = '0'
        elif near >= 10**21:
            value = f'{round(near / 10**24, 3)}N'
        else:
            value = value + 'yoctoN'

    if head_row[index] == 'near_gas':
        value = round(int(value) / 10**12)
        value = f'{value}TGas'

    if len(value) > 42:
        value = f'<p data-toggle="tooltip" title="{value}">{value[:39]}...</p>'

    if head_row[index] in ('#', 'tx_id'):
        pos = head_row.index('tx_id')
        tx_id = value_row[pos]
        value = f'<a href=https://explorer.mainnet.near.org/transactions/{tx_id}>{value}</a>'

    return value


def display_table(table):
    """
    Render the table
    """
    from pprint import pprint

    buffer = io.StringIO()
    cout = partial(print, file=buffer)

    cout('<tt>')
    cout('<table class="table table-striped">')
    cout('<thead>')
    cout('<tr>')
    for value in table[0]:
        cout(f'<th scope="col">{value}</th>')
    cout('</tr>')
    cout('</thead>')
    cout('<tbody>')
    for row in table[1:]:
        cout('<tr>')
        for ix, value in enumerate(row):
            cout(f'<th scope="col">{proc(ix, value, table[0], row)}</th>')
        cout('</tr>')
    cout('</tbody>')
    cout('</table>')
    cout('</tt>')

    return BODY(buffer.getvalue())


@app.route('/')
async def home():
    """
    Render webpage
    """
    # Fetch the data
    data = await fetch_data()
    # Preprocess the data
    table = create_table(data)
    # Render the data
    return display_table(table)
