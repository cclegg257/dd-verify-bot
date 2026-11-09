import discord
from discord import app_commands
import aiohttp
import os
import asyncio

# ---- CONFIG ----
ROLE_NAME = "DD Verified"
GUILD_ID = int(os.environ["GUILD_ID"])

# The site answers "is this email a paid member?" so there is no list to
# keep up to date by hand. Both are set in the bot host's environment.
#   DD_ENTITLEMENTS_URL  e.g. https://<site>/api/discord/entitlements
#   DD_SITE_SECRET       the same value as DISCORD_BOT_SECRET on Vercel
ENTITLEMENTS_URL = os.environ.get("DD_ENTITLEMENTS_URL", "").strip()
SITE_SECRET = os.environ.get("DD_SITE_SECRET", "").strip()

# Who has verified with which email. Point this at a persistent disk if the
# host has one: if a redeploy wipes it, nobody is ever removed again.
VERIFIED_FILE = os.environ.get("VERIFIED_FILE", "verified_members.txt")

# Safety rails for the daily check. If anything looks off, remove nobody.
MIN_PAID = int(os.environ.get("MIN_PAID", "500"))
MAX_REMOVE_FRACTION = float(os.environ.get("MAX_REMOVE_FRACTION", "0.10"))
# Off by default: the daily check only logs who it WOULD remove. Read a few
# days of those logs, then set REMOVALS_ENABLED=true.
REMOVALS_ENABLED = os.environ.get("REMOVALS_ENABLED", "").strip().lower() == "true"
# ----------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.daily_started = False

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print(f"Commands synced to guild {GUILD_ID}")


bot = MyBot()


async def check_emails(emails):
    """
    Ask the site which of these emails belong to paid members.

    Returns (set of entitled emails, paid_count), or None if the site could not
    answer. None always means "change nothing".
    """
    if not ENTITLEMENTS_URL or not SITE_SECRET:
        print("DD_ENTITLEMENTS_URL or DD_SITE_SECRET is not set.")
        return None

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300)
        ) as session:
            async with session.post(
                ENTITLEMENTS_URL,
                json={"emails": sorted(emails)},
                headers={"Authorization": f"Bearer {SITE_SECRET}"},
            ) as response:
                if response.status != 200:
                    print(f"Entitlement check failed: HTTP {response.status}")
                    return None
                data = await response.json()
    except Exception as error:
        print(f"Entitlement check failed: {error}")
        return None

    entitled = set(e.lower() for e in data.get("entitled", []))
    return entitled, data.get("paidCount")


def load_verified():
    """{discord member id: set of emails they verified with}"""
    verified = {}
    if not os.path.exists(VERIFIED_FILE):
        return verified
    with open(VERIFIED_FILE, "r") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 2:
                continue
            try:
                member_id = int(parts[0])
            except ValueError:
                continue
            verified.setdefault(member_id, set()).add(parts[1].strip().lower())
    return verified


async def daily_role_check():
    await bot.wait_until_ready()
    while not bot.is_closed():
        print("Running daily unsubscribe check...")
        try:
            await remove_unsubscribed_members()
        except Exception as error:
            print(f"Daily check failed, nobody removed: {error}")
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

    verified = load_verified()
    if not verified:
        print(f"No records in {VERIFIED_FILE}, skipping check.")
        return

    all_emails = set().union(*verified.values())
    result = await check_emails(all_emails)
    if result is None:
        print("Site could not answer; nobody removed today.")
        return
    entitled, paid_count = result

    if paid_count is not None and paid_count < MIN_PAID:
        print(f"Site reported only {paid_count} paid members (< {MIN_PAID}); "
              "that looks wrong, so nobody removed today.")
        return

    # Keep the role if ANY email a member verified with is still paid.
    to_remove = [
        member_id for member_id, emails in verified.items()
        if not (emails & entitled)
    ]

    if len(to_remove) > len(verified) * MAX_REMOVE_FRACTION:
        print(f"Would remove {len(to_remove)} of {len(verified)} members, more "
              f"than {MAX_REMOVE_FRACTION:.0%}; that looks wrong, so nobody "
              "removed today. Check the site before raising MAX_REMOVE_FRACTION.")
        return

    removed_count = 0
    for member_id in to_remove:
        member = guild.get_member(member_id)
        if member and role in member.roles:
            if not REMOVALS_ENABLED:
                print(f"[report only] Would remove role from {member.name} "
                      f"({member_id}, {', '.join(sorted(verified[member_id]))})")
                continue
            try:
                await member.remove_roles(role)
                removed_count += 1
                print(f"Removed role from {member.name} ({member_id})")
            except discord.Forbidden:
                print(f"Could not remove role from {member_id} - permission error")

    print(f"Daily check complete. {len(entitled)} of {len(all_emails)} emails "
          f"paid (site paidCount={paid_count}). Removed role from "
          f"{removed_count} member(s)."
          + ("" if REMOVALS_ENABLED else
             f" Report only: {len(to_remove)} would be removed."))


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print(f"Commands registered: {[cmd.name for cmd in bot.tree.get_commands()]}")
    # on_ready fires again on every reconnect; only start one daily loop.
    if not bot.daily_started:
        bot.daily_started = True
        asyncio.ensure_future(daily_role_check())


@bot.tree.command(name="verify", description="Verify your Dynasty Dugout membership", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(email="The email address you used to subscribe to Dynasty Dugout")
async def verify(interaction: discord.Interaction, email: str):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    member = interaction.user
    clean_email = email.strip().lower()

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

    result = await check_emails({clean_email})
    if result is None:
        await interaction.followup.send(
            "⚠️ We couldn't check your membership right now. Please try again in a few minutes, or DM an admin.",
            ephemeral=True
        )
        return
    entitled, _ = result

    if clean_email in entitled:
        try:
            await member.add_roles(role)
            with open(VERIFIED_FILE, "a") as f:
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
