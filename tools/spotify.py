from tools.lucy_client_module import LucyClientModule
import asyncio
import os

class LSpotifyClient(LucyClientModule):
    def __init__(self):
        super().__init__("spotify")

    async def handle_message(self, message):
        if message["message"] == "INIT_SPOTIFY_STREAMING":
            self.log("Initializing Spotify streaming...")
            start_time = asyncio.get_event_loop().time()
            url = f"{os.getenv('LUCY_SERVER_HTTP_URL')}/v1/{os.getenv("USER_ID")}/module/spotify/web_player"
            iframe_url = self.lucy_webview.run_javascript(f"LucyHub.getIFrameURL()")
            print(f"Current iframe URL: {iframe_url}")
            if iframe_url != url:
                print(f"Loading new URL: {url}")
                self.lucy_webview.run_javascript(f"LucyHub.loadIFrame('{url}', false)")
                print("Waiting for Spotify Web Playback SDK to be ready...")
                await self.get_lucy_webview().wait_for_var(f"LucyHub.getFlag('spotify_web_playback_sdk_ready')", True, timeout=5)
                print("Spotify Web Playback SDK is ready.")

            print("Sending trigger to IFrame to connect...")
            self.lucy_webview.run_javascript("LucyHub.sendTriggerToIFrame('connect')")
            is_ready = await self.get_lucy_webview().wait_for_var("LucyHub.getFlag('spotify_ready')", True, timeout=3)
            print(f"Spotify ready status: {is_ready}")

            end_time = asyncio.get_event_loop().time()
            self.log(f"Spotify streaming initialized in {end_time - start_time:.2f} seconds.")

            await asyncio.sleep(0.5)  # Allow time for the UI to update

            if is_ready:
                await self.send_socket_message({
                    "message": "SPOTIFY_STREAMING_INITIATED"
                })
            else:
                self.log("Failed to initialize Spotify streaming within 3 seconds.")
                await self.send_socket_message({
                    "message": "SPOTIFY_STREAMING_FAILED"
                })


            # self.log("Initializing Spotify streaming...")
            # start_time = asyncio.get_event_loop().time()
            # url = f"http{get_url()}/v1/{USER_ID}/module/spotify"
            # if self.lucy_webview.get_url() != url:
            #     self.lucy_webview.show_url(f"http{get_url()}/v1/{USER_ID}/module/spotify")
            #     await self.get_lucy_webview().wait_for_var("isPlaybackSDKReady", True, timeout=5)

            # self.lucy_webview.run_javascript("connect()")
            # is_ready = await self.get_lucy_webview().wait_for_var("isPlayerReady", True, timeout=3)
            # end_time = asyncio.get_event_loop().time()
            # self.log(f"Spotify streaming initialized in {end_time - start_time:.2f} seconds.")

            # if is_ready:
            #     await self.send_socket_message({
            #         "message": "SPOTIFY_STREAMING_INITIATED"
            #     })
            # else:
            #     self.log("Failed to initialize Spotify streaming within 3 seconds.")
            #     await self.send_socket_message({
            #         "message": "SPOTIFY_STREAMING_FAILED"
            #     })