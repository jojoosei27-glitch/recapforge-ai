# RecapForge AI — DVIDS military media starter

A restart-friendly starter for researching and collecting military videos and photos from DVIDS for a later AI-assisted editing workflow.

## What this first version does
- Searches the official DVIDS API for video and image assets.
- Saves search results as JSON and CSV manifests.
- Fetches detailed asset metadata for selected results.
- Downloads selected DVIDS-hosted media files when available.
- Saves attribution and source metadata next to each download.
- Keeps the API key in an environment variable, not in source code.
- Writes job data under `workspace/`, which should be on persistent storage (for example, Google Drive).

This is **Phase 1: the DVIDS footage pipeline**. Hermes orchestration, automatic shot selection, FFmpeg editing, Remotion graphics, and quality control will be added after this pipeline is verified on real results.

## 1. Get a DVIDS API key
Create/sign in to a DVIDS API account and create an API application:
https://api.dvidshub.net/

Read the API documentation and terms:
- https://api.dvidshub.net/docs
- https://api.dvidshub.net/docs/search_api/
- https://api.dvidshub.net/docs/asset_api/
- https://api.dvidshub.net/docs/tos
- https://www.dvidshub.net/about/copyright

DVIDS says much of its media is public domain, but **some assets have third-party rights or other restrictions**. Check the copyright/usage notes on each asset page before publishing. Preserve creator credits and do not imply U.S. Department of Defense endorsement.

## 2. Kaggle setup
In a Kaggle notebook, enable Internet and use a GPU accelerator if you plan to use the local model later. Upload or clone this repository, then run:

```bash
!bash setup.sh
```

Set your API key in the notebook without putting it in a saved cell or committing it:
```python
import os, getpass
os.environ["DVIDS_API_KEY"] = getpass.getpass("DVIDS API key: ")
```

For restart recovery, mount Google Drive and point the workspace there, for example:
```python
import os
os.environ["RECAPFORGE_WORKSPACE"] = "/content/drive/MyDrive/RecapForge/workspace"
```
Mount Drive first if using that path.

## 3. Search for military videos and photos
```bash
python -m recapforge search --query "F-35" --types video image --limit 20
python -m recapforge search --query "aircraft carrier flight deck" --types video image --branch Navy --limit 20
python -m recapforge search --query "Abrams tank training" --types video image --branch Army --limit 20
```

Search results are saved in `workspace/searches/` as JSON and CSV. The search command does not download media automatically.

## 4. Inspect results and download selected assets
Open the JSON/CSV manifest, then choose IDs that you actually want:
```bash
python -m recapforge download --ids video:284392 image:366678
```
The downloader fetches metadata, chooses the largest listed MP4 for videos, or the full-resolution image for photos, then writes source/credit metadata alongside the file.

You can also set a maximum download size in MB:
```bash
python -m recapforge download --ids video:284392 image:366678 --max-mb 800
```

The tool only downloads files from DVIDS media delivery hosts returned by the DVIDS API. It does not bypass login, access controls, geographic restrictions, or quotas.

## 5. Restarting a Kaggle session
Keep `workspace/` on persistent storage. After a session stops:
1. Start a new Kaggle session.
2. clone/upload the repo and run `setup.sh`.
3. remount persistent storage and set `RECAPFORGE_WORKSPACE`.
4. run another search, or use the same asset IDs with the download command.

Downloaded media is skipped if an existing file has a matching record and is non-empty. GitHub should contain code, not large media files, API keys, or private project materials.

## Notes
- DVIDS API use is subject to its terms, quotas, and API key restrictions. Do not try to evade quotas.
- Check asset-specific copyright/usage notices before commercial publication.
- Keep source links, title, description, date, branch, creator credit, and usage notes with every downloaded asset.
