# _UNINSTALL_NIX_FINISH

Script: `test/_uninstall_nix_finish.sh`

## Purpose

Finish removing a leftover [steam-frame-nix](https://github.com/lhns/steam-frame-nix) / Determinate `nix-installer` install on the Steam Frame (`/nix`, `/home/nix`) after user-level Home Manager files are already cleaned. Needs host `sudo`.

## Usage

Put the Frame root password in the repo `.env` (gitignored, never synced):

```
steamos_root_pwd="<password>"
```

Then from the PC checkout:

```
bash test/_uninstall_nix_finish.sh
```

## Related

[SCRIPTS_ENV.md](SCRIPTS_ENV.md) (`frame_sudo` / `steamos_root_pwd`), [OVERVIEW.md](OVERVIEW.md).
