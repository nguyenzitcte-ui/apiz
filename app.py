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
    <title>AI STV | RDP Manager</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root { --bg-color: #0f1115; --card-bg: #1a1d24; --card-border: #2a2f3a; --text-main: #e2e8f0; --text-muted: #94a3b8; --accent-blue: #3b82f6; --accent-green: #10b981; --accent-red: #ef4444; --accent-yellow: #f59e0b; --input-bg: #111318; }
        body { font-family: 'Segoe UI', sans-serif; background-color: var(--bg-color); color: var(--text-main); padding: 20px; margin: 0; }
        .container { max-width: 800px; margin: auto; background: var(--card-bg); padding: 25px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); margin-bottom: 25px; border: 1px solid var(--card-border); }
        h1, h2 { color: var(--text-main); border-bottom: 1px solid var(--card-border); padding-bottom: 12px; font-weight: 500; margin-top: 0; }
        h3 { margin: 0 0 10px 0; color: var(--accent-blue); font-weight: 500; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 8px; color: var(--text-muted); font-size: 14px; }
        input[type="text"] { width: 100%; padding: 12px; background: var(--input-bg); border: 1px solid var(--card-border); border-radius: 6px; color: var(--text-main); box-sizing: border-box; font-size: 14px; }
        input[type="text"]:focus { outline: none; border-color: var(--accent-blue); }
        button { padding: 10px 16px; border: none; border-radius: 6px; cursor: pointer; margin-right: 8px; margin-top: 8px; font-weight: 500; font-size: 14px; color: white; }
        button:hover { opacity: 0.85; }
        .btn-save { background: var(--accent-blue); width: 100%; }
        .btn-run { background: var(--accent-green); }
        .btn-clear { background: var(--accent-yellow); color: black; }
        .btn-del { background: var(--accent-red); }
        .card { border: 1px solid var(--card-border); padding: 20px; margin-bottom: 15px; border-radius: 8px; background: var(--input-bg); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
        .card-info { flex: 1 1 250px; margin-bottom: 10px; }
        .card-info p { margin: 5px 0; font-size: 13px; color: var(--text-muted); }
        .status { padding: 12px; border-radius: 6px; margin-bottom: 20px; font-weight: 500; text-align: center; }
        .status-on { background: rgba(16, 185, 129, 0.1); border: 1px solid var(--accent-green); color: var(--accent-green); }
        .status-off { background: rgba(239, 68, 68, 0.1); border: 1px solid var(--accent-red); color: var(--accent-red); }
        .actions { display: flex; gap: 5px; flex-wrap: wrap; }
    </style>
</head>
<body>

<div class="container">
    <h1>⚙️ CÀI ĐẶT HỆ THỐNG</h1>
    <div class="status {% if bot_token %}status-on{% else %}status-off{% endif %}">
        Trạng thái Bot: {% if bot_token %} ✅ Đã cấu hình Token {% else %} ❌ Chưa cấu hình Token {% endif %}
    </div>
    <form action="/save_bot_token" method="POST">
        <div class="form-group">
            <label>Discord Bot Token</label>
            <input type="text" name="bot_token" value="{{ bot_token }}" placeholder="Dán Token Bot Discord vào đây..." required>
        </div>
        <button type="submit" class="btn-save">💾 Lưu & Khởi động Bot</button>
    </form>
</div>

<div class="container">
    <h1>🚀 AI STV RDP MANAGER</h1>
    <h2>➕ Thêm Cấu Hình RDP Mới</h2>
    <form action="/add" method="POST">
        <div class="form-group"><label>Tên gợi nhớ (VD: Tài khoản 1)</label><input type="text" name="name" required></div>
        <div class="form-group"><label>GitHub Token</label><input type="text" name="github_token" required></div>
        <div class="form-group"><label>Tailscale Auth Key</label><input type="text" name="tailscale_key" required></div>
        <div class="form-group"><label>Discord Webhook URL</label><input type="text" name="webhook_url" required></div>
        <button type="submit" class="btn-save">💾 Lưu Cấu Hình</button>
    </form>

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
                <form action="/run/{{ loop.index0 }}" method="POST"><button type="submit" class="btn-run">🚀 Chạy</button></form>
                <form action="/clear/{{ loop.index0 }}" method="POST"><button type="submit" class="btn-clear">🧹 Xóa Repo</button></form>
                <form action="/del/{{ loop.index0 }}" method="POST"><button type="submit" class="btn-del">🗑️ Xóa</button></form>
            </div>
        </div>
        {% endfor %}
    {% endif %}
</div>

</body>
</html>
"""

def load_json(file):
    if not os.path.exists(file): return {} if file == SETTINGS_FILE else []
    try:
        with open(file, 'r') as f: return json.load(f)
    except: return {} if file == SETTINGS_FILE else []

def save_json(file, data):
    with open(file, 'w') as f: json.dump(data, f, indent=4)

@app.route('/')
def dashboard():
    settings = load_json(SETTINGS_FILE)
    configs = load_json(CONFIG_FILE)
    return render_template_string(HTML_TEMPLATE, configs=configs, bot_token=settings.get("bot_token", ""))

@app.route('/save_bot_token', methods=['POST'])
def save_bot_token():
    save_json(SETTINGS_FILE, {"bot_token": request.form.get('bot_token')})
    return "Đã lưu Token! Hệ thống đang khởi động lại... <script>window.location.href='/';</script>"

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
    return "Đã thêm! <script>window.location.href='/';</script>"

@app.route('/del/<int:index>', methods=['POST'])
def del_config(index):
    configs = load_json(CONFIG_FILE)
    if 0 <= index < len(configs):
        configs.pop(index)
        save_json(CONFIG_FILE, configs)
    return "Đã xóa! <script>window.location.href='/';</script>"

@app.route('/run/<int:index>', methods=['POST'])
def run_config(index):
    configs = load_json(CONFIG_FILE)
    if 0 <= index < len(configs):
        Thread(target=setup_and_run_rdp, args=(configs[index],)).start()
    return "🚀 Đã gửi lệnh chạy RDP! Check Discord. <script>window.location.href='/';</script>"

@app.route('/clear/<int:index>', methods=['POST'])
def clear_repo(index):
    configs = load_json(CONFIG_FILE)
    if 0 <= index < len(configs):
        try:
            config = configs[index]
            user_info = github_api(config['github_token'], "GET", "/user").json()
            github_api(config['github_token'], "DELETE", f"/repos/{user_info['login']}/AISTV-AUTO-RDP")
        except: pass
    return "🧹 Đã xóa Repo! <script>window.location.href='/';</script>"

# --- LOGIC GITHUB ---
REPO_NAME = "AISTV-AUTO-RDP"
WORKFLOW_FILE = "rdp.yml"
YAML_CONTENT = """name: 🚀 AI STV AUTO RDP
on:
  workflow_dispatch:
    inputs:
      duration: { description: 'Thời gian', default: '1h', type: choice, options: ['1h', '3h', '5h40m'] }
jobs:
  Setup:
    runs-on: windows-latest
    timeout-minutes: 340
    steps:
      - name: 🎯 KHỞI ĐỘNG
        env: { DISCORD_WEBHOOK: ${{ secrets.DISCORD_WEBHOOK }} }
        run: |
          $p = @{ content = "📊 **LOG:** Đang khởi tạo máy chủ GitHub..." } | ConvertTo-Json
          Invoke-RestMethod -Uri $env:DISCORD_WEBHOOK -Method Post -Body $p -ContentType "application/json"
      - name: 🔧 CẤU HÌNH RDP & TAILSCALE
        env: { TAILSCALE_AUTH_KEY: ${{ secrets.TAILSCALE_AUTH_KEY }}, DISCORD_WEBHOOK: ${{ secrets.DISCORD_WEBHOOK }} }
        run: |
          Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name "fDenyTSConnections" -Value 0 -Force
          netsh advfirewall firewall add rule name="RDP" dir=in action=allow protocol=TCP localport=3389
          $msi = "$env:TEMP\\ts.msi"; Invoke-WebRequest -Uri "https://pkgs.tailscale.com/stable/tailscale-setup-latest-amd64.msi" -OutFile $msi
          Start-Process msiexec.exe -ArgumentList "/i", "`"$msi`"", "/quiet", "/norestart" -Wait; Start-Sleep 10
          & "$env:ProgramFiles\\Tailscale\\tailscale.exe" up --authkey=$env:TAILSCALE_AUTH_KEY --hostname=ai-stv --reset
          $ip = & "$env:ProgramFiles\\Tailscale\\tailscale.exe" ip -4
          $pw = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 8 | % {[char]$_})
          $sp = ConvertTo-SecureString $pw -AsPlainText -Force
          New-LocalUser -Name "AISTV" -Password $sp -AccountNeverExpires
          Add-LocalGroupMember -Group "Administrators" -Member "AISTV"; Add-LocalGroupMember -Group "Remote Desktop Users" -Member "AISTV"
          $e = @{ content = "@here 🚀 **RDP PREMIUM ĐÃ SẴN SÀNG!**"; embeds = @(@{ title = "🔗 Thông tin"; color = 65280; fields = @(@{ name="IP"; value="```$ip```"; inline=$false }, @{ name="User"; value="```AISTV```"; inline=$true }, @{ name="Pass"; value="```$pw```"; inline=$true }) }) } | ConvertTo-Json -Depth 5
          Invoke-RestMethod -Uri $env:DISCORD_WEBHOOK -Method Post -Body $e -ContentType "application/json"
      - name: ⏳ DUY TRÌ
        run: | 
          $e = (Get-Date).AddHours(1); while ((Get-Date) -lt $e) { Start-Sleep 60 }
"""

def github_api(token, method, endpoint, data=None):
    return requests.request(method, f"https://api.github.com{endpoint}", headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}, json=data)

def create_github_secret(token, owner, repo, name, value):
    key_res = github_api(token, "GET", f"/repos/{owner}/{repo}/actions/secrets/public-key").json()
    pub = public.PublicKey(key_res['key'].encode(), encoding.Base64Encoder())
    enc = public.SealedBox(pub).encrypt(value.encode())
    github_api(token, "PUT", f"/repos/{owner}/{repo}/actions/secrets/{name}", {"encrypted_value": base64.b64encode(enc).decode(), "key_id": key_res['key_id']})

def setup_and_run_rdp(config):
    gh, ts, wh = config['github_token'], config['tailscale_key'], config['webhook_url']
    owner = github_api(gh, "GET", "/user").json()['login']
    github_api(gh, "POST", "/user/repos", {"name": REPO_NAME, "private": True}); time.sleep(3)
    sha = None
    res = github_api(gh, "GET", f"/repos/{owner}/{REPO_NAME}/contents/.github/workflows/{WORKFLOW_FILE}")
    if res.status_code == 200: sha = res.json()['sha']
    payload = {"message": "Update", "content": base64.b64encode(YAML_CONTENT.encode()).decode()}
    if sha: payload["sha"] = sha
    github_api(gh, "PUT", f"/repos/{owner}/{REPO_NAME}/contents/.github/workflows/{WORKFLOW_FILE}", payload)
    create_github_secret(gh, owner, REPO_NAME, "TAILSCALE_AUTH_KEY", ts)
    create_github_secret(gh, owner, REPO_NAME, "DISCORD_WEBHOOK", wh)
    github_api(gh, "POST", f"/repos/{owner}/{REPO_NAME}/actions/workflows/{WORKFLOW_FILE}/dispatches", {"ref": "main", "inputs": {"duration": "1h"}})

# --- DISCORD BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Bot {bot.user} đã online!')

@bot.command()
async def rdp(ctx):
    configs = load_json(CONFIG_FILE)
    if not configs:
        return await ctx.send("Chưa có cấu hình nào. Vào web để thêm!")
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

# --- CHẠY HỆ THỐNG ---
# Chạy Flask (Web)
port = int(os.environ.get('PORT', 5000))
Thread(target=lambda: app.run(host='0.0.0.0', port=port), daemon=True).start()

# Kiểm tra xem có Token Bot trong file settings chưa, nếu có thì chạy Bot
settings = load_json(SETTINGS_FILE)
bot_token = settings.get("bot_token")
if bot_token:
    # Dùng Thread để chạy bot không làm chặn Flask Web
    Thread(target=lambda: bot.run(bot_token), daemon=True).start()
else:
    print("Chưa có Bot Token. Vào web để nhập!")
