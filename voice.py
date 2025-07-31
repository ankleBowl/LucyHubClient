from kokoro import KPipeline
import pyaudio
import numpy as np
from multiprocessing import Queue, Process, Value
from queue import Empty
import threading
import time

from pydub import AudioSegment
from pydub.playback import play as pydub_play
from io import BytesIO

def decompress_mp3(mp3_bytes):
    try:
        audio = AudioSegment.from_file(BytesIO(mp3_bytes), format="mp3")
        return audio
    except Exception as e:
        print(f"Error decompressing MP3: {e}")
        return None


class AIVoice:
    def __init__(self):
        pass

    def stop(self):
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def generate(self, text):
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def generate_blocking(self, text):
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def wait_until_ready(self):
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def stop_speaking(self):
        raise NotImplementedError("This method should be implemented by subclasses.")
    
class QuietAIVoice(AIVoice):
    def __init__(self):
        self.is_ready = Value('b', True)

    def stop(self):
        pass

    def generate(self, text):
        pass

    def generate_blocking(self, text):
        pass

    def wait_until_ready(self):
        pass

    def stop_speaking(self):
        pass

class ElevenLabsAIVoice(AIVoice):
    def is_installed(self, lib_name: str) -> bool:
        import shutil

        lib = shutil.which(lib_name)
        if lib is None:
            return False
        return True

    def __init__(self, speech_start_callback, speech_end_callback, speech_volume_callback, api_key, voice_id, cache_dir=None):
        from elevenlabs.client import ElevenLabs
        self.client = ElevenLabs(api_key=api_key)
        self.dialogueQ = Queue()

        self.is_stopping = False

        self.is_done_speaking = True
        self.mpv_process = None
        self.cache_dir = cache_dir

        self.speech_start_callback = speech_start_callback
        self.speech_end_callback = speech_end_callback
        self.speech_volume_callback = speech_volume_callback

        self.model_id = "eleven_multilingual_v2"
        self.voice_id = voice_id

        self.stream_thread = threading.Thread(target=self._playback_thread)
        self.stream_thread.start()


        if not self.is_installed("mpv"):
            message = (
                "mpv not found, necessary to stream audio. "
                "On mac you can install it with 'brew install mpv'. "
                "On linux and windows you can install it from https://mpv.io/"
            )
            raise ValueError(message)

    def _playback_thread(self):
        import subprocess
        import threading
        import time
        import pyaudio
        from queue import Empty

        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, output=True)

        while True:
            if self.is_stopping:
                break

            try:
                text = self.dialogueQ.get(timeout=0.1)
            except Empty:
                time.sleep(0.05)
                continue

            self.is_done_speaking = False
            threading.Thread(target=self.speech_start_callback).start()

            audio_stream = self.client.text_to_speech.stream(
                text=text,
                voice_id=self.voice_id,
                model_id=self.model_id,
            )

            # Start ffmpeg process for decoding mp3 to pcm s16le mono 44.1kHz
            ffmpeg_proc = subprocess.Popen(
                [
                    'ffmpeg',
                    '-hide_banner',
                    '-loglevel', 'error',
                    '-i', 'pipe:0',          # input from stdin
                    '-f', 's16le',           # raw PCM 16-bit little endian
                    '-acodec', 'pcm_s16le',  # PCM codec
                    '-ac', '1',              # 1 channel (mono)
                    '-ar', '44100',          # sample rate
                    'pipe:1'                 # output to stdout
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0
            )

            for chunk in audio_stream:
                if chunk is None:
                    continue
                ffmpeg_proc.stdin.write(chunk)

            ffmpeg_proc.stdin.close()

            while True:
                pcm_data = ffmpeg_proc.stdout.read(4096)
                if not pcm_data:
                    break

                audio_data = np.frombuffer(pcm_data, dtype=np.int16)
                audio_data = audio_data.astype(np.float32) / 32768.0
                window = np.hanning(len(audio_data))
                audio_windowed = audio_data * window
                fft_result = np.fft.rfft(audio_windowed)
                magnitude = np.abs(fft_result)
                magnitude_db = 20 * np.log10(magnitude + 1e-8)
                threading.Thread(target=self.speech_volume_callback, args=(magnitude_db,)).start()

                stream.write(pcm_data)

            ffmpeg_proc.wait()

            self.is_done_speaking = True
            threading.Thread(target=self.speech_end_callback).start()

    # def _playback_thread(self):
    #     import subprocess
    #     import uuid
    #     import os
    #     import json
    #     import threading

    #     p = pyaudio.PyAudio()
    #     stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, output=True)

    #     while True:
    #         if self.is_stopping:
    #             break

    #         try:
    #             text = self.dialogueQ.get(timeout=0.1)
    #         except Empty:
    #             time.sleep(0.05)
    #             continue

    #         self.is_done_speaking = False
            
    #         threading.Thread(target=self.speech_start_callback).start()
            
    #         audio_stream = self.client.text_to_speech.stream(
    #             text=text,
    #             voice_id=self.voice_id,
    #             model_id=self.model_id,
    #         )

    #         byte_chunks = []
    #         prev_audio = None
    #         for chunk in audio_stream:
    #             if chunk is not None:
    #                 byte_chunks.append(b"" + chunk)

    #                 if len(byte_chunks) < 3:
    #                     continue

    #                 audio = decompress_mp3(b"".join(byte_chunks))
    #                 if prev_audio is not None:
    #                     cut_audio = audio[len(prev_audio):]
    #                 else:
    #                     cut_audio = audio
    #                 stream.write(cut_audio.raw_data)
    #                 prev_audio = audio
                    


    #         # audio = decompress_mp3(data)
    #         # stream.write(audio.raw_data)
                    
            
    #         # Audio is now played chunk by chunk, no need to write again

    #         self.is_done_speaking = True
    #         threading.Thread(target=self.speech_end_callback).start()

    #         # if self.cache_dir is None:
    #         #     continue

    #         # audio_file_name = f"elevenlabs_cache_{str(uuid.uuid4())[:8]}.mp3"
    #         # os.makedirs(self.cache_dir, exist_ok=True)
    #         # audio_file_path = os.path.join(self.cache_dir, audio_file_name)
    #         # with open(audio_file_path, "wb") as f:
    #         #     f.write(audio)

    #         # json_metadata = f"elevenlabs_cache.json"
    #         # json_metadata = os.path.join(self.cache_dir, json_metadata)
    #         # data = {}
    #         # if os.path.exists(json_metadata):
    #         #     data = json.load(open(json_metadata, "r"))
    #         # data[audio_file_name] = {
    #         #     "text": text,
    #         #     "voice_id": self.voice_id,
    #         #     "model_id": self.model_id,
    #         # }
    #         # with open(json_metadata, "w") as f:
    #         #     json.dump(data, f, indent=2)




    def generate(self, text):
        self.dialogueQ.put(text)

    def generate_blocking(self, text):
        self.is_done_speaking = False
        self.generate(text)
        while not self.is_done_speaking:
            time.sleep(0.1)

    def wait_until_ready(self):
        # ALWAYS READY BECAUSE CLOUD APIS :D
        pass

    def stop_speaking(self):
        self.mpv_process.terminate()
        self.is_done_speaking = True

    def stop(self):
        self.is_stopping = True
        self.stream_thread.join()
        if self.mpv_process:
            self.mpv_process.terminate()
        print("[VOICE] ElevenLabs voice stopped.")

    

class KokoroVoice(AIVoice):
    def __init__(self, speech_start_callback, speech_end_callback, speech_volume_callback):
        self.queue = Queue()
        self.audioQ = Queue()
        self.volume_callback_queue = Queue()

        self.should_close_process = Value('b', False)

        self.pause_speech = Value('b', False)

        self.stop_audio_gen = Value('b', False)

        self.is_ready = Value('b', False)

        self.process = Process(target=self._generate_loop)
        self.process.start()

        self.callback_thread = None

        self.time_since_speech_start = -1
        self.is_speaking = False

        if speech_start_callback or speech_end_callback:
            self.callback_thread = threading.Thread(target=self._watch_for_callbacks, args=(speech_start_callback, speech_end_callback, speech_volume_callback))
            self.callback_thread.start()

    def stop(self):
        print("[VOICE] Setting should_close_process to True")
        self.should_close_process.value = True
        
        print("[VOICE] Waiting for process to join...")
        self.process.join()

        print("[VOICE] Waiting for callback thread to join...")
        if self.callback_thread:
            self.callback_thread.join()

        print("[VOICE] Stopped")

    def _watch_for_callbacks(self, speech_start_callback, speech_end_callback, speech_volume_callback):
        was_speaking = False
        self.last_speaking_time = -1
        while True:
            if self.should_close_process.value:
                break

            is_speaking = self._is_speaking()

            if is_speaking and not was_speaking:
                was_speaking = True
                if speech_start_callback:
                    speech_start_callback()
            elif not is_speaking and was_speaking:
                was_speaking = False
                if speech_end_callback:
                    speech_end_callback()
            
            if not self.volume_callback_queue.empty():
                speech_volume_callback(self.volume_callback_queue.get_nowait())
            time.sleep(0.05)

    def _is_speaking(self):
        if time.time() - self.time_since_speech_start < 1.0:
            return True
        self.is_speaking = not self.audioQ.empty() or not self.queue.empty() or self.stop_audio_gen.value
        return self.is_speaking

    def stop_speaking(self):
        self.stop_audio_gen.value = True
        while self.stop_audio_gen.value: # wait until we know audio gen is done
            time.sleep(0.01)
        
        # clear the audioQ
        self.pause_speech.value = True
        while not self.audioQ.empty():
            self.audioQ.get()
        self.pause_speech.value = False


    def wait_until_ready(self):
        while not self.is_ready.value:
            time.sleep(0.1)

    def generate(self, text):
        self.queue.put(text)

    def generate_blocking(self, text):
        self.generate(text)

        self.time_since_speech_start = time.time()
        self.is_speaking = True

        while self._is_speaking():
            time.sleep(0.1)

    def _speak_audio_loop(self):
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paFloat32, channels=1, rate=24000, output=True)
        while True:

            if self.should_close_process.value:
                stream.stop_stream()
                stream.close()
                p.terminate()
                break

            if self.pause_speech.value:
                time.sleep(0.05)
                continue

            try:
                audio = self.audioQ.get(timeout=0.1)
            except Empty:
                time.sleep(0.05)
                continue

            window = np.hanning(2400)
            audio_windowed = audio * window
            fft_result = np.fft.rfft(audio_windowed)
            magnitude = np.abs(fft_result)
            magnitude_db = 20 * np.log10(magnitude + 1e-8)
            self.volume_callback_queue.put(magnitude_db)

            stream.write(audio.tobytes())


    def _generate_loop(self):
        pipeline = KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M')

        self.generate_loop_thread = threading.Thread(target=self._speak_audio_loop, args=())
        self.generate_loop_thread.start()

        self.is_ready.value = True
     
        while True:

            if self.should_close_process.value:
                print("[VOICE] Stopping generate loop")
                self.generate_loop_thread.join()
                print("[VOICE] Generate loop stopped")
                break

            try:
                text = self.queue.get_nowait()
            except Exception:
                text = None

            if text is None:
                time.sleep(0.05)
                continue

            generator = pipeline(text, voice='af_bella')

            for i, (gs, ps, audio) in enumerate(generator):
                audio = np.array(audio)
                if self.stop_audio_gen.value:
                    break
                for i in range(0, audio.size, 2400):
                    audio_clip = audio[i:i+2400]
                    if audio_clip.size < 2400:
                        audio_clip = np.pad(audio_clip, (0, 2400 - audio_clip.size), mode='constant')
                    self.audioQ.put(audio_clip)

            self.stop_audio_gen.value = False


if __name__ == "__main__":
    
    voice = ElevenLabsAIVoice(speech_start_callback=lambda: print("Speech started"),
                                speech_end_callback=lambda: print("Speech ended"),  
                                speech_volume_callback=lambda volume: print(f"Volume: {volume}"),
                                api_key=api_key, voice_id="odyUrTN5HMVKujvVAgWW", cache_dir="./elevenlabs_cache")
    voice.generate_blocking("Hello, this is a test of the ElevenLabs voice synthesis.")
    voice.stop()
