import json
from sound import SoundManager

class LucyClientModule:
    websocket = None
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
        wrapper = {
            "type": "tool_client_message",
            "tool": self.name,
            "data": data
        }
        await self.websocket.send(json.dumps(wrapper))


    def log(self, message):
        print(f"[{self.name.upper()} CLIENT] {message}")