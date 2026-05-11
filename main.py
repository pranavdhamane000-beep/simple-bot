

import os
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# In-memory storage (clears when bot restarts)
VIDEOS = []

# REPLACE WITH YOUR TELEGRAM USER ID
ADMIN_ID = 6234222988  # Your ID from the error message


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *Video Library Bot*\n\n"
        "Send me any video and I'll store it!\n\n"
        "*Commands:*\n"
        "/send10 - First 10 videos\n"
        "/send50 - First 50 videos\n"
        "/send100 - First 100 videos\n"
        "/sendall - All videos\n"
        "/total - Total videos\n"
        "/recent - Last 5 videos\n"
        "/status - Bot status\n\n"
        "*Admin:* /clear - Delete all videos\n\n"
        "⚠️ Videos disappear when bot restarts!",
        parse_mode='Markdown'
    )


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global VIDEOS
    
    if not update.message.video:
        await update.message.reply_text("❌ Please send a video file.")
        return
    
    video = update.message.video
    VIDEOS.append({
        'file_id': video.file_id,
        'caption': update.message.caption or "No caption",
        'sender_name': update.effective_user.first_name,
        'sender_id': update.effective_user.id,
        'file_size': video.file_size,
    })
    
    await update.message.reply_text(f"✅ Video saved! Total: {len(VIDEOS)}")


async def send_videos(update: Update, context: ContextTypes.DEFAULT_TYPE, limit=None):
    global VIDEOS
    
    if not VIDEOS:
        await update.message.reply_text("📭 No videos yet!")
        return
    
    count = len(VIDEOS) if limit is None else min(limit, len(VIDEOS))
    
    msg = await update.message.reply_text(f"Sending {count} videos...")
    
    sent = 0
    for idx, video in enumerate(VIDEOS[:count], 1):
        try:
            await update.message.reply_video(
                video['file_id'],
                caption=f"Video #{idx}: {video['caption'][:100]}",
                timeout=30
            )
            sent += 1
            await asyncio.sleep(0.5)  # Small delay to avoid flooding
        except Exception as e:
            print(f"Failed: {e}")
    
    await msg.delete()
    await update.message.reply_text(f"✅ Sent {sent} videos!")


async def send10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=10)


async def send50(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=50)


async def send100(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=100)


async def sendall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_videos(update, context, limit=None)


async def total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_size = sum(v['file_size'] for v in VIDEOS) if VIDEOS else 0
    await update.message.reply_text(
        f"📊 *Statistics*\n\n"
        f"Videos: {len(VIDEOS)}\n"
        f"Size: {total_size // (1024*1024)} MB\n"
        f"Senders: {len(set(v['sender_id'] for v in VIDEOS))}",
        parse_mode='Markdown'
    )


async def recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not VIDEOS:
        await update.message.reply_text("No videos yet!")
        return
    
    recent_count = min(5, len(VIDEOS))
    recent_videos = VIDEOS[-recent_count:]
    
    msg = f"🆕 *Last {recent_count} videos:*\n\n"
    for idx, video in enumerate(recent_videos, 1):
        msg += f"{idx}. {video['caption'][:50]}\n   👤 {video['sender_name']}\n\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global VIDEOS
    
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    
    count = len(VIDEOS)
    VIDEOS = []
    await update.message.reply_text(f"🗑️ Cleared {count} videos!")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 *Bot Status*\n\n"
        f"✅ Running on Python 3.14.3\n"
        f"📹 Videos in memory: {len(VIDEOS)}\n"
        f"🔄 Data resets on restart\n"
        f"🌐 Host: Render.com",
        parse_mode='Markdown'
    )


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only: Export video list to file"""
    global VIDEOS
    
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Access Denied!")
        return
    
    if not VIDEOS:
        await update.message.reply_text("No videos to backup!")
        return
    
    backup_text = f"Video Library Backup\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nTotal Videos: {len(VIDEOS)}\n{'='*50}\n\n"
    
    for idx, video in enumerate(VIDEOS, start=1):
        backup_text += f"Video #{idx}\nFile ID: {video['file_id']}\nCaption: {video['caption']}\nSender: {video['sender_name']}\nSize: {video['file_size']} bytes\n{'-'*30}\n"
    
    filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(backup_text)
    
    with open(filename, "rb") as f:
        await update.message.reply_document(document=f, filename=filename)
    
    os.remove(filename)
    await update.message.reply_text("💾 Backup created!")


async def main_async():
    """Async main function for Python 3.14"""
    print("🤖 Starting Video Library Bot...")
    print(f"🐍 Python version: 3.14.3 compatible")
    print("=" * 50)
    
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    
    print(f"✅ Bot token found")
    print(f"👤 Admin ID set to: {ADMIN_ID}")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("send10", send10))
    app.add_handler(CommandHandler("send50", send50))
    app.add_handler(CommandHandler("send100", send100))
    app.add_handler(CommandHandler("sendall", sendall))
    app.add_handler(CommandHandler("total", total))
    app.add_handler(CommandHandler("recent", recent))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("backup", backup))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    
    print(f"✅ Commands registered")
    print("🤖 Bot is polling for updates...")
    print("=" * 50)
    
    # For Python 3.14, we need to initialize and start properly
    await app.initialize()
    await app.start()
    
    # Start polling
    await app.updater.start_polling()
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main():
    """Entry point for Python 3.14"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped manually")


if __name__ == "__main__":
    main()


