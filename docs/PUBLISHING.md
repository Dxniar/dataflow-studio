# Publish the repository

Target: `Dxniar/dataflow-studio`, public, MIT license.

Before upload, run tests and Ruff and inspect the staged file list. Exclude `.venv`, temporary files, generated logs, credentials, build directories and non-synthetic data. Use a GitHub noreply commit email if keeping personal contact information private.

If the connected GitHub tools cannot create a repository, create an empty public repository named `dataflow-studio` on GitHub, without initializing a README, then run:

```powershell
git remote add origin https://github.com/Dxniar/dataflow-studio.git
git branch -M main
git push -u origin main
```

Description:

> Modern Python desktop application and CLI for cleaning, merging, transforming, and automating Excel & CSV workflows.

Topics: `python`, `excel`, `csv`, `automation`, `pandas`, `customtkinter`, `desktop-app`, `cli`, `data-processing`, `pytest`.

Upload portable Windows builds and video as release assets if desired; keep large binaries out of Git history. A source ZIP is also provided locally. Publication is confirmed only when the remote contains the expected commit and files. Check the Actions tab for actual remote CI results.
