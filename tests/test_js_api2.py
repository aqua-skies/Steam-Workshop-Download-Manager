import sys, re
sys.path.insert(0, ".")
import truststore, requests
truststore.inject_into_ssl()
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
s = requests.Session(); s.headers['User-Agent'] = UA
r = s.get('https://steamcommunity.com/workshop/browse/', params={'appid': '258130'}, timeout=30)
html = r.text

# 全部 js 引用（含动态 import 的 chunk 名）
js_refs = set(re.findall(r'https://cdn\.fastly\.steamstatic\.com/steamcommunity/public/ssr/[A-Za-z0-9_\-]+\.js', html))
js_refs |= set(re.findall(r'https://steamcommunity\.com/public/javascript/[^"\']+\.js', html))
print('js refs:', len(js_refs))

# workshop 查询相关字符串（React Query key 名通常在源码里作为字面量）
KEYS = ['workshop_files', 'workshop_files_v', 'GetWorkshopFiles', 'workshop_browse', 'browse_items',
        'workshop_files_v2', 'workshop_items', 'appworkshop', 'GetItems', 'files_v']
found = {}
for u in sorted(js_refs):
    try:
        jr = s.get(u, timeout=30)
        if jr.status_code != 200:
            continue
        body = jr.text
        for k in KEYS:
            if k in body:
                # 取上下文
                for m in re.finditer(re.escape(k), body):
                    ctx = body[max(0, m.start()-120):m.end()+120].replace('\n', ' ')
                    found.setdefault(k, []).append((u.split('/')[-1], ctx))
                    break
    except Exception as e:
        print(u, 'EXC', e)

print('\n=== KEY HITS ===')
for k, v in found.items():
    print(f'\n{k}:')
    for name, ctx in v[:3]:
        print(f'  [{name}] ...{ctx}...')
