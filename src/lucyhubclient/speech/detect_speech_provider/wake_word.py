import openwakeword
from openwakeword.model import Model

import threading
import time
import numpy as np

from ...speech.detect_speech_provider.vad import DetectSpeechSileroVADProvider

class DetectWakeWordProvider(DetectSpeechSileroVADProvider):
    def __init__(self, wake_word="alexa", wake_word_detection_callback=None):
        super().__init__()
        self.wake_word_audio_buffer = np.array([], dtype=np.int16)

        openwakeword.utils.download_models()
        self.wake_word_model = Model(wakeword_models=[wake_word], inference_framework="onnx")
        self.wake_word_likelyhood_history = []
        self.wake_word = wake_word

        self.last_triggered_time = 0

        self.is_closing = False

        self.wake_word_detected = False
        self.wake_word_check_thread = threading.Thread(target=self._check_for_wake_word, args=())
        self.wake_word_check_thread.start()

        self.wake_word_detection_callback = wake_word_detection_callback

    def _check_for_wake_word(self):
        while True:
            if self.is_closing:
                print("[WAKE WORD] Stopping wake word check thread")
                return
            if self.wake_word_detected:
                time.sleep(0.1)
                continue
            
            wake_word_detection_audio = self.wake_word_audio_buffer[-int(self.SAMPLERATE * 0.4):]

            prediction = self.wake_word_model.predict(wake_word_detection_audio)[self.wake_word]
            self.wake_word_likelyhood_history.append(prediction)

            if len(self.wake_word_likelyhood_history) < 5:
                time.sleep(0.1)
                continue
            if len(self.wake_word_likelyhood_history) > 5:
                self.wake_word_likelyhood_history = self.wake_word_likelyhood_history[-5:]
            total = sum(self.wake_word_likelyhood_history)
            self.wake_word_detected = total >= 1

            if self.wake_word_detected:
                print(f"[WAKE WORD DETECTED] {self.wake_word_detected}, {len(self.wake_word_audio_buffer)} samples, {total} likelyhood")
                self.last_triggered_time = time.time()
                if self.wake_word_detection_callback:
                    self.wake_word_detection_callback()

            time.sleep(0.01)


    def feed_audio(self, buffer):
        if self.wake_word_detected:
            super().feed_audio(buffer)
            return
        audio = np.frombuffer(buffer, dtype=np.int16)
        self.wake_word_audio_buffer = np.concatenate((self.wake_word_audio_buffer, audio))
        if len(self.wake_word_audio_buffer) > self.SAMPLERATE * 10:
            self.wake_word_audio_buffer = self.wake_word_audio_buffer[-self.SAMPLERATE * 10:]

    def is_speaking(self):
        return self.wake_word_detected and super().is_speaking()
    
    def is_done_speaking(self):
        if (self.wake_word_detected) and (time.time() - self.last_triggered_time < 1):
            return False
        return super().is_done_speaking()   

    def clear_audio(self):
        super().clear_audio()

        self.wake_word_audio_buffer = np.array([], dtype=np.int16)
        self.wake_word_likelyhood_history = []

        self.wake_word_detected = False
        self.wake_word_model.reset()
            
    def stop(self):
        self.is_closing = True
        self.wake_word_check_thread.join()
        super().stop()