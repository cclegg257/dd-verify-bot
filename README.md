# DD Verify Bot

`/verify <email>` gives the **DD Verified** role to paid Dynasty Dugout members.
A daily check takes the role back from members who have cancelled.

The bot no longer uses a list of emails. It asks the Dynasty Dugout site, which
checks billing directly (beehiiv today, Stripe after the move), so nothing needs
importing.

## Environment variables

| Variable | What it is |
| --- | --- |
| `DISCORD_TOKEN` | The bot's token (unchanged) |
| `GUILD_ID` | The server id (unchanged) |
| `DD_ENTITLEMENTS_URL` | `https://<site>/api/discord/entitlements` |
| `DD_SITE_SECRET` | Must equal `DISCORD_BOT_SECRET` on the site's Vercel project |
| `VERIFIED_FILE` | Optional. Where verified members are recorded. Point it at a persistent disk if the host has one |
| `REMOVALS_ENABLED` | Optional. Leave unset at first, so the daily check only logs who it *would* remove. Set to `true` once those logs look right |
| `MIN_PAID` | Optional, default `500`. If the site reports fewer paid members than this, nobody is removed |
| `MAX_REMOVE_FRACTION` | Optional, default `0.10`. If a run would remove more than this share of verified members, nobody is removed |

## Safety

The bot never removes anyone when the site can't answer or the answer looks wrong.
Members who verified with more than one email keep the role if any of those emails
is still paid. If the site is unreachable, `/verify` asks the member to try again
rather than turning them away.
