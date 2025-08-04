import os
import yaml
from pathlib import Path

DEFAULT_CONFIG_SCHEMA = {
    "url": "localhost:8000",
    "is_secure": False,
    "quiet_mode": False,
    "type_mode": False,
    "microphones": [],
    "webview_type": "chrome",
}
CONFIG_DIR = Path(os.path.expanduser("~/lucyclient"))
CONFIG_FILE = CONFIG_DIR / "config.yaml"

_APP_CONFIG = None

def save_empty_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        yaml.dump(DEFAULT_CONFIG_SCHEMA, f, indent=4, sort_keys=False)

def load_config():
    global _APP_CONFIG

    if not CONFIG_FILE.exists():
        save_empty_config() 

    try:
        with open(CONFIG_FILE, 'r') as f:
            config = yaml.safe_load(f)
        if config is None:
            save_empty_config()
            config = DEFAULT_CONFIG_SCHEMA.copy() 

        _APP_CONFIG = config
        return _APP_CONFIG
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing YAML configuration file '{CONFIG_FILE}': {e}")
    except Exception as e:
        raise RuntimeError(f"An unexpected error occurred while loading config: {e}")

def get_config():
    global _APP_CONFIG
    if _APP_CONFIG is None:
        _APP_CONFIG = load_config()
    return _APP_CONFIG

def write_config():
    with open(CONFIG_FILE, 'w') as f:
        yaml.dump(_APP_CONFIG, f, indent=4, sort_keys=False)

def get_http_url():
    config = get_config()
    if config["is_secure"]:
        return f"https://{config['url']}"
    else:
        return f"http://{config['url']}"
    
def get_ws_url():
    config = get_config()
    if config["is_secure"]:
        return f"wss://{config['url']}"
    else:
        return f"ws://{config['url']}"



from flask import Flask, request, jsonify
import threading
from importlib import resources

app = Flask(__name__)

import logging

# Disable Flask's default logger
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Disable all other Flask logging if needed
flask_log = logging.getLogger('flask.app')
flask_log.setLevel(logging.CRITICAL)

@app.route('/')
def index():
    file = resources.files('lucyhubclient.templates') / 'config.html'
    with open(file, 'r') as f:
        return f.read()
    
@app.route('/get_config')
def get_config_route():
    return jsonify(get_config())

@app.route('/set_server_address', methods=['POST'])
def set_server_address():
    data = request.json
    _APP_CONFIG['url'] = data['server_address']
    _APP_CONFIG['is_secure'] = data['is_secure']
    write_config()
    return jsonify({"status": "success"})

@app.route('/set_primary_mic', methods=['POST'])
def set_primary_mic():
    data = request.json
    _APP_CONFIG['microphones'] = [ data['primary_mic'] ]
    write_config()
    return jsonify({"status": "success"})

@app.route('/set_typing_mode', methods=['POST'])
def set_typing_mode():
    data = request.json
    _APP_CONFIG['type_mode'] = data['type_mode']
    write_config()
    return jsonify({"status": "success"})

@app.route('/set_quiet_mode', methods=['POST'])
def set_quiet_mode():
    data = request.json
    _APP_CONFIG['quiet_mode'] = data['quiet_mode']
    write_config()
    return jsonify({"status": "success"})

def run_flask_app():
    app.run(host='0.0.0.0', port=4812)

def start_flask_server():
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()