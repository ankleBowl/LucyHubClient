import torch
import numpy as np

class DetectSpeechSileroVADProvider:
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
    
    def stop(self):
        pass