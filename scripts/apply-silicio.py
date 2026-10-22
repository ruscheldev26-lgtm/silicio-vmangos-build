"""Apply the opt-in controller only to the pinned public source in a build workspace."""
import hashlib
import pathlib
import sys

source = pathlib.Path(sys.argv[1]).resolve()
control = pathlib.Path(__file__).resolve().parent.parent
cpp = source / 'src/game/PlayerBots/PlayerBotAI.cpp'
text = cpp.read_text(encoding='utf-8')
marker = 'PlayerBotAI* CreatePlayerBotAI(std::string ainame)\n{'
if text.count(marker) != 1 or 'SilicioAI.inc' in text:
    raise SystemExit('Unexpected or already patched source')
text = text.replace(marker, '#include "SilicioAI.inc"\n\n' + marker + '\n    if (ainame == "SilicioAI")\n        return new SilicioAI();')
cpp.write_text(text, encoding='utf-8', newline='\n')
payload = (control / 'ai/SilicioAI.inc').read_bytes()
(cpp.parent / 'SilicioAI.inc').write_bytes(payload)
print('SilicioAI applied:', hashlib.sha256(payload).hexdigest())
