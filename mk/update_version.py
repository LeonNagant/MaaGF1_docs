import re
import os
import sys
import json
import urllib.request
from typing import List, Dict, Optional

# Configuration
REPO_API_URL = "https://api.github.com/repos/MaaGF1/MaaGF1/releases"
TARGET_FILE = "docs/index.md"
# Regex to capture semantic versioning (e.g., v1.8.2, v1.7.1-fix)
# Group 1: Major.Minor (e.g., 1.8)
# Group 2: Patch + Suffix (e.g., 2-fix)
VERSION_PATTERN = re.compile(r"^v?(\d+\.\d+)\.(.+)$")

def fetch_releases() -> List[Dict]:
    """
    Fetches release data from GitHub API.
    """
    print(f"Fetching releases from {REPO_API_URL}...")
    try:
        # Use a User-Agent to avoid 403 Forbidden errors from GitHub
        req = urllib.request.Request(
            REPO_API_URL, 
            headers={'User-Agent': 'MaaGF1-Docs-Builder'}
        )
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return data
    except Exception as e:
        print(f"Error fetching releases: {e}")
        sys.exit(1)

def parse_versions(releases: List[Dict]) -> Dict[str, Dict]:
    """
    Parses releases and finds the latest version for each Major.Minor series.
    Returns a dict: {'1.8': {'tag': 'v1.8.9', 'url': '...'}, ...}
    """
    version_map = {}

    for release in releases:
        # Skip pre-releases and drafts
        if release.get('prerelease') or release.get('draft'):
            continue
        
        tag_name = release.get('tag_name', '')
        html_url = release.get('html_url', '')
        
        match = VERSION_PATTERN.match(tag_name)
        if match:
            major_minor = match.group(1) # e.g., "1.8"
            
            # We assume the API returns releases in chronological order (newest first).
            # So the first time we see a "1.8.x", it is the latest.
            if major_minor not in version_map:
                version_map[major_minor] = {
                    'tag': tag_name,
                    'url': html_url
                }
                print(f"Found latest for {major_minor}.x -> {tag_name}")
    
    return version_map

def update_markdown(file_path: str, version_map: Dict[str, Dict]):
    """
    Reads the markdown file and replaces [ver]X.Y.x[/ver] tags.
    """
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        sys.exit(1)

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex to find placeholders like [ver]1.8.x[/ver]
    # Captures "1.8" in group 1
    placeholder_pattern = re.compile(r"\[ver\](\d+\.\d+)\.x\[/ver\]")

    def replacement_handler(match):
        major_minor = match.group(1)
        if major_minor in version_map:
            info = version_map[major_minor]
            # Return markdown link: [v1.8.9](https://...)
            return f"[{info['tag']}]({info['url']})"
        else:
            print(f"Warning: No release found for version family {major_minor}.x")
            return match.group(0) # Return original text if not found

    new_content = placeholder_pattern.sub(replacement_handler, content)

    if content != new_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Successfully updated {file_path}")
    else:
        print("No version placeholders required updating.")

def main():
    releases = fetch_releases()
    version_map = parse_versions(releases)
    update_markdown(TARGET_FILE, version_map)

if __name__ == "__main__":
    main()