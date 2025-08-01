import nemo.collections.asr as nemo_asr
import numpy as np

class ParakeetTranscriptionProvider:
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