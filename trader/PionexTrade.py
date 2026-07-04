import os
import time
import hmac
import hashlib
import json
import requests
from urllib.parse import urlencode
from dotenv import load_dotenv
from datetime import datetime, timezone


load_dotenv()

MIN_NOMINAL_VALUE = 20 #minimum trades on the pair applied. if the pair need 20U notional to execute, anything less will not execute and appear "0" in the trade history details.

class PionexAccount:
    def __init__(self, debug=False):
        self.api_key = os.getenv("PIONEX_API_KEY")
        self.api_secret = os.getenv("PIONEX_API_SECRET")
        self.base_url = "https://api.pionex.com"
        self.debug = debug

        if not self.api_key and not self.api_secret:
            raise ValueError("E: Missing API KEY or API SECRET")
    
    def _timestamp(self):
        return int(time.time()*1000)
    
    def _sign(self, method, path, query_string="", body=""):
        payload = method.upper() + path

        if query_string:
            payload += "?" + query_string
        
        if body:
            payload += body

        return hmac.new(
            self.api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    
    def _request(self, method, path, params=None, body=None):
        if params is None:
            params = {}

        params["timestamp"] = self._timestamp()
        query_string = urlencode(sorted(params.items()))

        body_str = ""
        if body is not None:
            body_str = json.dumps(body, separators=(",", ":"))
        
        signature = self._sign(method, path, query_string, body_str)

        headers = {
            "PIONEX-KEY": self.api_key,
            "PIONEX-SIGNATURE": signature,
            "Content-Type": "application/json",
            "Accept": "*/*",
        }


        url = self.base_url + path + "?" + query_string

        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            data = body_str if body is not None else None,
            timeout=10,
        )

        if not resp.ok:
            print("[HTTP ERROR BODY]", resp.status_code, resp.text, flush=True)

        

        resp.raise_for_status()

        if self.debug:
            print(resp.status_code, resp.text)

        return resp.json()

    def get_balances(self):
        return self._request("GET", "/uapi/v1/account/balances")
    
    def get_positions(self, symbol=None):
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/uapi/v1/account/positions", params=params)
    
    def get_account_detail(self):
        return self._request("GET", "/uapi/v1/account/detail")
    
    def get_leverage(self, symbol="BTC_USDT_PERP"):
        return self._request(
            "GET",
            "/uapi/v1/account/leverage",
            params={"symbol": symbol},
        )
    
    def get_position_mode(self):
        return self._request("GET", "/uapi/v1/account/positionMode")
    

    def set_leverage(self, symbol: str, leverage: str):
        body = {
            "symbol": symbol,
            "leverage": str(leverage),
        }

        return self._request(
            "POST",
            "/uapi/v1/account/leverage",
            body=body,
        )
    
    def send_signal_webhook(self, bot_name, payload, trade_symbol="BTCUSDT.P"):
        """
        Need to write a function to get latest close price to make it more accurate.
        """
        bot_web_hook = bot_name.upper() + "_BOT_WEBHOOK"
        bot_signal_type = bot_name.upper() + "_BOT_SIGNAL_TYPE"

        webhook = os.getenv(bot_web_hook)
        signal_type = os.getenv(bot_signal_type)
        
        if (webhook is None) or (signal_type is None):
            raise ValueError(f"E: Bot webhook variable {bot_web_hook} or signal type variable {bot_signal_type} not found in environment please check the spell and the value in the environment.")
        
        payload = payload.copy()
        payload["signal_type"] = signal_type
        payload["symbol"] = trade_symbol

        body = json.dumps(payload, separators=(",", ":"))


        r = requests.post(
            webhook,
            data = body,
            headers={
                "Content-Type": "text/plain"
            },
            timeout=10,
        )

        return (r.status_code, r.text)
        

if __name__ == "__main__":
    trader = PionexAccount()

    # print("Details:")
    # print(trader.get_account_detail())

    # print("balances:")
    # print(trader.get_balances())

    # print("positions:")
    # print(trader.get_positions())

    # print("leverage:")
    # print(trader.get_leverage("BTC_USDT_PERP"))

    # print("position mode:")
    # print(trader.get_position_mode())

    # print("Set Leverage: ")
    # print(trader.set_leverage(
    #     symbol="BTC_USDT_PERP",
    #     leverage="1",
    # ))

    # buy 7% of the asset
    payload = payload = {

        "data": {
            "action": "buy",
            "contracts": f"{7/62000}",
            "position_size": f"{7/62000}",
        },
        "price": "61800",
        "signal_param":"{}",
        "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    trader.send_signal_webhook(bot_name = "Hypothesis", payload = payload)