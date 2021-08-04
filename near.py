from cache import cache
import requests
import json

URL = "https://archival-rpc.mainnet.near.org/"


@cache
def receipt(receipt_id):
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
def tx(tx_id):
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


@cache
def block(block_id):
    """
    Get a Block data from the RPC (each query is done only one time)
    """
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": "dontcare",
        "method": "block",
        "params":  {"block_id": block_id}
    })
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request("POST", URL, headers=headers, data=payload)
    return response.json()
