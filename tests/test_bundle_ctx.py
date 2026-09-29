import sys, re
sys.path.insert(0, ".")
import truststore, requests
truststore.inject_into_ssl()
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
s = requests.Session(); s.headers['User-Agent'] = UA
jr = s.get('https://cdn.fastly.steamstatic.com/steamcommunity/public/ssr/BKzAbcf9.js', timeout=30)
body = jr.text
i = body.find('workshop_browse')
# 打印 workshop_browse 周围 3000 字符
print(body[max(0,i-800):i+2200])
