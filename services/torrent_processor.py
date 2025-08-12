import re
import logging
from utils.episode_utils import EpisodeUtils

logger = logging.getLogger(__name__)

class TorrentProcessor:
    def __init__(self):
        self.episode_utils = EpisodeUtils()

    def process_seadex_torrents(self, torrents, season_filter=None, episode_filter=None):
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
            
            # Determine release type based on groupedUrl
            if grouped_url == "" or grouped_url is None:
                # Empty groupedUrl = Season pack
                is_season_pack = True
                logger.debug(f"Torrent {nyaa_id} identified as season pack (empty groupedUrl)")
            else:
                # Non-empty groupedUrl = Individual episode
                is_season_pack = False
                logger.debug(f"Torrent {nyaa_id} identified as individual episode (groupedUrl: {grouped_url})")
            
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
            if is_season_pack:
                # Season pack - contains multiple episodes
                torrent_info['season'] = list(seasons_found)[0] if seasons_found else 1
                torrent_info['episode'] = None  # Season packs don't have a single episode
            else:
                # Individual episode
                torrent_info['season'] = list(seasons_found)[0] if seasons_found else 1
                torrent_info['episode'] = list(episodes_found)[0] if episodes_found else None
            
            # Apply filters if needed (currently commented out in original code)
            should_include = True
            
            if should_include:
                processed_torrents.append(torrent_info)
                release_type = "season pack" if is_season_pack else "individual episode"
                logger.debug(f"Including {release_type}: Season {torrent_info['season']}, Episodes: {torrent_info['episode_numbers']}")
        
        return processed_torrents