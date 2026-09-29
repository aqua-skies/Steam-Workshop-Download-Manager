import sys, re
sys.path.insert(0, ".")
import truststore, requests
truststore.inject_into_ssl()
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
s = requests.Session(); s.headers['User-Agent'] = UA

r = s.get('https://steamcommunity.com/workshop/browse/', params={'appid': '258130'}, timeout=30)
html = r.text
print('len:', len(html))
# 查找可能的提示信息
for pat in ['login', 'sign in', 'must own', 'age', '不存在', '无权', '登录', 'error', 'No items', '没有', 'empty']:
    found = re.findall(rf'[^<>]{{0,60}}{pat}[^<>]{{0,60}}', html, re.I)
    if found:
        print(f'--- pattern {pat!r}: {len(found)} hits, sample: {[f.strip()[:80] for f in found[:3]]}')
# 查看是否有任何 sharedfiles 链接形式
print('any sharedfiles:', len(re.findall(r'sharedfiles', html)))
# 检查页面是否有 'workshopBrowseItems' 或 JS 数据
m = re.findall(r'(workshop\w+)', html)
print('workshop* tokens:', list(dict.fromkeys(m))[:15])
# 找到第一个含 "app" 的链接
apps = re.findall(r'href="https://steamcommunity\.com/app/(\d+)"', html)
print('app links:', list(dict.fromkeys(apps))[:5])
