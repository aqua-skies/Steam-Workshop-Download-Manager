import json

with open('.agent-teams/swdm-138/team.json', encoding='utf-8') as f:
    data = json.load(f)

with open('t2122.txt', 'w', encoding='utf-8') as out:
    for t in data['tasks']:
        if t['id'] in ('t21', 't22', 't23', 't24', 't25'):
            out.write('=' * 15 + ' ' + t['id'] + ' | ' + str(t['status']) + ' | ' + str(t.get('assignee')) + ' | ' + str(t.get('verdict')) + ' ' + '=' * 15 + '\n')
            out.write('OUTPUT:\n' + str(t.get('output', ''))[:4000] + '\n\n')
print('done')
