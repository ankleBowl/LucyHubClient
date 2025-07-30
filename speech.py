import pyaudio, torch
import numpy as np
import nemo.collections.asr as nemo_asr
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import threading
import time

from transformers import AutoTokenizer, BertForSequenceClassification
from peft import PeftModel, PeftConfig

class RequestType(str):
    QUERY = "query"
    NOT_QUERY = "not_query"
    INCOMPLETE_QUERY = "incomplete_query"

class RequestClassifier:
    def __init__(self):
        pass

    def classify(self, text):
        raise NotImplementedError("This method should be implemented by subclasses.")
    
class RequestClassifierBERT(RequestClassifier):
    def __init__(self):
        base_model_name = "bert-base-uncased"
        self.tokenizer = AutoTokenizer.from_pretrained(base_model_name)
        base_model = BertForSequenceClassification.from_pretrained(base_model_name, num_labels=3)

        lora_path = "models/request-classifier"
        self.model = PeftModel.from_pretrained(base_model, lora_path)

        self.class_map = {
            0: RequestType.QUERY,
            1: RequestType.NOT_QUERY,
            2: RequestType.INCOMPLETE_QUERY
        }

    def classify(self, text, return_logits=False):
        return RequestType.INCOMPLETE_QUERY
        text = ''.join(char for char in text if char.isalnum() or char.isspace())
        text = text.strip()
        text = text.lower()

        inputs = self.tokenizer(text, return_tensors="pt")
        outputs = self.model(**inputs)
        logits = outputs.logits
        if return_logits:
            return logits
        predicted_class = logits.argmax(dim=-1).item()
        return self.class_map[predicted_class]
        

# -------------------------------

class TranscriptionProvider:
    def __init__(self):
        pass

    def transcribe(self, audio):
        raise NotImplementedError()
    
    def stop(self):
        pass
    
class ParakeetTranscriptionProvider(TranscriptionProvider):
    def __init__(self):
        import logging
        logging.getLogger('nemo_logger').setLevel(logging.ERROR)
        self.asr_model = nemo_asr.models.ASRModel.from_pretrained(model_name="nvidia/parakeet-tdt-0.6b-v2")
        self.audio_history = []

    def transcribe(self, audio):
        audio = audio.astype(np.float32) / 32768.0
        from scipy.io.wavfile import write
        write("temp_audio.wav", 16000, audio)
        output = self.asr_model.transcribe([audio], verbose=False)
        text = output[0].text
        if len(text) <= 10:
            return None
        return text
    
# -------------------------------

class DetectSpeechProvider:
    def __init__(self):
        pass

    def feed_audio(self, buffer):
        raise NotImplementedError()
    
    def get_audio(self):
        raise NotImplementedError()
    
    def clear_audio(self):
        raise NotImplementedError()
    
    def is_speaking(self):
        raise NotImplementedError()
    
    def is_done_speaking(self):
        raise NotImplementedError()
    
    def stop(self):
        pass

class DetectSpeechVADProvider(DetectSpeechProvider):
    def __init__(self):
        # torch.set_num_threads(1)
        self.vad_model, utils = torch.hub.load(
            'snakers4/silero-vad', 'silero_vad', verbose=False
        )
        self.get_speech_timestamps, _, _, _, _ = utils

        self.audio_history = np.array([], dtype=np.int16) 
        self.speaking_history = []

        self.CHUNKSIZE = 1536
        self.SAMPLERATE = 16000

    def feed_audio(self, buffer):
        audio = np.frombuffer(buffer, dtype=np.int16)
        tensor = torch.from_numpy(audio).float() / 32768.0
        is_speaking = self.vad_model(tensor, 16000).item()

        if is_speaking >= 0.2:
            self.audio_history = np.concatenate((self.audio_history, audio))

        self.speaking_history.append(is_speaking)

        if len(self.audio_history) < self.SAMPLERATE * 0.25:
            pass

        self.speaking_history = self.speaking_history[-int((self.SAMPLERATE / self.CHUNKSIZE) * 0.5):]

    def get_audio(self):
        return self.audio_history
    
    def clear_audio(self):
        self.audio_history = np.array([], dtype=np.int16)

    def is_speaking(self):
        avg_speaking = np.mean(self.speaking_history)
        # print(f"[VAD] avg_speaking: {avg_speaking}, history length: {len(self.speaking_history)}")
        return avg_speaking > 0.8
    
    def is_done_speaking(self):
        avg_speaking = np.mean(self.speaking_history)
        return avg_speaking < 0.7
    
