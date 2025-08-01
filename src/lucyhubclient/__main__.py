import asyncio
import websockets
import json

import signal
import os
import threading
import time
from importlib import resources

from .tools.lucy_client_module import LucyClientModule
from .tools.spotify import LSpotifyClient
from .tools.clock import LClockClient

from .sound import SoundManager, Sound

from .speech.detect_speech_provider.wake_word import DetectWakeWordProvider
from .speech.transcription_provider.parakeet import ParakeetTranscriptionProvider
from .speech.request_classifier.none import EmptyRequestClassifier
from .speech import VoiceAssistant

voice = None
lucy_webview = None
va = None
websocket = None
main_loop = None
sound_manager = SoundManager()

last_request_sent = None
is_in_request = True
ready = False
close_websocket = False

client_modules = {}

def play_sound(sound_name):
    if get_config()["quiet_mode"] == "True":
        return
    sound_path = resources.files("lucyhubclient.sounds").joinpath(f"{sound_name}.wav")
    sound = Sound.from_wav(sound_path)
    sound_manager.add_sound(sound)

async def receive_messages():
    global last_request_sent, is_in_request, close_websocket, websocket, ready

    while True:
        if close_websocket:
            break

        set_lucy_webview_state("not-ready")
            
        try:
            websocket = await connect_socket()
            set_lucy_webview_state("idle")
            ready = True
            LucyClientModule.websocket = websocket
        except Exception as e:
            print_colored_log(f"[ERROR] Failed to connect to WebSocket: {e}", "red")
            await asyncio.sleep(1)
            continue

        while True:
            try:
                # message = await websocket.recv()
                message = await asyncio.wait_for(websocket.recv(), timeout=0.1)

                message = json.loads(message)
                current_time = asyncio.get_event_loop().time()

                print_colored_log(f"[{(current_time - last_request_sent):.2f}s] [SERVER] {message}", "yellow")
                if message["type"] == "tool":
                    # print(f"Tool call: {message['data']}")
                    play_sound("use_tool")
                    continue
                elif message["type"] == "assistant":
                    play_sound("complete")
                    lucy_webview.set_volume(0.1)
                    sound_manager.set_volume(0.1)
                    voice.generate_blocking(message["data"])
                elif message["type"] == "tool_message":
                    if message["tool"] in client_modules:
                        module = client_modules[message["tool"]]
                        await module.handle_message(message["data"])
                    
                elif message["type"] == "end":
                    print_colored_log("[INFO] End of conversation detected.", "blue")
                    is_in_request = False
                    set_lucy_webview_state("idle")
            except asyncio.TimeoutError:
                if close_websocket:
                    break
            except websockets.ConnectionClosedOK:
                print("WebSocket connection closed normally.")
                close_websocket = True
                break
            except websockets.ConnectionClosedError as e:
                print(f"WebSocket connection closed with error: {e}")
                break

async def connect_socket():
    global ready

    url = f'{get_config()["urls"]["ws"]}/v1/ws/meewhee'
    websocket = await websockets.connect(url)
    data = {"type": "auth"}
    await websocket.send(json.dumps(data))
    await websocket.recv()

    return websocket

def on_user_start_speaking():
    async def send_wake_word():
        await websocket.send(json.dumps({"type": "wake_word_detected"}))
    asyncio.run_coroutine_threadsafe(send_wake_word(), main_loop)
    lucy_webview.set_volume(0)
    sound_manager.set_volume(0.1)
    play_sound("wake")
    set_lucy_webview_state("listening")
    print_colored_log("[INFO] User started speaking. Wake word detected.", "blue")

def on_user_end_speaking(transcription):
    async def send_request():
        global last_request_sent
        print_colored_log(f"[INFO] Sending transcription: {transcription}", "blue")
        await websocket.send(json.dumps({"type": "request", "message": transcription}))
        last_request_sent = asyncio.get_event_loop().time()

    lucy_webview.set_volume(0.5)
    sound_manager.set_volume(1.0)

    if transcription is None:
        set_lucy_webview_state("idle")
    else:
        play_sound("acknowledge")
        set_lucy_webview_state("thinking")
        asyncio.run_coroutine_threadsafe(send_request(), main_loop)

def on_assistant_start_speaking():
    set_lucy_webview_state("speaking")
    lucy_webview.set_volume(0.1)
    sound_manager.set_volume(0.1)
    pass

def on_assistant_end_speaking():
    lucy_webview.set_volume(0.5)
    sound_manager.set_volume(1.0)
    set_lucy_webview_state("idle")


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
    json_array = json.dumps(reduced_data)
    js_func = f"LucyHub.setSpeakingVisualizer({json_array});"
    # print_colored_log(f"[INFO] Sending JS function: {js_func}", "blue")
    lucy_webview.run_javascript(js_func)
        

