# -*- coding: utf-8 -*-
"""
版本：1.0.0.1
作者：ifind 时间：20250619
文档介绍：iFinD Python订阅接口程序。可单独使用
版权：同花顺iFinD
"""

import threading
import json
import logging
import random
import requests
import websocket
from typing import Callable, Optional

logging.basicConfig(level=logging.INFO)

class iFinDPushDataClient:
    """
    WebSocket 推送客户端封装
    支持订阅回调，将服务器 push 数据通过回调传递给调用方（JSON 字符串）。
    """
    def __init__(
        self,
        url: str,
        token: str,
        hb_min: int = 10,
        hb_max: int = 30,
        ping_timeout: int = 10
    ):
        self.url = url
        self.token = token
        self.hb_min = hb_min
        self.hb_max = hb_max
        self.ping_timeout = ping_timeout

        self._ws_app: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None

        # 同步连接结果
        self._conn_event = threading.Event()
        self._conn_code: int = -1

        self._lock = threading.Lock()
        self._callback: Optional[Callable[[str], None]] = None

    def connect(self, timeout: int = 10) -> int:
        """
        建立 WebSocket 连接并启动 ping 心跳
        等待首次返回包含 connId 或 code 的 JSON 后返回 0
        若超时未收到，返回 -1。
        """
        # 拼接鉴权参数到 URL
        connect_url = (
            f"{self.url}?jgbsessid={self.token}"
            "&userid=default&user=default&ticket=default"
            "&tag=BROKER_QUOTATION&service=dsApi"
            "&extra_info=%7B%22businessTag%22%3A%22BROKER_QUOTATION%22%7D"
        )
        logging.info(f"Connecting to {connect_url}")

        # 创建 WebSocketApp
        self._ws_app = websocket.WebSocketApp(
            connect_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )

        # 随机心跳间隔
        interval = random.uniform(self.hb_min, self.hb_max)
        logging.info(
            f"心跳: ping_interval={interval:.1f}s, ping_timeout={self.ping_timeout}s"
        )

        # 重置连接状态
        self._conn_event.clear()
        self._conn_code = -1

        # 启动 WebSocket 线程
        self._ws_thread = threading.Thread(
            target=self._ws_app.run_forever,
            kwargs={'ping_interval': interval, 'ping_timeout': self.ping_timeout},
            daemon=True
        )
        self._ws_thread.start()

        # 等待首次连接确认
        if not self._conn_event.wait(timeout):
            logging.error("连接结果超时，未收到服务器返回")
            return -1
        logging.info(f"连接结果，code={self._conn_code}")
        return self._conn_code

    def subscription(
        self,
        brokers,
        codes,
        indicators,
        mode: str = "add",
        callback: Optional[Callable[[str], None]] = None
    ):
        """
        Add / Update
        :param brokers: list 或逗号分隔字符串
        :param codes: list 或逗号分隔字符串
        :param indicators: list 或分号分隔字符串
        :param mode: "add" 或 "update"
        :param callback: 接收 push 数据的回调函数，callback(json_str: str)
        """
        if mode not in ("add", "update"):
            raise ValueError("mode 必须是 'add' 或 'update'")

        # 统一处理参数
        brokers = _normalize_list(brokers, ',', 'brokers')
        codes = _normalize_list(codes, ',', 'codes')
        indicators = _normalize_list(indicators, ';', 'indicators')

        # 更新本地状态与回调
        with self._lock:
            self._current_params = {
                'brokers': brokers,
                'codes': codes,
                'indicators': indicators
            }
            if callback:
                self._callback = callback

        # 发送订阅/更新
        self._send(build_request_content(brokers,codes,indicators,mode))

    def unsubscribe(self):
        """取消订阅并清理状态"""
        with self._lock:
            self._current_params.clear()
            self._callback = None
        self._send(build_request_content([], [], [], 'cancel'))

    def close(self):
        """主动关闭连接并等待线程结束"""
        if self._ws_app:
            self._ws_app.close()
        if self._ws_thread:
            self._ws_thread.join(timeout=2)

    # WebSocket 回调
    def _on_open(self, ws):
        logging.info("已连接")

    def _on_message(self, ws, message: str):
        """
        处理服务器消息：
         - 首次包含 connId 字段的消息用于连接结果
         - 其它消息用于回调
        """
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        # 首次连接结果
        if not self._conn_event.is_set() and 'connId' in data:
            self._conn_code = 0
            self._conn_event.set()
            return

        # 推送数据
        if self._callback:
            try:
                self._callback(message)
            except Exception as e:
                logging.error(f"Push callback error: {e}")
        else:
            # 没有设置自定义回调函数 直接打印结果
            print(message)

    def _on_error(self, ws, err):
        if self._conn_code != 0 :
            self._conn_event.set()
        logging.error(f"Error: {err}")

    def _on_close(self, ws, code, reason):
        logging.warning(f"Closed: code={code}, reason={reason}")
        try:
            num = int(reason)
            self._conn_code = num
        except (TypeError, ValueError):
            self._conn_code = -1000
        if not self._conn_event.is_set():
            self._conn_event.set()

    def _send(self, body: str):
        if self._conn_code != 0 or not self._ws_app or not getattr(self._ws_app, 'sock', None) or not self._ws_app.sock.connected:
            raise ConnectionError("尚未连接或已断开")
        self._ws_app.send(body)
        logging.debug(f"Sent: {body}")


