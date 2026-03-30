import sys

with open('www/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

logo_svg = """
<svg class="aster-prism" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M50 5 L10 85 L90 85 Z" fill="url(#silver-outer)" />
  <path d="M50 5 L10 85 L30 85 L50 45 Z" fill="#E5E5E5" />
  <path d="M50 5 L30 85 L50 55 Z" fill="#B0B0B0" />
  <path d="M50 5 L90 85 L70 85 L50 45 Z" fill="#D0D0D0" />
  <path d="M50 5 L70 85 L50 55 Z" fill="#909090" />
  <!-- Central Gold Prism -->
  <path d="M50 25 L30 65 L70 65 Z" fill="url(#gold-core)" />
  <!-- Gold Facets -->
  <path d="M50 25 L30 65 L50 60 Z" fill="#FFE87C" />
  <path d="M50 25 L70 65 L50 60 Z" fill="#D4AF37" />
  <path d="M30 65 L70 65 L50 60 Z" fill="#B58B12" />

  <defs>
    <linearGradient id="silver-outer" x1="0" y1="0" x2="100" y2="100">
      <stop offset="0%" stop-color="#FFFFFF"/>
      <stop offset="50%" stop-color="#C0C0C0"/>
      <stop offset="100%" stop-color="#505050"/>
    </linearGradient>
    <linearGradient id="gold-core" x1="50" y1="25" x2="50" y2="65">
      <stop offset="0%" stop-color="#FFF0A0"/>
      <stop offset="100%" stop-color="#D4AF37"/>
    </linearGradient>
  </defs>
</svg>
"""

html = html.replace('<div class="brand-badge brand-badge--ambient">A</div>', logo_svg.replace('class="aster-prism"', 'class="brand-badge brand-badge--ambient aster-prism"'))
html = html.replace('<div class="brand-badge">J</div>', logo_svg.replace('class="aster-prism"', 'class="brand-badge aster-prism"'))

with open('www/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('SVG replacement complete.')
