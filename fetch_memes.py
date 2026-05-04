import requests
import json
import os
from datetime import datetime, timezone
import pytz

SUBREDDITS = ["shitposting", "TheRealJoke", "blursedimages"]
HEADERS = {"User-Agent": "MemeDigest/1.0 (daily meme aggregator)"}
TOP_N = 10  # top 10 po subredditu

def get_upvote_ratio_score(post):
    """Score = upvotes * ratio (penalizuje downvote-ovane postove)"""
    ups = post.get("ups", 0)
    ratio = post.get("upvote_ratio", 0.5)
    return ups * ratio

def fetch_top_memes(subreddit, limit=50):
    url = f"https://www.reddit.com/r/{subreddit}/top.json?t=day&limit={limit}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        posts = data["data"]["children"]
    except Exception as e:
        print(f"Greška pri učitavanju r/{subreddit}: {e}")
        return []

    memes = []
    for post in posts:
        p = post["data"]

        # Filtriramo samo image/gif postove
        url_lower = p.get("url", "").lower()
        post_hint = p.get("post_hint", "")
        is_image = (
            post_hint in ("image", "link")
            or url_lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))
            or "i.redd.it" in url_lower
            or "i.imgur.com" in url_lower
        )

        if not is_image:
            continue

        # Thumbnail za preview
        thumbnail = p.get("thumbnail", "")
        if thumbnail in ("self", "default", "nsfw", "spoiler", ""):
            thumbnail = p.get("url", "")

        # Za galerije uzmi prvu sliku
        image_url = p.get("url", "")
        if "gallery" in image_url:
            try:
                media_metadata = p.get("media_metadata", {})
                first_key = next(iter(media_metadata))
                image_url = media_metadata[first_key]["s"]["u"].replace("&amp;", "&")
            except:
                pass

        score = get_upvote_ratio_score(p)

        memes.append({
            "title": p.get("title", ""),
            "score": score,
            "ups": p.get("ups", 0),
            "upvote_ratio": p.get("upvote_ratio", 0),
            "url": image_url,
            "thumbnail": thumbnail,
            "reddit_url": f"https://www.reddit.com{p.get('permalink', '')}",
            "author": p.get("author", ""),
            "num_comments": p.get("num_comments", 0),
            "subreddit": subreddit,
        })

    # Sortiraj po score-u i uzmi top N
    memes.sort(key=lambda x: x["score"], reverse=True)
    return memes[:TOP_N]

