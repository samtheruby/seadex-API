import requests
import logging
from typing import Dict, List
from services.anilist_service import AniListService
from services.seadex_service import SeadexService
from services.torrent_processor import TorrentProcessor
from services.mapping_service import MappingService

logger = logging.getLogger(__name__)

class SearchService:
    def __init__(self):
        self.anilist_service = AniListService()
        self.seadex_service = SeadexService()
        self.torrent_processor = TorrentProcessor()
        self.mapping_service = MappingService()

    def perform_search(self, query, season=None, episode=None, search_type="ANIME"):
        """Main search function with mapping support"""
        logger.info(f"Performing search for: {query} (season={season}, episode={episode}, type={search_type})")
        
        # Check for custom mapping first
        mapping = self.mapping_service.find_mapping(query)
        
        if mapping:
            logger.info(f"Found custom mapping for: {query}")
            
            # Get info from mapping
            main_anilist_id = mapping.get('anilist_id')
            anime_name = mapping.get('anime_name', query)
            anime_format = mapping.get('anime_format', 'TV')
            year = mapping.get('year')
            
            # Get custom torrents from mapping (these always override Seadex)
            custom_torrents = self.mapping_service.get_custom_torrents(mapping)
            
            # Check if we should ALSO query Seadex (in addition to custom torrents)
            if self.mapping_service.should_use_seadex(mapping):
                logger.debug("Mapping indicates to also include Seadex results")
                
                # Get AniList info and Seadex results
                anilist_result = self.anilist_service.get_anilist_id_with_relations(
                    anime_name, search_type
                )
                
                if len(anilist_result) == 5:
                    _, _, all_anilist_ids, seadex_format, seadex_year = anilist_result
                    
                    # Use mapping values, fill in missing with Seadex values
                    if not anime_format:
                        anime_format = seadex_format
                    if not year:
                        year = seadex_year
                    
                    # Get Seadex torrents
                    seadex_torrents = self.seadex_service.get_all_releases(all_anilist_ids)
                    processed_seadex = self.torrent_processor.process_seadex_torrents(
                        seadex_torrents, season, episode, anime_format
                    )
                    
                    # Get nyaa IDs from custom torrents to avoid duplicates
                    custom_nyaa_ids = {t['nyaa_id'] for t in custom_torrents}
                    
                    # Add Seadex torrents that aren't already in custom mapping
                    for torrent in processed_seadex:
                        if torrent.get('nyaa_id') not in custom_nyaa_ids:
                            custom_torrents.append(torrent)
            
            # Apply season/episode filters to custom torrents
            filtered_torrents = self._filter_torrents(custom_torrents, season, episode)
            
            # If we have movie format, ensure movie torrents are properly marked
            if anime_format == 'MOVIE':
                for torrent in filtered_torrents:
                    torrent['is_movie'] = True
            
            logger.info(f"Found {len(filtered_torrents)} torrents after mapping and filtering")
            return main_anilist_id, anime_name, filtered_torrents, anime_format, year
        
        # No mapping found, use original Seadex flow
        logger.debug("No mapping found, using standard Seadex flow")
        result = self.anilist_service.get_anilist_id_with_relations(query, search_type)
        
        # Handle the 5-tuple return value
        if len(result) == 5:
            main_anilist_id, anime_name, all_anilist_ids, anime_format, year = result
        else:
            # Fallback for old format
            main_anilist_id, anime_name, all_anilist_ids = result
            anime_format = None
            year = None
        
        if not main_anilist_id:
            logger.error(f"Could not find AniList ID for: {query}")
            return None, None, [], None, None
        
        logger.info(f"Found anime: {anime_name} ({anime_format}) (Main ID: {main_anilist_id}, Year: {year})")
        logger.info(f"Searching across {len(all_anilist_ids)} related anime entries")
        
        # Get releases from seadex for all related anime
        torrents = self.seadex_service.get_all_releases(all_anilist_ids)
        
        if not torrents:
            logger.warning(f"No torrents found for {anime_name} and related anime")
            return main_anilist_id, anime_name, [], anime_format, year
        
        # Process torrents with enhanced movie support
        processed_torrents = self.torrent_processor.process_seadex_torrents(
            torrents, season, episode, anime_format
        )
        
        logger.info(f"Found {len(processed_torrents)} matching torrents after filtering")
        return main_anilist_id, anime_name, processed_torrents, anime_format, year
    
    def _filter_torrents(self, torrents: List[Dict], season=None, episode=None) -> List[Dict]:
        """Filter torrents based on season and episode criteria"""
        if not season and not episode:
            return torrents
        
        filtered = []
        for torrent in torrents:
            should_include = True
            
            # Season filtering
            if season and torrent.get('season') != season:
                # Check if it's a season pack that includes the requested season
                if not (torrent.get('is_season_pack') and season in torrent.get('seasons', [])):
                    should_include = False
            
            # Episode filtering
            if episode and should_include:
                episode_numbers = torrent.get('episode_numbers', [])
                if episode_numbers and episode not in episode_numbers:
                    should_include = False
            
            if should_include:
                filtered.append(torrent)
        
        return filtered
