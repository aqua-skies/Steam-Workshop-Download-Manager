"""诊断某些游戏浏览页返回 0 的原因。"""
import sys, io
sys.path.insert(0, ".")
import truststore, requests, re
truststore.inject_into_ssl()
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
s = requests.Session(); s.headers['User-Agent'] = UA

CARD_RE = re.compile(
    r'<a href="https://steamcommunity\.com/sharedfiles/filedetails/\?id=(\d+)"[^>]*>\s*'
    r'<img src="([^"]+)" alt="([^"]*)"'
)

def probe(appid, params):
    r = s.get('https://steamcommunity.com/workshop/browse/', params={'appid': appid, **params}, timeout=30)
    cards = CARD_RE.findall(r.text)
    title = re.findall(r'<title>([^<]*)</title>', r.text)
    return r.status_code, len(cards), (title[0][:70] if title else ''), r.url[:100]

tests = [
    ('258130', {}),                        # Don't Starve Together，默认参数
    ('258130', {'p':1,'actualsort':'trend','browsesort':'trend','numperpage':30,'l':'schinese'}),
    ('258130', {'p':1,'l':'schinese'}),
    ('258130', {'p':1}),
    ('258130', {'p':1,'browsesort':'trend','l':'schinese'}),
    ('821130', {'p':1,'actualsort':'trend','browsesort':'trend','numperpage':30,'l':'schinese'}),
    ('821130', {'p':1}),
    ('4000', {'p':1,'actualsort':'trend','browsesort':'trend','numperpage':30,'l':'schinese'}),
]
for appid, params in tests:
    try:
        st, n, t, url = probe(appid, params)
        print(f'[{st}] appid={appid} params={params} -> cards={n} title={t!r}')
    except Exception as e:
        print(f'[EXC] appid={appid} params={params} -> {type(e).__name__}: {str(e)[:120]}')
