import re

with open('www/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

with open('min_loader.html', 'r', encoding='utf-8') as f:
    min_loader = f.read()

# Replace everything from <section id="loader"... > to right before <section id="face-auth" ...>
html = re.sub(r'<section id="loader".*?(?=<section id="face-auth")', min_loader + '\n\n', html, flags=re.DOTALL)

with open('www/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print("Loader replaced.")
