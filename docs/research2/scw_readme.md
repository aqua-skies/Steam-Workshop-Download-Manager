# Problem
When downloading mods for Rimworld with RimPy I would run into an issue where existing mod files were just overwritten but never deleted.
So if a mod author updated their mod and deleted a file, due to how RimPy and Steamcmd work, it would never be deleted for me. This tool helps solve that.

# Instructions
1. Paste `SteamCmdWrapper.exe` into your steamcmd folder.
2. Run it.
3. It will move the contents into a subfolder named `core` and setup correct symlinks so that RimPy is still happy.
4. When you perform a download/update operation with RimPy it will trigger this wrapper instead and backups will be created as timestamped zips!
