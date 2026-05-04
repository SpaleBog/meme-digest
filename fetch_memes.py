import requests
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import pytz
import re
import time

SUBREDDITS = ["shitposting", "okbuddyretard", "blursedimages", "ihaveihaveihavereddit"]
TOP_N = 10

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_upvote_ratio_score(post):
    ups = post.get("ups", 0)
    ratio = post.get("upvote_ratio", 0.5)
    num_comments = post.get("num_comments", 0)
    awards = post.get("total_awards_received", 0)

    # Bazni score: upvote-ovi * ratio
    base = ups * ratio

    # Kriterijum 1: engagement (komentari po upvotu)
    # Smesni postovi provociraju komentare - bonus ako je comment/ups ratio visok
    engagement_bonus = 0
    if ups > 0:
        comment_ratio = num_comments / ups
        engagement_bonus = comment_ratio * ups * 0.3  # 30% tezine

    # Kriterijum 3: awards (ljudi trose novac da nagrade smesne postove)
    awards_bonus = awards * 500

    return base + engagement_bonus + awards_bonus

def extract_image_from_html(html_content):
    """Izvuci URL slike iz Reddit HTML opisa posta"""
    # Traži img tag
    match = re.search(r'<img[^>]+src="([^"]+)"', html_content)
    if match:
        url = match.group(1).replace("&amp;", "&")
        if any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
            return url
    return ""

def fetch_top_memes_json(subreddit, limit=50):
    """Pokušaj sa JSON API"""
    url = f"https://www.reddit.com/r/{subreddit}/top.json?t=day&limit={limit}&raw_json=1"
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        print(f"    JSON status: {response.status_code}")
        if response.status_code != 200:
            return None
        data = response.json()
        posts = data["data"]["children"]
        print(f"    JSON vratio {len(posts)} postova")
        return posts
    except Exception as e:
        print(f"    JSON greška: {e}")
        return None

