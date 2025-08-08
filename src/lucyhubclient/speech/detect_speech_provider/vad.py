import numpy as np


class DetectSpeechSileroVADProvider:
    def __init__(self):
        # torch.set_num_threads(1)
        # self.vad_model, _ = torch.hub.load(
        #     'snakers4/silero-vad', 'silero_vad', verbose=False
        # )
        self.vad_model = SileroVAD()

        self.audio_history = np.array([], dtype=np.int16) 
        self.speaking_history = []

        self.CHUNKSIZE = 1536
        self.SAMPLERATE = 16000

    def feed_audio(self, buffer):
        audio = np.frombuffer(buffer, dtype=np.int16)
        chunks = np.split(audio, 3)  # 1536 / 3 = 512 samples per chunk
        is_speaking_arr = []
        for chunk in chunks:
            # print(f"[VAD] Feeding audio of shape: {chunk.shape}")
            # is_speaking_arr.append(self.vad_model(chunk, 16000).item())
            is_speaking_arr.append(self.vad_model.process_array(chunk))
        is_speaking = np.mean(is_speaking_arr)

        # is_speaking = self.vad_model(tensor, 16000).item()
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


_RATE = 16000
_CONTEXT_SIZE = 64  # 16Khz
_CHUNK_SAMPLES = 512

from importlib import resources
import onnxruntime

class SileroVAD:
    def __init__(self):
        onnx_path = resources.files('lucyhubclient.speech.detect_speech_provider') / 'silero_vad.onnx'

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1

        self.session = onnxruntime.InferenceSession(
            onnx_path, providers=["CPUExecutionProvider"], sess_options=opts
        )

        self._context = np.zeros((1, _CONTEXT_SIZE), dtype=np.float32)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._sr = np.array(_RATE, dtype=np.int64)

    def process_array(self, audio_array: np.ndarray) -> float:
        audio_array = audio_array.astype(np.float32) / 32768.0

        if len(audio_array) != _CHUNK_SAMPLES:
            # Window size is fixed at 512 samples in v5
            raise ValueError(f"Expected audio of length {_CHUNK_SAMPLES}, got {len(audio_array)}")

        # Add batch dimension and context
        audio_array = np.concatenate(
            (self._context, audio_array[np.newaxis, :]), axis=1
        )
        self._context = audio_array[:, -_CONTEXT_SIZE:]

        # ort_inputs = {"input": audio_array, "state": self._state, "sr": self._sr}
        ort_inputs = {
            "input": audio_array[:, : _CHUNK_SAMPLES + _CONTEXT_SIZE],
            "state": self._state,
            "sr": self._sr,
        }
        ort_outs = self.session.run(None, ort_inputs)
        out, self._state = ort_outs

        return out.squeeze()