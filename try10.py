from flask import Flask, request, Response
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, UTC
import re
from bs4 import BeautifulSoup
import logging

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

TV_CATEGORY_ID = "5000"  # Anime TV
MOVIE_CATEGORY_ID = "2000"  # Anime Movies

# --- AniList GraphQL query to get AniList ID ---
def get_anilist_id_with_relations(anime_name, search_type="ANIME"):
    """Get AniList ID, related media, and year with enhanced movie support"""
    logger.debug(f"Searching AniList for: {anime_name} (type: {search_type})")
    
    query = '''
    query ($search: String, $type: MediaType) {
      Page(page: 1, perPage: 15) {
        media(search: $search, type: $type, sort: [POPULARITY_DESC, START_DATE_DESC]) {
          id
          title {
            romaji
            english
            native
          }
          startDate {
            year
            month
            day
          }
          endDate {
            year
          }
          popularity
          format
          status
          episodes
          duration
          genres
          relations {
            edges {
              relationType
              node {
                id
                title {
                  romaji
                  english
                  native
                }
                format
                startDate {
                  year
                }
                episodes
                duration
              }
            }
          }
        }
      }
    }
    '''
    variables = {'search': anime_name, 'type': search_type}
    url = "https://graphql.anilist.co"
    
    try:
        res = requests.post(url, json={'query': query, 'variables': variables})
        res.raise_for_status()
        data = res.json()
        logger.debug(f"AniList response: {data}")
        
        media_list = data.get("data", {}).get("Page", {}).get("media", [])
        if not media_list:
            logger.debug("No anime found in AniList")
            return None, None, [], None, None
        
        # Smart selection logic for movies vs series
        main_anime = None
        
        # Special handling for well-known movies
        if anime_name.lower() in ["akira", "spirited away", "your name", "weathering with you"]:
            # Prefer movies for these titles
            for media in media_list:
                if media.get("format") == "MOVIE":
                    main_anime = media
                    break
        
        # For movie searches, prefer MOVIE format
        if search_type == "ANIME" and not main_anime:
            for media in media_list:
                if media.get("format") == "MOVIE":
                    main_anime = media
                    break
        
        # Fallback to first result
        if not main_anime:
            main_anime = media_list[0]
        
        # Collect related media based on type
        all_related_ids = [main_anime["id"]]
        main_title = main_anime["title"]["romaji"]
        main_format = main_anime.get("format", "")
        main_year = main_anime.get("startDate", {}).get("year")
        
        logger.debug(f"Main anime format: {main_format}, year: {main_year}")
        
        # Get relations - different logic for movies vs series
        relations = main_anime.get("relations", {}).get("edges", [])
        for relation in relations:
            relation_type = relation.get("relationType", "")
            related_media = relation.get("node", {})
            related_format = related_media.get("format", "")
            
            if main_format == "MOVIE":
                # For movies, include sequels, prequels, and related movies
                if relation_type in ["SEQUEL", "PREQUEL", "SIDE_STORY", "ALTERNATIVE"] and related_format == "MOVIE":
                    related_id = related_media.get("id")
                    if related_id and related_id not in all_related_ids:
                        all_related_ids.append(related_id)
                        related_title = related_media.get("title", {}).get("romaji", "")
                        logger.debug(f"Found related movie: {related_title} (ID: {related_id}, Type: {relation_type})")
            else:
                # For series, use existing logic
                if relation_type in ["SEQUEL", "PREQUEL"]:
                    if related_format in ["TV", "MOVIE"]:
                        related_id = related_media.get("id")
                        if related_id and related_id not in all_related_ids:
                            all_related_ids.append(related_id)
                            related_title = related_media.get("title", {}).get("romaji", "")
                            logger.debug(f"Found related season: {related_title} (ID: {related_id}, Type: {relation_type})")
        
        logger.debug(f"Found main anime: {main_title} ({main_format}) with {len(all_related_ids)} total entries")
        return main_anime["id"], main_title, all_related_ids, main_format, main_year
        
    except Exception as e:
        logger.error(f"Error querying AniList: {e}")
        return None, None, [], None, None

