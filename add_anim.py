import re

with open('www/style.css', 'r', encoding='utf-8') as f:
    css = f.read()

anim_css = """
#loader .aster-prism {
  animation: prismAssemble 3.0s cubic-bezier(0.37, 0, 0.63, 1) forwards;
}

#loader .aster-prism path:nth-of-type(6),
#loader .aster-prism path:nth-of-type(7),
#loader .aster-prism path:nth-of-type(8),
#loader .aster-prism path:nth-of-type(9) {
  animation: corePulse 3.0s cubic-bezier(0.37, 0, 0.63, 1) forwards;
}

@keyframes prismAssemble {
  0% { transform: scale(0) rotateY(-180deg) rotateX(45deg); opacity: 0; filter: blur(10px); }
  40% { transform: scale(1.1) rotateY(20deg) rotateX(-10deg); opacity: 0.8; filter: blur(2px); }
  70% { transform: scale(1) rotateY(0deg) rotateX(0deg); opacity: 1; filter: blur(0); }
  100% { transform: scale(1) rotateY(0deg) rotateX(0deg); opacity: 1; filter: blur(0); }
}

@keyframes corePulse {
  0%, 60% { opacity: 0; transform: translateY(10px); }
  75% { opacity: 1; transform: translateY(0); filter: drop-shadow(0 0 20px rgba(212,175,55,1)); }
  100% { opacity: 1; transform: translateY(0); filter: drop-shadow(0 0 8px rgba(212,175,55,0.6)); }
}
"""

css += anim_css

with open('www/style.css', 'w', encoding='utf-8') as f:
    f.write(css)
print("Prism animation CSS added.")
