import pyaudio
import threading
import uuid
from scipy.io import wavfile
import numpy as np
import time
import warnings

warnings.filterwarnings("ignore", category=wavfile.WavFileWarning)

# ----------

class SoundEffect:
    def apply(self, audio_chunk):
        raise NotImplementedError("Subclasses should implement this method")
    
class FadeInEffect(SoundEffect):
    def __init__(self, duration):
        self.duration = duration
        self.progress = 0

    def apply(self, audio_chunk):
        if self.progress >= self.duration:
            return audio_chunk

        for i in range(len(audio_chunk)):
            factor = self.progress / self.duration
            audio_chunk[i] = audio_chunk[i] * factor
            self.progress += 1

        return audio_chunk
    
    def is_done_playing(self):
        return False
    
class FadeOutEffect(SoundEffect):
    def __init__(self, duration): 
        self.duration = duration
        self.progress = 0

    def apply(self, audio_chunk):
        if self.progress >= self.duration:
            return np.zeros_like(audio_chunk)

        for i in range(len(audio_chunk)):
            factor = (self.duration - self.progress) / self.duration
            if factor < 0:
                factor = 0
            audio_chunk[i] = audio_chunk[i] * factor
            self.progress += 1

        return audio_chunk
    
    def is_done_playing(self):
        return self.progress >= self.duration

# ----------

class SoundPlaybackModifier:
    def apply(self, sound):
        raise NotImplementedError("Subclasses should implement this method")
    
class LoopPlaybackModifier(SoundPlaybackModifier):
    def __init__(self, loop_start_frame, loop_end_frame):
        self.loop_start_frame = loop_start_frame
        self.loop_end_frame = loop_end_frame

    def apply(self, sound):
        if sound.current_position >= self.loop_end_frame:
            sound.current_position = self.loop_start_frame

class Sound:
    def from_wav(file_path):
        audio_sr, audio_data = wavfile.read(file_path)
        if audio_data.dtype == 'int16':
            audio_data = audio_data.astype(np.int32)
            audio_data = audio_data * 32768  # Normalize to int32 range

        if audio_data.dtype != 'int32':
            raise ValueError(f"Audio data must be in int32 or int16 format. Found: {audio_data.dtype}")
        if audio_sr != 48000:
            raise ValueError("Audio sample rate must be 48000 Hz")
        return Sound(audio_data)

    def __init__(self, audio_data):
        self.uuid = str(uuid.uuid4())
        self.audio_data = audio_data
        self.current_position = 0
        self.effects = []
        self.playback_modifiers = []

    def get_next(self, chunk_size):
        audio_chunk = self.audio_data[self.current_position:self.current_position + chunk_size]
        if len(audio_chunk) < chunk_size:
            pad_amount = chunk_size - len(audio_chunk)
            audio_chunk = np.pad(audio_chunk, ((0, pad_amount), (0, 0)), 'constant')

        for effect in self.effects:
            audio_chunk = effect.apply(audio_chunk)

        self.current_position += chunk_size

        for modifier in self.playback_modifiers:
            if isinstance(modifier, SoundPlaybackModifier):
                modifier.apply(self)

        return audio_chunk
    
    def add_effect(self, effect):
        self.effects.append(effect)

    def add_playback_modifier(self, modifier: SoundPlaybackModifier):
        self.playback_modifiers.append(modifier)    

    def get_id(self):
        return self.uuid

    def is_done_playing(self):
        for effect in self.effects:
            if effect.is_done_playing():
                return True
        return self.current_position >= len(self.audio_data)

class SoundManager:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=pyaudio.paInt32, channels=2, rate=48000, output=True)

        self.sounds = {}
        self.volume = 1.0

        self.should_stop = False

        self.thread = threading.Thread(target=self._playing_thread)
        self.thread.start()


    def stop(self):
        self.should_stop = True
        self.thread.join()
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()

    def add_sound(self, sound: Sound):
        if sound.get_id() in self.sounds:
            raise ValueError("Sound with this ID already exists")
        self.sounds[sound.get_id()] = sound

    def add_effect_to_sound(self, sound_id, effect: SoundEffect):
        if sound_id not in self.sounds:
            raise ValueError("Sound with this ID does not exist")
        self.sounds[sound_id].add_effect(effect)

    def set_volume(self, volume):
        if not (0 <= volume <= 1):
            raise ValueError("Volume must be between 0 and 1")
        self.volume = volume

    def _playing_thread(self):
        CHUNK_SIZE = 1024
        
        while True:
            if self.should_stop:
                break

            chunk = np.zeros((CHUNK_SIZE, 2), dtype=np.int32)
            done_sounds = []
            for sound in self.sounds:
                sound = self.sounds[sound]
                if sound.is_done_playing():
                    done_sounds.append(sound.get_id())
                    continue
                next_chunk = sound.get_next(CHUNK_SIZE)
                if next_chunk is not None:
                    chunk += next_chunk

            for sound_id in done_sounds:
                del self.sounds[sound_id]

            # chunk *= self.volume

            self.stream.write(chunk.tobytes())
                

    def close(self):
        self.stream.close()
        self.p.terminate()

if __name__ == "__main__":
    # Example usage
    sound_manager = SoundManager()
    # sound = Sound.from_wav("tools/clock/alarm.wav")
    # sound.add_effect(FadeInEffect(48000))
    # sound.add_playback_modifier(LoopPlaybackModifier(len(sound.audio_data) // 3, len(sound.audio_data) // 3 * 2))
    sound = Sound.from_wav("sounds/wake.wav")
    sound_manager.add_sound(sound)

    # time.sleep(2)
    # sound_manager.add_effect_to_sound(sound.get_id(), FadeOutEffect(48000))  # 1 second fade out

    try:
        while True:
            pass  # Keep the main thread alive
    except KeyboardInterrupt:
        sound_manager.add_effect_to_sound(sound.get_id(), FadeOutEffect(48000))
        time.sleep(2)
        sound_manager.close()  # Clean up on exit