import os
import time
import discord
from discord.ext import tasks, commands
import cloudscraper  # Replaces requests
from bs4 import BeautifulSoup
from deepdiff import DeepDiff
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
YOUR_DISCORD_USER_ID = int(os.getenv("DISCORD_USER_ID"))

ARTICLE_URL = "https://support.discord.com/hc/en-us/articles/360046057772-Discord-Bugs"
STATE_FILE = "last_content.txt"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def fetch_article_text():
    """Fetches the article page using cloudscraper to bypass Cloudflare/bot blocks."""
    # Create a cloudscraper instance
    scraper = cloudscraper.create_scraper()
    
    try:
        response = scraper.get(ARTICLE_URL)
        if response.status_code != 200:
            print(f"Cloudflare/HTTP Error status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"Request exception: {e}")
        return None
    
    soup = BeautifulSoup(response.text, "html.parser")
    article_body = soup.find("div", class_="article-body")
    
    if not article_body:
        return None
    
    for unwanted in article_body.select(".article-votes, .social-share, script, style"):
        unwanted.decompose()

    tags_to_find = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "blockquote", "div"]
    
    content_lines = []
    for el in article_body.find_all(tags_to_find):
        if el.name == "div":
            if not any(cls in el.get("class", []) for cls in ["mega-box", "toc-box"]):
                continue
                
        text = el.get_text(strip=True)
        if text and text not in content_lines:
            content_lines.append(text)
            
    return content_lines

# (Keep the rest of your process_and_notify_changes, check_article loop, and manual_fetch command exactly the same)

async def process_and_notify_changes(user):
    """Core checking and diff logic shared by the loop and the manual command."""
    current_paragraphs = fetch_article_text()
    if not current_paragraphs:
        return "Failed to fetch article content."

    old_paragraphs = []
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            old_paragraphs = [line.strip() for line in f.readlines()]

    if not old_paragraphs:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(current_paragraphs))
        return "Baseline article content saved."

    if current_paragraphs != old_paragraphs:
        diff = DeepDiff(old_paragraphs, current_paragraphs)
        
        change_summary = "**Discord Bug Article Update Detected!**\n"
        change_summary += f"<{ARTICLE_URL}>\n\n"
        
        if "iterable_item_added" in diff:
            change_summary += "**Added/Changed Content:**\n"
            for key, value in diff["iterable_item_added"].items():
                change_summary += f"+ {value}\n"
        
        if "iterable_item_removed" in diff:
            change_summary += "\n**Removed Content:**\n"
            for key, value in diff["iterable_item_removed"].items():
                change_summary += f"- {value}\n"

        if len(change_summary) > 1900:
            chunks = [change_summary[i:i+1900] for i in range(0, len(change_summary), 1900)]
            for chunk in chunks:
                await user.send(chunk)
        else:
            await user.send(change_summary)

        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(current_paragraphs))
        return "Changes found and sent via DM."
    else:
        return "Checked article. No changes detected."

@tasks.loop(hours=2)
async def check_article():
    user = await bot.fetch_user(YOUR_DISCORD_USER_ID)
    if not user:
        return
    result = await process_and_notify_changes(user)
    print(result)

@bot.command(name="fetch")
async def manual_fetch(ctx):
    if ctx.author.id != YOUR_DISCORD_USER_ID:
        return

    await ctx.send("Manually fetching article and checking for updates...")
    result = await process_and_notify_changes(ctx.author)
    await ctx.send(f"Result: {result}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Starting article monitor loop...")
    check_article.start()

bot.run(TOKEN)