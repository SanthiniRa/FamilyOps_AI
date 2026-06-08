import shutil
from pathlib import Path

root = Path(__file__).resolve().parent

targets = [
    root / 'frontend',
    root / 'main.py',
    root / 'pyproject.toml',
    root / 'sql query',
]

for target in targets:
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
            print('Removed directory:', target)
        else:
            target.unlink()
            print('Removed file:', target)
    else:
        print('Skipping missing:', target)

print('Cleanup script complete. Verify the repository contents.')
