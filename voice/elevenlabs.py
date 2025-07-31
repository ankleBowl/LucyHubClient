import threading
from multiprocessing import Queue
import numpy as np
import time
from elevenlabs.client import ElevenLabs

class ElevenLabsAIVoice:
    def __init__(self, speech_start_callback, speech_end_callback, speech_volume_callback, api_key, voice_id, cache_dir=None):
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