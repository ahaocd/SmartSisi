"""
解析抖音browser_snapshot的YAML结构，提取评论信息
"""
import sys
import io
import re
from typing import List, Dict, Optional

# 强制UTF-8输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def parse_douyin_comments_from_snapshot(snapshot_text: str) -> List[Dict]:
    """
    从browser_snapshot的YAML结构中提取评论信息
    
    Args:
        snapshot_text: browser_snapshot返回的完整文本
    
    Returns:
        评论列表，每个评论包含：
        - nickname: 昵称
        - user_url: 用户主页URL
        - user_id: 用户ID（从URL提取）
        - comment_text: 评论内容
        - ref_nickname: 昵称的ref（用于点击）
        - ref_reply: 回复按钮的ref（用于点击回复）
    """
    comments = []
    lines = snapshot_text.split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 查找昵称链接（格式：- link "昵称" [ref=eXXX] [cursor=pointer]:）
        nickname_match = re.search(r'- link "([^"]+)" \[ref=(e\d+)\] \[cursor=pointer\]:', line)
        
        if nickname_match and '头像' not in nickname_match.group(1):
            nickname = nickname_match.group(1)
            ref_nickname = nickname_match.group(2)
            
            # 排除导航栏和无关链接
            if nickname in ['精选', '推荐', 'AI抖音', '关注', '朋友', '我的', '直播', '放映厅', '短剧']:
                i += 1
                continue
            
            # 下一行应该是user URL
            if i + 1 < len(lines):
                url_line = lines[i + 1]
                url_match = re.search(r'- /url: (.+)', url_line)
                
                if url_match:
                    user_url = url_match.group(1).strip()
                    
                    # 必须是user主页URL
                    if '/user/' in user_url:
                        # 提取user_id
                        user_id = user_url.split('/user/')[-1].split('?')[0] if '/user/' in user_url else nickname
                        
                        # 向下找评论文本（通常在昵称后面几行）
                        comment_text = ""
                        for j in range(i + 2, min(i + 20, len(lines))):
                            # 评论文本的格式：- generic [ref=eXXX]: 评论内容
                            # 或者：- text: 评论内容
                            text_match1 = re.search(r'- generic \[ref=e\d+\]: (.+)', lines[j])
                            text_match2 = re.search(r'- text: (.+)', lines[j])
                            
                            if text_match1:
                                potential_text = text_match1.group(1).strip()
                                # 排除时间、地点等
                                if '分钟前' not in potential_text and '小时前' not in potential_text and \
                                   '天前' not in potential_text and '周前' not in potential_text and \
                                   '月前' not in potential_text and '年前' not in potential_text and \
                                   '·' not in potential_text and \
                                   len(potential_text) > 5:  # 评论至少5个字符
                                    comment_text = potential_text
                                    break
                            elif text_match2:
                                comment_text = text_match2.group(1).strip()
                                break
                        
                        # 向下找回复按钮的ref
                        ref_reply = None
                        for j in range(i + 2, min(i + 30, len(lines))):
                            reply_match = re.search(r'- generic \[ref=(e\d+)\] \[cursor=pointer\]:', lines[j])
                            if reply_match and j + 2 < len(lines):
                                # 检查后面是否有"回复"文字
                                if '回复' in lines[j + 2]:
                                    ref_reply = reply_match.group(1)
                                    break
                        
                        comments.append({
                            'nickname': nickname,
                            'user_url': user_url,
                            'user_id': user_id,
                            'comment_text': comment_text,
                            'ref_nickname': ref_nickname,
                            'ref_reply': ref_reply
                        })
        
        i += 1
    
    return comments


# 测试函数
if __name__ == '__main__':
    # 读取snapshot文件
    import sys
    if len(sys.argv) > 1:
        snapshot_file = sys.argv[1]
    else:
        snapshot_file = r"C:\Users\senlin\.cursor\browser-logs\snapshot-2025-11-07T07-29-41-309Z.log"
    
    with open(snapshot_file, 'r', encoding='utf-8') as f:
        snapshot_text = f.read()
    
    comments = parse_douyin_comments_from_snapshot(snapshot_text)
    
    print(f"\n✅ 提取到 {len(comments)} 个评论：\n")
    for i, c in enumerate(comments, 1):
        print(f"{i}. {c['nickname']:15s} | {c['comment_text'][:60]}...")
        print(f"   URL: {c['user_url'][:80]}...")
        print(f"   User ID: {c['user_id'][:30]}...")
        print(f"   Ref昵称: {c['ref_nickname']:10s} | Ref回复: {c['ref_reply']}")
        print()