async def shutdown():
    global va, voice, websocket, close_websocket

    print("Shutting down...")
    
    if va:
        print("[SYSTEM] Closing Voice Assistant...")
        va.stop()
        print("[SYSTEM] Voice Assistant closed.")
    if voice:
        print("[SYSTEM] Stopping Voice...")
        voice.stop()
        print("[SYSTEM] Voice stopped.")
    if sound_manager:
        print("[SYSTEM] Stopping Sound Manager...")
        sound_manager.stop()
        print("[SYSTEM] Sound Manager stopped.")

    print("[SYSTEM] Closing WebSocket...")
    if websocket != None:
        await websocket.close()
        await websocket.wait_closed()
    print("[SYSTEM] WebSocket closed.")

    # import threading

    # print("=== Active threads ===")
    # for t in threading.enumerate():
    #     print(f"Thread name: {t.name}, daemon: {t.daemon}, ident: {t.ident}")
    # print("======================")

    # import faulthandler
    # import sys

    # print("=== Dumping all thread stacks ===")
    # faulthandler.dump_traceback(file=sys.stdout, all_threads=True)
    # print("===============================")



def set_lucy_webview_state(state):
    lucy_webview.run_javascript(f"LucyHub.setState('{state}');")

async def app():
    global voice, lucy_webview, va, websocket, main_loop, is_in_request

    main_loop = asyncio.get_event_loop()

    print_colored_log("Connecting to WebSocket...", "blue")

    if get_config()["quiet_mode"] == False:
        print_colored_log("Starting Voice...", "blue")
        if get_config()["voice_system"] == "kokoro":
            from .voice.kokoro import KokoroVoice
            voice = KokoroVoice(speech_start_callback=on_assistant_start_speaking, speech_end_callback=on_assistant_end_speaking, speech_volume_callback=on_assistant_speech_volume)
        elif get_config()["voice_system"] == "elevenlabs":
            from .voice.elevenlabs import ElevenLabsAIVoice
            voice = ElevenLabsAIVoice(
                speech_start_callback=on_assistant_start_speaking, 
                speech_end_callback=on_assistant_end_speaking,
                speech_volume_callback=on_assistant_speech_volume,
                api_key=get_config()["elevenlabs_api_key"],
                # voice_id="lcMyyd2HUfFzxdCaC4Ta",
                voice_id="E393dkE75hqtz1LO2aEJ",
                cache_dir="./elevenlabs_cache"
            )
    else:
        from voice.quiet import QuietAIVoice
        voice = QuietAIVoice()
        print_colored_log("Quiet mode enabled. Skipping voice and microphone setup.", "yellow")

    if get_config()["type_mode"] == "True":
        def input_thread():
            global is_in_request, ready

            while not ready:
                time.sleep(0.1)

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
        print_colored_log("Starting Microphone...", "blue")

        detect_speech_provider = DetectWakeWordProvider(wake_word_detection_callback=on_user_start_speaking)
        transcription_provider = ParakeetTranscriptionProvider()
        request_classifier = EmptyRequestClassifier()
        va = VoiceAssistant(detect_speech_provider, 
                            transcription_provider,
                            request_classifier,
                            mic_list=get_config()["microphones"],
                            start_speaking_callback=None, 
                            end_speaking_callback=on_user_end_speaking)
        va.run()

    print_colored_log("Loading Client Modules...", "blue")
    LucyClientModule.lucy_webview = lucy_webview
    LucyClientModule.sound_manager = sound_manager
    client_modules["spotify"] = LSpotifyClient()
    client_modules["clock"] = LClockClient()

    print_colored_log("Setup Complete!", "green")

    is_in_request = False
    await receive_messages()

def print_colored_log(message, str_color):
    color_map = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
    }
    color = color_map.get(str_color, "\033[0m")  # Default to no color if not found
    reset_color = "\033[0m"
    print(f"{color}{message}{reset_color}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true", help="Run in development mode")
    args = parser.parse_args()

    from .config import get_config

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    print_colored_log("Starting Lucy WebView...", "blue")
    if get_config()["webview_type"] == "pywebview":
        from .lucywebview.pywebview import PyLucyWebView
        lucy_webview = PyLucyWebView(fullscreen=not args.dev)
    else:
        from .lucywebview.selenium import SeleniumLucyWebView
        lucy_webview = SeleniumLucyWebView(driver=get_config()["webview_type"], fullscreen=not args.dev)

    try:
        loop.run_until_complete(app())
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()