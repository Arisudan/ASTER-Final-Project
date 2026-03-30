import re

with open('www/style.css', 'r', encoding='utf-8') as f:
    css = f.read()

# Replace brand badge CSS
css = re.sub(
    r'\.brand-badge\s*\{[^}]+\}',
    """\.brand-badge {
  width: 60px;
  height: 60px;
  flex: 0 0 auto;
  position: relative;
  overflow: visible;
  filter: drop-shadow(0 4px 12px rgba(0,0,0,0.4));
}""",
    css
)

# Remove the old background/color rules for brand-badge
css = re.sub(r'\.brand-badge--ambient\s*\{[^}]+\}', '', css)
css = re.sub(r'body\[data-mode="ambient"\]\s*\.brand-badge--ambient\s*\{[^}]+\}', '', css)
css = re.sub(r'body\[data-mode="driving"\]\s*\.brand-badge\s*\{[^}]+\}', '', css)

with open('www/style.css', 'w', encoding='utf-8') as f:
    f.write(css)
print("CSS brand badge fixed.")
