import multiprocessing
import webview
from webview.errors import JavascriptException
import time
import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

import logging
logging.getLogger("pywebview").setLevel(logging.WARNING)


class LucyWebView:
    def __init__(self, fullscreen=False):
        self.queue = multiprocessing.Queue()
        self.response_queue = multiprocessing.Queue()
        self.fullscreen = multiprocessing.Value('b', fullscreen)

        self.process = multiprocessing.Process(target=self.start)
        self.process.start()

        self.url = ""

    def start(self):
        index_path = "file://" + os.path.abspath("templates/index.html")
        if self.fullscreen.value:
            webview.create_window("Lucy WebView", index_path, fullscreen=True, resizable=False, confirm_close=False)
        else:
            webview.create_window("Lucy WebView", index_path, width=1024, height=600, resizable=True, confirm_close=False)
        webview.start(self._webview_ready, debug=True)

    def _webview_ready(self):
        while True:
            msg = self.queue.get()
            if msg["type"] == "load_url":
                webview.windows[0].load_url(msg["url"])
                self.response_queue.put({"status": "loaded", "url": msg["url"]})
            elif msg["type"] == "run_javascript":
                try:
                    response = webview.windows[0].evaluate_js(msg["script"])
                    self.response_queue.put({"status": "js_executed", "response": response})
                except JavascriptException as e:
                    print(f"[WARN] JS Error: {e.message}")
                    self.response_queue.put({"status": "js_executed", "response": None})
            elif msg["type"] == "set_voluem":
                volume = msg["volume"]
                try:
                    webview.windows[0].evaluate_js(f"LucyHub.setVolume({volume})")
                except JavascriptException as e:
                    pass
                self.response_queue.put({"status": "volume_set", "volume": volume})

    def show_url(self, url):
        self.url = url
        self.queue.put({
            "type": "load_url",
            "url": url
        })
        self.response_queue.get()

    def get_url(self):
        return self.url

    def run_javascript(self, script):
        self.queue.put({
            "type": "run_javascript",
            "script": script
        })
        response = self.response_queue.get()
        if response["status"] == "js_executed":
            return response["response"]
        else:
            raise Exception("JavaScript execution failed or returned no response.")

    def set_volume(self, volume):
        self.queue.put({
            "type": "set_voluem",
            "volume": volume
        })
        self.response_queue.get()

    async def wait_for_var(self, variable, value, timeout=5):
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            response = self.run_javascript(f"{variable};")
            await asyncio.sleep(0.01)
            if response == value:
                return True
        return False
        


from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager


class SeleniumLucyWebView:
    def __init__(self, driver="", fullscreen=False):
        self.driver = None
        if driver == "chrome":
            options = webdriver.ChromeOptions()
            options.add_experimental_option("excludeSwitches", ['enable-automation']);
            if fullscreen:
                options.add_argument("--kiosk")
            self.driver = webdriver.Chrome(
                options=options,
                service=ChromeService(ChromeDriverManager().install()))
            
        elif driver == "firefox":
            options = webdriver.FirefoxOptions()
            # THIS CURRENTLY DOES NOT WORK DUE TO FIREFOX NOT COMING WITH WIDEVINE DRM SUPPORT
            options.set_preference("browser.fullscreen.autohide", True)
            options.set_preference("media.eme.enabled", True)
            options.set_preference("media.gmp-manager.updateEnabled", True)
            self.driver = webdriver.Firefox(
                options=options,
                service=FirefoxService(GeckoDriverManager().install()))
            self.driver.fullscreen_window()

        index_path = "file://" + os.path.abspath("templates/index.html")
        self.show_url(index_path)

    def show_url(self, url):
        self.driver.get(url)

    def run_javascript(self, script):
        try:
            return self.driver.execute_script(script)
        except Exception as e:
            print(f"[WARN] JS Error: {e}")
            return None
        
    def set_volume(self, volume):
        try:
            self.run_javascript(f"LucyHub.setVolume({volume})")
        except Exception as e:
            print(f"[WARN] JS Error: {e}")

    def get_url(self):
        return self.driver.current_url
    
    async def wait_for_var(self, variable, value, timeout=5):
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            response = self.run_javascript(f"return {variable};")
            await asyncio.sleep(0.01)
            if response == value:
                return True
        return False

if __name__ == "__main__":
    lucy_webview = SeleniumLucyWebView(driver="firefox", fullscreen=True)
    while True:
        url = input("Enter URL to load in Lucy WebView (or 'exit' to quit): ")
        if url.lower() == 'exit':
            break
        lucy_webview.show_url(url)