def generate_html(all_memes_by_sub, generated_at):
    cet = pytz.timezone("Europe/Belgrade")
    dt = datetime.fromisoformat(generated_at).astimezone(cet)
    date_str = dt.strftime("%d.%m.%Y")
    time_str = dt.strftime("%H:%M")

    # Build meme cards per subreddit
    sections_html = ""
    for sub, memes in all_memes_by_sub.items():
        cards_html = ""
        for i, m in enumerate(memes, 1):
            ratio_pct = int(m["upvote_ratio"] * 100)
            ups_fmt = f"{m['ups']:,}".replace(",", ".")
            img_src = m["url"]
            # fallback na thumbnail ako URL nije direktna slika
            if not any(img_src.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                img_src = m["thumbnail"] if m["thumbnail"].startswith("http") else ""

            title_short = m['title'][:120] + ('...' if len(m['title']) > 120 else '')
            if img_src:
                img_tag = '<img src="' + img_src + '" alt="meme" loading="lazy" onerror="this.style.display=\'none\'"/>'
            else:
                img_tag = '<div class="no-img">🖼️</div>'

            cards_html += f"""
            <div class="meme-card" style="--i:{i}">
                <div class="rank">#{i}</div>
                <div class="meme-img-wrap">
                    {img_tag}
                </div>
                <div class="meme-info">
                    <p class="meme-title">{title_short}</p>
                    <div class="meme-stats">
                        <span class="stat ups">▲ {ups_fmt}</span>
                        <span class="stat ratio">💯 {ratio_pct}%</span>
                        <span class="stat comments">💬 {m['num_comments']}</span>
                    </div>
                    <a href="{m['reddit_url']}" target="_blank" class="view-btn">Pogledaj na Reddit →</a>
                </div>
            </div>
            """

        sections_html += f"""
        <section class="sub-section">
            <h2 class="sub-title">r/{sub}</h2>
            <div class="meme-grid">{cards_html}</div>
        </section>
        """

    html = f"""<!DOCTYPE html>
<html lang="sr">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Dnevni Meme Digest – {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0d0d0f;
    --surface: #18181c;
    --surface2: #222228;
    --accent: #ff4500;
    --accent2: #ff6b35;
    --text: #f0f0f0;
    --muted: #888;
    --border: #2a2a32;
    --radius: 12px;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'DM Sans', sans-serif;
    min-height: 100vh;
    background-image:
      radial-gradient(ellipse 80% 40% at 50% -10%, rgba(255,69,0,0.12) 0%, transparent 60%);
  }}

  header {{
    text-align: center;
    padding: 3rem 1rem 2rem;
    border-bottom: 1px solid var(--border);
    position: relative;
  }}

  .logo {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: clamp(2.8rem, 8vw, 5rem);
    letter-spacing: 0.05em;
    background: linear-gradient(135deg, #ff4500, #ff8c42);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1;
  }}

  .tagline {{
    color: var(--muted);
    font-size: 0.95rem;
    margin-top: 0.5rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }}

  .date-badge {{
    display: inline-block;
    margin-top: 1rem;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 99px;
    padding: 0.3rem 1.1rem;
    font-size: 0.85rem;
    color: var(--accent2);
    font-weight: 500;
  }}

  main {{
    max-width: 1100px;
    margin: 0 auto;
    padding: 2rem 1rem 4rem;
  }}

  .sub-section {{
    margin-bottom: 3.5rem;
  }}

  .sub-title {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 2rem;
    letter-spacing: 0.08em;
    color: var(--accent);
    margin-bottom: 1.2rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }}

  .sub-title::after {{
    content: '';
    flex: 1;
    height: 1px;
    background: linear-gradient(to right, var(--border), transparent);
    margin-left: 0.5rem;
  }}

  .meme-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1.2rem;
  }}

  .meme-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    transition: transform 0.2s ease, border-color 0.2s ease;
    animation: fadeUp 0.4s ease both;
    animation-delay: calc(var(--i) * 0.05s);
  }}

  .meme-card:hover {{
    transform: translateY(-4px);
    border-color: var(--accent);
  }}

  @keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(16px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}

  .rank {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: 0.85rem;
    letter-spacing: 0.1em;
    color: var(--accent);
    padding: 0.5rem 0.8rem 0;
  }}

  .meme-img-wrap {{
    width: 100%;
    aspect-ratio: 16/9;
    background: var(--surface2);
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }}

  .meme-img-wrap img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }}

  .no-img {{
    font-size: 3rem;
    opacity: 0.3;
  }}

  .meme-info {{
    padding: 0.9rem;
    display: flex;
    flex-direction: column;
    gap: 0.7rem;
  }}

  .meme-title {{
    font-size: 0.88rem;
    line-height: 1.4;
    color: var(--text);
  }}

  .meme-stats {{
    display: flex;
    gap: 0.6rem;
    flex-wrap: wrap;
  }}

  .stat {{
    font-size: 0.78rem;
    background: var(--surface2);
    border-radius: 6px;
    padding: 0.2rem 0.6rem;
    color: var(--muted);
    font-weight: 500;
  }}

  .stat.ups {{ color: var(--accent2); }}

  .view-btn {{
    display: inline-block;
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--accent);
    text-decoration: none;
    letter-spacing: 0.03em;
    transition: color 0.15s;
  }}

  .view-btn:hover {{ color: var(--accent2); }}

  footer {{
    text-align: center;
    padding: 2rem;
    color: var(--muted);
    font-size: 0.8rem;
    border-top: 1px solid var(--border);
  }}

  @media (max-width: 500px) {{
    .meme-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<header>
  <div class="logo">🔥 Meme Digest</div>
  <p class="tagline">Najbol­ji mimovi dana • Auto­matski sakupljeno</p>
  <span class="date-badge">📅 {date_str} u {time_str} CET</span>
</header>
<main>
  {sections_html}
</main>
<footer>
  Generisano automatski iz r/shitposting, r/TheRealJoke, r/blursedimages<br>
  Sortirano po: upvote-ovi × ratio | Poslednje ažuriranje: {date_str} {time_str}
</footer>
</body>
</html>"""
    return html

def main():
    print("🚀 Sakupljam meme...")
    all_memes = {}
    for sub in SUBREDDITS:
        print(f"  → r/{sub}")
        memes = fetch_top_memes(sub)
        all_memes[sub] = memes
        print(f"     {len(memes)} memova pronađeno")

    now = datetime.now(timezone.utc).isoformat()
    html = generate_html(all_memes, now)

    # Sačuvaj HTML
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    # Sačuvaj JSON (za debug)
    with open("docs/memes.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": now, "data": all_memes}, f, ensure_ascii=False, indent=2)

    print(f"✅ Gotovo! docs/index.html generisan.")

if __name__ == "__main__":
    main()
