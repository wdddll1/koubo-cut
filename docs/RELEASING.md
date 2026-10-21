# 发布 / Releasing

Use Windows x64 and Python 3.12. Install requirements-dev.txt and pyinstaller==6.22.3. Run pytest and Node syntax checks, then `python -m PyInstaller --noconfirm portable.spec` in a clean staging directory. Never point PyInstaller's COLLECT output at a user's existing portable folder.

The spec uses runtime/ as its content directory and the page scissors logo as the multi-size Windows icon. Copy the EXE and runtime into a versioned folder. Add an empty data/ folder, root portable.json with `{}`, README files, LICENSE, THIRD_PARTY_NOTICES.md and docs/. Models and FFmpeg executables must not be bundled in the public ZIP. Copying private user data is forbidden.

Audit every release: no API keys, personal paths, media, transcript/project data, model weights or cached output. Run the frozen EXE self-test on a fresh data directory, verify English and Chinese routes, perform real English ASR and verify the first-use media-tool download. Archive with ZIP, publish SHA256SUMS.txt, tag the tested commit, and mark beta releases as prereleases. Verify uploaded assets against local hashes.

源码与应用自身为 MIT；保留第三方全部许可。升级用户本机时备份原目录，在停止本机启动器后替换程序，保留 data，把旧根缓存迁移到 data/cache。不要覆盖或公开个人素材。详见 THIRD_PARTY_NOTICES.md。
