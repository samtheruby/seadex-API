import re
import logging
from utils.episode_utils import EpisodeUtils

logger = logging.getLogger(__name__)

class TorrentProcessor:
    def __init__(self):
        self.episode_utils = EpisodeUtils()

    def is_movie_torrent(self, torrent_info, anime_format=None):
        """Determine if a torrent is for a movie based on stricter indicators"""
        
        # If we know from AniList that it's a movie format, trust it
        if anime_format == "MOVIE":
            return True
            
        # First check for season/episode indicators which would indicate it's NOT a movie
        season_episode_indicators = [
            r'S\d+', r'Season \d+',  # Season indicators
            r'E\d+', r'Episode \d+',  # Episode indicators
            r'Complete Series',
            r'Season Pack'
        ]
        
        for file_info in torrent_info.get('files', []):
            filename = file_info.get('name', '').lower()
            # If any file has season/episode markers, it's not a movie
            if any(re.search(pattern, filename, re.IGNORECASE) for pattern in season_episode_indicators):
                return False
        
        # Check file patterns for explicit movie indicators
        movie_indicators = [
            'movie', 'film', 'gekijo', 'gekijou', 'gekijouban',
            'theatrical', 'cinema', 'feature'
        ]
        
        for file_info in torrent_info.get('files', []):
            filename = file_info.get('name', '').lower()
            # Check for explicit movie keywords
            if any(indicator in filename for indicator in movie_indicators):
                return True
        
        # Don't use file size as an indicator anymore as it's unreliable
        return False

    def process_seadex_torrents(self, torrents, season_filter=None, episode_filter=None, anime_format=None):
        """Process Seadex torrent data using groupedUrl to determine release type"""
        processed_torrents = []
        
        for torrent in torrents:
            url = torrent.get("url", "")
            grouped_url = torrent.get("groupedUrl", "")
            
            # Skip non-Nyaa torrents
            if "nyaa.si/view/" not in url:
                logger.debug(f"Skipping non-nyaa torrent: {url}")
                continue
            
            # Extract nyaa ID
            match = re.search(r"nyaa.si/view/(\d+)", url)
            if not match:
                logger.debug(f"Could not extract nyaa ID from: {url}")
                continue
            
            nyaa_id = int(match.group(1))
            
            # Enhanced release type detection
            is_movie = self.is_movie_torrent(torrent, anime_format)
            
            if grouped_url == "" or grouped_url is None:
                is_season_pack = True
                logger.debug(f"Torrent {nyaa_id} identified as season pack (empty groupedUrl)")
            else:
                is_season_pack = False
                logger.debug(f"Torrent {nyaa_id} identified as individual episode (groupedUrl: {grouped_url})")
            
            # Override season pack detection for movies
            if is_movie:
                is_season_pack = False
                logger.debug(f"Torrent {nyaa_id} identified as movie")
            
            # Get basic torrent info
            torrent_info = {
                'nyaa_id': nyaa_id,
                'url': url,
                'grouped_url': grouped_url,
                'release_group': torrent.get('releaseGroup', ''),
                'dual_audio': torrent.get('dualAudio', False),
                'is_best': torrent.get('isBest', False),
                'info_hash': torrent.get('infoHash', ''),
                'files': torrent.get('files', []),
                'tracker': torrent.get('tracker', 'Nyaa'),
                'is_season_pack': is_season_pack,
                'is_movie': is_movie,
                'anime_format': anime_format,
                'episodes': [],
                'source_anilist_id': torrent.get('source_anilist_id')
            }
            
            # Process files to extract episode information
            total_size = 0
            episode_count = 0
            seasons_found = set()
            episodes_found = set()
            
            for file_info in torrent.get('files', []):
                filename = file_info.get('name', '')
                file_size = file_info.get('length', 0)
                total_size += file_size
                
                # For movies, don't try to extract episode info
                if is_movie:
                    episode_count += 1
                else:
                    # Extract episode info from filename
                    season_num, episode_num = self.episode_utils.extract_episode_info(filename)
                    
                    if episode_num:
                        episode_count += 1
                        episodes_found.add(episode_num)
                        if season_num:
                            seasons_found.add(season_num)
                        
                        # Store episode info
                        torrent_info['episodes'].append({
                            'filename': filename,
                            'season': season_num,
                            'episode': episode_num,
                            'size': file_size
                        })
            
            # Set torrent metadata
            torrent_info['total_size'] = total_size
            torrent_info['episode_count'] = episode_count
            torrent_info['seasons'] = list(seasons_found)
            torrent_info['episode_numbers'] = list(episodes_found)
            
            # Set season/episode info based on release type
            if is_movie:
                torrent_info['season'] = None
                torrent_info['episode'] = None
            elif is_season_pack:
                # Season pack - contains multiple episodes
                torrent_info['season'] = list(seasons_found)[0] if seasons_found else 1
                torrent_info['episode'] = None  # Season packs don't have a single episode
            else:
                # Individual episode
                torrent_info['season'] = list(seasons_found)[0] if seasons_found else 1
                torrent_info['episode'] = list(episodes_found)[0] if episodes_found else None
            
            # Apply filters based on release type
            should_include = True
            
            if should_include:
                processed_torrents.append(torrent_info)
                release_type = "movie" if is_movie else ("season pack" if is_season_pack else "individual episode")
                logger.debug(f"Including {release_type}: Season {torrent_info['season']}, Episodes: {torrent_info['episode_numbers']}")
        
        return processed_torrents
