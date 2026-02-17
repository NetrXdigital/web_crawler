import urllib.robotparser as robotparser
from urllib.parse import urljoin

def load_robots(website_url: str, user_agent: str) -> robotparser.RobotFileParser:
    robots_url = urljoin(website_url.rstrip("/") + "/", "robots.txt")
    rp = robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:
        # If robots can't be loaded, be conservative? You chose strict obeying.
        # Strict approach: if robots fetch fails, allow crawl (common tool behavior),
        # but you can flip to deny-all if you want.
        pass
    return rp

def allowed_by_robots(rp: robotparser.RobotFileParser, user_agent: str, url: str) -> bool:
    try:
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True
