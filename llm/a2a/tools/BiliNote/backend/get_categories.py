#!/usr/bin/env python
"""通过SSH连接服务器查询WordPress分类ID"""
import paramiko
import time

# SSH配置
SSH_HOST = "38.182.122.28"
SSH_PORT = 30022
SSH_USER = "root"
SSH_PASS = "NALS5WFx9DGU"

# MySQL查询
MYSQL_CMD = '''docker exec wordpress_db mysql -u wordpressuser -pwordpresspassword wordpress -e "
SELECT t.term_id, t.name, t.slug, tt.taxonomy, tt.count 
FROM wp_terms t 
JOIN wp_term_taxonomy tt ON t.term_id = tt.term_id 
WHERE tt.taxonomy = 'category' 
ORDER BY t.term_id;
"'''

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    for attempt in range(3):
        try:
            print(f"连接服务器... (尝试 {attempt+1}/3)")
            ssh.connect(SSH_HOST, port=SSH_PORT, username=SSH_USER, password=SSH_PASS, timeout=30, banner_timeout=30)
            break
        except Exception as e:
            print(f"连接失败: {e}")
            if attempt < 2:
                time.sleep(2)
            else:
                return
    
    print("查询WordPress分类...\n")
    stdin, stdout, stderr = ssh.exec_command(MYSQL_CMD, timeout=30)
    
    output = stdout.read().decode('utf-8')
    error = stderr.read().decode('utf-8')
    
    if error and 'Warning' not in error:
        print(f"错误: {error}")
    
    print(output)
    
    ssh.close()

if __name__ == "__main__":
    main()
