def get_cached_briefing(markdown: str | None) -> str | None:
    if not markdown:
        return None
    if markdown.startswith("<!-- briefing-context:"):
        _, separator, content = markdown.partition("\n")
        if separator:
            return content.lstrip()
    return markdown
