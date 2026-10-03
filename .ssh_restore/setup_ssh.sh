#!/bin/bash
# 恢复 SSH 配置和密钥（沙箱重置后运行一次即可）
set -e

mkdir -p ~/.ssh
chmod 700 ~/.ssh

# 恢复密钥
cp /workspace/.ssh_restore/id_ed25519 ~/.ssh/id_ed25519
cp /workspace/.ssh_restore/id_ed25519.pub ~/.ssh/id_ed25519.pub
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub

# 写入 SSH config（通过本地 HTTP 代理 18080 建隧道）
cat > ~/.ssh/config << 'EOF'
Host job-server
    HostName 47.250.216.165
    User admin
    Port 22
    IdentityFile ~/.ssh/id_ed25519
    ProxyCommand nc -X connect -x 127.0.0.1:18080 %h %p
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 10m
EOF
chmod 600 ~/.ssh/config

echo "SSH 配置已恢复。测试连接："
ssh -o ConnectTimeout=10 job-server "echo '连接成功' && hostname"
