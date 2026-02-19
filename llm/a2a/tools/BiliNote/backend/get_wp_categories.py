import paramiko

# SSH 连接
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('38.182.122.28', port=30022, username='root', password='NALS5WFx9DGU')

# 查询分类
cmd = '''docker exec wordpress_db mysql -uwordpressuser -pwordpresspassword wordpress -N -e "SELECT t.term_id, t.name, t.slug FROM wp_terms t JOIN wp_term_taxonomy tt ON t.term_id=tt.term_id WHERE tt.taxonomy='category' ORDER BY t.term_id;"'''

stdin, stdout, stderr = ssh.exec_command(cmd)
print("WordPress 分类列表:")
print("-" * 50)
for line in stdout:
    print(line.strip())
print("-" * 50)
ssh.close()
