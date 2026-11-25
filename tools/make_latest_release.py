"""Mark a release as the official latest (not a pre-release) using the existing Git credential.
Never prints or saves the credential. The launcher's own auto-update picks the highest version
either way; this only changes what https://github.com/japanoxx-afk/samchun/releases/latest shows.
Usage: python tools/make_latest_release.py v1.3.58
"""
import json, subprocess, sys, urllib.request

tag = sys.argv[1]
result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                        text=True, capture_output=True, check=True)
token = dict(l.split('=', 1) for l in result.stdout.splitlines() if '=' in l)['password']
base = 'https://api.github.com/repos/japanoxx-afk/samchun'


def request(url, data=None, method=None):
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': 'Bearer ' + token, 'User-Agent': 'samchun-release',
        'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


release = request(base + '/releases/tags/' + tag)
release = request(base + '/releases/' + str(release['id']),
                  json.dumps({'prerelease': False, 'make_latest': 'true'}).encode(), 'PATCH')
print('Latest release:', release['tag_name'], release['html_url'])
print('Assets:', ', '.join(a['name'] for a in release['assets']))
