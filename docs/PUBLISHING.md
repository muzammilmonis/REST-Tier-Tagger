# Publishing notes

This project is a derivative build layer for the public `mctiers-dev/TierTagger` source branches.

1. Keep the upstream LICENSE copied by the cloned branch inside source distributions.
2. Keep `NOTICE-REST.md` in source releases.
3. Do **not** restore MCTiers/SubTiers icon assets removed by the patcher. Upstream's repository explicitly treats those visual assets separately from code reuse.
4. Use your own REST Tier Tagger icon/logo on Modrinth.
5. Do not publish a build until its GitHub Actions job passes and `verify_jars.py` reports `OK`.
6. Recommended project title: **REST Tier Tagger**.
7. Recommended summary: **Client-side tier tags powered by REST Tiers (tiers.rest).**

The patch layer deliberately disables the original Modrinth update checker so REST users are not told to install the unrelated upstream release.
