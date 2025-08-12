import requests
import logging
from bs4 import BeautifulSoup
from datetime import datetime
from utils.size_utils import SizeUtils

logger = logging.getLogger(__name__)

class NyaaService:
    def __init__(self):
        self.base_url = "https://nyaa.si"
        self.size_utils = SizeUtils()

    def fetch_nyaa_metadata(self, nyaa_id: int) -> dict | None:
        """Fetch additional metadata from Nyaa (seeders, leechers, etc.)"""
        url = f"{self.base_url}/view/{nyaa_id}"
        logger.debug(f"Fetching Nyaa metadata for ID: {nyaa_id}")
        
        try:
            res = requests.get(url)
            res.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch Nyaa page {nyaa_id}: {e}")
            return None

        soup = BeautifulSoup(res.text, "html.parser")

        def get_text(selector):
            el = soup.select_one(selector)
            return el.text.strip() if el else ""

        title = get_text("body > div > div:nth-child(1) > div.panel-heading > h3")
        date_str = get_text("div.row:nth-child(1) > div:nth-child(4)")
        seeders = get_text("div.row:nth-child(2) > div:nth-child(4) > span:nth-child(1)")
        leechers = get_text("div.row:nth-child(3) > div:nth-child(4) > span:nth-child(1)")
        size_str = get_text("div.row:nth-child(4) > div:nth-child(2)")
        completed = get_text("div.row:nth-child(4) > div:nth-child(4)")

        # Convert numeric values safely
        try:
            seeders = int(seeders)
        except:
            seeders = 0
        try:
            leechers = int(leechers)
        except:
            leechers = 0
        try:
            completed = int(completed)
        except:
            completed = 0

        size_in_bytes = self.size_utils.size_to_bytes(size_str)

        timestamp = None
        try:
            dt_str = date_str.replace(" UTC", "")
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            timestamp = int(dt.timestamp())
        except:
            timestamp = int(datetime.now().timestamp())

        return {
            "title": title,
            "date": date_str,
            "seeders": seeders,
            "leechers": leechers,
            "size": size_str,
            "size_bytes": size_in_bytes,
            "completed": completed,
            "timestamp": timestamp,
        }