import os
import glob
import runpod

def handler(job):
    files = sorted(glob.glob("/runpod-volume/**", recursive=True))
    sizes = {}
    for f in files:
        try:
            sizes[f] = os.path.getsize(f)
        except Exception:
            sizes[f] = -1
    return {"files": files, "sizes": sizes}

runpod.serverless.start({"handler": handler})
