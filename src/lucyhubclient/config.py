import os
import yaml
from pathlib import Path

# GEMINI WROTE THIS BECAUSE I AM SO SICK OF WRITING CONFIG LOADING CODE

# Define the default configuration structure as the schema
# This dictionary serves as the blueprint for what the config.yaml should contain.
# It also provides initial values if a template file needs to be generated.
DEFAULT_CONFIG_SCHEMA = {
    "urls": {
        "http": "http://localhost:8000",
        "ws": "ws://localhost:8000",
    },
    "quiet_mode": False,
    "type_mode": False,
    "microphones": [],
    "webview_type": "pywebview",
    "voice_system": "kokoro",
    "elevenlabs_api_key": "",
}

# Define the path where the configuration file will be stored
# It expands to a full path like /home/youruser/lucyclient/config.yaml
CONFIG_DIR = Path(os.path.expanduser("~/lucyclient"))
CONFIG_FILE = CONFIG_DIR / "config.yaml"

# Global variable to store the loaded configuration
# This will be populated by load_config() and can be accessed by get_config()
_APP_CONFIG = None

def load_config():
    """
    Loads the configuration from CONFIG_FILE.
    If the file doesn't exist, it creates a template file with default values.
    It strictly validates against the schema, raising an error if any key is missing.
    The loaded configuration is stored in the module-level variable _APP_CONFIG.
    """
    global _APP_CONFIG # Declare intent to modify the global variable

    if not CONFIG_FILE.exists():
        print(f"Configuration file not found at '{CONFIG_FILE}'.")
        print("Generating a template config.yaml with default values.")
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(DEFAULT_CONFIG_SCHEMA, f, indent=4, sort_keys=False)
        print(f"Template config.yaml created at '{CONFIG_FILE}'.")
        print("Please review and populate the configuration file.")
        # Raise an error to indicate that the user needs to populate the config
        raise FileNotFoundError(
            f"Configuration file '{CONFIG_FILE}' was just created. "
            "Please populate it with your settings and re-run the application."
        )

    try:
        with open(CONFIG_FILE, 'r') as f:
            config = yaml.safe_load(f)
        if config is None: # Handle empty YAML file
            config = {}

        _APP_CONFIG = config # Store the loaded config in the global variable
        print(f"Configuration loaded successfully from '{CONFIG_FILE}'.")
        return _APP_CONFIG # Also return it for immediate use if desired

    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing YAML configuration file '{CONFIG_FILE}': {e}")
    except KeyError as e:
        # Re-raise the KeyError from validation directly
        raise e
    except TypeError as e:
        # Re-raise the TypeError from validation directly
        raise e
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred while loading config: {e}")

def get_config():
    """
    Returns the globally loaded application configuration.
    If the configuration has not been loaded yet, it attempts to load it.
    """
    global _APP_CONFIG
    if _APP_CONFIG is None:
        print("Configuration not yet loaded. Attempting to load now...")
        _APP_CONFIG = load_config() # Attempt to load if not already loaded
    return _APP_CONFIG

# --- Example Usage ---
if __name__ == "__main__":
    try:
        # Attempt to load the configuration
        # You can call load_config() once at the start of your application
        # or rely on get_config() to lazily load it.
        app_config_main = load_config() # This will populate _APP_CONFIG

        # Now, from any other file, you can import get_config and use it:
        # from config_manager import get_config
        # my_config = get_config()

        print("\n--- Loaded Configuration (via app_config_main) ---")
        print(f"HTTP URL: {app_config_main['urls']['http']}")
        print(f"WS URL: {app_config_main['urls']['ws']}")

        print("\n--- Loaded Configuration (via get_config()) ---")
        retrieved_config = get_config()
        print(f"Quiet Mode: {retrieved_config['quiet_mode']}")
        print(f"Voice System: {retrieved_config['voice_system']}")
        print(f"ElevenLabs API Key (first 5 chars): {retrieved_config['elevenlabs_api_key'][:5]}...")

        # Example of how a missing key would cause an error if you manually
        # remove a key from config.yaml after it's generated.
        # Uncomment the following line and remove 'type_mode' from your config.yaml
        # to see the KeyError in action.
        # print(f"Type Mode: {app_config['type_mode_missing_key']}")

    except (FileNotFoundError, ValueError, KeyError, TypeError, RuntimeError) as e:
        print(f"\nError: {e}")
        print("Please ensure your config.yaml is correctly formatted and contains all required keys.")
        print(f"Refer to the schema: {DEFAULT_CONFIG_SCHEMA}")

