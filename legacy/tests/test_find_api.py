import sys, re, json
sys.path.insert(0, ".")
import truststore, requests
truststore.inject_into_ssl()
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
s = requests.Session(); s.headers['User-Agent'] = UA
r = s.get('https://steamcommunity.com/workshop/browse/', params={'appid': '258130'}, timeout=30)
html = r.text

# 查找所有 api 端点
apis = re.findall(r'https://steamcommunity\.com/api/[A-Za-z0-9_/]+', html)
print('api endpoints found:', list(dict.fromkeys(apis))[:15])

# 查找 queryKey
qk = re.findall(r'queryKey[\\":\[\],a-zA-Z0-9_\-]{5,80}', html)
print('\nqueryKey samples:', list(dict.fromkeys(qk))[:10])

# 查找可能的内联数据中的 publishedfileid
pf = re.findall(r'publishedfileid[\\":\s]*(\d{6,})', html)
print('\npublishedfileid in html:', len(pf), pf[:5])

# 查找 JSON 中的 items 数组线索
m = re.findall(r'"queryKey":\s*(\[[^\]]{0,120}\])', html)
print('\nqueryKey JSON:', list(dict.fromkeys(m))[:10])
