import sys, re
sys.path.insert(0, ".")
import truststore, requests
truststore.inject_into_ssl()
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
s = requests.Session(); s.headers['User-Agent'] = UA
jr = s.get('https://cdn.fastly.steamstatic.com/steamcommunity/public/ssr/BKzAbcf9.js', timeout=30)
body = jr.text

# 枚举所有 h(...) / g(...) / y(...) 形式的 API 调用
calls = re.findall(r'(?:await\s+)?[a-zA-Z]{1,2}\(\s*[`"\'](/[\w/]+)[`"\']\s*,\s*[`"\'](\w+)[`"\']', body)
print('=== API METHOD CALLS ===')
seen = set()
for path, method in calls:
    key = (path, method)
    if key not in seen:
        seen.add(key)
        print(f'  {path} :: {method}')

# 同时找 workshop_browse 的 queryFn 真正调的方法
print('\n=== h/g 函数定义（找 URL 构造） ===')
for m in re.finditer(r'function\s+h\(', body):
    print(body[m.start():m.start()+400])
    break
for m in re.finditer(r'function\s+g\(', body):
    print(body[m.start():m.start()+400])
    break
