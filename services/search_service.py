import requests
import logging
from services.anilist_service import AniListService
from services.seadex_service import SeadexService
from services.torrent_processor import TorrentProcessor

logger = logging.getLogger(__name__)

class SearchService:
    def __init__(self):
        self.anilist_service = AniListService()
        self.seadex_service = SeadexService()
        self.torrent_processor = TorrentProcessor()

    def perform_search(self, query, season=None, episode=None):
        """Main search function that returns processed torrent releases from all related anime"""
        logger.info(f"Performing search for: {query} (season={season}, episode={episode})")
        
        # Get AniList ID and all related IDs
        main_anilist_id, anime_name, all_anilist_ids = self.anilist_service.get_anilist_id_with_relations(query)
        if not main_anilist_id:
            logger.error(f"Could not find AniList ID for: {query}")
            return None, None, []
        
        logger.info(f"Found anime: {anime_name} (Main ID: {main_anilist_id})")
        logger.info(f"Searching across {len(all_anilist_ids)} related anime entries")
        
        # Get releases from seadex for all related anime
        torrents = self.seadex_service.get_all_releases(all_anilist_ids)
        
        if not torrents:
            logger.warning(f"No torrents found for {anime_name} and related anime")
            return main_anilist_id, anime_name, []
        
        # Process torrents with filtering
        processed_torrents = self.torrent_processor.process_seadex_torrents(torrents, season, episode)
        
        logger.info(f"Found {len(processed_torrents)} matching torrents after filtering")
        return main_anilist_id, anime_name, processed_torrents