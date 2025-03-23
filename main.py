import discord
from discord.ext import commands, tasks
import os
import shutil
import random
import json
import itertools
import aiohttp
import zipfile
import io

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all(), help_command=None)

COMMANDS_FILE = 'commands.json'
BASE_DIR = 'codes'
status_cycle = itertools.cycle(["Join OTC Group", "Making 1000s with OTC", "Cooking OTC"])

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

@bot.event
async def on_ready():
    print(f"Bot ready as {bot.user}")
    for cmd in load_commands():
        bot.add_command(generate_dynamic_command(cmd))
    rotate_status.start()
@bot.event
async def on_command_error(ctx, error):
    # Ignore unknown command errors (let other bots handle them)
    if isinstance(error, commands.CommandNotFound):
        return
    else:
        raise error  # You can also log this if you want

@tasks.loop(seconds=20)
async def rotate_status():
    await bot.change_presence(activity=discord.Game(next(status_cycle)), status=discord.Status.dnd)

def generate_dynamic_command(name):
    @commands.command(name=name)
    async def _dynamic(ctx, amount: int = 5):  # default = 5
        folder_path = os.path.join(BASE_DIR, name)
        used_path = os.path.join(folder_path, 'used')
        available = get_available_images(name)

        if not available:
            await ctx.send(f"No more codes left in `{name}`.")
            return

        selected = random.sample(available, min(amount, len(available)))
        files = []

        for img in selected:
            img_path = os.path.join(folder_path, img)
            # Force Discord to treat it as a previewable image by specifying filename
            files.append(discord.File(img_path, filename=img))

            # Move to used folder
            shutil.move(img_path, os.path.join(used_path, img))

        await ctx.send(content=f"📦 `{ctx.author}` used `{name}` for {len(files)} code(s):", files=files)
    return _dynamic

@bot.command()
async def add(ctx, name: str):
    commands_list = load_commands()
    if name in commands_list:
        await ctx.send(f"`{name}` already exists.")
        return
    create_folder(name)
    commands_list.append(name)
    save_commands(commands_list)
    new_cmd = generate_dynamic_command(name)
    bot.add_command(new_cmd)
    await ctx.send(f"Added new code set `{name}` with command `!{name}`.")
    
@bot.command()
async def upload(ctx, name: str):
    if not ctx.message.attachments:
        await ctx.send("Please attach a zip file.")
        return

    folder_path = os.path.join(BASE_DIR, name)
    if not os.path.exists(folder_path):
        await ctx.send(f"The folder `{name}` does not exist. Use `!add {name}` first.")
        return

    attachment = ctx.message.attachments[0]
    if not attachment.filename.endswith(".zip"):
        await ctx.send("Only zip files are supported.")
        return

    # Download the zip file
    async with aiohttp.ClientSession() as session:
        async with session.get(attachment.url) as resp:
            if resp.status != 200:
                await ctx.send("Failed to download the zip file.")
                return
            data = await resp.read()

    # Extract the zip file in-memory
    with zipfile.ZipFile(io.BytesIO(data)) as zip_ref:
        image_count = 0
        for file in zip_ref.namelist():
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                source = zip_ref.open(file)
                target_path = os.path.join(folder_path, os.path.basename(file))
                with open(target_path, 'wb') as out_file:
                    out_file.write(source.read())
                image_count += 1

    await ctx.send(f"Uploaded `{image_count}` code(s) to `{name}` folder.")
    
@bot.command()
async def purge_used(ctx):
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
    await ctx.send(f"Purged `{deleted_total}` used code(s) from all folders.")
@bot.command()
async def delete(ctx, name: str):
    commands_list = load_commands()
    if name not in commands_list:
        await ctx.send(f"`{name}` doesn't exist.")
        return
    shutil.rmtree(os.path.join(BASE_DIR, name), ignore_errors=True)
    bot.remove_command(name)
    commands_list.remove(name)
    save_commands(commands_list)
    await ctx.send(f"Deleted `{name}` and its files.")

@bot.command()
async def purge(ctx, name: str):
    folder = os.path.join(BASE_DIR, name)
    if not os.path.exists(folder):
        await ctx.send(f"`{name}` doesn't exist.")
        return
    for f in get_available_images(name):
        os.remove(os.path.join(folder, f))
    await ctx.send(f"Purged all unsent codes in `{name}`.")

@bot.command()
async def stats(ctx):
    commands_list = load_commands()
    msg = "**Active Code Sets:**\n"
    for cmd in commands_list:
        count = len(get_available_images(cmd))
        msg += f"`{cmd}`: {count} code(s) remaining\n"
    await ctx.send(msg or "No active folders found.")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="📘 OTC Bot Help", description="Here's how to use the bot!", color=discord.Color.blue())
    embed.add_field(name="!add <name>", value="Create a new folder and command. Example: `!add nike`", inline=False)
    embed.add_field(name="!<name> <amount>", value="Send a specific number of codes from that folder. Example: `!nike 3`", inline=False)
    embed.add_field(name="!delete <name>", value="Delete a folder and remove the command. Example: `!delete nike`", inline=False)
    embed.add_field(name="!purge <name>", value="Delete all unsent codes from a folder. Example: `!purge nike`", inline=False)
    embed.add_field(name="!purge_used", value="Deletes all codes that were already sent (in `used` folders).", inline=False)
    embed.add_field(name="!upload <name>", value="Upload a zip file of codes into the specified folder. Attach the .zip when using this command.", inline=False)
    embed.add_field(name="!stats", value="See all active code folders and how many codes are left in each.", inline=False)
    embed.set_footer(text="All images are referred to as codes. Make sure to upload images to the correct folder!")
    await ctx.send(embed=embed)

with open("settings.json", "r") as f:
    settings = json.load(f)

bot.run(settings["bot_token"])