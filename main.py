import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import shutil
import random
import json
import itertools
import aiohttp
import zipfile
import io
import sys

COMMANDS_FILE = 'commands.json'
BASE_DIR = 'codes'
status_cycle = itertools.cycle(["Join OTC Group", "Making 1000s with OTC", "Cooking OTC"])

TEST_GUILD = discord.Object(id=1353283544926916659)

# Load existing commands
if not os.path.exists(COMMANDS_FILE):
    with open(COMMANDS_FILE, 'w') as f:
        json.dump([], f)

def load_commands():
    with open(COMMANDS_FILE, 'r') as f:
        return json.load(f)

def save_commands(commands_list):
    with open(COMMANDS_FILE, 'w') as f:
        json.dump(commands_list, f)

def create_folder(name):
    path = os.path.join(BASE_DIR, name)
    used_path = os.path.join(path, 'used')
    os.makedirs(used_path, exist_ok=True)
    return path

def get_available_images(folder):
    folder_path = os.path.join(BASE_DIR, folder)
    return [f for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')) and os.path.isfile(os.path.join(folder_path, f))]

class MyBot(commands.Bot):
    async def setup_hook(self):
        for cmd in load_commands():
            self.tree.add_command(generate_dynamic_slash_command(cmd), guild=TEST_GUILD)
        await self.tree.sync(guild=TEST_GUILD)

bot = MyBot(command_prefix='!', intents=discord.Intents.all(), help_command=None)

@bot.event
async def on_ready():
    print(f"Bot ready as {bot.user}")
    rotate_status.start()

@tasks.loop(seconds=20)
async def rotate_status():
    await bot.change_presence(activity=discord.Game(next(status_cycle)), status=discord.Status.dnd)

def generate_dynamic_slash_command(name):
    @app_commands.command(name=name, description=f"Send codes from {name}")
    @app_commands.describe(amount="Number of codes to send")
    async def _slash_command(interaction: discord.Interaction, amount: int = 5):
        folder_path = os.path.join(BASE_DIR, name)
        used_path = os.path.join(folder_path, 'used')
        available = get_available_images(name)

        if not available:
            await interaction.response.send_message(f"No more codes left in `{name}`.", ephemeral=True)
            return

        selected = random.sample(available, min(amount, len(available)))

        files = []
        for img in selected:
            img_path = os.path.join(folder_path, img)
            if not img.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                continue
            files.append(discord.File(fp=img_path, filename=os.path.basename(img)))
            shutil.move(img_path, os.path.join(used_path, img))

        if not files:
            await interaction.response.send_message("⚠️ No valid image files found to send.", ephemeral=True)
        else:
            await interaction.response.send_message(content=f"📦 `{interaction.user}` used `{name}` for {len(files)} code(s):", files=files)

    return _slash_command
@bot.tree.command(name="add", description="Add a new code set")
@app_commands.describe(name="Name of the new folder")
async def add(interaction: discord.Interaction, name: str):
    commands_list = load_commands()
    if name in commands_list:
        await interaction.response.send_message(f"`{name}` already exists.")
        return
    create_folder(name)
    commands_list.append(name)
    save_commands(commands_list)
    new_cmd = generate_dynamic_slash_command(name)
    bot.tree.add_command(new_cmd, guild=TEST_GUILD)
    await bot.tree.sync(guild=TEST_GUILD)
    await interaction.response.send_message(f"Added new code set `{name}` with slash command `/{name}`. Restarting bot to apply...")

    # Restart the bot process
    os.execv(sys.executable, ['python'] + sys.argv)
@bot.tree.command(name="upload", description="Upload a zip file of codes")
@app_commands.describe(name="Name of the folder to upload into")
async def upload(interaction: discord.Interaction, name: str):
    if not interaction.attachments:
        await interaction.response.send_message("Please attach a zip file.")
        return

    folder_path = os.path.join(BASE_DIR, name)
    if not os.path.exists(folder_path):
        await interaction.response.send_message(f"The folder `{name}` does not exist. Use `/add {name}` first.")
        return

    attachment = interaction.attachments[0]
    if not attachment.filename.lower().endswith(".zip"):
        await interaction.response.send_message("Only zip files are supported.")
        return

    async with aiohttp.ClientSession() as session:
        async with session.get(attachment.url) as resp:
            if resp.status != 200:
                await interaction.response.send_message("Failed to download the zip file.")
                return
            zip_data = await resp.read()

    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zip_ref:
            image_count = 0
            for file_info in zip_ref.infolist():
                filename = file_info.filename
                if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    with zip_ref.open(file_info) as source_file:
                        safe_name = os.path.basename(filename)
                        target_path = os.path.join(folder_path, safe_name)
                        with open(target_path, "wb") as f:
                            f.write(source_file.read())
                        image_count += 1
            await interaction.response.send_message(f"✅ Uploaded `{image_count}` code(s) to `{name}` folder.")
    except zipfile.BadZipFile:
        await interaction.response.send_message("❌ That file is not a valid ZIP.")

@bot.tree.command(name="purge_used", description="Purge all used codes")
async def purge_used(interaction: discord.Interaction):
    commands_list = load_commands()
    deleted_total = 0
    for cmd in commands_list:
        used_folder = os.path.join(BASE_DIR, cmd, "used")
        if os.path.exists(used_folder):
            for f in os.listdir(used_folder):
                file_path = os.path.join(used_folder, f)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted_total += 1
    await interaction.response.send_message(f"Purged `{deleted_total}` used code(s) from all folders.")

@bot.tree.command(name="delete", description="Delete a code set")
@app_commands.describe(name="Name of the code set to delete")
async def delete(interaction: discord.Interaction, name: str):
    commands_list = load_commands()
    if name not in commands_list:
        await interaction.response.send_message(f"`{name}` doesn't exist.")
        return
    shutil.rmtree(os.path.join(BASE_DIR, name), ignore_errors=True)
    bot.tree.remove_command(name)
    commands_list.remove(name)
    save_commands(commands_list)
    await bot.tree.sync(guild=TEST_GUILD)
    await interaction.response.send_message(f"Deleted `{name}` and its files.")

@bot.tree.command(name="purge", description="Purge unsent codes from a set")
@app_commands.describe(name="Name of the folder")
async def purge(interaction: discord.Interaction, name: str):
    folder = os.path.join(BASE_DIR, name)
    if not os.path.exists(folder):
        await interaction.response.send_message(f"`{name}` doesn't exist.")
        return
    for f in get_available_images(name):
        os.remove(os.path.join(folder, f))
    await interaction.response.send_message(f"Purged all unsent codes in `{name}`.")

@bot.tree.command(name="stats", description="Show available codes in each folder")
async def stats(interaction: discord.Interaction):
    commands_list = load_commands()
    msg = "**Active Code Sets:**\n"
    for cmd in commands_list:
        count = len(get_available_images(cmd))
        msg += f"`{cmd}`: {count} code(s) remaining\n"
    await interaction.response.send_message(msg or "No active folders found.")

with open("settings.json", "r") as f:
    settings = json.load(f)

bot.run(settings["bot_token"])
