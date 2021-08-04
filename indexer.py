import psycopg2

QUERY = """
SELECT public.receipts.receipt_id, public.receipts.originated_from_transaction_hash, public.action_receipt_actions.action_kind, public.action_receipt_actions.args
FROM public.receipts
JOIN public.action_receipt_actions
ON public.action_receipt_actions.receipt_id = public.receipts.receipt_id
where
receiver_account_id = 'aurora'
"""


def fetch_data():
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
