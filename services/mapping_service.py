import json
import os
import re
import logging
import requests
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class MappingService:
    def __init__(self, mapping_file_path='mapping.json', remote_url=None, update_interval_hours=1):
        self.mapping_file_path = mapping_file_path
        self.remote_url = remote_url or 'https://raw.githubusercontent.com/samtheruby/seadex-API-Mappings/refs/heads/main/mapping.json'
        self.update_interval_hours = update_interval_hours
        self.mappings = {}
        self.search_index = {}
        self.settings = {}
        self.last_update = None
        self.update_thread = None
        self.stop_updates = False
        
        # Load mappings on initialization
        self.initialize_mappings()
        
        # Start background update thread
        self.start_auto_updates()
    
    def initialize_mappings(self):
        """Initialize mappings - download from remote or use local"""
        # First, try to download from remote
        if self.download_remote_mapping():
            logger.info("Successfully downloaded remote mapping file")
        elif os.path.exists(self.mapping_file_path):
            # Fall back to local file if remote download fails
            logger.info("Using existing local mapping file")
            self.load_mappings()
        else:
            # Create default if nothing exists
            logger.info("No mapping file found, creating default")
            self.create_default_mapping_file()
            self.load_mappings()
    
    def download_remote_mapping(self) -> bool:
        """Download mapping file from remote URL"""
        try:
            logger.info(f"Downloading mapping file from: {self.remote_url}")
            response = requests.get(self.remote_url, timeout=30)
            response.raise_for_status()
            
            # Validate JSON
            mapping_data = response.json()
            
            # Save to local file
            with open(self.mapping_file_path, 'w', encoding='utf-8') as f:
                json.dump(mapping_data, f, indent=2, ensure_ascii=False)
            
            # Load the new mappings
            self.mappings = mapping_data.get('mappings', {})
            self.settings = mapping_data.get('settings', {
                'fallback_to_seadex': True,
                'priority': 'mapping_first'
            })
            self._build_search_index()
            
            self.last_update = datetime.now()
            logger.info(f"Successfully updated mappings from remote. Found {len(self.mappings)} entries")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download remote mapping file: {e}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in remote mapping file: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error downloading mapping file: {e}")
            return False
    
    def start_auto_updates(self):
        """Start background thread for automatic updates"""
        def update_loop():
            while not self.stop_updates:
                # Wait for the update interval
                time.sleep(self.update_interval_hours * 3600)  # Convert hours to seconds
                
                if not self.stop_updates:
                    logger.info("Running scheduled mapping update")
                    if self.download_remote_mapping():
                        logger.info("Scheduled update completed successfully")
                    else:
                        logger.warning("Scheduled update failed, will retry next interval")
        
        self.update_thread = threading.Thread(target=update_loop, daemon=True)
        self.update_thread.start()
        logger.info(f"Started auto-update thread (interval: {self.update_interval_hours} hours)")
    
    def stop_auto_updates(self):
        """Stop the background update thread"""
        self.stop_updates = True
        if self.update_thread:
            self.update_thread.join(timeout=5)
    
    def force_update(self) -> bool:
        """Force an immediate update from remote"""
        logger.info("Forcing immediate mapping update")
        return self.download_remote_mapping()
    
    def get_last_update_time(self) -> Optional[datetime]:
        """Get the last successful update time"""
        return self.last_update
    
    def load_mappings(self):
        """Load mappings from local JSON file"""
        if not os.path.exists(self.mapping_file_path):
            logger.warning(f"Local mapping file not found at {self.mapping_file_path}")
            return
        
        try:
            with open(self.mapping_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.mappings = data.get('mappings', {})
                self.settings = data.get('settings', {
                    'fallback_to_seadex': True,
                    'priority': 'mapping_first'
                })
                self._build_search_index()
                logger.info(f"Loaded {len(self.mappings)} mapping entries from local file")
        except Exception as e:
            logger.error(f"Error loading local mapping file: {e}")
            self.mappings = {}
            self.settings = {}
            self.search_index = {}
    
    def _build_search_index(self):
        """Build search index for fast lookup including alternative search terms"""
        self.search_index = {}
        
        for primary_key, mapping_data in self.mappings.items():
            # Index by primary key
            normalized_key = self._normalize_search_term(primary_key)
            self.search_index[normalized_key] = primary_key
            
            # Index by alternative search terms
            for alt_term in mapping_data.get('also_search', []):
                normalized_alt = self._normalize_search_term(alt_term)
                self.search_index[normalized_alt] = primary_key
    
    def _normalize_search_term(self, term: str) -> str:
        """Normalize search terms for consistent matching"""
        # Convert to lowercase, remove special characters, collapse spaces
        normalized = term.lower()
        # Keep alphanumeric and spaces only
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        # Collapse multiple spaces to single space
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    def find_mapping(self, query: str) -> Optional[Dict]:
        """Find a mapping for the given search query"""
        normalized_query = self._normalize_search_term(query)
        
        # Direct match in search index
        if normalized_query in self.search_index:
            primary_key = self.search_index[normalized_query]
            logger.debug(f"Found direct mapping for '{query}' -> '{primary_key}'")
            return self.mappings[primary_key]
        
        # Partial match - check if query contains or is contained in indexed terms
        for indexed_term, primary_key in self.search_index.items():
            # Check both directions for flexibility
            if indexed_term in normalized_query or normalized_query in indexed_term:
                logger.debug(f"Found partial mapping for '{query}' -> '{primary_key}'")
                return self.mappings[primary_key]
        
        logger.debug(f"No mapping found for: {query}")
        return None
    
    def get_custom_torrents(self, mapping: Dict) -> List[Dict]:
        """Get custom torrent entries from a mapping with complete names"""
        custom_torrents = []
        
        anime_format = mapping.get('anime_format', 'TV')
        
        for torrent in mapping.get('torrents', []):
            if torrent.get('nyaa_id') and torrent.get('name'):
                # Parse season and episode info from the custom name
                parsed_info = self._parse_torrent_name(torrent['name'])
                
                custom_torrent = {
                    'nyaa_id': torrent['nyaa_id'],
                    'url': f"https://nyaa.si/view/{torrent['nyaa_id']}",
                    'custom_name': torrent['name'],  # Full custom name with all info
                    'release_group': parsed_info['release_group'],
                    'is_best': 'best' in torrent['name'].lower(),
                    'dual_audio': 'dual audio' in torrent['name'].lower(),
                    'info_hash': '',
                    'files': [],
                    'tracker': 'Nyaa',
                    'is_season_pack': parsed_info['is_season_pack'],
                    'is_movie': anime_format == 'MOVIE',
                    'anime_format': anime_format,
                    'episodes': [],
                    'total_size': 0,
                    'episode_count': parsed_info['episode_count'],
                    'seasons': parsed_info['seasons'],
                    'episode_numbers': parsed_info['episode_numbers'],
                    'season': parsed_info['season'],
                    'episode': parsed_info['episode'],
                    'is_custom_mapping': True
                }
                custom_torrents.append(custom_torrent)
        
        return custom_torrents
    
    def _parse_torrent_name(self, name: str) -> Dict:
        """Parse torrent name to extract season, episode, and other info"""
        result = {
            'release_group': 'Unknown',
            'season': 1,
            'episode': None,
            'seasons': [],
            'episode_numbers': [],
            'episode_count': 0,
            'is_season_pack': False
        }
        
        # Extract release group [Group] at the beginning
        group_match = re.match(r'\[([^\]]+)\]', name)
        if group_match:
            result['release_group'] = group_match.group(1)
        
        # Check for season info
        season_patterns = [
            r'Season\s*(\d+)',
            r'S(\d+)',
            r's(\d+)',
        ]
        
        for pattern in season_patterns:
            match = re.search(pattern, name, re.IGNORECASE)
            if match:
                result['season'] = int(match.group(1))
                result['seasons'] = [result['season']]
                break
        
        # Check for episode ranges (e.g., "01-12", "1-24", "Episodes 1-12")
        episode_range_match = re.search(r'(\d+)\s*-\s*(\d+)', name)
        if episode_range_match:
            start_ep = int(episode_range_match.group(1))
            end_ep = int(episode_range_match.group(2))
            result['episode_numbers'] = list(range(start_ep, end_ep + 1))
            result['episode_count'] = len(result['episode_numbers'])
            result['is_season_pack'] = True
        else:
            # Check for single episode
            episode_patterns = [
                r'E(\d+)',
                r'Episode\s*(\d+)',
                r'Ep\.?\s*(\d+)',
            ]
            
            for pattern in episode_patterns:
                match = re.search(pattern, name, re.IGNORECASE)
                if match:
                    result['episode'] = int(match.group(1))
                    result['episode_numbers'] = [result['episode']]
                    result['episode_count'] = 1
                    break
        
        # If no episode info found but it says "Complete" or "Batch", assume season pack
        if not result['episode_numbers'] and any(word in name.lower() for word in ['complete', 'batch', 'full']):
            result['is_season_pack'] = True
            # Estimate episodes based on common anime season lengths
            result['episode_count'] = 12  # Default assumption
            result['episode_numbers'] = list(range(1, 13))
        
        return result
    
    def should_use_seadex(self, mapping: Optional[Dict]) -> bool:
        """Determine if we should also query Seadex"""
        if not mapping:
            return self.settings.get('fallback_to_seadex', True)
        
        # Check if mapping explicitly wants to also use Seadex
        return mapping.get('use_seadex_also', False)
    
    def create_default_mapping_file(self):
        """Create a default mapping file with examples"""
        default_mappings = {
            "mappings": {
                "example anime": {
                    "anilist_id": 12345,
                    "anime_name": "Example Anime",
                    "anime_format": "TV",
                    "year": 2024,
                    "also_search": [
                        "example show",
                        "eks anime"
                    ],
                    "torrents": [
                        {
                            "nyaa_id": 1234567,
                            "name": "[ExampleGroup] Example Anime Season 1 (01-12) (BD 1080p HEVC 10-bit FLAC) [Dual Audio] [Complete]"
                        }
                    ]
                }
            },
            "settings": {
                "fallback_to_seadex": true,
                "priority": "mapping_first",
                "remote_url": "https://raw.githubusercontent.com/samtheruby/seadex-API-Mappings/refs/heads/main/mapping.json",
                "update_interval_hours": 1
            }
        }
        
        try:
            with open(self.mapping_file_path, 'w', encoding='utf-8') as f:
                json.dump(default_mappings, f, indent=2, ensure_ascii=False)
            logger.info(f"Created default mapping file at {self.mapping_file_path}")
        except Exception as e:
            logger.error(f"Error creating default mapping file: {e}")
    
    def reload_mappings(self):
        """Reload mappings from file (useful for hot-reloading)"""
        logger.info("Reloading mappings from file")
        self.load_mappings()
    
    def get_stats(self) -> Dict:
        """Get statistics about the current mappings"""
        return {
            'total_mappings': len(self.mappings),
            'total_search_terms': len(self.search_index),
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'remote_url': self.remote_url,
            'update_interval_hours': self.update_interval_hours
        }
