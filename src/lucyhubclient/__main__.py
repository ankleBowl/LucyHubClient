import asyncio
import json
import socket
import qrcode

import signal
import threading
import time
import base64
import numpy as np
from importlib import resources

from .tools.lucy_client_module import LucyClientModule
from .tools.spotify import LSpotifyClient
from .tools.clock import LClockClient

from .sound import SoundManager, Sound, SpeechSound

from .socket_webview import SocketWebView

from .speech.detect_speech_provider.wake_word import DetectWakeWordProvider
from .speech import VoiceAssistant

from .client import LucyWebSocketClient

from .config import get_config, get_ws_url, start_flask_server, get_http_url

from rich.console import Console
from rich.theme import Theme
from rich.pretty import Pretty
import rich.traceback

rich.traceback.install()

custom_theme = Theme({
    "system": "cyan",
    "audio": "magenta",
    "websocket": "blue",
    "webview": "green",
})

console = Console(theme=custom_theme)

lucy_webview = None
va = None
websocket_client = None

sound_manager = None
speech_sound = None

main_loop_asyncio = None

is_in_request = True

client_modules = {}

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't need to be reachable, just forces routing table use
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()

def get_qr_code_base64():
    local_ip = get_local_ip()
    qr_img = qrcode.make(f"http://{local_ip}:4812")
    import base64
    from io import BytesIO
    buffer = BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return qr_base64

async def on_user_start_speaking():
    await websocket_client.send_wake_word_trigger()

    sound = Sound.from_name("wake")
    sound_manager.add_sound(sound)

    await lucy_webview.set_volume(0)
    sound_manager.set_volume(0.1)
    await lucy_webview.set_state("listening")
    console.print("User started speaking. Wake word detected.", style="audio")

async def on_user_end_speaking(transcription):
    await lucy_webview.set_volume(0.5)
    sound_manager.set_volume(1.0)

    if transcription is None:
        await lucy_webview.set_state("idle")
    else:
        sound = Sound.from_name("acknowledge")
        sound_manager.add_sound(sound)

        await lucy_webview.set_state("thinking")
        console.print(f"Sending transcription: {transcription}", style="websocket")
        await websocket_client.send_request(transcription)

async def on_assistant_start_speaking():
    await lucy_webview.set_state("speaking")
    await lucy_webview.set_volume(0.1)
    sound_manager.set_volume(0.1)

def on_assistant_end_speaking():
    sound_manager.set_volume(1.0)

    async def update_state():
        await lucy_webview.set_volume(0.5)
        await lucy_webview.set_state("idle")
        
    asyncio.run_coroutine_threadsafe(update_state(), main_loop_asyncio) 

def on_assistant_speech_volume(data):
    amount_per_new_bin = len(data) // 5
    reduced_data = []
    for i in range(0, 5):
        start = i * amount_per_new_bin
        end = start + amount_per_new_bin
        if end > len(data):
            end = len(data)
        reduced_data.append(sum(data[start:end]) / (end - start))
    reduced_data = [max(min((x + 145) / 145, 1), 0) for x in reduced_data]
    
    async def update_visualizer():
        await lucy_webview.set_speaing_visualizer(reduced_data)

    asyncio.run_coroutine_threadsafe(update_visualizer(), main_loop_asyncio)
        
async def shutdown():
    console.print("Shutting down...", style="system")
    
    # if lucy_webview:
    #     console.print("Closing Lucy WebView...", style="webview")
    #     lucy_webview.close()
    #     console.print("Lucy WebView closed.", style="webview")
    # if va:
    #     console.print("Stopping Voice Assistant...", style="audio")
    #     va.stop()
    #     console.print("Voice Assistant stopped.", style="audio")
    # if sound_manager:
    #     console.print("Stopping Sound Manager...", style="audio")
    #     sound_manager.stop()
    #     console.print("Sound Manager stopped.", style="audio")

    # console.print("Closing WebSocket...", style="websocket")
    # await websocket_client.close()
    # console.print("WebSocket closed.", style="websocket")

async def on_reconnect():
    print("[WebSocket] Reconnected to server.")
    await lucy_webview.set_connected(True)
    await lucy_webview.set_state('idle')