import openwakeword
from openwakeword.model import Model

class DetectWakeWordProvider(DetectSpeechVADProvider):
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

# -------------------------------

class VoiceAssistant:
    def __init__(self, detect_speech_provider, transcription_provider, request_classifier, mic_list=[], start_speaking_callback=None, end_speaking_callback=None):
        self.CHUNKSIZE = 1536
        self.SAMPLERATE = 16000

        self.attempts = 0

        p = pyaudio.PyAudio()

        def find_device_by_name(name):
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if name.lower() in info['name'].lower():
                    return i
            return None

        device_index = None
        for mic_name in mic_list:
            device_index = find_device_by_name(mic_name)
            if device_index is not None:
                print(f"[AUDIO] Using microphone: {mic_name} (index {device_index})")
                break
        
        if device_index is None:
            print("[AUDIO] No microphone found, using default device")
            device_index = p.get_default_input_device_info()['index']

        self.stream = p.open(format=pyaudio.paInt16, channels=1, rate=self.SAMPLERATE,input=True, frames_per_buffer=self.CHUNKSIZE, input_device_index=device_index)

        self.current_conversation_response_nonce = 0

        self.start_speaking_callback = start_speaking_callback
        self.end_speaking_callback = end_speaking_callback

        self.transcription_provider = transcription_provider
        self.detect_speech_provider = detect_speech_provider
        self.request_classifier = request_classifier

        self.is_closing = False

    def run(self):
        self.vad_loop_thread = threading.Thread(target=self._loop, args=())
        self.transcribe_loop_thread = threading.Thread(target=self._transcribe_loop, args=())

        self.vad_loop_thread.start()
        self.transcribe_loop_thread.start()


    def _loop(self):
        self.awake = False
        self.can_try_transcribe = False

        # CHUNKSIZE_SECONDS = self.CHUNKSIZE / 16000.0

        while True:
            if self.is_closing:
                self.stream.stop_stream()
                self.stream.close()
                return
            
            data = self.stream.read(self.CHUNKSIZE, exception_on_overflow=False)
            self.detect_speech_provider.feed_audio(data)

            if self.detect_speech_provider.is_speaking() and not self.awake:
                print("[AUDIO] User started speaking")
                if self.start_speaking_callback != None:
                    self.start_speaking_callback()
                self.awake = True
                self.last_transcription_submitted_time = float('inf')
            elif self.detect_speech_provider.is_done_speaking() and self.awake:
                print("[AUDIO] User finished speaking")
                self.awake = False
                self.try_transcribe = True

            # arr = np.frombuffer(data, dtype=np.int16)
            # tensor = torch.from_numpy(audio).float() / 32768.0
            # is_speaking = self.vad_model(tensor, 16000).item()

            # if is_speaking >= 0.2:
            #     self.audio_history.append(data)
            # self.speaking_history.append(is_speaking)

            # if len(self.audio_history) < int(0.25 / CHUNKSIZE_SECONDS):
            #     continue

            # self.speaking_history = self.speaking_history[-int(0.25 / CHUNKSIZE_SECONDS):]
            # avg_speaking = np.mean(self.speaking_history)
            # if avg_speaking > 0.8 and not self.awake:
            #     self.start_speaking_callback()
            #     self.awake = True
            #     self.last_transcription_submitted_time = float('inf') # Ensure any previously queued transcription is NOT submitted
            # elif avg_speaking < 0.6 and self.awake:
            #     self.awake = False
            #     self.try_transcribe = True


    def _transcribe_loop(self):
        self.last_transcription = ""
        self.try_transcribe = False

        while True:
            if self.is_closing:
                return
            if not self.try_transcribe:
                time.sleep(0.05)
                continue
            self.try_transcribe = False

            self.current_conversation_response_nonce += 1

            audio = self.detect_speech_provider.get_audio()
            if len(audio) < self.SAMPLERATE * 0.25:
                continue
            transcription = self.transcription_provider.transcribe(audio)
            request_type = self.request_classifier.classify(transcription) if transcription else RequestType.NOT_QUERY

            print(f"[TRANSCRIPTION] {transcription} (request_type={request_type})")
            if request_type == RequestType.QUERY:        
                self._generate_response(transcription, self.current_conversation_response_nonce, time.time())
            elif request_type == RequestType.INCOMPLETE_QUERY:
                extra_time = 2
                self.respond_thread = threading.Thread(target=self._generate_response, args=(transcription, self.current_conversation_response_nonce, time.time() + extra_time))
                self.respond_thread.start()
            elif request_type == RequestType.NOT_QUERY:
                self._generate_response(None, self.current_conversation_response_nonce, time.time())

    def _generate_response(self, transcription, nonce, respond_time):                
        while respond_time > time.time():
            time.sleep(0.01)

        if nonce != self.current_conversation_response_nonce or self.try_transcribe or self.awake:
            # There's another transcription in progress or the response was interrupted
            print("[INTERRUPTED] Response generation interrupted, skipping")
            return
        
        self.detect_speech_provider.clear_audio()
        self.end_speaking_callback(transcription)

    def stop(self):
        print("[AUDIO] Stopping...")
        self.is_closing = True
        print("[AUDIO] Waiting for VAD thread to join...")
        self.vad_loop_thread.join()
        print("[AUDIO] Waiting for transcription thread to join...")
        self.transcribe_loop_thread.join()

        print("[AUDIO] Closing VAD provider")
        self.detect_speech_provider.stop()

        print("[AUDIO] Closing transcription provider")
        self.transcription_provider.stop()

        print("[AUDIO] Stopped")
    
