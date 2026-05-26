import discord
from discord import app_commands
import os
import asyncio
 
# ---- CONFIG ----
ROLE_NAME = "DD Verified"
ALLOWED_EMAILS_FILE = "emails.txt"
GUILD_ID = int(os.environ["GUILD_ID"])
# ----------------
 
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
 
class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
 
    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print(f"Commands synced to guild {GUILD_ID}")
 
bot = MyBot()
 
def load_emails():
    with open(ALLOWED_EMAILS_FILE, "r") as f:
        return set(line.strip().lower() for line in f if line.strip())
 
async def daily_role_check():
    await bot.wait_until_ready()
    while not bot.is_closed():
        print("Running daily unsubscribe check...")
        await remove_unsubscribed_members()
        await asyncio.sleep(86400)
 
async def remove_unsubscribed_members():
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        print("Could not find guild for role check.")
        return
 
    role = discord.utils.get(guild.roles, name=ROLE_NAME)
    if role is None:
        print(f"Could not find role '{ROLE_NAME}' for check.")
        return
 
    allowed_emails = load_emails()
    removed_count = 0
    verified_file = "verified_members.txt"
 
    if not os.path.exists(verified_file):
        print("No verified_members.txt found, skipping check.")
        return
 
    with open(verified_file, "r") as f:
        records = [line.strip().split(",") for line in f if "," in line.strip()]
 
    for parts in records:
        member_id, member_email = int(parts[0]), parts[1].lower()
        if member_email not in allowed_emails:
            member = guild.get_member(member_id)
            if member and role in member.roles:
                try:
                    await member.remove_roles(role)
                    removed_count += 1
                    print(f"Removed role from {member.name} ({member_email})")
                except discord.Forbidden:
                    print(f"Could not remove role from {member_id} - permission error")
 
    print(f"Daily check complete. Removed role from {removed_count} member(s).")
 
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print(f"Commands registered: {[cmd.name for cmd in bot.tree.get_commands()]}")
    asyncio.ensure_future(daily_role_check())
 
@bot.tree.command(name="verify", description="Verify your Dynasty Dugout membership", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(email="The email address you used to subscribe to Dynasty Dugout")
async def verify(interaction: discord.Interaction, email: str):
    await interaction.response.defer(ephemeral=True)
 
    allowed_emails = load_emails()
    guild = interaction.guild
    member = interaction.user
    clean_email = email.strip().lower()
 
    if clean_email in allowed_emails:
        role = discord.utils.get(guild.roles, name=ROLE_NAME)
        if role is None:
            await interaction.followup.send(
                f"❌ Could not find the '{ROLE_NAME}' role. Please contact an admin.",
                ephemeral=True
            )
            return
        if role in member.roles:
            await interaction.followup.send(
                "✅ You're already verified! You should have full access.",
                ephemeral=True
            )
            return
        try:
            await member.add_roles(role)
            with open("verified_members.txt", "a") as f:
                f.write(f"{member.id},{clean_email}\n")
            await interaction.followup.send(
                "✅ You've been verified as a paid Dynasty Dugout member! Welcome to the GM War Room. 🎉",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to assign roles. Please contact an admin.",
                ephemeral=True
            )
    else:
        await interaction.followup.send(
            "❌ That email wasn't found on our subscriber list. Make sure you're using the email you signed up with at The Dynasty Dugout. If you think this is an error, DM an admin.",
            ephemeral=True
        )
 
bot.run(os.environ["DISCORD_TOKEN"])
