"""Regression checks for patch registration and test staging (no server/database)."""
import pathlib, subprocess, sys, unittest
from contextlib import nullcontext
HERE=pathlib.Path(__file__).resolve().parents[1]
class PatchTests(unittest.TestCase):
    def test_apply_once(self):
        with nullcontext(HERE/'tests/.test-work/apply') as tmp:
            folder=pathlib.Path(tmp)/'src/game/PlayerBots';folder.mkdir(parents=True,exist_ok=True)
            cpp=folder/'PlayerBotAI.cpp'
            cpp.write_text('PlayerBotAI* CreatePlayerBotAI(std::string ainame)\n{\n    return new PlayerBotAI();\n}\n')
            cmd=[sys.executable,str(HERE/'scripts/apply-silicio.py'),tmp]
            subprocess.run(cmd,check=True,capture_output=True)
            self.assertIn('return new SilicioAI();',cpp.read_text())
            self.assertEqual((folder/'SilicioAI.inc').read_bytes(),(HERE/'ai/SilicioAI.inc').read_bytes())
            before=cpp.read_bytes()
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(cpp.read_bytes(),before)
    def test_unexpected_source_untouched(self):
        with nullcontext(HERE/'tests/.test-work/reject') as tmp:
            folder=pathlib.Path(tmp)/'src/game/PlayerBots';folder.mkdir(parents=True,exist_ok=True)
            cpp=folder/'PlayerBotAI.cpp';cpp.write_text('different upstream')
            p=subprocess.run([sys.executable,str(HERE/'scripts/apply-silicio.py'),tmp],capture_output=True)
            self.assertNotEqual(p.returncode,0)
            self.assertEqual(cpp.read_text(),'different upstream')
if __name__=='__main__':unittest.main()
