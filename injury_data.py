"""
NBA Injury Data Fetcher
=======================

Fetches current NBA injury information from multiple sources:
1. NBA Official Injury Report (via nbainjuries package)
2. ESPN Injuries Page (web scraping)

This module provides real-time injury data for use in game predictions,
allowing automatic adjustment of predictions based on player availability.

Usage:
    from injury_data import get_current_injuries, get_team_injuries

    # Get all current injuries
    injuries = get_current_injuries()

    # Get injuries for a specific team
    lakers_injuries = get_team_injuries(1610612747)  # Lakers team ID
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import re
import time

# Try to import nbainjuries package
try:
    from nbainjuries import injury as nba_injury
    NBA_INJURIES_AVAILABLE = True
except ImportError:
    NBA_INJURIES_AVAILABLE = False
    print("Note: nbainjuries package not installed. Install with: pip install nbainjuries")
    print("      Also requires Java 8+ for PDF parsing.")


# ============================================================================
# TEAM MAPPINGS
# ============================================================================

# NBA team ID to abbreviation mapping
TEAM_ID_TO_ABBREV = {
    1610612737: 'ATL',  # Atlanta Hawks
    1610612738: 'BOS',  # Boston Celtics
    1610612739: 'CLE',  # Cleveland Cavaliers
    1610612740: 'NOP',  # New Orleans Pelicans
    1610612741: 'CHI',  # Chicago Bulls
    1610612742: 'DAL',  # Dallas Mavericks
    1610612743: 'DEN',  # Denver Nuggets
    1610612744: 'GSW',  # Golden State Warriors
    1610612745: 'HOU',  # Houston Rockets
    1610612746: 'LAC',  # LA Clippers
    1610612747: 'LAL',  # Los Angeles Lakers
    1610612748: 'MIA',  # Miami Heat
    1610612749: 'MIL',  # Milwaukee Bucks
    1610612750: 'MIN',  # Minnesota Timberwolves
    1610612751: 'BKN',  # Brooklyn Nets
    1610612752: 'NYK',  # New York Knicks
    1610612753: 'ORL',  # Orlando Magic
    1610612754: 'IND',  # Indiana Pacers
    1610612755: 'PHI',  # Philadelphia 76ers
    1610612756: 'PHX',  # Phoenix Suns
    1610612757: 'POR',  # Portland Trail Blazers
    1610612758: 'SAC',  # Sacramento Kings
    1610612759: 'SAS',  # San Antonio Spurs
    1610612760: 'OKC',  # Oklahoma City Thunder
    1610612761: 'TOR',  # Toronto Raptors
    1610612762: 'UTA',  # Utah Jazz
    1610612763: 'MEM',  # Memphis Grizzlies
    1610612764: 'WAS',  # Washington Wizards
    1610612765: 'DET',  # Detroit Pistons
    1610612766: 'CHA',  # Charlotte Hornets
}

ABBREV_TO_TEAM_ID = {v: k for k, v in TEAM_ID_TO_ABBREV.items()}

# ESPN uses different abbreviations - map them to standard NBA abbreviations
ESPN_ABBREV_TO_NBA = {
    'SA': 'SAS',    # San Antonio Spurs
    'NO': 'NOP',    # New Orleans Pelicans
    'GS': 'GSW',    # Golden State Warriors
    'NY': 'NYK',    # New York Knicks
    'UTAH': 'UTA',  # Utah Jazz
    'WSH': 'WAS',   # Washington Wizards (sometimes)
    'PHO': 'PHX',   # Phoenix Suns (sometimes)
    'BKN': 'BKN',   # Brooklyn Nets (same)
    'CHA': 'CHA',   # Charlotte Hornets (same)
}

def normalize_team_abbrev(abbrev: str) -> str:
    """Convert ESPN abbreviation to standard NBA abbreviation."""
    return ESPN_ABBREV_TO_NBA.get(abbrev, abbrev)

# Team name variations for matching
TEAM_NAME_MAPPING = {
    # Full names
    'Atlanta Hawks': 'ATL',
    'Boston Celtics': 'BOS',
    'Brooklyn Nets': 'BKN',
    'Charlotte Hornets': 'CHA',
    'Chicago Bulls': 'CHI',
    'Cleveland Cavaliers': 'CLE',
    'Dallas Mavericks': 'DAL',
    'Denver Nuggets': 'DEN',
    'Detroit Pistons': 'DET',
    'Golden State Warriors': 'GSW',
    'Houston Rockets': 'HOU',
    'Indiana Pacers': 'IND',
    'LA Clippers': 'LAC',
    'Los Angeles Clippers': 'LAC',
    'LA Lakers': 'LAL',
    'Los Angeles Lakers': 'LAL',
    'Memphis Grizzlies': 'MEM',
    'Miami Heat': 'MIA',
    'Milwaukee Bucks': 'MIL',
    'Minnesota Timberwolves': 'MIN',
    'New Orleans Pelicans': 'NOP',
    'New York Knicks': 'NYK',
    'Oklahoma City Thunder': 'OKC',
    'Orlando Magic': 'ORL',
    'Philadelphia 76ers': 'PHI',
    'Phoenix Suns': 'PHX',
    'Portland Trail Blazers': 'POR',
    'Sacramento Kings': 'SAC',
    'San Antonio Spurs': 'SAS',
    'Toronto Raptors': 'TOR',
    'Utah Jazz': 'UTA',
    'Washington Wizards': 'WAS',
    # City names only
    'Atlanta': 'ATL',
    'Boston': 'BOS',
    'Brooklyn': 'BKN',
    'Charlotte': 'CHA',
    'Chicago': 'CHI',
    'Cleveland': 'CLE',
    'Dallas': 'DAL',
    'Denver': 'DEN',
    'Detroit': 'DET',
    'Golden State': 'GSW',
    'Houston': 'HOU',
    'Indiana': 'IND',
    'L.A. Clippers': 'LAC',
    'L.A. Lakers': 'LAL',
    'Memphis': 'MEM',
    'Miami': 'MIA',
    'Milwaukee': 'MIL',
    'Minnesota': 'MIN',
    'New Orleans': 'NOP',
    'New York': 'NYK',
    'Oklahoma City': 'OKC',
    'Orlando': 'ORL',
    'Philadelphia': 'PHI',
    'Phoenix': 'PHX',
    'Portland': 'POR',
    'Sacramento': 'SAC',
    'San Antonio': 'SAS',
    'Toronto': 'TOR',
    'Utah': 'UTA',
    'Washington': 'WAS',
}


def normalize_team_name(team_name: str) -> str:
    """Convert team name to standard abbreviation."""
    if not team_name:
        return None

    # Check if already an abbreviation
    if team_name.upper() in ABBREV_TO_TEAM_ID:
        return team_name.upper()

    # Check mapping
    if team_name in TEAM_NAME_MAPPING:
        return TEAM_NAME_MAPPING[team_name]

    # Try case-insensitive match
    for name, abbrev in TEAM_NAME_MAPPING.items():
        if name.lower() == team_name.lower():
            return abbrev

    # Try partial match
    team_lower = team_name.lower()
    for name, abbrev in TEAM_NAME_MAPPING.items():
        if name.lower() in team_lower or team_lower in name.lower():
            return abbrev

    return None


def normalize_status(status: str) -> str:
    """
    Normalize injury status to standard categories.

    Returns one of: 'OUT', 'DOUBTFUL', 'QUESTIONABLE', 'PROBABLE', 'AVAILABLE'
    """
    if not status:
        return 'UNKNOWN'

    status_upper = status.upper().strip()

    if 'OUT' in status_upper:
        return 'OUT'
    elif 'DOUBT' in status_upper:
        return 'DOUBTFUL'
    elif 'QUESTION' in status_upper or 'DAY-TO-DAY' in status_upper or 'DAY TO DAY' in status_upper or 'GTD' in status_upper:
        return 'QUESTIONABLE'
    elif 'PROB' in status_upper:
        return 'PROBABLE'
    elif 'AVAIL' in status_upper:
        return 'AVAILABLE'
    else:
        return status_upper


# ============================================================================
# NBA OFFICIAL INJURY REPORT (via nbainjuries package)
# ============================================================================

def fetch_nba_official_injuries(report_datetime: datetime = None) -> List[Dict]:
    """
    Fetch injury data from NBA's official injury report.

    Args:
        report_datetime: When to get report for. Defaults to current time.

    Returns:
        List of injury records with standardized format:
        [
            {
                'player_name': str,
                'team_abbrev': str,
                'team_id': int,
                'status': str,  # OUT, QUESTIONABLE, PROBABLE, AVAILABLE
                'injury': str,  # Description of injury
                'source': 'nba_official'
            },
            ...
        ]
    """
    if not NBA_INJURIES_AVAILABLE:
        print("Warning: nbainjuries package not available")
        return []

    if report_datetime is None:
        report_datetime = datetime.now()

    try:
        # Get injury report as DataFrame for easier processing
        df = nba_injury.get_reportdata(report_datetime, return_df=True)

        if df is None or len(df) == 0:
            print("No NBA official injury data available for this time")
            return []

        injuries = []
        for _, row in df.iterrows():
            # Extract team abbreviation from matchup or team name
            team_abbrev = None
            if 'Team' in row and row['Team']:
                team_abbrev = normalize_team_name(str(row['Team']))
            elif 'Matchup' in row and row['Matchup']:
                # Matchup format: "BOS@ORL" - need to determine which team
                matchup = str(row['Matchup'])
                # This is complex - player could be on either team
                # For now, rely on Team column
                pass

            if team_abbrev is None:
                continue

            team_id = ABBREV_TO_TEAM_ID.get(team_abbrev)

            injury_record = {
                'player_name': str(row.get('Player Name', '')).strip(),
                'team_abbrev': team_abbrev,
                'team_id': team_id,
                'status': normalize_status(str(row.get('Current Status', ''))),
                'injury': str(row.get('Reason', '')).strip(),
                'source': 'nba_official',
                'game_date': str(row.get('Game Date', '')),
                'game_time': str(row.get('Game Time', ''))
            }

            injuries.append(injury_record)

        print(f"Fetched {len(injuries)} injuries from NBA official report")
        return injuries

    except Exception as e:
        print(f"Error fetching NBA official injuries: {e}")
        return []


# ============================================================================
# ESPN INJURIES (Web Scraping)
# ============================================================================

def fetch_espn_injuries() -> List[Dict]:
    """
    Fetch injury data from ESPN's NBA injuries page.

    Returns:
        List of injury records with standardized format
    """
    url = "https://www.espn.com/nba/injuries"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        injuries = []

        # Find all team sections
        # ESPN uses different class names, so we try multiple approaches

        # Look for team injury tables
        team_sections = soup.find_all('div', class_=re.compile(r'ResponsiveTable|Table__league-injuries'))

        if not team_sections:
            # Alternative: look for any tables with injury data
            team_sections = soup.find_all('section', class_=re.compile(r'Card'))

        current_team = None

        # Parse by looking at the structure
        # Each team has a header followed by a table of players
        for section in soup.find_all(['div', 'section']):
            # Look for team headers
            team_header = section.find(['h2', 'h3', 'div'], class_=re.compile(r'Table__Title|headline'))
            if team_header:
                team_text = team_header.get_text(strip=True)
                new_team = normalize_team_name(team_text)
                if new_team:
                    current_team = new_team

            # Look for player rows
            rows = section.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 4 and current_team:
                    # Extract data from cells
                    # Typical structure: NAME, POS, DATE, STATUS, COMMENT
                    player_name = cells[0].get_text(strip=True)

                    # Skip header rows
                    if player_name.upper() in ['NAME', 'PLAYER', '']:
                        continue

                    # Find status cell (usually contains "Out" or "Day-To-Day")
                    status = ''
                    injury = ''

                    for cell in cells[1:]:
                        text = cell.get_text(strip=True)
                        if text.upper() in ['OUT', 'DAY-TO-DAY', 'DOUBTFUL', 'QUESTIONABLE', 'PROBABLE']:
                            status = text
                        elif len(text) > 10 and status:  # Likely the comment/injury field
                            injury = text

                    if player_name and status:
                        injury_record = {
                            'player_name': player_name,
                            'team_abbrev': current_team,
                            'team_id': ABBREV_TO_TEAM_ID.get(current_team),
                            'status': normalize_status(status),
                            'injury': injury,
                            'source': 'espn'
                        }
                        injuries.append(injury_record)

        # Alternative parsing method using more specific selectors
        if len(injuries) == 0:
            injuries = _parse_espn_alternative(soup)

        print(f"Fetched {len(injuries)} injuries from ESPN")
        return injuries

    except requests.RequestException as e:
        print(f"Error fetching ESPN injuries: {e}")
        return []
    except Exception as e:
        print(f"Error parsing ESPN injuries: {e}")
        return []


def _parse_espn_alternative(soup: BeautifulSoup) -> List[Dict]:
    """
    Alternative ESPN parsing method using different selectors.
    ESPN's HTML structure can vary, so we try multiple approaches.
    """
    injuries = []

    # Try finding tables directly
    tables = soup.find_all('table')

    current_team = None

    for element in soup.find_all(['h2', 'table', 'div']):
        # Check if this is a team header
        if element.name in ['h2', 'div']:
            text = element.get_text(strip=True)
            team = normalize_team_name(text)
            if team:
                current_team = team
                continue

        # Check if this is a table with injury data
        if element.name == 'table' and current_team:
            rows = element.find_all('tr')
            for row in rows:
                cells = row.find_all(['td'])
                if len(cells) >= 2:
                    # First cell is usually player name
                    player_cell = cells[0]
                    player_name = player_cell.get_text(strip=True)

                    # Skip empty or header rows
                    if not player_name or player_name.upper() == 'NAME':
                        continue

                    # Look for status in other cells
                    status = 'OUT'  # Default if on injury list
                    injury = ''

                    for cell in cells[1:]:
                        text = cell.get_text(strip=True)
                        normalized = normalize_status(text)
                        if normalized in ['OUT', 'DOUBTFUL', 'QUESTIONABLE', 'PROBABLE']:
                            status = normalized
                        elif len(text) > 5:
                            injury = text

                    injuries.append({
                        'player_name': player_name,
                        'team_abbrev': current_team,
                        'team_id': ABBREV_TO_TEAM_ID.get(current_team),
                        'status': status,
                        'injury': injury,
                        'source': 'espn'
                    })

    return injuries


# ============================================================================
# ESPN CORE API (JSON Endpoint)
# ============================================================================

def fetch_espn_api_injuries() -> List[Dict]:
    """
    Fetch injury data from ESPN's Core API (JSON format).
    This is more reliable than web scraping when available.
    """
    injuries = []

    # ESPN Core API base URL for NBA teams
    base_url = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/teams"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
    }

    try:
        # First, get list of all teams
        response = requests.get(base_url, headers=headers, timeout=10)

        if response.status_code != 200:
            print(f"ESPN API returned status {response.status_code}")
            return []

        teams_data = response.json()
        team_refs = teams_data.get('items', [])

        # For each team, try to get injuries
        for team_ref in team_refs:
            team_url = team_ref.get('$ref', '')
            if not team_url:
                continue

            # Get team details to find team ID
            try:
                team_response = requests.get(team_url, headers=headers, timeout=10)
                if team_response.status_code != 200:
                    continue

                team_data = team_response.json()
                team_abbrev = team_data.get('abbreviation', '')
                # Normalize ESPN abbreviations to standard NBA abbreviations
                team_abbrev = normalize_team_abbrev(team_abbrev)
                espn_team_id = team_data.get('id', '')

                # Try injuries endpoint
                injuries_url = f"{base_url}/{espn_team_id}/injuries"
                inj_response = requests.get(injuries_url, headers=headers, timeout=10)

                if inj_response.status_code == 200:
                    inj_data = inj_response.json()
                    for item in inj_data.get('items', []):
                        # Each item has a $ref to full injury details
                        item_url = item.get('$ref', '')
                        if item_url:
                            try:
                                detail_response = requests.get(item_url, headers=headers, timeout=10)
                                if detail_response.status_code == 200:
                                    detail = detail_response.json()

                                    # Get player name - try multiple paths
                                    athlete = detail.get('athlete', {})
                                    player_name = ''

                                    # If athlete is a reference, fetch it
                                    if isinstance(athlete, dict) and '$ref' in athlete:
                                        try:
                                            athlete_response = requests.get(athlete['$ref'], headers=headers, timeout=10)
                                            if athlete_response.status_code == 200:
                                                athlete_data = athlete_response.json()
                                                player_name = athlete_data.get('displayName', '')
                                        except:
                                            pass
                                    else:
                                        player_name = athlete.get('displayName', '')

                                    # Get injury type
                                    injury_type = detail.get('type', {})
                                    if isinstance(injury_type, dict) and '$ref' in injury_type:
                                        # Skip fetching injury type details
                                        injury_desc = detail.get('details', {}).get('detail', '')
                                    else:
                                        injury_desc = injury_type.get('description', '') if isinstance(injury_type, dict) else ''

                                    if not injury_desc:
                                        injury_desc = detail.get('details', {}).get('detail', '')

                                    # Get status
                                    status = detail.get('status', '')

                                    if player_name:  # Only add if we have a player name
                                        injuries.append({
                                            'player_name': player_name,
                                            'team_abbrev': team_abbrev,
                                            'team_id': ABBREV_TO_TEAM_ID.get(team_abbrev),
                                            'status': normalize_status(status),
                                            'injury': injury_desc,
                                            'source': 'espn_api'
                                        })
                            except Exception:
                                continue

                time.sleep(0.3)  # Rate limiting

            except Exception as e:
                continue

        print(f"Fetched {len(injuries)} injuries from ESPN API")
        return injuries

    except Exception as e:
        print(f"Error fetching ESPN API injuries: {e}")
        return []


# ============================================================================
# COMBINED INJURY FETCHING
# ============================================================================

def get_current_injuries(use_nba_official: bool = False,
                         use_espn: bool = True,
                         deduplicate: bool = True) -> List[Dict]:
    """
    Get current NBA injuries from all available sources.

    Args:
        use_nba_official: Whether to fetch from NBA official report (default: False, often blocked)
        use_espn: Whether to fetch from ESPN (default: True, more reliable)
        deduplicate: Whether to remove duplicate entries

    Returns:
        List of injury records, sorted by team and then status severity
    """
    all_injuries = []

    # Fetch from NBA Official (disabled by default - often returns 403)
    if use_nba_official and NBA_INJURIES_AVAILABLE:
        nba_injuries = fetch_nba_official_injuries()
        all_injuries.extend(nba_injuries)

    # Fetch from ESPN (try API first, then scraping)
    if use_espn:
        espn_injuries = fetch_espn_api_injuries()
        if not espn_injuries:
            espn_injuries = fetch_espn_injuries()
        all_injuries.extend(espn_injuries)

    # Deduplicate by player name and team
    if deduplicate and len(all_injuries) > 0:
        seen = set()
        unique_injuries = []

        for inj in all_injuries:
            key = (inj['player_name'].lower(), inj['team_abbrev'])
            if key not in seen:
                seen.add(key)
                unique_injuries.append(inj)
            else:
                # If we have a duplicate, prefer NBA official source
                if inj['source'] == 'nba_official':
                    # Replace existing
                    unique_injuries = [i for i in unique_injuries
                                      if (i['player_name'].lower(), i['team_abbrev']) != key]
                    unique_injuries.append(inj)

        all_injuries = unique_injuries

    # Sort by team and then by status severity
    status_order = {'OUT': 0, 'DOUBTFUL': 1, 'QUESTIONABLE': 2, 'PROBABLE': 3, 'AVAILABLE': 4}
    all_injuries.sort(key=lambda x: (x.get('team_abbrev', 'ZZZ'),
                                      status_order.get(x.get('status', 'UNKNOWN'), 5)))

    return all_injuries


def get_team_injuries(team_id: int = None,
                      team_abbrev: str = None) -> List[Dict]:
    """
    Get current injuries for a specific team.

    Args:
        team_id: NBA team ID (e.g., 1610612747 for Lakers)
        team_abbrev: Team abbreviation (e.g., 'LAL')

    Returns:
        List of injury records for the specified team
    """
    if team_abbrev is None and team_id is not None:
        team_abbrev = TEAM_ID_TO_ABBREV.get(team_id)

    if team_abbrev is None:
        print("Error: Must provide either team_id or team_abbrev")
        return []

    all_injuries = get_current_injuries()

    return [inj for inj in all_injuries if inj.get('team_abbrev') == team_abbrev]


def get_players_out(team_id: int = None,
                    team_abbrev: str = None,
                    include_questionable: bool = False) -> List[str]:
    """
    Get list of player names who are OUT (or questionable) for a team.

    Args:
        team_id: NBA team ID
        team_abbrev: Team abbreviation
        include_questionable: If True, also include DOUBTFUL and QUESTIONABLE players

    Returns:
        List of player names
    """
    team_injuries = get_team_injuries(team_id=team_id, team_abbrev=team_abbrev)

    if include_questionable:
        statuses = ['OUT', 'DOUBTFUL', 'QUESTIONABLE']
    else:
        statuses = ['OUT', 'DOUBTFUL']

    return [inj['player_name'] for inj in team_injuries if inj.get('status') in statuses]


def get_injuries_for_matchup(home_team_id: int, away_team_id: int) -> Dict[str, List[Dict]]:
    """
    Get injuries relevant to a specific matchup.

    Args:
        home_team_id: Home team's NBA ID
        away_team_id: Away team's NBA ID

    Returns:
        Dict with 'home' and 'away' keys containing injury lists
    """
    all_injuries = get_current_injuries()

    home_abbrev = TEAM_ID_TO_ABBREV.get(home_team_id)
    away_abbrev = TEAM_ID_TO_ABBREV.get(away_team_id)

    return {
        'home': [inj for inj in all_injuries if inj.get('team_abbrev') == home_abbrev],
        'away': [inj for inj in all_injuries if inj.get('team_abbrev') == away_abbrev],
        'home_team': home_abbrev,
        'away_team': away_abbrev
    }


def print_injury_report(team_id: int = None, team_abbrev: str = None):
    """Print formatted injury report for a team or all teams."""
    if team_id or team_abbrev:
        injuries = get_team_injuries(team_id=team_id, team_abbrev=team_abbrev)
        team = team_abbrev or TEAM_ID_TO_ABBREV.get(team_id, 'Unknown')
        print(f"\n{'='*60}")
        print(f"INJURY REPORT: {team}")
        print('='*60)
    else:
        injuries = get_current_injuries()
        print(f"\n{'='*60}")
        print("NBA INJURY REPORT - ALL TEAMS")
        print('='*60)

    if not injuries:
        print("No injuries found.")
        return

    current_team = None
    for inj in injuries:
        if inj['team_abbrev'] != current_team:
            current_team = inj['team_abbrev']
            if not (team_id or team_abbrev):
                print(f"\n--- {current_team} ---")

        status_emoji = {
            'OUT': '[OUT]',
            'DOUBTFUL': '[DBT]',
            'QUESTIONABLE': '[Q]',
            'PROBABLE': '[PRB]',
        }.get(inj['status'], '[?]')

        print(f"  {status_emoji:6} {inj['player_name']:<25} {inj.get('injury', '')[:30]}")

    print(f"\nTotal injuries: {len(injuries)}")
    print(f"Sources: {', '.join(set(i['source'] for i in injuries))}")


# ============================================================================
# MAIN (Testing)
# ============================================================================

if __name__ == '__main__':
    print("Testing NBA Injury Data Fetcher")
    print("="*60)

    # Test ESPN scraping
    print("\n1. Testing ESPN scraping...")
    espn_injuries = fetch_espn_injuries()
    print(f"   Found {len(espn_injuries)} injuries")
    if espn_injuries:
        print(f"   Sample: {espn_injuries[0]}")

    # Test ESPN API
    print("\n2. Testing ESPN API...")
    espn_api_injuries = fetch_espn_api_injuries()
    print(f"   Found {len(espn_api_injuries)} injuries")

    # Test NBA Official (if available)
    if NBA_INJURIES_AVAILABLE:
        print("\n3. Testing NBA Official Report...")
        nba_injuries = fetch_nba_official_injuries()
        print(f"   Found {len(nba_injuries)} injuries")
    else:
        print("\n3. NBA Official Report: Package not installed")

    # Test combined
    print("\n4. Testing combined injury fetch...")
    all_injuries = get_current_injuries()
    print(f"   Total unique injuries: {len(all_injuries)}")

    # Print sample report
    print("\n5. Sample injury report:")
    print_injury_report()

    # Test team-specific
    print("\n6. Testing team-specific query (Lakers)...")
    lakers = get_team_injuries(team_id=1610612747)
    print(f"   Lakers injuries: {len(lakers)}")
    for inj in lakers:
        print(f"     - {inj['player_name']}: {inj['status']}")

    print("\nDone!")
