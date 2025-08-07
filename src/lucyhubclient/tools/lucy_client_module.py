import json
from ..sound import SoundManager

class LucyClientModule:

    websocket_client = None
    lucy_webview = None
    sound_manager: SoundManager = None

    def __init__(self, name):
        self.name = name

    def get_lucy_webview(self):
        return self.lucy_webview
    
    async def handle_message(self, message):
        """
        Handle incoming messages from the Lucy Server.
        This method should be overridden by subclasses to implement specific behavior.
        """
        raise NotImplementedError("Subclasses must implement handle_message method.")
    
    async def send_socket_message(self, data):
        await self.websocket_client.send_tool_message(self.name, data)

    def log(self, message):
        print(f"[{self.name.upper()} CLIENT] {message}")