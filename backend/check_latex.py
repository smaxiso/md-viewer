import json, urllib.request, re

resp = urllib.request.urlopen("http://localhost:8001/api/file?path=docs/buying/unified_strategy.md")
d = json.loads(resp.read())
html = d['html']

# Find all $...$ sections and print raw bytes
for m in re.finditer(r'\$[^$]+\$', html):
    text = m.group()
    print(f"TEXT: {text}")
    print(f"BYTES: {text.encode()}")
    print()
