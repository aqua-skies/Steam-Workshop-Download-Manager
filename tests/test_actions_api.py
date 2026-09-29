import sys, re
sys.path.insert(0, ".")
import truststore, requests
truststore.inject_into_ssl()
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
s = requests.Session(); s.headers['User-Agent'] = UA
s.headers['Referer'] = 'https://steamcommunity.com/workshop/browse/?appid=258130'

# 1) 验证 URL 格式：GET 与 POST 两种
for method, params in [
    ('GET',  {'appid': 258130}),
    ('POST', None),
]:
    if method == 'GET':
        r = s.get('https://steamcommunity.com/workshop/actions/GetUserWorkshopAppDetails',
                  params=params, timeout=30)
    else:
        r = s.post('https://steamcommunity.com/workshop/actions/GetUserWorkshopAppDetails',
                   data={'appid': 258130}, timeout=30)
    print(f'{method} -> [{r.status_code}] {r.text[:300]}')
