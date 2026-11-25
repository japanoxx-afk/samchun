"""Add (or replace) one asset on an existing GitHub release using the existing Git credential.
Never prints or saves the credential.
Usage: python tools/add_release_asset.py v1.3.58 dist/launcher.exe samchun-launcher.exe
"""
import json, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

tag, file = sys.argv[1], Path(sys.argv[2])
name = sys.argv[3] if len(sys.argv) > 3 else file.name
result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                        text=True, capture_output=True, check=True)
token = dict(l.split('=', 1) for l in result.stdout.splitlines() if '=' in l)['password']
base = 'https://api.github.com/repos/japanoxx-afk/samchun'


def request(url, data=None, method=None, content_type='application/json'):
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': 'Bearer ' + token, 'User-Agent': 'samchun-release',
        'Accept': 'application/vnd.github+json', 'Content-Type': content_type})
    with urllib.request.urlopen(req, timeout=120) as r:
        body = r.read()
        return json.loads(body) if body else None


release = request(base + '/releases/tags/' + tag)
for asset in release['assets']:
    if asset['name'] == name:
        request(base + '/releases/assets/' + str(asset['id']), method='DELETE')
        print('Replaced old asset:', name)
url = release['upload_url'].split('{')[0] + '?name=' + urllib.parse.quote(name)
asset = request(url, file.read_bytes(), 'POST', 'application/octet-stream')
print('Uploaded:', asset['name'], asset['size'], asset['browser_download_url'])