if __name__ == "__main__":
    request_classifier = RequestClassifierBERT()
    while True:
        request = input("Enter a request: ")
        if request.lower() == "exit":
            break
        request_type = request_classifier.classify(request, return_logits=True)
        import matplotlib.pyplot as plt

        # Get the logits as numpy array
        logits = request_type.detach().numpy()[0]
        classes = ["QUERY", "NOT_QUERY", "INCOMPLETE_QUERY"]

        # Create a bar plot
        plt.figure(figsize=(10, 5))
        bars = plt.bar(classes, logits)

        # Add colors to indicate the highest value
        max_idx = logits.argmax()
        for i, bar in enumerate(bars):
            if i == max_idx:
                bar.set_color('green')
            else:
                bar.set_color('lightblue')

        plt.title('Request Classification Logits')
        plt.xlabel('Request Type')
        plt.ylabel('Logit Value')

        # Add the actual values on top of the bars
        for i, v in enumerate(logits):
            plt.text(i, v + 0.1, f"{v:.2f}", ha='center')

        predicted_class = request_classifier.class_map[max_idx]
        plt.annotate(f"Predicted: {predicted_class}", 
                    xy=(0.5, 0.95), 
                    xycoords='axes fraction',
                    ha='center',
                    fontsize=12,
                    bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.3))

        plt.tight_layout()
        plt.show()

    
# if __name__ == "__main__":
#     def start_speaking():
#         # pass
#         print("User started speaking")

#     def end_speaking(transcription):
#         # pass
#         print("User finished speaking:", transcription)
    
#     detect_speech_provider = DetectWakeWordProvider()
#     # detect_speech_provider = DetectSpeechVADProvider()
#     transcription_provider = ParakeetTranscriptionProvider()
#     va = VoiceAssistant(detect_speech_provider, transcription_provider, start_speaking_callback=start_speaking, end_speaking_callback=end_speaking)
#     va.run()

#     try:
#         import time
#         while True:
#             time.sleep(1)
#     except KeyboardInterrupt:
#         print("Stopping Voice Assistant...")
#         va.stop()
        