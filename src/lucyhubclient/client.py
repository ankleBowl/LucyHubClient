import websockets
import json
import asyncio

class LucyWebSocketClient:
    def __init__(self, url, on_reconnect, on_disconnect, on_message):
        self.url = url
        self.close_websocket = False
        self.is_closed = False

        self.on_reconnect = on_reconnect
        self.on_disconnect = on_disconnect
        self.on_message = on_message

    async def connect(self):
        asyncio.create_task(self._internal_loop())

    async def _internal_loop(self):
        is_first_disconnect = True
        self.close_websocket = False

        self.websocket = None

        url = f'{self.url}/v1/ws/meewhee'

        async for websocket in websockets.connect(url):
            try:
                if self.close_websocket:
                    break

                await websocket.send(json.dumps({"type": "auth"}))
                await websocket.recv()

                self.websocket = websocket

                await self.on_reconnect()

                while True:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                        message = json.loads(message)
                        await self.on_message(message)
                    except asyncio.TimeoutError:
                        if self.close_websocket:
                            break
            except Exception as e:
                print(f"[WebSocket] Connection error: {e}")
                self.websocket = None
                if is_first_disconnect:
                    await self.on_disconnect()
                    is_first_disconnect = False
                if self.close_websocket:
                    print("[WebSocket] Closing connection as requested.")
                    break

        self.is_closed = True

    async def close(self):
        self.close_websocket = True
        while not self.is_closed:
            await asyncio.sleep(0.1)

    async def send_request(self, request):
        if self.websocket is None:
            return
        data = {
            "type": "request",
            "message": request
        }
        await self.websocket.send(json.dumps(data))

    async def send_wake_word_trigger(self):
        if self.websocket is None:
            return
        data = {
            "type": "wake_word_detected"
        }
        await self.websocket.send(json.dumps(data))

    async def send_tool_message(self, tool_name, data):
        data = {
            "type": "tool_client_message",
            "tool": tool_name,
            "data": data
        }
        await self.websocket.send(json.dumps(data))