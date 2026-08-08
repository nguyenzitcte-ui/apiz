import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta

# Load config
with open('config.json', 'r', encoding='utf-8') as f:
    CONFIG = json.load(f)

# Cấu hình intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Lưu trữ phiên RDP đang chạy
active_sessions = {}

GITHUB_API = "https://api.github.com"
HEADERS = {
    "Authorization": f"token {CONFIG['github_token']}",
    "Accept": "application/vnd.github.v3+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

# Vietnam timezone
VN_TZ = timezone(timedelta(hours=7))


class RDPSession:
    """Lưu trạng thái một phiên RDP"""
    def __init__(self, user_id):
        self.user_id = user_id
        self.run_id = None
        self.ip = None
        self.username = None
        self.password = None
        self.start_time = None
        self.end_time = None
        self.message = None  # Discord message để update


@bot.event
async def on_ready():
    print(f'✅ Bot đã đăng nhập: {bot.user}')
    print(f'📌 Servers: {len(bot.guilds)}')
    try:
        synced = await bot.tree.sync()
        print(f'🔄 Synced {len(synced)} slash commands')
    except Exception as e:
        print(f'❌ Lỗi sync: {e}')


class RDPLoginView(discord.ui.View):
    """View chứa nút Login Tailscale"""

    def __init__(self, author_id, duration):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.duration = duration
        self.triggered = False

    @discord.ui.button(
        label="🔐 Login Tailscale & Khởi động RDP",
        style=discord.ButtonStyle.success,
        emoji="🚀",
        custom_id="rdp_login_btn"
    )
    async def login_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Chỉ người gọi lệnh mới được click
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Bạn không phải người yêu cầu RDP!",
                ephemeral=True
            )
            return

        if self.triggered:
            await interaction.response.send_message(
                "⏳ Phiên RDP đang được khởi tạo, vui lòng đợi...",
                ephemeral=True
            )
            return

        self.triggered = True
        button.disabled = True
        button.label = "⏳ Đang khởi tạo..."
        await interaction.response.edit_message(view=self)

        # Bắt đầu tạo RDP
        await start_rdp_workflow(interaction, self.duration)


@bot.command(name='rdp')
async def rdp_command(ctx, duration: str = None):
    """Tạo RDP - !rdp [1h|3h|5h40m]"""
    # Kiểm tra channel
    if CONFIG.get('allowed_channel_ids') and ctx.channel.id not in CONFIG['allowed_channel_ids']:
        return

    # Kiểm tra user
    if CONFIG.get('allowed_user_ids') and ctx.user.id not in CONFIG['allowed_user_ids']:
        await ctx.send("❌ Bạn không có quyền sử dụng lệnh này!")
        return

    duration = duration or CONFIG.get('duration', '5h40m')
    valid_durations = ['1h', '3h', '5h40m']
    if duration not in valid_durations:
        await ctx.send(f"❌ Thời gian không hợp lệ! Chọn: {', '.join(valid_durations)}")
        return

    # Kiểm tra user đã có phiên chạy chưa
    if ctx.author.id in active_sessions:
        await ctx.send("⚠️ Bạn đã có phiên RDP đang chạy! Dùng `!stop` để dừng.")
        return

    # Tạo embed giới thiệu
    embed = discord.Embed(
        title="🚀 SEVER AI STV PREMIUM RDP",
        description=(
            "Hệ thống RDP Premium đã sẵn sàng!\n\n"
            f"⏱️ **Thời gian:** `{duration}`\n"
            f"👤 **Người dùng:** {ctx.author.mention}\n\n"
            "👇 Nhấn nút bên dưới để khởi động RDP:"
        ),
        color=discord.Color.blue(),
        timestamp=datetime.now(VN_TZ)
    )
    embed.set_footer(text="AI STV PREMIUM • Powered by Tailscale VPN")
    embed.set_thumbnail(url="https://i.imgur.com/8tBXd6Y.png")

    view = RDPLoginView(ctx.author.id, duration)
    await ctx.send(embed=embed, view=view)


