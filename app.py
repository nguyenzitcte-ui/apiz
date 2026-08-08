import discord
from discord.ext import commands
from flask import Flask, request, render_template_string
from threading import Thread
import requests
import base64
from nacl import encoding, public
import os
import time
import json

CONFIG_FILE = "config.json"
SETTINGS_FILE = "settings.json"

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AI STV RDP Manager</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f4f7f6; padding: 20px; }
        .container { max-width: 800px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }
        h1, h2 { color: #333; border-bottom: 2px solid #f4f7f6; padding-bottom: 10px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type="text"] { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
        button { background-color: #28a745; color: white; padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; margin-right: 5px; margin-top: 5px;}
        button:hover { opacity: 0.9; }
        .card { border: 1px solid #ddd; padding: 15px; margin-bottom: 15px; border-radius: 8px; background: #fafafa; }
        .btn-run { background-color: #007bff; }
        .btn-del { background-color: #dc3545; }
        .btn-clear { background-color: #ffc107; color: black; }
        .btn-save { background-color: #6c757d; }
        .status { padding: 10px; background: #e9ecef; border-radius: 4px; margin-bottom: 15px; }
    </style>
</head>
<body>

<div class="container">
    <h1>⚙️ CÀI ĐẶT HỆ THỐNG</h1>
    <div class="status">
        Trạng thái Bot: {% if bot_token %} ✅ Đã cấu hình {% else %} ❌ Chưa cấu hình {% endif %}
    </div>
    <form action="/save_bot_token" method="POST">
        <div class="form-group">
            <label>Discord Bot Token</label>
            <input type="text" name="bot_token" value="{{ bot_token }}" placeholder="Dán Token Bot Discord vào đây...">
        </div>
        <button type="submit" class="btn-save">💾 Lưu & Khởi động Bot</button>
    </form>
</div>

<div class="container">
    <h1>🚀 AI STV RDP MANAGER</h1>
    
    <h2>➕ Thêm Cấu Hình RDP Mới</h2>
    <form action="/add" method="POST">
        <div class="form-group">
            <label>Tên gợi nhớ (VD: Tài khoản 1)</label>
            <input type="text" name="name" required>
        </div>
        <div class="form-group">
            <label>GitHub Token (All quyền)</label>
            <input type="text" name="github_token" required>
        </div>
        <div class="form-group">
            <label>Tailscale Auth Key (tskey-auth...)</label>
            <input type="text" name="tailscale_key" required>
        </div>
        <div class="form-group">
            <label>Discord Webhook URL</label>
            <input type="text" name="webhook_url" required>
        </div>
        <button type="submit">Lưu Cấu Hình</button>
    </form>

    <h2>📋 Danh Sách RDP</h2>
    {% if configs.length == 0 %}
        <p>Chưa có cấu hình nào. Hãy thêm ở trên!</p>
    {% else %}
        {% for c in configs %}
        <div class="card">
            <h3>{{ c.name }}</h3>
            <p><b>GitHub:</b> {{ c.github_token[:10] }}...{{ c.github_token[-4:] }}</p>
            <p><b>Tailscale:</b> {{ c.tailscale_key[:10] }}...</p>
            
            <form action="/run/{{ loop.index0 }}" method="POST" style="display:inline;">
                <button type="submit" class="btn-run">🚀 Chạy RDP / Chạy lại</button>
            </form>
            <form action="/clear/{{ loop.index0 }}" method="POST" style="display:inline;">
                <button type="submit" class="btn-clear">🧹 Xóa Repo GitHub</button>
            </form>
            <form action="/del/{{ loop.index0 }}" method="POST" style="display:inline;">
                <button type="submit" class="btn-del">🗑️ Xóa Cấu Hình</button>
            </form>
        </div>
        {% endfor %}
    {% endif %}
</div>
</body>
</html>
"""

def load_json(file):
    if not os.path.exists(file):
        return {} if file == SETTINGS_FILE else []
    with open(file, 'r') as f:
        return json.load(f)

def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=4)

@app.route('/')
def dashboard():
    settings = load_json(SETTINGS_FILE)
    configs = load_json(CONFIG_FILE)
    return render_template_string(HTML_TEMPLATE, configs=configs, bot_token=settings.get("bot_token", ""))

@app.route('/save_bot_token', methods=['POST'])
def save_bot_token():
    save_json(SETTINGS_FILE, {"bot_token": request.form.get('bot_token')})
    # Tự động crash app để Render tự động Restart, từ đó bot sẽ lấy token mới mà chạy
    os._exit(1)
    return "Đang lưu..."

@app.route('/add', methods=['POST'])
def add_config():
    configs = load_json(CONFIG_FILE)
    configs.append({
        "name": request.form.get('name'),
        "github_token": request.form.get('github_token'),
        "tailscale_key": request.form.get('tailscale_key'),
        "webhook_url": request.form.get('webhook_url')
    })
    save_json(CONFIG_FILE, configs)
    return "Đã thêm! <a href='/'>Quay lại</a>"

@app.route('/del/<int:index>', methods=['POST'])
def del_config(index):
    configs = load_json(CONFIG_FILE)
    if 0 <= index < len(configs):
        configs.pop(index)
        save_json(CONFIG_FILE, configs)
    return "Đã xóa! <a href='/'>Quay lại</a>"

@app.route('/run/<int:index>', methods=['POST'])
def run_config(index):
    configs = load_json(CONFIG_FILE)
    if 0 <= index < len(configs):
        Thread(target=setup_and_run_rdp, args=(configs[index],)).start()
        return "🚀 Đã gửi lệnh chạy RDP! Check Discord để nhận IP và Mật khẩu. <a href='/'>Quay lại</a>"
    return "Lỗi!"

@app.route('/clear/<int:index>', methods=['POST'])
def clear_repo(index):
    configs = load_json(CONFIG_FILE)
    if 0 <= index < len(configs):
        config = configs[index]
        try:
            user_info = github_api(config['github_token'], "GET", "/user").json()
            owner = user_info['login']
            github_api(config['github_token'], "DELETE", f"/repos/{owner}/AISTV-AUTO-RDP")
            return "🧹 Đã xóa Repo GitHub! <a href='/'>Quay lại</a>"
        except:
            return "Lỗi xóa repo. <a href='/'>Quay lại</a>"
    return "Lỗi!"

# --- LOGIC BOT DISCORD & GITHUB ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

REPO_NAME = "AISTV-AUTO-RDP"
WORKFLOW_FILE = "rdp.yml"
YAML_CONTENT = """name: 🚀 AI STV AUTO RDP
on:
  workflow_dispatch:
    inputs:
      duration:
        description: 'Thời gian'
        default: '1h'
        type: choice
        options: ['1h', '3h', '5h40m']

jobs:
  Setup:
    runs-on: windows-latest
    timeout-minutes: 340
    steps:
      - name: 🎯 KHỞI ĐỘNG
        env:
          DISCORD_WEBHOOK: ${{ secrets.DISCORD_WEBHOOK }}
        run: |
          $payload = @{ content = "📊 **LOG:** Đang khởi tạo máy chủ GitHub Actions..." } | ConvertTo-Json
          Invoke-RestMethod -Uri $env:DISCORD_WEBHOOK -Method Post -Body $payload -ContentType "application/json"
          
      - name: 🔧 CẤU HÌNH RDP & TAILSCALE
        env:
          TAILSCALE_AUTH_KEY: ${{ secrets.TAILSCALE_AUTH_KEY }}
          DISCORD_WEBHOOK: ${{ secrets.DISCORD_WEBHOOK }}
        run: |
          Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name "fDenyTSConnections" -Value 0 -Force
          netsh advfirewall firewall add rule name="RDP" dir=in action=allow protocol=TCP localport=3389
          
          $msiPath = "$env:TEMP\\ts.msi"
          Invoke-WebRequest -Uri "https://pkgs.tailscale.com/stable/tailscale-setup-latest-amd64.msi" -OutFile $msiPath
          Start-Process msiexec.exe -ArgumentList "/i", "`"$msiPath`"", "/quiet", "/norestart" -Wait
          Start-Sleep -Seconds 10
          
          & "$env:ProgramFiles\\Tailscale\\tailscale.exe" up --authkey=$env:TAILSCALE_AUTH_KEY --hostname=ai-stv-premium --reset
          $ip = & "$env:ProgramFiles\\Tailscale\\tailscale.exe" ip -4
          
          $pw = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 8 | % {[char]$_})
          $sp = ConvertTo-SecureString $pw -AsPlainText -Force
          New-LocalUser -Name "AISTV" -Password $sp -AccountNeverExpires
          Add-LocalGroupMember -Group "Administrators" -Member "AISTV"
          Add-LocalGroupMember -Group "Remote Desktop Users" -Member "AISTV"
          
          $log = "✅ Đã kết nối Tailscale thành công! Đang tạo tài khoản..."
          $payload = @{ content = $log } | ConvertTo-Json
          Invoke-RestMethod -Uri $env:DISCORD_WEBHOOK -Method Post -Body $payload -ContentType "application/json"

          $embed = @{
            content = "@here 🚀 **RDP PREMIUM ĐÃ SẴN SÀNG!**"
            embeds = @(@{
              title = "🔗 Thông tin kết nối RDP"
              color = 65280
              fields = @(
                @{ name = "🌐 Địa chỉ IP"; value = "```$ip```"; inline = $false },
                @{ name = "👤 Tài khoản"; value = "```AISTV```"; inline = $true },
                @{ name = "🔐 Mật khẩu"; value = "```$pw```"; inline = $true }
              )
              footer = @{ text = "Powered by AI STV" }
            })
          } | ConvertTo-Json -Depth 5
          Invoke-RestMethod -Uri $env:DISCORD_WEBHOOK -Method Post -Body $embed -ContentType "application/json"

      - name: ⏳ DUY TRÌ
        run: |
          $endTime = (Get-Date).AddHours(1)
          while ((Get-Date) -lt $endTime) { Start-Sleep -Seconds 60 }
"""

def github_api(token, method, endpoint, data=None):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    res = requests.request(method, f"https://api.github.com{endpoint}", headers=headers, json=data)
    return res

def create_github_secret(token, owner, repo, secret_name, secret_value):
    key_res = github_api(token, "GET", f"/repos/{owner}/{repo}/actions/secrets/public-key").json()
    pub_key = public.PublicKey(key_res['key'].encode(), encoding.Base64Encoder())
    sealed_box = public.SealedBox(pub_key)
    encrypted = sealed_box.encrypt(secret_value.encode())
    secret_b64 = base64.b64encode(encrypted).decode()
    github_api(token, "PUT", f"/repos/{owner}/{repo}/actions/secrets/{secret_name}", {
        "encrypted_value": secret_b64, "key_id": key_res['key_id']
    })

def setup_and_run_rdp(config):
    gh_token = config['github_token']
    ts_key = config['tailscale_key']
    wh_url = config['webhook_url']
    
    user_info = github_api(gh_token, "GET", "/user").json()
    owner = user_info['login']
    
    # Tạo Repo (nếu đã có thì báo lỗi nhưng ta bỏ qua lỗi đó)
    github_api(gh_token, "POST", "/user/repos", {"name": REPO_NAME, "private": True})
    time.sleep(3)
    
    # Lấy SHA của file cũ nếu có (để update thay vì tạo mới)
    sha = None
    file_res = github_api(gh_token, "GET", f"/repos/{owner}/{REPO_NAME}/contents/.github/workflows/{WORKFLOW_FILE}")
    if file_res.status_code == 200:
        sha = file_res.json()['sha']
        
    content_b64 = base64.b64encode(YAML_CONTENT.encode()).decode()
    payload = {"message": "Update workflow", "content": content_b64}
    if sha: payload["sha"] = sha
    
    github_api(gh_token, "PUT", f"/repos/{owner}/{REPO_NAME}/contents/.github/workflows/{WORKFLOW_FILE}", payload)
    
    create_github_secret(gh_token, owner, REPO_NAME, "TAILSCALE_AUTH_KEY", ts_key)
    create_github_secret(gh_token, owner, REPO_NAME, "DISCORD_WEBHOOK", wh_url)
    
    github_api(gh_token, "POST", f"/repos/{owner}/{REPO_NAME}/actions/workflows/{WORKFLOW_FILE}/dispatches", {"ref": "main", "inputs": {"duration": "1h"}})

@bot.event
async def on_ready():
    print(f'Bot {bot.user} đã online!')

@bot.command()
async def rdp(ctx):
    configs = load_json(CONFIG_FILE)
    if not configs:
        await ctx.send("Chưa có cấu hình nào. Vào web để thêm!")
        return
    
    desc = "**Chọn cấu hình RDP để chạy:**\n"
    for i, c in enumerate(configs):
        desc += f"`{i}` - {c['name']}\n"
    desc += "\nGõ `!run <số>` (VD: `!run 0`)"
    await ctx.send(desc)

@bot.command()
async def run(ctx, index: int):
    configs = load_json(CONFIG_FILE)
    if 0 <= index < len(configs):
        await ctx.send(f"🚀 Đang chạy RDP cho: {configs[index]['name']}...")
        Thread(target=setup_and_run_rdp, args=(configs[index],)).start()
    else:
        await ctx.send("Số thứ tự không hợp lệ!")

if __name__ == "__main__":
    # Chạy Flask (Web)
    port = int(os.environ.get('PORT', 5000))
    Thread(target=lambda: app.run(host='0.0.0.0', port=port)).start()
    
    # Chạy Bot Discord (nếu đã có Token trên Web)
    settings = load_json(SETTINGS_FILE)
    bot_token = settings.get("bot_token")
    if bot_token:
        bot.run(bot_token)
    else:
        print("Chưa có Bot Token. Vào web để nhập!")
        # Giữ cho app chạy tiếp tục nếu chưa có token
        while True:
            time.sleep(3600)
