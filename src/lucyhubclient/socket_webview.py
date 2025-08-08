import os
import websockets
import uuid
import asyncio
import json
import time

IS_MACOS = (os.uname().sysname == 'Darwin')

class SocketWebView:
    def __init__(self):
        self.client = None
        self.responses = {}

    def open(self, chrome_path, dev=False):
        if not IS_MACOS:
            command = f'{chrome_path} "http://localhost:4814/"'
        else:
            command = f'open -a "{chrome_path}" "http://localhost:4814/" --args'
        if not dev:
            command += ' --kiosk --disable-infobars'
        print(f"[WebView] Opening webview with command: {command}")
        os.system(f"{command} &")

    async def wait_for_connection(self):
        while self.client is None:
            await asyncio.sleep(0.1)

    async def _websocket_handler(self, websocket, path):
        self.client = websocket
        try:
            async for message in websocket:
                import json
                data = json.loads(message)
                if 'uuid' in data:
                    self.responses[data['uuid']] = data["result"]
        except:
            self.client = None

    async def start(self):
        self.server = await websockets.serve(self._websocket_handler, "localhost", 4813)

    async def set_state(self, state):
        js = f"LucyHub.setState('{state}');"
        await self.run_javascript(js, forget=True)

    async def update_ip_qr(self, ip_port, qr):
        await self.run_javascript(f"LucyHub.updateIPAndQR('{ip_port}', '{qr}');", forget=True)

    async def set_connected(self, connected: bool):
        js = f"LucyHub.setConnected({str(connected).lower()});"
        await self.run_javascript(js, forget=True)

    async def set_speaing_visualizer(self, bars):
        json_array = json.dumps(bars)
        js_func = f"LucyHub.setSpeakingVisualizer({json_array});"
        await self.run_javascript(js_func, forget=True)

    async def set_volume(self, volume: float):
        js = f"LucyHub.setVolume({volume});"
        await self.run_javascript(js, forget=True)

    async def wait_for_var(self, var_name, expected_value, timeout=5):
        start_time = time.time()
        while True:
            if self.client is None:
                return False
            js = f"{var_name};"
            result = await self.run_javascript(js)
            print(f"[WebView] wait_for_var: {var_name} = {result}, expecting {expected_value}")
            if result == expected_value:
                return True
            if time.time() - start_time > timeout:
                return False
            await asyncio.sleep(0.1)
        
    async def run_javascript(self, script, forget=False):
        if self.client is None:
            return
        this_uuid = str(uuid.uuid4())
        await self.client.send(json.dumps({
            "type": "run_javascript",
            "script": script,
            "forget": forget,
            "uuid": this_uuid
        }))

        if forget:
            return None
        
        while this_uuid not in self.responses:
            await asyncio.sleep(0.01)
        response = self.responses.pop(this_uuid)
        return response

    async def close(self):
        self.server.close()
        await self.server.wait_closed()

    def start_frontend_server(self):
        from flask import Flask
        import threading
        from importlib import resources

        app = Flask(__name__)

        import logging

        # Disable Flask's default logger
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        # Disable all other Flask logging if needed
        flask_log = logging.getLogger('flask.app')
        flask_log.setLevel(logging.CRITICAL)

        @app.route('/')
        def internal_ui():
            file = resources.files('lucyhubclient.templates') / 'index.html'
            with open(file, 'r') as f:
                return f.read()
            
        @app.route('/background.html')
        def background_html():
            file = resources.files('lucyhubclient.templates') / 'background.html'
            with open(file, 'r') as f:
                return f.read()
            
        def run_flask_app():
            app.run(host='127.0.0.1', port=4814)
            
        flask_thread = threading.Thread(target=run_flask_app)
        flask_thread.daemon = True
        flask_thread.start()
        