def _normalize_list(val, delimiter: str, name: str) -> list:
    """
    Normalize input to list of str, 支持 list/tuple 或 分隔字符串
    """
    if isinstance(val, str):
        items = [s.strip() for s in val.split(delimiter)]
    elif isinstance(val, (list, tuple)):
        items = val
    else:
        raise TypeError(f"{name} 必须为 list, tuple, 或 {delimiter} 分隔字符串")

    res = [s for s in items if isinstance(s, str) and s]
    return res
    
def build_request_content(brokers, codes, indicators, mode="add"):
    """
    构造订阅请求体
    """
    con_dict = {
        "brokers": brokers,
        "indicators": indicators,
        "codes": codes
    }
    con_json = json.dumps(con_dict)
    con_str  = con_json.replace('"', "'")

    if('cancel' == mode):
        inner = {
        "businessTag": "BROKER_QUOTATION",
        "operate": mode,
        "source":"client"
        }
    else:
        inner = {
        "businessTag": "BROKER_QUOTATION",
        "content": con_str,
        "operate": mode,
        "source":"client"
    }

    inner_str = json.dumps(inner, separators=(',',':'))

    reqContent = {
        "service": "dsApi",
        "request": inner_str
    }
    
    reqContent = json.dumps(reqContent, separators=(',',':'))
    return reqContent

# client
client: Optional[iFinDPushDataClient] = None

def THS_BondBrokerConnect(refresh_token: str) -> int:
    """
    初始化并连接推送客户端，返回服务器返回的 code，超时返回 -1。
    连接超时设为10s
    """
    try:
        resp = requests.post(
            'https://quantapi.51ifind.com/api/v1/get_access_token',
            headers={
                'Content-Type': 'application/json',
                'refresh_token': refresh_token
            }
        )
        data = resp.json().get('data', {})
        token = data.get('access_token')
        global client
        if client is None:
            client = iFinDPushDataClient(
                # url='wss://testwsft.51ifind.com:8443/ws',
                # url='ws://test-open-server.51ifind.com/ws',
                url='ws://ws.51ifind.com/ws',
                token=token
            )
        return client.connect()
    except Exception as e:
        logging.error(f"Connect error: {e}")
        return -1


def THS_BondBrokerSubscribe(
    brokers,
    codes,
    indicators,
    mode: str = 'add',
    callback: Optional[Callable[[str], None]] = None
):
    """
    订阅接口，支持传入回调
    :param callback: push数据回调函数，callback(json_str: str)
    """
    if client is None:
        raise RuntimeError("请先调用 THS_BondBrokerConnect() 初始化连接")
    client.subscription(brokers, codes, indicators, mode, callback)


def THS_BondBrokerUnsubscribe():
    if client is None:
        raise RuntimeError("请先调用 THS_BondBrokerConnect() 初始化连接")
    client.unsubscribe()
    client.close()

