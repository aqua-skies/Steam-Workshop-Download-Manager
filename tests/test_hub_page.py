"""测试新 hub 页面是否对 browse 返回空的游戏有效。"""
import sys, re
sys.path.insert(0, ".")
import truststore, requests
truststore.inject_into_ssl()
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
s = requests.Session(); s.headers['User-Agent'] = UA

CARD_RE = re.compile(
    r'<a href="https://steamcommunity\.com/sharedfiles/filedetails/\?id=(\d+)"[^>]*>\s*'
    r'<img src="([^"]+)" alt="([^"]*)"'
)

def show(label, url, params=None):
    try:
        r = s.get(url, params=params or {}, timeout=30)
        ids = re.findall(r'sharedfiles/filedetails/\?id=(\d+)', r.text)
        uniq = list(dict.fromkeys(ids))
        cards = CARD_RE.findall(r.text)
        title = re.findall(r'<title>([^<]*)</title>', r.text)
        print(f'{label}: [{r.status_code}] len={len(r.text)} raw_ids={len(ids)} uniq={len(uniq)} cards={len(cards)} title={(title[0][:50] if title else None)!r}')
        return uniq[:5]
    except Exception as e:
        print(f'{label}: EXC {type(e).__name__}: {str(e)[:100]}')
        return []

for appid in ('258130', '821130'):
    print(f'===== appid={appid} =====')
    a = show('  新hub /app/X/workshop/          ', f'https://steamcommunity.com/app/{appid}/workshop/')
    print('    ids:', a)
    b = show('  browse + section=readytouseitems', 'https://steamcommunity.com/workshop/browse/', {'appid': appid, 'section': 'readytouseitems'})
    print('    ids:', b)
    c = show('  browse + browsefilter=mostrecent', 'https://steamcommunity.com/workshop/browse/', {'appid': appid, 'browsefilter': 'mostrecent', 'actualsort': 'mostrecent'})
    print('    ids:', c)
