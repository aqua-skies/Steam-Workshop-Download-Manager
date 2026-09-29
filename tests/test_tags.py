import truststore, requests, re, sys
truststore.inject_into_ssl()
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
s = requests.Session(); s.headers['User-Agent'] = UA

def ids_of(params):
    r = s.get('https://steamcommunity.com/workshop/browse/', params={'appid':4000, **params}, timeout=30)
    found = re.findall(r'sharedfiles/filedetails/\?id=(\d+)', r.text)
    return list(dict.fromkeys(found))

base = ids_of({'p':1})
tag_map = ids_of({'p':1, 'requiredtags[]':'map'})
tag_weapon = ids_of({'p':1, 'requiredtags[]':'weapon'})
print('base:', len(base), base[:4])
print('tag map:', len(tag_map), tag_map[:4])
print('tag weapon:', len(tag_weapon), weapon:=tag_weapon[:4])
print('base==tagmap?', set(base)==set(tag_map))
print('base==weapon?', set(base)==set(tag_weapon))
