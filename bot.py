import discord
from discord.ext import commands
from discord import app_commands
import os

# ---- CONFIG ----
ROLE_NAME = "DD Verified"
ALLOWED_EMAILS_FILE = "emails.txt"
# ----------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

def load_emails():
    with open(ALLOWED_EMAILS_FILE, "r") as f:
        return set(line.strip().lower() for line in f if line.strip())

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

@bot.tree.command(name="verify", description="Verify your Dynasty Dugout membership")
@app_commands.describe(email="The email address you used to subscribe")
async def verify(interaction: discord.Interaction, email: str):
    await interaction.response.defer(ephemeral=True)

    allowed_emails = load_emails()
    guild = interaction.guild
    member = interaction.user

    if email.strip().lower() in allowed_emails:
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
