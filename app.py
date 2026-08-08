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

# ==========================================
DISCORD_BOT_TOKEN = 'MTMzMDg4Nzk2NDI2NzUxNTkzNA.Gdnigp.xdve_AlqdzV9iipvMwqYBsWaO78UVn2IZalhzM'
# ==========================================

CONFIG_FILE = "config.json"

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AI STV | RDP Manager</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {
            --bg-color: #0f1115;
            --card-bg: #1a1d24;
            --card-border: #2a2f3a;
            --text-main: #e2e8f0;
            --text-muted: #94a3b8;
            --accent-blue: #3b82f6;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --accent-yellow: #f59e0b;
            --input-bg: #111318;
        }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: var(--bg-color); color: var(--text-main); padding: 20px; margin: 0; }
        .container { max-width: 800px; margin: auto; background: var(--card-bg); padding: 25px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); margin-bottom: 25px; border: 1px solid var(--card-border); }
        h1, h2 { color: var(--text-main); border-bottom: 1px solid var(--card-border); padding-bottom: 12px; font-weight: 500; margin-top: 0; }
        h3 { margin: 0 0 10px 0; color: var(--accent-blue); font-weight: 500; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 8px; color: var(--text-muted); font-size: 14px; font-weight: 500; }
        input[type="text"] { width: 100%; padding: 12px; background: var(--input-bg); border: 1px solid var(--card-border); border-radius: 6px; color: var(--text-main); box-sizing: border-box; font-size: 14px; transition: 0.2s; }
        input[type="text"]:focus { outline: none; border-color: var(--accent-blue); }
        button { padding: 10px 16px; border: none; border-radius: 6px; cursor: pointer; margin-right: 8px; margin-top: 8px; font-weight: 500; font-size: 14px; transition: 0.2s; }
        button:hover { opacity: 0.85; }
        .btn-save { background: var(--accent-blue); color: white; width: 100%; }
        .btn-run { background: var(--accent-green); color: white; }
        .btn-clear { background: var(--accent-yellow); color: black; }
        .btn-del { background: var(--accent-red); color: white; }
        .card { border: 1px solid var(--card-border); padding: 20px; margin-bottom: 15px; border-radius: 8px; background: var(--input-bg); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
        .card-info { flex: 1 1 250px; margin-bottom: 10px; }
        .card-info p { margin: 5px 0; font-size: 13px; color: var(--text-muted); }
        .status { padding: 12px; background: rgba(16, 185, 129, 0.1); border: 1px solid var(--accent-green); border-radius: 6px; margin-bottom: 20px; color: var(--accent-green); font-weight: 500; text-align: center; }
        .actions { display: flex; gap: 5px; flex-wrap: wrap; }
    </style>
</head>
<body>

<div class="container">
    <h1>⚙️ AI STV RDP MANAGER</h1>
    <div class="status">✅ HỆ THỐNG HOẠT ĐỘNG ỔN ĐỊNH</div>
    
    <h2>➕ Thêm Cấu Hình Mới</h2>
    <form action="/add" method="POST">
        <div class="form-group">
            <label>Tên gợi nhớ (VD: Tài khoản 1)</label>
            <input type="text" name="name" required>
        </div>
        <div class="form-group">
            <label>GitHub Token</label>
            <input type="text" name="github_token" required>
        </div>
        <div class="form-group">
            <label>Tailscale Auth Key</label>
            <input type="text" name="tailscale_key" required>
        </div>
        <div class="form-group">
            <label>Discord Webhook URL</label>
            <input type="text" name="webhook_url" required>
        </div>
        <button type="submit" class="btn-save">💾 Lưu Cấu Hình</button>
    </form>
</div>

<div class="container">
    <h2>📋 Danh Sách RDP</h2>
    {% if configs.length == 0 %}
        <p style="color: var(--text-muted);">Chưa có cấu hình nào. Hãy thêm ở trên!</p>
    {% else %}
        {% for c in configs %}
        <div class="card">
            <div class="card-info">
                <h3>{{ c.name }}</h3>
                <p><b>GitHub:</b> {{ c.github_token[:10] }}...{{ c.github_token[-4:] }}</p>
                <p><b>Tailscale:</b> {{ c.tailscale_key[:10] }}...</p>
            </div>
            <div class="actions">
                <form action="/run/{{ loop.index0 }}" method="POST">
                    <button type="submit" class="btn-run">🚀 Chạy</button>
                </form>
                <form action="/clear/{{ loop.index0 }}" method="POST">
                    <button type="submit" class="btn-clear">🧹 Xóa Repo</button>
                </form>
                <form action="/del/{{ loop.index0 }}" method="POST">
                    <button type="submit" class="btn-del">🗑️ Xóa</button>
                </form>
            </div>
        </div>
        {% endfor %}
    {% endif %}
</div>

</body>
</html>
"""

def load_configs():
    if not os.path.exists(CONFIG_FILE):
        return []
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_configs(configs):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(configs, f, indent=4)

@app.route('/')
def dashboard():
    configs = load_configs()
    return render_template_string(HTML_TEMPLATE, configs=configs)

@app.route('/add', methods=['POST'])
def add_config():
    configs = load_configs()
    configs.append({
        "name": request.form.get('name'),
        "github_token": request.form.get('github_token'),
        "tailscale_key": request.form.get('tailscale_key'),
        "webhook_url": request.form.get('webhook_url')
    })
    save_configs(configs)
    return "Đã thêm! <script>window.location.href='/';</script>"

@app.route('/del/<int:index>', methods=['POST'])
def del_config(index):
    configs = load_configs()
    if 0 <= index < len(configs):
        configs.pop(index)
        save_configs(configs)
    return "Đã xóa! <script>window.location.href='/';</script>"

@app.route('/run/<int:index>', methods=['POST'])
def run_config(index):
    configs = load_configs()
    if 0 <= index < len(configs):
        Thread(target=setup_and_run_rdp, args=(configs[index],)).start()
        return "🚀 Đã gửi lệnh chạy! Check Discord. <script>window.location.href='/';</script>"
    return "Lỗi!"

@app.route('/clear/<int:index>', methods=['POST'])
def clear_repo(index):
    configs = load_configs()
    if 0 <= index < len(configs):
        config = configs[index]
        try:
            user_info = github_api(config['github_token'], "GET", "/user").json()
            owner = user_info['login']
            github_api(config['github_token'], "DELETE", f"/repos/{owner}/AISTV-AUTO-RDP")
            return "🧹 Đã xóa Repo! <script>window.location.href='/';</script>"
        except:
            return "Lỗi xóa repo. <script>window.location.href='/';</script>"
    return "Lỗi!"

# --- LOGIC BOT & GITHUB ---
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
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
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
    
    github_api(gh_token, "POST", "/user/repos", {"name": REPO_NAME, "private": True})
    time.sleep(3)
    
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
    configs = load_configs()
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
    configs = load_configs()
    if 0 <= index < len(configs):
        await ctx.send(f"🚀 Đang chạy RDP cho: {configs[index]['name']}...")
        Thread(target=setup_and_run_rdp, args=(configs[index],)).start()
    else:
        await ctx.send("Số thứ tự không hợp lệ!")

# Khởi động Bot nền (chạy cùng lúc với Gunicorn Web Server)
def start_bot():
    if DISCORD_BOT_TOKEN and DISCORD_BOT_TOKEN != 'dán_token_bot_discord_vào_đây':
        bot.run(DISCORD_BOT_TOKEN)

Thread(target=start_bot, daemon=True).start()
