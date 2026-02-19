import json
import requests
from core import content_db


def question(cont, uid=0, observation=""):
    contentdb = content_db.new_instance()
    if uid == 0:
        list = contentdb.get_list('all','desc', 11, type='sisi')
    else:
        list = contentdb.get_list('all','desc', 11, uid, type='sisi')
    chat_list = []
    i = len(list)-1
    while i >= 0:
        chat_list.append(list[i][2])
        i -= 1
    content = {
        "prompt": cont,
        "history": chat_list
    }
    url = "http://127.0.0.1:8000/v1/completions"
    req = json.dumps(content)
    headers = {'content-type': 'application/json'}
    try:
        r = requests.post(url, headers=headers, data=req)
        res = json.loads(r.text).get('response')
        if not res:
            return "让我想想该怎么回答...", "gentle"
        return res, "gentle"
    except Exception as e:
        print(f"Error in question: {str(e)}")
        return "让我想想该怎么回答...", "gentle"

if __name__ == "__main__":
    print(question("你叫什么名字"))