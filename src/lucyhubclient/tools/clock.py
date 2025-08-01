from ..tools.lucy_client_module import LucyClientModule
import os
from scipy.io import wavfile
import asyncio
from importlib import resources

from ..sound import Sound, LoopPlaybackModifier, FadeOutEffect, FadeInEffect

class LClockClient(LucyClientModule):
    def __init__(self):
        super().__init__("clock")

        timer_audio_path = resources.files("lucyhubclient.tools.clock_util").joinpath("alarm.wav")
        if not os.path.exists(timer_audio_path):
            raise FileNotFoundError(f"Timer audio file not found at {timer_audio_path}")
        
        audio_data = wavfile.read(timer_audio_path)[1]

        self.timer_sound_id = None
        
        self.timer_audio_path = timer_audio_path
        self.loop_start_pos = int(len(audio_data) / 3)
        self.loop_end_pos = int(len(audio_data) * 2 / 3)
        # loop between 1/3 and 2/3 of the audio data


    async def handle_message(self, message):
        if message["message"] == "START_TIMER_SOUND":
            if self.timer_sound_id is not None:
                return
            sound = Sound.from_wav(self.timer_audio_path)
            sound.add_effect(FadeInEffect(48000))
            sound.add_playback_modifier(LoopPlaybackModifier(loop_start_frame=self.loop_start_pos, loop_end_frame=self.loop_end_pos))
            self.timer_sound_id = sound.get_id()
            self.sound_manager.add_sound(sound)

        elif message["message"] == "STOP_TIMER_SOUND":
            if self.timer_sound_id is None:
                return
            sound = self.sound_manager.add_effect_to_sound(self.timer_sound_id, FadeOutEffect(48000))
            self.timer_sound_id = None


if __name__ == "__main__":
    client = LClockClient()
    asyncio.run(client.handle_message({
        "message": "START_TIMER_SOUND"
    }))
    asyncio.run(asyncio.sleep(5))  # Play for 5 seconds
    asyncio.run(client.handle_message({
        "message": "STOP_TIMER_SOUND"
    }))