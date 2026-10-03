"""Publish explicitly requested release assets using the existing Git credential.
Never prints or saves the credential. Draft first, publish after all uploads.
Usage: python tools/publish_release.py v1.2.0 path/to/package.zip
"""
import argparse, hashlib, json, subprocess, urllib.request, urllib.parse, zipfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('tag')
parser.add_argument('package')
parser.add_argument('--assets-directory', type=Path, default=Path('dist'))
parser.add_argument('--prerelease', action='store_true')
args = parser.parse_args()
tag, package = args.tag, args.package
launcher = args.assets_directory/'launcher.exe'
checksum = args.assets_directory/'SHA256.txt'
if hashlib.sha256(launcher.read_bytes()).hexdigest().lower() != checksum.read_text().strip().lower():
    raise SystemExit('Launcher checksum mismatch')
with zipfile.ZipFile(package) as archive:
    if archive.read('launcher.exe') != launcher.read_bytes():
        raise SystemExit('ZIP and update launcher differ')
if not tag.startswith('v'):
    raise SystemExit('Version tag must start with v')
result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                        text=True, capture_output=True, check=True)
credential = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
token = credential['password']
base = 'https://api.github.com/repos/japanoxx-afk/samchun'

def request(url, data=None, method=None, content_type='application/json'):
    req = urllib.request.Request(url, data=data, method=method,
        headers={'Authorization': 'Bearer ' + token, 'User-Agent': 'samchun-release',
                 'Accept': 'application/vnd.github+json', 'Content-Type': content_type})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)

body = Path('RELEASE_NOTES.md').read_text(encoding='utf-8-sig')
release = request(base + '/releases', json.dumps(dict(tag_name=tag, target_commitish='main',
    name='samchun ' + tag, body=body, draft=True, prerelease=args.prerelease)).encode(), 'POST')
print('Draft release created:', release['id'])
for path in [launcher, checksum, Path(package)]:
    url = release['upload_url'].split('{')[0] + '?name=' + urllib.parse.quote(path.name)
    asset = request(url, path.read_bytes(), 'POST', 'application/octet-stream')
    print('Uploaded:', asset['name'], asset['size'])
release = request(base + '/releases/' + str(release['id']),
                  json.dumps(dict(draft=False, make_latest='false' if args.prerelease else 'true')).encode(), 'PATCH')
print('Published:', release['html_url'])
