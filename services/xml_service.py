import xml.etree.ElementTree as ET
import logging
from datetime import datetime
from services.nyaa_service import NyaaService

logger = logging.getLogger(__name__)

class XMLService:
    def __init__(self):
        self.nyaa_service = NyaaService()

    def build_caps_xml(self):
        """Build capabilities XML response"""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<caps>
  <server version="1.0" title="SeadexNab" strapline="Anime releases with the best video+subs" url="https://seadexnab.moe/"/>
  <limits max="9999" default="100"/>
  <retention days="9999"/>
  <registration available="no" open="yes"/>
  <searching>
    <search available="yes" supportedParams="q"/>
    <tv-search available="yes" supportedParams="q,season,ep"/>
    <movie-search available="yes" supportedParams="q"/>
  </searching>
  <categories>
    <category id="5000" name="Anime" description="Anime TV Shows"/>
    <category id="2000" name="Movies" description="Anime Movies"/>
  </categories>
</caps>'''

    def build_empty_rss(self, title="SeadexNab", description="No results found"):
        """Build empty RSS response"""
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="1.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/" xmlns:torznab="http://torznab.com/schemas/2015/feed">
<channel>
    <title>{title}</title>
    <link>https://releases.moe</link>
    <description>{description}</description>
    <newznab:response offset="0" total="0"/>
</channel>
</rss>'''

    def build_rss_enhanced(self, anilist_id, anime_name, processed_torrents, season=None, episode=None, 
                           anime_format=None, year=None, force_anime_category=False):
        """Enhanced RSS builder with movie support and proper categorization"""
        logger.debug(f"Building RSS for {anime_name} ({anime_format}) with {len(processed_torrents)} torrents, force_anime_category={force_anime_category}")
        
        rss = ET.Element("rss", version="1.0", attrib={
            "xmlns:atom": "http://www.w3.org/2005/Atom",
            "xmlns:newznab": "http://www.newznab.com/DTD/2010/feeds/attributes/",
            "xmlns:torznab": "http://torznab.com/schemas/2015/feed"
        })
        
        channel = ET.SubElement(rss, "channel")
        title_text = f"SeadexNab - {anime_name}"
        if season:
            title_text += f" - Season {season}"
        if episode:
            title_text += f" Episode {episode}"
        if anime_format == "MOVIE" and year:
            title_text += f" ({year}) [Movie]"
        
        ET.SubElement(channel, "title").text = title_text
        ET.SubElement(channel, "link").text = "https://releases.moe"
        ET.SubElement(channel, "description").text = f"Torrents for {anime_name} and related anime from releases.moe"

        valid_torrents = 0
        for torrent_info in processed_torrents:
            nyaa_id = torrent_info['nyaa_id']
            
            # Fetch additional metadata from Nyaa
            nyaa_metadata = self.nyaa_service.fetch_nyaa_metadata(nyaa_id)
            if not nyaa_metadata:
                nyaa_metadata = {
                    "title": f"{anime_name} - {torrent_info['release_group']}",
                    "seeders": 0,
                    "leechers": 0,
                    "size_bytes": torrent_info['total_size'],
                    "completed": 0,
                    "timestamp": int(datetime.now().timestamp()),
                }

            # Build title with improved episode info based on release type
            title = nyaa_metadata["title"]
            
            if (torrent_info.get('is_movie') or anime_format == "MOVIE") and year:
                title += f" ({year}) [Movie]"
            elif torrent_info.get('is_movie') or anime_format == "MOVIE":
                title += " [Movie]"
            elif torrent_info['is_season_pack']:
                if torrent_info['episode_numbers']:
                    episodes_str = f"Episodes {min(torrent_info['episode_numbers'])}-{max(torrent_info['episode_numbers'])}"
                    title += f" [{episodes_str}]"
                else:
                    title += f" [Season {torrent_info['season']}]" if torrent_info['seasons'] else " [Season Pack]"
            else:
                if torrent_info.get('episode'):
                    title += f" [S{torrent_info['season']:02d}E{torrent_info['episode']:02d}]"
                elif torrent_info.get('season'):
                    title += f" [Season {torrent_info['season']}]"

            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = title
            ET.SubElement(item, "link").text = torrent_info['url']
            ET.SubElement(item, "guid", isPermaLink="true").text = torrent_info['url']
            
            description = f"{title} - {nyaa_metadata.get('size', 'Unknown size')} - S:{nyaa_metadata['seeders']} L:{nyaa_metadata['leechers']}"
            if torrent_info['dual_audio']:
                description += " [Dual Audio]"
            if torrent_info['is_best']:
                description += " [Best]"
            if torrent_info.get('is_movie') or anime_format == "MOVIE":
                description += " [Movie]"
            elif torrent_info['is_season_pack']:
                description += " [Season Pack]"
            
            # Add source anime info if different from main
            source_id = torrent_info.get('source_anilist_id')
            if source_id and source_id != anilist_id:
                description += f" [Related Anime: {source_id}]"
                
            ET.SubElement(item, "description").text = description
            
            # Download and torrent info
            download_url = f"https://nyaa.si/download/{nyaa_id}.torrent"
            ET.SubElement(item, "enclosure", url=download_url, type="application/x-bittorrent")
            ET.SubElement(item, "comments").text = torrent_info['url']
            ET.SubElement(item, "size").text = str(nyaa_metadata["size_bytes"])
            
            # Assign category based on torrent type and force_anime_category flag
            if force_anime_category or not (torrent_info.get('is_movie') or anime_format == "MOVIE"):
                # TV Series or forced anime category
                ET.SubElement(item, "category").text = "Anime"
                category_id = "5000"
            else:
                # Movies
                ET.SubElement(item, "category").text = "Movies"
                category_id = "2000"
            
            ET.SubElement(item, "pubDate").text = datetime.fromtimestamp(nyaa_metadata["timestamp"]).strftime("%a, %d %b %Y %H:%M:%S GMT")
            
            # Torznab attributes
            ET.SubElement(item, "torznab:attr", name="category", value=category_id)
            if torrent_info['info_hash']:
                ET.SubElement(item, "torznab:attr", name="infohash", value=torrent_info['info_hash'])
            ET.SubElement(item, "torznab:attr", name="downloadvolumefactor", value="0")
            ET.SubElement(item, "torznab:attr", name="uploadvolumefactor", value="1")
            ET.SubElement(item, "torznab:attr", name="seeders", value=str(nyaa_metadata["seeders"]))
            ET.SubElement(item, "torznab:attr", name="peers", value=str(nyaa_metadata["seeders"] + nyaa_metadata["leechers"]))
            ET.SubElement(item, "torznab:attr", name="size", value=str(nyaa_metadata["size_bytes"]))
            ET.SubElement(item, "torznab:attr", name="files", value=str(torrent_info['episode_count']))
            ET.SubElement(item, "torznab:attr", name="grabs", value=str(nyaa_metadata["completed"]))
            
            # Special handling for movies in attributes
            if torrent_info.get('is_movie') or anime_format == "MOVIE":
                ET.SubElement(item, "torznab:attr", name="genre", value="Anime Movie")
                # Movies need season/episode for compatibility
                ET.SubElement(item, "torznab:attr", name="season", value="1")
                ET.SubElement(item, "torznab:attr", name="episode", value="1")
            else:
                if torrent_info.get('season'):
                    ET.SubElement(item, "torznab:attr", name="season", value=str(torrent_info['season']))
                if torrent_info.get('episode'):
                    ET.SubElement(item, "torznab:attr", name="episode", value=str(torrent_info['episode']))
            
            ET.SubElement(item, "torznab:attr", name="details", value=torrent_info['url'])
            
            if torrent_info['release_group']:
                ET.SubElement(item, "torznab:attr", name="group", value=torrent_info['release_group'])
            
            # Add source anime ID as additional attribute
            if source_id:
                ET.SubElement(item, "torznab:attr", name="anilist_id", value=str(source_id))
            
            valid_torrents += 1

        ET.SubElement(channel, "newznab:response", offset="0", total=str(valid_torrents))
        
        logger.debug(f"Built RSS with {valid_torrents} valid torrents")
        xml_str = ET.tostring(rss, encoding='utf-8').decode('utf-8')
        xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
        return xml_str
