import pyaudio
import threading
import time

class RequestType(str):
    QUERY = "query"
    NOT_QUERY = "not_query"
    INCOMPLETE_QUERY = "incomplete_query"

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
    