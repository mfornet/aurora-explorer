"""
All data is saved in an sqlite database
"""
import base64
from datetime import datetime

import humanize
import rlp
from dotmap import DotMap
from flask import Flask, render_template
from yattag import Doc

import indexer
import near
from cache import cache
from utils import decode_uint

app = Flask(__name__)


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


class EthTransaction:
    @staticmethod
    def parse(buffer):
        # TODO: Use proper rlp deserialization
        _data = rlp.decode(buffer)

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


class Proof:
    @staticmethod
    def parse(buffer):
        # TODO: Parse proof (This is for deposit)
        return buffer.hex()

# pub struct FinishDepositCallArgs {
#     pub new_owner_id: AccountId,
#     pub amount: Balance,
#     pub proof_key: String,
#     pub relayer_id: AccountId,
#     pub fee: Balance,
#     pub msg: Option<Vec<u8>>,
# }


class FinishDeposit:
    @staticmethod
    def parse(buffer):
        return buffer.hex()


# TODO: Use Json for this one
# pub struct NEP141FtOnTransferArgs {
#     pub sender_id: AccountId,
#     pub amount: Balance,
#     pub msg: String,
# }
class NEP141FtOnTransfer:
    @staticmethod
    def parse(buffer):
        return buffer.hex()

#         pub struct ResolveTransferCallArgs {
#     pub sender_id: AccountId,
#     pub amount: Balance,
#     pub receiver_id: AccountId,
# }


class ResolveTransferCallArgs:
    @staticmethod
    def parse(buffer):
        return buffer.hex()


class Dummy:
    @staticmethod
    def parse(buffer):
        return buffer.hex()


parse_with = {
    'submit': EthTransaction,
    'deposit': Proof,
    'finish_deposit': FinishDeposit,
    'ft_on_transfer': NEP141FtOnTransfer,
    'ft_resolve_transfer': ResolveTransferCallArgs,
    'get_nep141_from_erc20': Dummy,
    'call': Dummy,
    'deploy_erc20_token': Dummy,
    'new': Dummy,
    'ft_transfer': Dummy,
    'ft_transfer_call': Dummy,
    'withdraw': Dummy,
    'new_eth_connector': Dummy,
    'set_eth_connector_contract_data': Dummy,
    'ft_balance_of_eth': Dummy,
    'get_erc20_from_nep141': Dummy,
    'storage_deposit': Dummy
}


class Record:
    near_receipt_id = None
    near_tx_id = None
    near_block_hash = None
    near_action_kind = None
    near_gas_attached = None
    near_gas_burnt = None
    near_tokens_attached = None
    near_tokens_burnt = None
    near_method = None
    near_success_value = None
    near_success_receipt_id = None
    near_timestamp = None
    near_height = None
    input = None

    def __init__(self, receipt_id: str, tx_id: str, action_kind, args):
        from pprint import pprint
        ignore_action_kind = {'CREATE_ACCOUNT',
                              'TRANSFER', 'ADD_KEY', 'DEPLOY_CONTRACT'}

        self.near_receipt_id = receipt_id
        self.near_tx_id = tx_id
        self.near_action_kind = action_kind

        if action_kind == 'FUNCTION_CALL':
            args = DotMap(args)
            self.near_gas_attached = args.gas or None
            self.near_tokens_attached = args.deposit or None
            self.near_method = args.method_name or None

            transaction = near.tx(tx_id)
            transaction = DotMap(transaction)

            tx_outcome = None
            for outcome in transaction.result.receipts_outcome:
                if outcome.id == receipt_id:
                    tx_outcome = DotMap(outcome)
                    break

            self.near_gas_burnt = tx_outcome.outcome.gas_burnt
            self.near_tokens_burnt = int(tx_outcome.outcome.tokens_burnt)
            self.near_block_hash = tx_outcome.block_hash

            block = DotMap(near.block(tx_outcome.block_hash)).result
            self.near_timestamp = block.header.timestamp
            self.near_height = block.header.height

            success_value = None
            if 'SuccessValue' in tx_outcome.outcome.status:
                success_value = tx_outcome.outcome.status.SuccessValue
                success_value = '0x' + \
                    base64.b64decode(success_value.encode()).hex()
                self.near_success_value = success_value

            success_receipt_id = None
            if 'SuccessReceiptId' in tx_outcome.outcome.status:
                success_receipt_id = tx_outcome.outcome.status.SuccessReceiptId
                self.near_success_receipt_id = success_receipt_id

            input = base64.b64decode(args.args_base64.encode())

            if args.method_name in parse_with:
                cls = parse_with[args.method_name]
                input = cls.parse(input)
            else:
                print(input)
                raise NotImplementedError(f'Method name: {args.method_name}')

            self.input = input
        elif action_kind in ignore_action_kind:
            pass
        else:
            print(receipt_id, tx_id, action_kind)
            pprint(args)
            raise NotImplementedError(f'Action Kind: {action_kind}')

    def is_function_call(self):
        return self.near_action_kind == 'FUNCTION_CALL'


def compute_records(data):
    rows = []
    for row in data:
        record = Record(*row)
        # return
        if not record.is_function_call():
            continue
        rows.append(record)

    rows.sort(key=lambda x: (-x.near_timestamp, x.near_receipt_id))
    return rows


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


def to_near(amount):
    return f'{round(int(amount) / 10**24, 4)}N'