def fetch_top_memes_rss(subreddit, period="day"):
    """Fallback na RSS feed, sa automatskim prelaskom na sedmicu ako nema dnevnih"""
    url = f"https://www.reddit.com/r/{subreddit}/top.rss?t={period}&limit=50"
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        print(f"    RSS status: {response.status_code} (period={period})")
        if response.status_code != 200:
            return []
        
        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)
        print(f"    RSS vratio {len(entries)} unosa")


        
        memes = []
        for entry in entries:
            title_el = entry.find("atom:title", ns)
            link_el = entry.find("atom:link", ns)
            content_el = entry.find("atom:content", ns)
            
            title = title_el.text if title_el is not None else ""
            reddit_url = link_el.get("href", "") if link_el is not None else ""
            content_html = content_el.text if content_el is not None else ""
            
            image_url = extract_image_from_html(content_html)
            
            # Izvuci thumbnail iz content-a
            thumb_match = re.search(r'<a href="([^"]+)">\[link\]', content_html)
            if not image_url and thumb_match:
                link = thumb_match.group(1).replace("&amp;", "&")
                if any(ext in link.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                    image_url = link

            memes.append({
                "title": title,
                "score": 1000,  # RSS nema score, koristimo poziciju
                "ups": 0,
                "upvote_ratio": 1.0,
                "url": image_url,
                "thumbnail": image_url,
                "reddit_url": reddit_url,
                "author": "",
                "num_comments": 0,
                "subreddit": subreddit,
            })
        
        # Pozicija u RSS = sortiranost po popularnosti
        for i, m in enumerate(memes):
            m["score"] = len(memes) - i
        
        return memes[:TOP_N]
    except Exception as e:
        print(f"    RSS greška: {e}")
        return []

def fetch_top_memes(subreddit):
    print(f"  → r/{subreddit}")
    
    # Pokušaj JSON API prvo
    posts = fetch_top_memes_json(subreddit)
    
    if posts is not None and len(posts) > 0:
        memes = []
        for post in posts:
            p = post["data"]
            
            # Ne filtriramo striktno - prihvatamo sve osim self postova
            if p.get("is_self", False):
                continue
            
            image_url = p.get("url", "")
            
            # Galerija - uzmi prvu sliku
            if "reddit.com/gallery" in image_url or p.get("is_gallery", False):
                try:
                    media_metadata = p.get("media_metadata", {})
                    if media_metadata:
                        first_key = next(iter(media_metadata))
                        s = media_metadata[first_key].get("s", {})
                        image_url = s.get("u", image_url).replace("&amp;", "&")
                except:
                    pass
            
            # Preview slika kao fallback
            preview_url = ""
            try:
                preview_url = p["preview"]["images"][0]["source"]["url"].replace("&amp;", "&")
            except:
                pass
            
            thumbnail = p.get("thumbnail", "")
            if thumbnail in ("self", "default", "nsfw", "spoiler", "", "image"):
                thumbnail = preview_url or image_url
            
            final_image = image_url if any(ext in image_url.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", "i.redd.it", "i.imgur.com"]) else preview_url
            
            score = get_upvote_ratio_score(p)
            
            memes.append({
                "title": p.get("title", ""),
                "score": score,
                "ups": p.get("ups", 0),
                "upvote_ratio": p.get("upvote_ratio", 1.0),
                "url": final_image,
                "thumbnail": thumbnail,
                "reddit_url": f"https://www.reddit.com{p.get('permalink', '')}",
                "author": p.get("author", ""),
                "num_comments": p.get("num_comments", 0),
                "awards": p.get("total_awards_received", 0),
                "subreddit": subreddit,
            })
        
        memes.sort(key=lambda x: x["score"], reverse=True)
        result = memes[:TOP_N]
        print(f"     ✅ {len(result)} memova (JSON)")
        return result
    
    # Fallback na RSS
    print(f"    JSON nije radio, probam RSS...")
    result = fetch_top_memes_rss(subreddit)
    print(f"     ✅ {len(result)} memova (RSS)")
    return result

def generate_html(all_memes_by_sub, generated_at):
    cet = pytz.timezone("Europe/Belgrade")
    dt = datetime.fromisoformat(generated_at).astimezone(cet)
    date_str = dt.strftime("%d.%m.%Y")
    time_str = dt.strftime("%H:%M")

    sections_html = ""
    for sub, memes in all_memes_by_sub.items():
        if not memes:
            cards_html = '<p style="color:#888;padding:1rem;">Nema podataka za danas.</p>'
        else:
            cards_html = ""
            for i, m in enumerate(memes, 1):
                ratio_pct = int(m["upvote_ratio"] * 100)
                ups = m["ups"]
                ups_fmt = f"{ups:,}".replace(",", ".") if ups > 0 else "N/A"
                img_src = m.get("url", "") or m.get("thumbnail", "")

                title_short = m["title"][:120] + ("..." if len(m["title"]) > 120 else "")

                reddit_url = m["reddit_url"]
                if img_src and img_src.startswith("http"):
                    img_tag = '<a href="' + reddit_url + '" target="_blank" style="display:block;height:100%"><img src="' + img_src + '" alt="meme" loading="lazy" onerror="this.parentElement.innerHTML=\'<div class=no-img>🖼️</div>\'"/></a>'
                else:
                    img_tag = '<div class="no-img">🖼️</div>'

                awards = m.get("awards", 0)
                awards_badge = f'<span class="stat awards">🏆 {awards}</span>' if awards > 0 else ""
                num_comments = m["num_comments"]

                cards_html += f"""
                <div class="meme-card" style="--i:{i}">
                    <div class="rank">#{i}</div>
                    <div class="meme-img-wrap">{img_tag}</div>
                    <div class="meme-info">
                        <p class="meme-title">{title_short}</p>
                        <div class="meme-stats">
                            <span class="stat ups">▲ {ups_fmt}</span>
                            <span class="stat ratio">💯 {ratio_pct}%</span>
                            <span class="stat comments">💬 {num_comments}</span>
                            {awards_badge}
                        </div>
                        <a href="{m['reddit_url']}" target="_blank" class="view-btn">Pogledaj na Reddit →</a>
                    </div>
                </div>
                """

        sections_html += f"""
        <section class="sub-section" data-sub="{sub}">
            <h2 class="sub-title">r/{sub}</h2>
            <div class="meme-grid">{cards_html}</div>
        </section>
        """

    html = f"""<!DOCTYPE html>
<html lang="sr">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"/>
<meta http-equiv="Pragma" content="no-cache"/>
<meta http-equiv="Expires" content="0"/>
<title>Dnevni Meme Digest – {date_str}</title>
<meta name="generated" content="{date_str}-{time_str}"/>
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
    --radius: 14px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'DM Sans', sans-serif;
    min-height: 100vh;
    background-image: radial-gradient(ellipse 80% 40% at 50% -10%, rgba(255,69,0,0.12) 0%, transparent 60%);
  }}

  /* ===== HEADER ===== */
  header {{ text-align: center; padding: 2rem 1rem 1.5rem; border-bottom: 1px solid var(--border); }}
  .logo {{
    font-family: 'Bebas Neue', sans-serif;
    font-size: clamp(2.2rem, 8vw, 5rem);
    letter-spacing: 0.05em;
    background: linear-gradient(135deg, #ff4500, #ff8c42);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1;
  }}
  .tagline {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.4rem; letter-spacing: 0.08em; text-transform: uppercase; }}
  .date-badge {{
    display: inline-block; margin-top: 0.8rem;
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 99px; padding: 0.3rem 1rem;
    font-size: 0.82rem; color: var(--accent2); font-weight: 500;
  }}

  /* ===== NAV TABS (mobile subreddit switcher) ===== */
  .sub-nav {{
    display: flex;
    overflow-x: auto;
    gap: 0.5rem;
    padding: 1rem 1rem 0;
    max-width: 1100px;
    margin: 0 auto;
    scrollbar-width: none;
    -ms-overflow-style: none;
  }}
  .sub-nav::-webkit-scrollbar {{ display: none; }}
  .sub-tab {{
    flex-shrink: 0;
    padding: 0.45rem 1rem;
    border-radius: 99px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--muted);
    font-size: 0.82rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;
  }}
  .sub-tab.active {{
    background: var(--accent);
    border-color: var(--accent);
    color: white;
  }}

  /* ===== MAIN ===== */
  main {{ max-width: 1100px; margin: 0 auto; padding: 1.2rem 1rem 4rem; }}
  .sub-section {{ display: none; }}
  .sub-section.active {{ display: block; }}

  .sub-title {{
    font-family: 'Bebas Neue', sans-serif; font-size: 1.8rem;
    letter-spacing: 0.08em; color: var(--accent); margin-bottom: 1rem;
    display: flex; align-items: center; gap: 0.5rem;
  }}
  .sub-title::after {{
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(to right, var(--border), transparent); margin-left: 0.5rem;
  }}

  /* ===== GRID ===== */
  /* Desktop: 3 kolone, Tablet: 2, Mobile: 1 */
  .meme-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
  }}
  @media (max-width: 900px) {{
    .meme-grid {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  @media (max-width: 560px) {{
    .meme-grid {{ grid-template-columns: 1fr; }}
  }}

  /* ===== CARDS ===== */
  .meme-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); overflow: hidden;
    transition: transform 0.2s ease, border-color 0.2s ease;
    animation: fadeUp 0.35s ease both;
    animation-delay: calc(var(--i) * 0.04s);
    display: flex;
    flex-direction: column;
  }}
  .meme-card:hover {{ transform: translateY(-3px); border-color: var(--accent); }}
  @keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(14px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}

  .rank {{
    font-family: 'Bebas Neue', sans-serif; font-size: 0.8rem;
    letter-spacing: 0.1em; color: var(--accent); padding: 0.5rem 0.8rem 0;
  }}
  .meme-img-wrap {{
    width: 100%; aspect-ratio: 1/1;
    background: var(--surface2);
    display: flex; align-items: center; justify-content: center; overflow: hidden;
  }}
  .meme-img-wrap img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
  .no-img {{ font-size: 3rem; opacity: 0.3; }}
  .meme-info {{ padding: 0.8rem; display: flex; flex-direction: column; gap: 0.5rem; flex: 1; }}
  .meme-title {{ font-size: 0.85rem; line-height: 1.4; color: var(--text); }}
  .meme-stats {{ display: flex; gap: 0.4rem; flex-wrap: wrap; margin-top: auto; padding-top: 0.3rem; }}
  .stat {{
    font-size: 0.74rem; background: var(--surface2);
    border-radius: 6px; padding: 0.2rem 0.5rem; color: var(--muted); font-weight: 500;
  }}
  .stat.ups {{ color: var(--accent2); }}
  .view-btn {{
    display: block; text-align: center;
    font-size: 0.8rem; font-weight: 700;
    color: white; background: var(--accent);
    text-decoration: none; border-radius: 8px;
    padding: 0.5rem; margin-top: 0.5rem;
    transition: background 0.15s;
  }}
  .view-btn:hover {{ background: var(--accent2); }}

  /* ===== FOOTER ===== */
  footer {{ text-align: center; padding: 1.5rem; color: var(--muted); font-size: 0.78rem; border-top: 1px solid var(--border); }}
</style>
</head>
<body>
<header>
  <div class="logo">🔥 Meme Digest</div>
  <p class="tagline">Najbolji mimovi dana • Automatski sakupljeno</p>
  <span class="date-badge">📅 {date_str} u {time_str} CET</span>
</header>

<nav class="sub-nav" id="subNav"></nav>
<main id="mainContent">{sections_html}</main>

<footer>
  Generisano automatski iz r/shitposting, r/okbuddyretard, r/blursedimages, r/ihaveihaveihavereddit<br>
  Sortirano po: upvote-ovi × ratio + engagement | Poslednje ažuriranje: {date_str} {time_str}
</footer>

<script>
  // Skupi sve sekcije i napravi tabove
  const sections = document.querySelectorAll('.sub-section');
  const nav = document.getElementById('subNav');

  sections.forEach((sec, idx) => {{
    const name = sec.dataset.sub;
    const btn = document.createElement('button');
    btn.className = 'sub-tab' + (idx === 0 ? ' active' : '');
    btn.textContent = 'r/' + name;
    btn.onclick = () => {{
      document.querySelectorAll('.sub-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.sub-section').forEach(s => s.classList.remove('active'));
      btn.classList.add('active');
      sec.classList.add('active');
    }};
    nav.appendChild(btn);
    if (idx === 0) sec.classList.add('active');
  }});
</script>
<script>
  (function() {{
    var meta = document.querySelector('meta[name="generated"]');
    if (!meta) return;
    var current = meta.getAttribute('content');
    var stored = sessionStorage.getItem('meme_version');
    if (stored && stored !== current) {{
      sessionStorage.setItem('meme_version', current);
      window.location.href = window.location.href.split('?')[0] + '?v=' + current.replace(/[^a-zA-Z0-9]/g, '');
    }} else {{
      sessionStorage.setItem('meme_version', current);
    }}
  }})();
</script>
</body>
</html>"""
    return html



def main():
    print("🚀 Sakupljam meme...")
    all_memes = {}
    for sub in SUBREDDITS:
        memes = fetch_top_memes(sub)
        all_memes[sub] = memes
        time.sleep(2)  # pauza između requesta da ne dobijemo rate limit

    now = datetime.now(timezone.utc).isoformat()
    html = generate_html(all_memes, now)

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    with open("docs/memes.json", "w", encoding="utf-8") as f:
        json.dump({"generated_at": now, "data": all_memes}, f, ensure_ascii=False, indent=2)

    total = sum(len(v) for v in all_memes.values())
    print(f"✅ Gotovo! {total} memova ukupno. docs/index.html generisan.")

if __name__ == "__main__":
    main()