@bot.tree.command(name="rdp", description="Khởi tạo RDP Premium")
@app_commands.choices(duration=[
    app_commands.Choice(name="1 giờ", value="1h"),
    app_commands.Choice(name="3 giờ", value="3h"),
    app_commands.Choice(name="5 giờ 40 phút", value="5h40m"),
])
async def rdp_slash(interaction: discord.Interaction, duration: app_commands.Choice[str] = None):
    """Slash command version"""
    dur = duration.value if duration else "5h40m"

    embed = discord.Embed(
        title="🚀 SEVER AI STV PREMIUM RDP",
        description=(
            "Hệ thống RDP Premium đã sẵn sàng!\n\n"
            f"⏱️ **Thời gian:** `{dur}`\n"
            f"👤 **Người dùng:** {interaction.user.mention}\n\n"
            "👇 Nhấn nút bên dưới để khởi động RDP:"
        ),
        color=discord.Color.blue(),
        timestamp=datetime.now(VN_TZ)
    )
    embed.set_footer(text="AI STV PREMIUM • Powered by Tailscale VPN")

    view = RDPLoginView(interaction.user.id, dur)
    await interaction.response.send_message(embed=embed, view=view)


@bot.command(name='stop')
async def stop_command(ctx):
    """Dừng phiên RDP - !stop"""
    if ctx.author.id not in active_sessions:
        await ctx.send("❌ Bạn không có phiên RDP nào đang chạy!")
        return

    session = active_sessions[ctx.author.id]
    await cancel_workflow(session)
    del active_sessions[ctx.author.id]

    embed = discord.Embed(
        title="🛑 ĐÃ DỪNG RDP",
        description=f"Phiên RDP của {ctx.author.mention} đã được dừng.",
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)


async def start_rdp_workflow(interaction: discord.Interaction, duration: str):
    """Trigger GitHub Actions workflow và theo dõi"""
    session = RDPSession(interaction.user.id)
    session.start_time = datetime.now(VN_TZ)
    active_sessions[interaction.user.id] = session

    # Embed loading
    embed = discord.Embed(
        title="⏳ ĐANG KHỞI TẠO RDP",
        description=(
            "🔄 Đang trigger GitHub Actions...\n"
            "⏱️ Vui lòng đợi 1-3 phút để hệ thống chuẩn bị.\n\n"
            "```\n[████░░░░░░░░░░░░░░░] 20%\n```"
        ),
        color=discord.Color.yellow()
    )
    embed.add_field(name="⏱️ Thời gian", value=duration, inline=True)
    embed.add_field(name="👤 User", value=interaction.user.mention, inline=True)
    embed.set_footer(text="Đang khởi tạo... Vui lòng đợi")

    await interaction.followup.send(embed=embed)
    session.message = await interaction.original_response()

    # Bước 1: Trigger workflow
    run_id = await trigger_github_workflow(duration)
    if not run_id:
        embed = discord.Embed(
            title="❌ LỖI KHỞI TẠO",
            description="Không thể trigger GitHub Actions. Kiểm tra token/repo!",
            color=discord.Color.red()
        )
        await session.message.edit(embed=embed, view=None)
        del active_sessions[interaction.user.id]
        return

    session.run_id = run_id

    # Bước 2: Poll workflow status
    await poll_workflow_status(session)


async def trigger_github_workflow(duration: str) -> str:
    """Trigger GitHub Actions workflow dispatch"""
    url = f"{GITHUB_API}/repos/{CONFIG['github_repo']}/actions/workflows/{CONFIG['workflow_id']}/dispatches"

    payload = {
        "ref": "main",  # hoặc "master"
        "inputs": {
            "duration": duration
        }
    }

    async with aiohttp.ClientSession() as http:
        async with http.post(url, json=payload, headers=HEADERS) as resp:
            if resp.status not in [200, 204]:
                print(f"❌ Trigger lỗi: {resp.status}")
                return None

    # Đợi 1 chút rồi lấy run_id mới nhất
    await asyncio.sleep(5)
    return await get_latest_workflow_run()


async def get_latest_workflow_run() -> str:
    """Lấy run_id của workflow vừa trigger"""
    url = f"{GITHUB_API}/repos/{CONFIG['github_repo']}/actions/runs?per_page=5"

    async with aiohttp.ClientSession() as http:
        async with http.get(url, headers=HEADERS) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

    for run in data.get('workflow_runs', []):
        if run.get('name') == '🚀 SEVER AI STV PREMIUM':
            return run.get('id')

    return None


