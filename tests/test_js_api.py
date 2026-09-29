import sys, re
sys.path.insert(0, ".")
import truststore, requests
truststore.inject_into_ssl()
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
s = requests.Session(); s.headers['User-Agent'] = UA
r = s.get('https://steamcommunity.com/workshop/browse/', params={'appid': '258130'}, timeout=30)
html = r.text

# 找 JS bundle
scripts = re.findall(r'src="(https://[^"]+\.js[^"]*)"', html)
scripts = [u for u in scripts if 'workshop' in u.lower() or 'community' in u.lower()]
print('candidate scripts:', scripts[:10])

# 也找相对路径
rel = re.findall(r'src="(/public/javascript/[^"]+)"', html)
print('relative scripts:', rel[:10])

# 抓取每个候选 bundle 搜索 workshop API
for u in scripts[:6] + [f'https://steamcommunity.com{x}' for x in rel[:6]]:
    try:
        jr = s.get(u, timeout=30)
        if jr.status_code != 200:
            continue
        body = jr.text
        hits = set()
        for m in re.finditer(r'/(api|sharedfiles|appworkshop)/[A-Za-z0-9_/]{3,40}', body):
            hits.add(m.group(0))
        workshop_hits = {h for h in hits if 'workshop' in h.lower() or 'file' in h.lower()}
        if workshop_hits:
            print(f'\n=== {u} (len={len(body)}) ===')
            for h in sorted(workshop_hits)[:20]:
                print('   ', h)
    except Exception as e:
        print(f'{u}: EXC {e}')