async def on_disconnect():
    print("[WebSocket] Disconnected from server.")
    await lucy_webview.set_connected(False)
    await lucy_webview.set_state('not-ready')

async def on_message(message):
    global is_in_request, speech_sound

    if message["type"] == "tool":
        sound = Sound.from_name("use_tool")
        sound_manager.add_sound(sound)
    elif message["type"] == "assistant":
        sound = Sound.from_name("complete")
        sound_manager.add_sound(sound)

        await lucy_webview.set_volume(0.1)
        sound_manager.set_volume(0.1)
    elif message["type"] == "tool_message":
        if message["tool"] in client_modules:
            module = client_modules[message["tool"]]
            await module.handle_message(message["data"])
    elif message["type"] == "end":
        console.print("End of conversation detected.", style="system")
        is_in_request = False
    elif message["type"] == "speech_start":
        await on_assistant_start_speaking()
    elif message["type"] == "audio":
        base64_data = message["data"]
        audio_data = base64.b64decode(base64_data)
        audio_array = np.frombuffer(audio_data, dtype=np.float32)
        audio_array = (audio_array * 32767 * 32767).astype(np.int32)
        speech_sound.add_audio_data(audio_array)

async def app():
    global lucy_webview, va, main_loop_asyncio, is_in_request, websocket_client, sound_manager, speech_sound

    main_loop_asyncio = asyncio.get_event_loop()

    console.print("Starting Flask Config Server...", style="system")
    start_flask_server()

    console.print("Starting Lucy WebView...", style="webview")
    lucy_webview = SocketWebView()
    lucy_webview.start_frontend_server()
    await lucy_webview.start()
    if args.open_ui:
        lucy_webview.open(args.browser_path)
    await lucy_webview.wait_for_connection()
    await lucy_webview.update_ip_qr(f"{get_local_ip()}:4812", get_qr_code_base64())    
    await lucy_webview.set_connected(False)
    
    if get_config()["type_mode"] == True:
        console.print("Starting Lucy WebView in Type Mode...", style="webview")
        def input_thread():
            global is_in_request

            while True:
                try:
                    if is_in_request:
                        time.sleep(0.1)
                        continue
                    is_in_request = True
                    transcription = input("Enter your message: ")
                    on_user_end_speaking(transcription.strip())
                except KeyboardInterrupt:
                    break
                except EOFError:
                    break

        input_thread = threading.Thread(target=input_thread, daemon=True)
        input_thread.start()
    else:
        console.print("Starting Voice Assistant...", style="audio")

        detect_speech_provider = DetectWakeWordProvider(wake_word_detection_callback=on_user_start_speaking)
        va = VoiceAssistant(detect_speech_provider, 
                            mic_list=get_config()["microphones"],
                            start_speaking_callback=None, 
                            end_speaking_callback=on_user_end_speaking)
        await va.run()

    console.print("Connecting to Lucy Server...", style="websocket")
    global websocket_client
    websocket_client = LucyWebSocketClient(
        get_ws_url(),
        on_reconnect=on_reconnect,
        on_disconnect=on_disconnect,
        on_message=on_message
    )
    await websocket_client.connect()

    console.print("Starting Sound Manager...", style="audio")
    sound_manager = SoundManager()

    console.print("Adding Speech Sound...", style="audio")
    speech_sound = SpeechSound(sample_rate=24000, volume_callback=on_assistant_speech_volume, done_speaking_callback=on_assistant_end_speaking)
    sound_manager.add_sound(speech_sound)

    console.print("Loading Client Modules...", style="system")
    LucyClientModule.websocket_client = websocket_client
    LucyClientModule.lucy_webview = lucy_webview
    LucyClientModule.sound_manager = sound_manager
    client_modules["spotify"] = LSpotifyClient()
    client_modules["clock"] = LClockClient()

    console.print("Setup Complete!", style="system")

    # keep thread alive
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--open-ui", action="store_true", help="Open the web UI automatically in the default browser")
    parser.add_argument("--browser-path", type=str, default="chrome", help="Path to the browser executable to open the web UI")
    args = parser.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    console.print("Starting LucyHubClient...", style="system")
    
    try:
        loop.run_until_complete(app())
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()