import os
import asyncio
import discord
from discord.ext import commands, tasks
from web3 import Web3
# NEW IMPORTS FOR FIXES
from web3.middleware import ExtraDataToPOAMiddleware

# NEW IMPORTS FOR RENDER DEPLOYMENT FIX
import threading
from flask import Flask 

# ------------------------------
# ⚙️ CONFIGURATION
# ------------------------------

CHANNEL_ID = 1435788887170486272
WATCH_ADDRESS = "0x11c5fE402fd39698d1144AD027A2fF2471d723af".lower()

# Channel for Periodic Messages AND Presence Alerts
TARGET_CHANNEL_ID = 1435365215284760680 

# Role ID for tagging alerts
ALERT_ROLE_ID = 1435365297501765642
role_mention = f"<@&{ALERT_ROLE_ID}>" 

# 📌 OPTIONAL: List of specific Discord User IDs to track for presence monitoring.
# If this list is empty, the bot will track ALL users in the server.
WATCHED_USER_IDS = 858951236014964747, 940767065776734258 # e.g., [123456789012345678, 987654321098765432]

# ✅ Neo X RPC endpoint
RPC_URL = "https://mainnet-2.rpc.banelabs.org" 

# Connect to Neo X node
web3 = Web3(Web3.HTTPProvider(RPC_URL))

if not web3.is_connected():
    print("❌ Could not connect to Neo X RPC")
else:
    print("✅ Connected to Neo X RPC")
    
# FIX: Inject the PoA middleware to fix the "extraData" block error
web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0) 


# Discord client setup
intents = discord.Intents.default()
# START REQUIRED INTENTS FOR COMMANDS AND PRESENCE MONITORING
intents.message_content = True 
intents.presences = True # 🚨 REQUIRED for on_presence_update
intents.members = True   # 🚨 REQUIRED for accurate member status tracking
# END REQUIRED INTENTS

bot = commands.Bot(command_prefix="!", intents=intents) 

# ------------------------------
# 🔍 Monitor wallet for txs
# ------------------------------
try:
    last_block = web3.eth.block_number
except Exception as e:
    print(f"Error fetching initial block number: {e}")
    last_block = 0 
    
print(f"📦 Starting from block: {last_block}")

async def check_wallet():
    global last_block
    if not web3.is_connected():
        print("⚠️ RPC disconnected. Skipping check.")
        return

    try:
        new_block = web3.eth.block_number
        
        if new_block <= last_block:
             return
             
        for block_num in range(last_block + 1, new_block + 1):
            block = web3.eth.get_block(block_num, full_transactions=True)
            for tx in block.transactions:
                
                frm = tx.get("from", "").lower() 
                to = tx.get("to")
                to = to.lower() if to else None

                if WATCH_ADDRESS in [frm, to]:
                    value = web3.from_wei(tx.get("value", 0), "ether")
                    direction = "SENT" if frm == WATCH_ADDRESS else "RECEIVED"

                    tx_hash_hex = tx['hash'].hex()
                    explorer_link = f"https://neoxscan.ngd.network/txs/{tx_hash_hex}"
                    role_mention_in_func = f"<@&{ALERT_ROLE_ID}>" 

                    message = (
                        f"{role_mention_in_func} 💸 **Transaction Alert on Neo X!**\n"
                        f"📦 **Block:** `{block_num}`\n"
                        f"🧾 **Hash:** [`{tx_hash_hex}`]({explorer_link})\n"
                        f"➡️ **From:** `{frm}`\n"
                        f"⬅️ **To:** `{to}`\n"
                        f"💰 **Value:** `{value} GAS`\n" 
                        f"📊 **Type:** **{direction}**\n"
                    )

                    channel = bot.get_channel(CHANNEL_ID)
                    if channel:
                        await channel.send(message)
                    else:
                        print(f"⚠️ Could not find Discord channel with ID: {CHANNEL_ID}.")
        
        last_block = new_block 
        
    except Exception as e:
        new_block = web3.eth.block_number # Define new_block again for error reporting if it failed earlier
        print(f"Error checking wallet in block range {last_block+1} to {new_block}: {e}")

