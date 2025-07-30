URL = "localhost:8000"
IS_SECURE = False

USER_ID = "meewhee"

QUIET_MODE = False
TYPE_MODE = False
MICROPHONES = [
    "ReSpeaker 4 Mic Array",
    "MacBook Pro Microphone"
]

# ---------------------------

def get_url():
    if IS_SECURE:
        return f"s://{URL}"
    else:
        return f"://{URL}"
    
