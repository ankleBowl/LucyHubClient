from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.core.os_manager import ChromeType

from importlib import resources

import os
import asyncio

class SeleniumLucyWebView:
    def __init__(self, driver, fullscreen=False):
        self.driver = None
        if driver == "chrome" or driver == "chromium":
            options = webdriver.ChromeOptions()
            options.add_experimental_option("excludeSwitches", ['enable-automation']);
            if fullscreen:
                options.add_argument("--kiosk")
            if driver == "chromium":
                import shutil
                if shutil.which("chromium-browser"):
                    options.binary_location = shutil.which("chromium-browser")
                else:
                    options.binary_location = shutil.which("chromium")
                self.driver = webdriver.Chrome(
                    options=options)
            else:
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

        index_path = resources.files("lucyhubclient.templates").joinpath("index.html")
        index_path = "file://" + os.path.abspath(index_path)
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
    
    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

if __name__ == "__main__":
    lucy_webview = SeleniumLucyWebView(driver="chromium", fullscreen=True)
    while True:
        url = input("Enter URL to load in Lucy WebView (or 'exit' to quit): ")
        if url.lower() == 'exit':
            break
        lucy_webview.show_url(url)