# --- Parse size string like '1.23 GiB' into bytes ---
def size_to_bytes(size_str):
    m = re.match(r"([\d\.]+)\s*(GiB|MiB|KiB|TiB|B)", size_str, re.I)
    if m:
        num, unit = m.groups()
        num = float(num)
        unit = unit.lower()
        multipliers = {
            'b': 1,
            'kib': 1024,
            'mib': 1024**2,
            'gib': 1024**3,
            'tib': 1024**4
        }
        return int(num * multipliers.get(unit, 1))
    return 0

# --- Extract episode info from filename ---
def extract_episode_info(filename):
    """Extract season and episode info from filename"""
    patterns = [
        r'S(\d+)E(\d+)',  # S01E01
        r'Season\s*(\d+).*?E(\d+)',  # Season 1 E01
        r'(\d+)x(\d+)',  # 1x01
        r'S(\d+).*?(\d+)',  # S01 01 (less reliable)
        r'E(\d+)',  # Just E01 (episode only)
        r'Episode\s*(\d+)',  # Episode 01
        r'Ep\.?\s*(\d+)',  # Ep. 01 or Ep 01
        r'(\d+)',  # Just a number (least reliable)
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                # Season and episode
                return int(groups[0]), int(groups[1])
            elif len(groups) == 1:
                # Episode only
                return None, int(groups[0])
    
    return None, None

def is_movie_torrent(torrent_info, anime_format=None):
    """Determine if a torrent is for a movie based on stricter indicators"""
    
    # If we know from AniList that it's a movie format, trust it
    if anime_format == "MOVIE":
        return True
    
    # Check file patterns for movie indicators
    movie_indicators = [
        'movie', 'film', 'gekijo', 'gekijou', 'gekijouban', 
        'theatrical', 'cinema', 'feature'
    ]
    
    for file_info in torrent_info.get('files', []):
        filename = file_info.get('name', '').lower()
        
        # Check for explicit movie keywords
        if any(indicator in filename for indicator in movie_indicators):
            return True
    
    # Only consider large file sizes if episode count is very low
    episode_count = torrent_info.get('episode_count', 0)
    if episode_count <= 1:  # Stricter condition to avoid misclassifying OVAs/specials
        for file_info in torrent_info.get('files', []):
            file_size = file_info.get('length', 0)
            if file_size > 1024**3:  # 1GB
                return True
    
    return False

# --- Process Seadex torrent data ---
def process_seadex_torrents(torrents, season_filter=None, episode_filter=None, anime_format=None):
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
        is_movie = is_movie_torrent(torrent, anime_format)
        
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
            'episodes': []
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
                season_num, episode_num = extract_episode_info(filename)
                
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

# --- Scrape Nyaa page for additional metadata ---
def fetch_nyaa_metadata(nyaa_id: int) -> dict | None:
    """Fetch additional metadata from Nyaa (seeders, leechers, etc.)"""
    url = f"https://nyaa.si/view/{nyaa_id}"
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

    size_in_bytes = size_to_bytes(size_str)

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

# --- Fetch releases.moe entries for an AniList ID ---
def get_all_releases(anilist_ids):
    """Get releases for multiple AniList IDs"""
    all_torrents = []
    
    for anilist_id in anilist_ids:
        url = f"https://releases.moe/api/collections/entries/records?filter=alID={anilist_id}&expand=trs"
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

# --- Search function ---
def perform_search(query, season=None, episode=None, search_type="ANIME"):
    """Main search function that returns processed torrent releases from all related anime"""
    logger.info(f"Performing search for: {query} (season={season}, episode={episode}, type={search_type})")
    
    # Get AniList ID and all related IDs
    result = get_anilist_id_with_relations(query, search_type)
    if len(result) == 5:
        main_anilist_id, anime_name, all_anilist_ids, anime_format, year = result
    else:
        main_anilist_id, anime_name, all_anilist_ids = result
        anime_format = None
        year = None
    
    if not main_anilist_id:
        logger.error(f"Could not find AniList ID for: {query}")
        return None, None, [], None, None
    
    logger.info(f"Found anime: {anime_name} ({anime_format}) (Main ID: {main_anilist_id}, Year: {year})")
    logger.info(f"Searching across {len(all_anilist_ids)} related anime entries")
    
    # Get releases from seadex for all related anime
    torrents = get_all_releases(all_anilist_ids)
    
    if not torrents:
        logger.warning(f"No torrents found for {anime_name} and related anime")
        return main_anilist_id, anime_name, [], anime_format, year
    
    # Process torrents with enhanced movie support
    processed_torrents = process_seadex_torrents(torrents, season, episode, anime_format)
    
    logger.info(f"Found {len(processed_torrents)} matching torrents after filtering")
    return main_anilist_id, anime_name, processed_torrents, anime_format, year

# --- Build consistent caps XML ---
def build_caps_xml():
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

# --- Build empty RSS response ---
def build_empty_rss(title="SeadexNab", description="No results found"):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="1.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/" xmlns:torznab="http://torznab.com/schemas/2015/feed">
<channel>
    <title>{title}</title>
    <link>https://releases.moe</link>
    <description>{description}</description>
    <newznab:response offset="0" total="0"/>
</channel>
</rss>'''

# --- Build Torznab XML RSS from processed data ---
def build_rss_enhanced(anilist_id, anime_name, processed_torrents, season=None, episode=None, anime_format=None, year=None, force_anime_category=False):
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
        nyaa_metadata = fetch_nyaa_metadata(nyaa_id) or {
            "title": f"{anime_name} - {torrent_info['release_group']}",
            "seeders": 0,
            "leechers": 0,
            "size_bytes": torrent_info['total_size'],
            "completed": 0,
            "timestamp": int(datetime.now().timestamp()),
        }

        title = nyaa_metadata["title"]
        if (torrent_info['is_movie'] or anime_format == "MOVIE") and year:
            title += f" ({year}) [Movie]"
        elif torrent_info['is_movie'] or anime_format == "MOVIE":
            title += " [Movie]"
        elif torrent_info['is_season_pack']:
            title += f" [Season {torrent_info['season']}]" if torrent_info['seasons'] else " [Season Pack]"
        else:
            if torrent_info['episode']:
                title += f" [S{torrent_info['season']:02d}E{torrent_info['episode']:02d}]"
            elif torrent_info['season']:
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
        if torrent_info['is_movie'] or anime_format == "MOVIE":
            description += " [Movie]"
        elif torrent_info['is_season_pack']:
            description += " [Season Pack]"
        
        source_id = torrent_info.get('source_anilist_id')
        if source_id and source_id != anilist_id:
            description += f" [Related Anime: {source_id}]"
            
        ET.SubElement(item, "description").text = description
        download_url = f"https://nyaa.si/download/{nyaa_id}.torrent"
        ET.SubElement(item, "enclosure", url=download_url, type="application/x-bittorrent")
        ET.SubElement(item, "comments").text = torrent_info['url']
        ET.SubElement(item, "size").text = str(nyaa_metadata["size_bytes"])
        
        # Assign category based on torrent type and force_anime_category flag
        if force_anime_category or not (torrent_info['is_movie'] or anime_format == "MOVIE"):
            ET.SubElement(item, "category").text = "Anime"
            ET.SubElement(item, "torznab:attr", name="category", value="5000")
        else:
            ET.SubElement(item, "category").text = "Movies"
            ET.SubElement(item, "torznab:attr", name="category", value="2000")
        
        ET.SubElement(item, "pubDate").text = datetime.fromtimestamp(nyaa_metadata["timestamp"]).strftime("%a, %d %b %Y %H:%M:%S GMT")
        
        # Torznab attributes
        if torrent_info['info_hash']:
            ET.SubElement(item, "torznab:attr", name="infohash", value=torrent_info['info_hash'])
        ET.SubElement(item, "torznab:attr", name="downloadvolumefactor", value="0")
        ET.SubElement(item, "torznab:attr", name="uploadvolumefactor", value="1")
        ET.SubElement(item, "torznab:attr", name="seeders", value=str(nyaa_metadata["seeders"]))
        ET.SubElement(item, "torznab:attr", name="peers", value=str(nyaa_metadata["seeders"] + nyaa_metadata["leechers"]))
        ET.SubElement(item, "torznab:attr", name="size", value=str(nyaa_metadata["size_bytes"]))
        ET.SubElement(item, "torznab:attr", name="files", value=str(torrent_info['episode_count']))
        ET.SubElement(item, "torznab:attr", name="grabs", value=str(nyaa_metadata["completed"]))
        
        if torrent_info['is_movie'] or anime_format == "MOVIE":
            ET.SubElement(item, "torznab:attr", name="genre", value="Anime Movie")
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
        if source_id:
            ET.SubElement(item, "torznab:attr", name="anilist_id", value=str(source_id))
        
        valid_torrents += 1

    ET.SubElement(channel, "newznab:response", offset="0", total=str(valid_torrents))
    xml_str = ET.tostring(rss, encoding='utf-8').decode('utf-8')
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
    return xml_str

# --- Enhanced search query processing ---
def process_search_query(query_param, season=None, episode=None):
    """Process search query with enhanced Sonarr support and better movie handling"""
    if not query_param:
        return "Spirited Away"  # Default fallback
    
    query = str(query_param).strip()  # Ensure it's a string
    original_query = query
    
    # Handle various formats that Sonarr might send
    if ' : ' in query:
        query = query.split(' : ')[0]
    
    # Remove year info like (2023) or 2021 at the end - but store it for fallback
    year_match = re.search(r'(\d{4})', query)
    extracted_year = year_match.group(1) if year_match else None
    
    # Remove year from query
    query = re.sub(r'\s*\(\d{4}\)$', '', query)
    query = re.sub(r'\s+\d{4}$', '', query)
    
    # Remove season indicators from the title itself
    query = re.sub(r'\s+S\d+$', '', query, flags=re.IGNORECASE)
    query = re.sub(r'\s+Season\s*\d+$', '', query, flags=re.IGNORECASE)
    
    # Remove episode patterns from title
    query = re.sub(r'\s+E\d+$', '', query, flags=re.IGNORECASE)
    query = re.sub(r'\s+Episode\s*\d+$', '', query, flags=re.IGNORECASE)
    
    query = query.strip()
    
    # Special handling for movie titles with numbers (like "Jujutsu Kaisen 0")
    movie_indicators = ['0', 'movie', 'film', 'gekijo', 'gekijou', 'gekijouban']
    looks_like_movie = any(indicator in query.lower() for indicator in movie_indicators)
    
    # Ensure we always return a non-empty string
    if not query:
        query = "Spirited Away"
    
    logger.debug(f"Processed query: '{query}' (original: '{original_query}', year: {extracted_year}, looks_like_movie: {looks_like_movie})")
    return query

# --- Flask routes ---
@app.route('/api')
def api():
    t = request.args.get('t', '').lower()
    logger.debug(f"API request: {request.args}")

    if t == 'caps':
        return Response(build_caps_xml(), mimetype='application/xml')

    elif t == 'search':
        query_param = request.args.get('q', '')
        return_type = request.args.get('response', 'xml')
        
        processed_query = process_search_query(query_param)
        logger.info(f"Processed search query: '{processed_query}' (original: '{query_param}')")
        
        result = perform_search(processed_query)
        if len(result) == 5:
            anilist_id, anime_name, processed_torrents, anime_format, year = result
        else:
            anilist_id, anime_name, processed_torrents = result
            anime_format = None
            year = None
        
        if not anilist_id or not processed_torrents:
            if return_type == 'json':
                return Response('{"usenetReleases": [], "torrentReleases": []}', 
                              mimetype='application/json', status=404)
            else:
                return Response(build_empty_rss("SeadexNab - No Results", 
                                              f"No results found for: {processed_query}"), 
                              mimetype='application/xml')
        
        if return_type == 'json':
            json_response = {
                "usenetReleases": [],
                "torrentReleases": [{"title": t.get("title", ""), "url": t.get("url", "")} for t in processed_torrents]
            }
            return Response(str(json_response), mimetype='application/json')
        else:
            xml = build_rss_enhanced(anilist_id, anime_name, processed_torrents, anime_format=anime_format, year=year)
            return Response(xml, mimetype='application/xml')

    elif t == 'tvsearch':
        query_param = request.args.get('q', '')
        season = request.args.get('season')
        episode = request.args.get('ep')
        
        try:
            season = int(season) if season else None
        except ValueError:
            season = None
            
        try:
            episode = int(episode) if episode else None
        except ValueError:
            episode = None
        
        processed_query = process_search_query(query_param, season, episode)
        logger.info(f"TV search for: '{processed_query}' (season={season}, episode={episode})")
        
        result = perform_search(processed_query, season, episode)
        if len(result) == 5:
            anilist_id, anime_name, processed_torrents, anime_format, year = result
        else:
            anilist_id, anime_name, processed_torrents = result
            anime_format = None
            year = None
        
        if not anilist_id or not processed_torrents:
            return Response(build_empty_rss("SeadexNab - No Results", 
                                          f"No results found for: {processed_query}"), 
                          mimetype='application/xml')
        
        # Force anime category (5000) for Sonarr compatibility
        xml = build_rss_enhanced(anilist_id, anime_name, processed_torrents, season, episode, anime_format, year, force_anime_category=True)
        return Response(xml, mimetype='application/xml')

    elif t == 'movie':
        query_param = request.args.get('q', '')
        processed_query = process_search_query(query_param)
        logger.info(f"Movie search for: '{processed_query}'")
        
        result = perform_search(processed_query, search_type="ANIME")
        if len(result) == 5:
            anilist_id, anime_name, processed_torrents, anime_format, year = result
        else:
            anilist_id, anime_name, processed_torrents = result
            anime_format = None
            year = None
        
        if not anilist_id or not processed_torrents:
            return Response(build_empty_rss("SeadexNab - No Results", 
                                          f"No results found for: {processed_query}"), 
                          mimetype='application/xml')
        
        # Use movie category (2000) for Radarr compatibility
        xml = build_rss_enhanced(anilist_id, anime_name, processed_torrents, anime_format=anime_format, year=year, force_anime_category=False)
        return Response(xml, mimetype='application/xml')

    else:
        logger.error(f"Invalid request type: {t}")
        return Response("Invalid request", status=400)

@app.route('/test')
def test():
    """Test endpoint to debug the search functionality"""
    q = request.args.get('q', 'Fate/stay night')
    season = request.args.get('season')
    episode = request.args.get('ep')
    
    try:
        season = int(season) if season else None
    except ValueError:
        season = None
        
    try:
        episode = int(episode) if episode else None
    except ValueError:
        episode = None
    
    logger.info(f"Test search for: {q} (season={season}, episode={episode})")
    
    processed_query = process_search_query(q, season, episode)
    result = perform_search(processed_query, season, episode)
    
    if len(result) == 5:
        anilist_id, anime_name, processed_torrents, anime_format, year = result
    else:
        anilist_id, anime_name, processed_torrents = result
        anime_format = None
        year = None
    
    if not anilist_id:
        return f"Could not find AniList ID for: {q}"
    
    result_text = f"Found {len(processed_torrents)} torrents for {anime_name} ({anime_format}) (ID: {anilist_id}, Year: {year})<br>"
    result_text += f"Processed query: {processed_query}<br><br>"
    
    for i, torrent in enumerate(processed_torrents):
        result_text += f"Torrent {i+1}:<br>"
        result_text += f"  - Movie: {torrent.get('is_movie', False)}<br>"
        result_text += f"  - Season Pack: {torrent['is_season_pack']}<br>"
        result_text += f"  - Seasons: {torrent['seasons']}<br>"
        result_text += f"  - Episodes: {torrent['episode_numbers']}<br>"
        result_text += f"  - Release Group: {torrent['release_group']}<br>"
        result_text += f"  - Size: {torrent['total_size'] / (1024**3):.2f} GB<br>"
        result_text += f"  - Files: {torrent['episode_count']}<br><br>"
    
    return result_text

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=11124, debug=True)