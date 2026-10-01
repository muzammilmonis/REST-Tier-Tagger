# Validation notes

Checks performed in the artifact-generation environment:

- Python source patcher self-test passes.
- Every Python build/patch/verification tool passes `py_compile`.
- Legacy-style synthetic TierTagger tree patches successfully (profile provider, old `/all` bootstrap, config URL, mod id/metadata, title-screen update mixin).
- Modern-style synthetic TierTagger tree patches successfully (profile/rankings provider, dynamic REST modes, icon fallback, Fabric metadata, NeoForge metadata/dependency table id, restricted MCTiers/SubTiers assets removal).
- `RestTiersBridge.java` passes `javac --release 17` against minimal Gson API stubs, which validates Java syntax and the Java-17 language/API baseline used by the bridge.
- Generated-JAR verifier accepts a clean synthetic JAR and rejects restricted/backdoor paths or legacy MCTiers API strings.

## Limitation

Actual Minecraft/Gradle builds were not run in this container because it has no outbound Gradle/Maven dependency access. The included GitHub Actions workflow is the authoritative build verification for all upstream branches and runs `verify_jars.py` before artifacts are uploaded.