def render_table(records):
    """
    Render the table
    """
    doc, tag, text = Doc().tagtext()

    keys = ['Receipt Hash', 'Aurora Method',
            'Near Block', 'Near Time', 'Value', 'Fee']

    with tag('tt'):
        with tag('table', klass='table table-stripped'):
            with tag('thead'):
                with tag('tr'):
                    for key in keys:
                        with tag('th', scope='col'):
                            text(key)

            with tag('tbody'):
                for rec in records:
                    with tag('tr'):
                        # Receipt Hash
                        with tag('td'):
                            with tag('a', href=f'/r/{rec.near_receipt_id}/{rec.near_tx_id}'):
                                text(rec.near_receipt_id[:10]+'...')
                        with tag('td'):
                            text(rec.near_method)
                        with tag('td'):
                            with tag('a', href=f'https://explorer.near.org/blocks/{rec.near_block_hash}'):
                                text(rec.near_height)
                        with tag('td'):
                            moment = datetime.fromtimestamp(
                                rec.near_timestamp//10**9)
                            now = datetime.now()
                            text(humanize.naturaldelta(
                                now - moment, minimum_unit='seconds'))
                        with tag('td'):
                            text('0')
                        with tag('td'):
                            with tag('p', ('data-toggle', 'tooltip'), title=int(rec.near_tokens_burnt)):
                                text(to_near(rec.near_tokens_burnt))

    table_html = doc.getvalue()

    return render_template('template.html', title='Aurora Explorer', body=table_html)


@app.route('/r/<receipt_id>/<tx_id>')
def status(receipt_id, tx_id):
    receipt = DotMap(near.receipt(receipt_id))
    tx = DotMap(near.tx(tx_id))
    if 'error' in receipt or 'error' in tx:
        return {
            'receipt': receipt,
            'tx': tx
        }

    receipt = receipt.result
    tx = tx.result

    tx_outcome = None
    for outcome in tx.receipts_outcome:
        if outcome.id == receipt_id:
            tx_outcome = DotMap(outcome)
            break

    block = DotMap(near.block(tx_outcome.block_hash))
    if 'error' in block:
        return {
            'receipt': receipt,
            'tx': tx,
            'block': block,
        }
    block = block.result
    doc, tag, text = Doc().tagtext()

    action_kind = list(receipt.receipt.Action.actions[0].keys())[0]
    args = receipt.receipt.Action.actions[0][action_kind]

    if action_kind == 'FunctionCall':
        method_name = args.method_name
    else:
        method_name = None

    if method_name in parse_with:
        input_raw = base64.b64decode(args.args.encode())
        input = parse_with[method_name].parse(input_raw)
    else:
        input_raw = None
        input = None

    with tag('tt'):
        with tag('a', href='/', klass='center'):
            text('<-- Aurora Explorer')

        with tag('table', klass='table table-stripped'):
            with tag('tbody'):
                with tag('tr'):
                    with tag('td'):
                        text('Receipt Hash')
                    with tag('td'):
                        with tag('a', href=f'https://explorer.near.org/transactions/{tx_id}#{receipt_id}'):
                            text(receipt_id)

                with tag('tr'):
                    with tag('td'):
                        text('Block')
                    with tag('td'):
                        with tag('a', href=f'https://explorer.near.org/block/{block.header.hash}'):
                            text(block.header.height)
                            text(receipt_id)

                with tag('tr'):
                    with tag('td'):
                        text('Timestamp')
                    with tag('td'):
                        moment = datetime.fromtimestamp(
                            block.header.timestamp//10**9)
                        now = datetime.now()
                        text(
                            f'{humanize.naturaldelta(now - moment)} ago ({humanize.naturalday(moment)})')

                with tag('tr'):
                    with tag('td'):
                        text('Tx Fee (NEAR)')
                    with tag('td'):
                        text(to_near(tx_outcome.outcome.tokens_burnt))

                if method_name == 'submit':
                    input = DotMap(input)
                    with tag('tr'):
                        with tag('td'):
                            text('From')
                        with tag('td'):
                            text(input.sender)

                    with tag('tr'):
                        with tag('td'):
                            text('To')
                        with tag('td'):
                            text(input.to)

                    with tag('tr'):
                        with tag('td'):
                            text('Value')
                        with tag('td'):
                            text(input.value)

                    with tag('tr'):
                        with tag('td'):
                            text('Gas Price (Aurora)')
                        with tag('td'):
                            text(input.gas_price)

                    with tag('tr'):
                        with tag('td'):
                            text('Gas Used (Aurora)')
                        with tag('td'):
                            text(input.gas)

                    with tag('tr'):
                        with tag('td'):
                            text('Nonce')
                        with tag('td'):
                            text(input.nonce)

                    with tag('tr'):
                        with tag('td'):
                            text('Data')
                        with tag('td'):
                            text(input.data.hex())

                else:
                    with tag('tr'):
                        with tag('td'):
                            text('Input Data')
                        with tag('td'):
                            text(input_raw.hex())

                # if method_name == 'submit':
                #     with tag('tr'):
                #         with tag('td'):
                #             text('Input')
                #         with tag('td'):
                #             text(str(input))

    table_html = doc.getvalue()
    return render_template('template.html', title='Aurora Explorer', body=table_html)


@ app.route('/')
def home():
    """
    Render webpage
    """
    # Fetch the data
    data = indexer.fetch_data()
    # Preprocess the data
    table = compute_records(data)
    # Render the data
    return render_table(table)


@ cache
def get_data():
    return indexer.fetch_data()


def main():
    data = get_data()
    table = compute_records(data)
    result = render_table(table)
    print(result)


if __name__ == '__main__':
    main()