async def poll_workflow_status(session: RDPSession):
    """Poll trạng thái workflow cho đến khi hoàn tất"""
    progress = 20
    stages = [
        (20, "🎯 Khởi động hệ thống..."),
        (35, "🔧 Cấu hình RDP..."),
        (50, "👤 Tạo tài khoản Premium..."),
        (65, "🔍 Kiểm tra quyền..."),
        (80, "🌐 Thiết lập Tailscale..."),
        (95, "🎉 Chuẩn bị thông tin kết nối..."),
    ]
    stage_idx = 0

    while True:
        # Update progress bar
        bar_filled = int(progress / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        stage_text = stages[stage_idx][1] if stage_idx < len(stages) else "Đang xử lý..."

        embed = discord.Embed(
            title="⏳ ĐANG KHỞI TẠO RDP",
            description=f"```\n[{bar}] {progress}%\n```\n🔄 {stage_text}",
            color=discord.Color.yellow()
        )
        embed.add_field(name="🆔 Run ID", value=f"`{session.run_id}`", inline=True)
        embed.set_footer(text="Đang khởi tạo... Vui lòng đợi")

        try:
            await session.message.edit(embed=embed)
        except:
            pass

        # Kiểm tra status
        status = await get_workflow_status(session.run_id)
        if status == "completed":
            # Lấy thông tin từ logs
            await extract_credentials_from_logs(session)
            await send_final_credentials(session)
            return
        elif status == "failed" or status == "cancelled":
            embed = discord.Embed(
                title="❌ RDP KHỞI TẠO THẤT BẠI",
                description="Workflow chạy thất bại. Vui lòng thử lại!",
                color=discord.Color.red()
            )
            await session.message.edit(embed=embed, view=None)
            del active_sessions[session.user_id]
            return

        # Tăng progress
        progress = min(95, progress + 5)
        if progress >= stages[stage_idx][0] + 15 and stage_idx < len(stages) - 1:
            stage_idx += 1

        await asyncio.sleep(10)


async def get_workflow_status(run_id: str) -> str:
    """Lấy status của workflow run"""
    url = f"{GITHUB_API}/repos/{CONFIG['github_repo']}/actions/runs/{run_id}"

    async with aiohttp.ClientSession() as http:
        async with http.get(url, headers=HEADERS) as resp:
            if resp.status != 200:
                return "unknown"
            data = await resp.json()
            return data.get('status', 'unknown') if data.get('status') == 'in_progress' else data.get('conclusion', 'in_progress')


async def extract_credentials_from_logs(session: RDPSession):
    """Trích xuất IP/Pass từ logs của workflow"""
    # Lấy logs
    url = f"{GITHUB_API}/repos/{CONFIG['github_repo']}/actions/runs/{session.run_id}/logs"

    async with aiohttp.ClientSession() as http:
        async with http.get(url, headers=HEADERS) as resp:
            if resp.status != 200:
                return
            # Logs là file zip - cần xử lý
            zip_data = await resp.read()

    # Lưu và giải nén logs
    import zipfile
    import io
    import re

    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            for filename in zf.namelist():
                if 'THÔNG TIN KẾT NỐI' in filename or 'Premium-RDP-Setup' in filename:
                    content = zf.read(filename).decode('utf-8', errors='ignore')

                    # Parse IP
                    ip_match = re.search(r'Địa chỉ:\s*(\d+\.\d+\.\d+\.\d+)', content)
                    if ip_match:
                        session.ip = ip_match.group(1)

                    # Parse password
                    pass_match = re.search(r'Mật khẩu:\s*(\S+)', content)
                    if pass_match:
                        session.password = pass_match.group(1)

                    # Parse username (mặc định)
                    session.username = "AISTV-PREMIUM"

                    # Parse end time
                    end_match = re.search(r'Kết thúc:\s*(\d{2}:\d{2}:\d{2})', content)
                    if end_match:
                        session.end_time = end_match.group(1)
    except Exception as e:
        print(f"Lỗi parse logs: {e}")

    # Fallback: nếu không parse được, thử dùng jobs API
    if not session.ip:
        await extract_from_jobs_api(session)


async def extract_from_jobs_api(session: RDPSession):
    """Fallback: parse từ jobs API"""
    url = f"{GITHUB_API}/repos/{CONFIG['github_repo']}/actions/runs/{session.run_id}/jobs"

    import re
    async with aiohttp.ClientSession() as http:
        async with http.get(url, headers=HEADERS) as resp:
            if resp.status != 200:
                return
            data = await resp.json()

    for job in data.get('jobs', []):
        for step in job.get('steps', []):
            if 'THÔNG TIN KẾT NỐI' in step.get('name', ''):
                # Lấy logs của step
                step_url = f"{GITHUB_API}/repos/{CONFIG['github_repo']}/actions/jobs/{job['id']}/logs"
                async with aiohttp.ClientSession() as http:
                    async with http.get(step_url, headers=HEADERS) as resp:
                        if resp.status == 200:
                            content = await resp.text()
                            ip_match = re.search(r'Địa chỉ:\s*(\d+\.\d+\.\d+\.\d+)', content)
                            pass_match = re.search(r'Mật khẩu:\s*(\S+)', content)
                            if ip_match:
                                session.ip = ip_match.group(1)
                            if pass_match:
                                session.password = pass_match.group(1)
                            session.username = "AISTV-PREMIUM"
                break


async def send_final_credentials(session: RDPSession):
    """Gửi thông tin đăng nhập RDP cho user"""
    if not session.ip:
        session.ip = "Không xác định"
    if not session.password:
        session.password = "Không xác định"

    end_time_display = session.end_time or "N/A"

    embed = discord.Embed(
        title="🎉 KẾT NỐI RDP THÀNH CÔNG!",
        description=(
            "✅ Hệ thống RDP Premium đã sẵn sàng!\n"
            "👇 Thông tin đăng nhập bên dưới 👇"
        ),
        color=discord.Color.green(),
        timestamp=datetime.now(VN_TZ)
    )

    embed.add_field(
        name="🌐 Địa chỉ IP",
        value=f"```\n{session.ip}\n```",
        inline=False
    )
    embed.add_field(
        name="👤 Tài khoản",
        value=f"```\n{session.username}\n```",
        inline=True
    )
    embed.add_field(
        name="🔐 Mật khẩu",
        value=f"```\n{session.password}\n```",
        inline=True
    )
    embed.add_field(
        name="📍 Port",
        value="```\n3389\n```",
        inline=True
    )
    embed.add_field(
        name="⏰ Kết thúc lúc",
        value=f"`{end_time_display}`",
        inline=False
    )

    embed.add_field(
        name="📖 Hướng dẫn kết nối",
        value=(
            "1️⃣ Mở **Remote Desktop Connection** (Windows + R → `mstsc`)\n"
            f"2️⃣ Nhập IP: `{session.ip}`\n"
            f"3️⃣ User: `{session.username}` | Pass: `{session.password}`\n"
            "4️⃣ Click **Connect** và enjoy! 🚀"
        ),
        inline=False
    )

    # View có nút copy và nút stop
    view = RDPControlView(session.user_id)
    embed.set_footer(text="AI STV PREMIUM • Lưu ý: không chia sẻ thông tin này!")
    embed.set_thumbnail(url="https://i.imgur.com/8tBXd6Y.png")

    await session.message.edit(embed=embed, view=view)


class RDPControlView(discord.ui.View):
    """View điều khiển sau khi RDP chạy"""

    def __init__(self, author_id):
        super().__init__(timeout=None)
        self.author_id = author_id

    @discord.ui.button(
        label="📋 Copy thông tin",
        style=discord.ButtonStyle.primary,
        emoji="📋",
        custom_id="rdp_copy_btn"
    )
    async def copy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = active_sessions.get(interaction.user.id)
        if not session:
            await interaction.response.send_message("❌ Phiên RDP không tồn tại!", ephemeral=True)
            return

        info = (
            f"🌐 IP: {session.ip}\n"
            f"👤 User: {session.username}\n"
            f"🔐 Pass: {session.password}\n"
            f"📍 Port: 3389"
        )
        await interaction.response.send_message(f"```\n{info}\n```", ephemeral=True)

    @discord.ui.button(
        label="🛑 Dừng RDP",
        style=discord.ButtonStyle.danger,
        emoji="🛑",
        custom_id="rdp_stop_btn"
    )
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Không có quyền!", ephemeral=True)
            return

        session = active_sessions.get(interaction.user.id)
        if not session:
            await interaction.response.send_message("❌ Không có phiên nào!", ephemeral=True)
            return

        await cancel_workflow(session)
        del active_sessions[interaction.user.id]

        embed = discord.Embed(
            title="🛑 ĐÃ DỪNG RDP",
            description="Phiên RDP đã được dừng thành công.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=None)


async def cancel_workflow(session: RDPSession):
    """Hủy workflow đang chạy"""
    if not session.run_id:
        return

    url = f"{GITHUB_API}/repos/{CONFIG['github_repo']}/actions/runs/{session.run_id}/cancel"
    async with aiohttp.ClientSession() as http:
        async with http.post(url, headers=HEADERS) as resp:
            pass


# Chạy bot
if __name__ == '__main__':
    bot.run(CONFIG['discord_token'])