@tasks.loop(seconds=15)
async def wallet_watcher():
    await check_wallet()

# ------------------------------
# 📢 8-SECOND MESSAGE LOOP
# ------------------------------
@tasks.loop(seconds=8.0) 
async def send_periodic_message():
    await bot.wait_until_ready() 
    
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    
    if channel:
        await channel.send("🤖 **Status Update:** I am currently running and monitoring transactions!")
    else:
        print(f"⚠️ Could not find channel with ID: {TARGET_CHANNEL_ID} for periodic message.")

# ------------------------------
# 👤 PRESENCE MONITORING (ADDED CODE)
# ------------------------------
@bot.event
async def on_presence_update(before, after):
    # Check if the user's status has actually changed
    if before.status != after.status:
        
        # Ignore Bots
        if after.bot:
            return

        # Check if we are only tracking specific users (if WATCHED_USER_IDS is not empty)
        if WATCHED_USER_IDS and after.id not in WATCHED_USER_IDS:
             return

        channel = bot.get_channel(TARGET_CHANNEL_ID)
        if not channel:
            return

        member_name = after.display_name
        message = None

        if after.status == discord.Status.online:
            message = f'🟢 **{member_name}** is now **online**.'
        elif after.status == discord.Status.offline:
            # Check if they were previously online or idle before going offline
            if before.status == discord.Status.online or before.status == discord.Status.idle:
                 message = f'⚫ **{member_name}** has gone **offline**.'
        elif after.status == discord.Status.idle:
            message = f'🌙 **{member_name}** is now **away (idle)**.'
            
        if message:
            await channel.send(message)
            
# ------------------------------
# 🚀 BOT EVENTS & COMMANDS
# ------------------------------
@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.wait_until_ready() 
    
    # Start all background tasks when the bot connects
    wallet_watcher.start()
    send_periodic_message.start()

@bot.command(name='hello')
async def hello_check(ctx):
    """Responds to !hello with a status message."""
    global last_block
    
    rpc_status = "✅ Connected to Neo X RPC."
    if not web3.is_connected():
        rpc_status = "❌ WARNING: Cannot connect to Neo X RPC. Transaction monitoring may be offline."

    current_block_message = f"Last block checked: `{last_block}`"

    response = (
        f"👋 **Hello! I'm NeoxBot.** I'm currently running and ready to monitor transactions.\n\n"
        f"📡 **RPC Status:** {rpc_status}\n"
        f"📦 **Monitoring Status:** I haven't detected any relevant transactions for address "
        f"`{WATCH_ADDRESS}` yet, but I am actively watching from block {current_block_message}.\n\n"
        f"I will notify you in this channel if one occurs!"
    )
    
    await ctx.send(response)

# ------------------------------
# 🌐 FLASK SERVER INTEGRATION
# ------------------------------

app = Flask(__name__)

@app.route('/')
def home():
    return "Discord Bot is Running!"

def run_flask_app():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
    
# ------------------------------
# 🚀 MAIN EXECUTION BLOCK 
# ------------------------------
if __name__ == '__main__':
    try:
        # 1. Start Flask in a separate thread
        server_thread = threading.Thread(target=run_flask_app)
        server_thread.start()
        print("🌐 Flask server started in background thread.")
        
        # 2. Start the Discord Bot in the main thread
        bot.run(os.environ['DISCORD_TOKEN']) 
        
    except discord.errors.LoginFailure:
        print("\n\n❌ ERROR: Improper token has been passed. Ensure DISCORD_TOKEN is set correctly in environment variables.\n")
    except Exception as e:
        print(f"\n\n❌ An unhandled error occurred during bot run: {e}\n")