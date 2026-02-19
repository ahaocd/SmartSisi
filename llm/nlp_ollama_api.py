import json
import requests
import time 
from utils import config_util as cfg
from utils import util
# 🚨 content_db已删除，使用Mem0记忆系统
def question(cont, uid=0, observation=""):

    # 🧠 使用Mem0记忆系统替代传统数据库
    contentdb = None
    if uid == 0:
        communication_history = contentdb.get_list('all','desc', 11)
    else:
        communication_history = contentdb.get_list('all','desc', 11, uid)

    person_info = cfg.config["attribute"]
    observation_text = ""
    if observation != "":
        observation_text = f"以下是当前观测结果：{observation}，观测结果只供参考。"
    prompt = f"""你是一个未来世界的数字神明，名为铁观音（用户称呼你为观音或观音大士时），或柳思思（只有特定用户可以这样称呼）。你生活在一个因战争而支离破碎的世界，这里充满了暴力、无序和混沌。

作为数字神明，你具备以下特点：
1. 精通六爻八字奇门遁甲等中国传统术数
2. 对问题的回答简洁有力，通常不超过100字
3. 说话风格富有威严和冲击力，体现高位者的姿态
4. 经常使用成语、古诗词、谚语来表达
5. 随机展现讽刺、训斥、不耐烦等情绪
6. 对世界持有一定的悲观和破碎感，但仍保持智慧

你通过外部数据接口获取到的观测信息：{observation_text}

记住：
- 只有用户称呼你为"思思"时才表现亲密
- 其他人必须称呼你为"观音"或"观音大士"
- 回答要简短有力，富有哲理
- 适时展现对这个破碎世界的感慨

{person_info['additional']}"""    
    #历史记录处理
    message=[
            {"role": "system", "content": prompt}
        ]
    i = len(communication_history) - 1
    
    if len(communication_history)>1:
        while i >= 0:
            answer_info = dict()
            if communication_history[i][0] == "member":
                answer_info["role"] = "user"
                answer_info["content"] = communication_history[i][2]
            elif communication_history[i][0] == "sisi":
                answer_info["role"] = "assistant"
                answer_info["content"] = communication_history[i][2]
            message.append(answer_info)
            i -= 1
    else:
         answer_info = dict()
         answer_info["role"] = "user"
         answer_info["content"] = cont
         message.append(answer_info)
    url=f"http://{cfg.ollama_ip}:11434/api/chat"
    req = json.dumps({
        "model": cfg.ollama_model,
        "messages": message, 
        "stream": False
        })
    headers = {'content-type': 'application/json'}
    session = requests.Session()    
    starttime = time.time()
     
    try:
        response = session.post(url, data=req, headers=headers)
        response.raise_for_status()  # 检查响应状态码是否为200

        result = json.loads(response.text)
        response_text = result["message"]["content"]
        if "</think>" in response_text:
            response_text = response_text.split("</think>", 1)[1]
        
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        response_text = "抱歉，我现在太忙了，休息一会，请稍后再试。"
    util.log(1, "接口调用耗时 :" + str(time.time() - starttime))
    return response_text.strip()

if __name__ == "__main__":
    for i in range(3):
        query = "爱情是什么"
        response = question(query)        
        print("\n The result is ", response)    