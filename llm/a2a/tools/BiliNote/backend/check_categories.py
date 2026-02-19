import requests

r = requests.get(
    'https://xasia.cc/wp-json/wp/v2/categories?per_page=100', 
    auth=('67859543', 'XqXt bHFX rwL3 M5kc rDqd HXD2')
)
for c in r.json():
    print(f"ID={c['id']}, name={c['name']}, slug={c['slug']}")
