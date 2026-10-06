# _probe_steamurl_applies_wrap.sh

Disarms the game-route chooser, sets `ft-game-run %command%` via
`SetAppLaunchOptions`, triggers `steam://run/<appId>`, and checks whether the
wrapper appears in the process cmdline / log. Restores empty launch options
afterward.

## Usage

```
bash test/_probe_steamurl_applies_wrap.sh
# or:
bash test/_probe_steamurl_applies_wrap.sh 1145360
```
