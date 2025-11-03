import requests
import logging

logger = logging.getLogger(__name__)

class SeadexService:
    def __init__(self):
        self.base_url = "https://releases.moe/api/collections/entries/records"

    def get_all_releases(self, anilist_ids):
        """Get releases for multiple AniList IDs"""
        all_torrents = []
        
        for anilist_id in anilist_ids:
            url = f"{self.base_url}?filter=alID={anilist_id}&expand=trs"
            logger.debug(f"Fetching releases for AniList ID: {anilist_id}")
            
            try:
                res = requests.get(url)
                if res.status_code != 200:
                    logger.error(f"Failed to fetch releases for ID {anilist_id}: HTTP {res.status_code}")
                    continue
                
                data = res.json()
                
                items = data.get("items", [])
                if not items:
                    logger.debug(f"No items found for AniList ID: {anilist_id}")
                    continue
                
                # Extract all torrents from all entries for this ID
                for item in items:
                    trs = item.get("expand", {}).get("trs", [])
                    # Add the AniList ID to each torrent for tracking
                    for torrent in trs:
                        torrent['source_anilist_id'] = anilist_id
                    all_torrents.extend(trs)
                    
            except Exception as e:
                logger.error(f"Error fetching releases for ID {anilist_id}: {e}")
                continue
        
        logger.debug(f"Found {len(all_torrents)} total torrent records across all related anime")
        return all_torrents