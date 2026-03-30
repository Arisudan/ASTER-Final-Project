import re

with open('www/style.css', 'r', encoding='utf-8') as f:
    content = f.read()

# using regex
pattern = re.compile(r'\.auth-shell\s*\{.*?(?=\.auth-actions,\s*\n\s*\.voice-actions)', re.DOTALL)
match = pattern.search(content)
if match:
    print("MATCH FOUND")
    new_auth_css = """
  .auth-panel,
  .success-panel {
    text-align: center;
    background: radial-gradient(circle at 18% 12%, rgba(0, 212, 255, 0.08), transparent 44%),
                linear-gradient(180deg, rgba(8, 12, 22, 0.9), rgba(5, 8, 14, 0.95));
    border: 1px solid rgba(0, 212, 255, 0.16);
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5), inset 0 0 0 1px rgba(255,255,255,0.04);
  }

  .enrollment-panel {
    position: relative;
  }
  
  .auth-art {
    display: block;
    margin: 0 auto 18px;
    max-width: 120px;
    width: 100%;
    filter: drop-shadow(0 0 18px rgba(0, 212, 255, 0.24));
  }

  .scan-orb {
    width: 180px;
    height: 180px;
    margin: 0 auto 26px;
    border-radius: 50%;
    position: relative;
    background:
      radial-gradient(circle at center, rgba(0, 212, 255, 0.08), transparent 58%),
      linear-gradient(180deg, rgba(0, 212, 255, 0.12), rgba(123, 47, 255, 0.08));
    border: 1px solid rgba(0, 212, 255, 0.28);
    box-shadow: 0 0 48px rgba(0, 212, 255, 0.18);
    overflow: hidden;
  }
  
  .scan-orb--enroll {
    width: 150px;
    height: 150px;
  }

  .scan-orb::before,
  .scan-orb::after {
    content: "";
    position: absolute;
    inset: 18px;
    border-radius: 50%;
    border: 1px solid rgba(0, 212, 255, 0.16);
  }

  .scan-orb::after {
    inset: 38px;
  }

  .scan-line {
    position: absolute;
    inset: 0;
    background: linear-gradient(180deg, transparent 0%, rgba(0, 212, 255, 0.9) 50%, transparent 100%);
    opacity: 0.3;
    transform: translateY(-100%);
    animation: scan 2.2s ease-in-out infinite;
  }

  .scan-line--alt {
    animation-delay: 1.1s;
  }

  .success-mark {
    width: 110px;
    height: 110px;
    margin: 0 auto 22px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-size: 58px;
    font-weight: 700;
    color: #09101d;
    background: linear-gradient(135deg, #33ffda, #00d4ff);
    box-shadow: 0 0 36px rgba(51, 255, 218, 0.38);
  }
  
  #auth-status, #enrollment-status {
    color: var(--driving-muted);
    margin-bottom: 24px;
    font-size: 0.95rem;
  }
"""
    content = content[:match.start()] + new_auth_css + content[match.end():]
    with open('www/style.css', 'w', encoding='utf-8') as f:
        f.write(content)
else:
    print("NO MATCH")
