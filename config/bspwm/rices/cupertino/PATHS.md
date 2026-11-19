# cupertino — external references

Everything this rice *owns* lives in this folder. Everything it *depends on*
that lives elsewhere on the filesystem is listed here, with the exact path.

## Files in this rice folder

| File | Purpose |
|------|---------|
| `theme-config.bash` | palette + all per-app settings (the single source of truth); `main_bar="cupertino"` picks the bar |
| `apply.sh` | per-rice hook — macOS rofi geometry |
| `preview.webp` | RiceSelector thumbnail |
| `walls` | symlink → `~/.config/bspwm/wallpapers` |
| `PATHS.md` | this file |

## The bar: `~/.config/bspwm/bars/cupertino/`

Since the Nov 2026 upstream merge, bars live apart from rices, so any rice
can use any bar (BarSelector, `super + alt + space`).

| File | Purpose |
|------|---------|
| `config.ini` | polybar `[bar/menubar]`; defines its own `[color]` section instead of including `../colors.ini` |
| `modules.ini` | polybar modules |
| `Bar.bash` | launches the menubar on every monitor |
| `preview-bar.webp` | BarSelector thumbnail |

## External packages (installed via pacman/paru)

| Component | Path | Package |
|-----------|------|---------|
| GTK theme | `/usr/share/themes/WhiteSur-Dark/` | `whitesur-gtk-theme` (AUR, MIT) |
| Icon theme | `/usr/share/icons/WhiteSur-dark/` | `whitesur-icon-theme` (AUR) |
| Cursor theme | `/usr/share/icons/WhiteSur-cursors/` | `whitesur-cursor-theme-git` (AUR) |
| UI font | fontconfig: `Adwaita Sans` | `adwaita-fonts` (extra) |
| Mono font | fontconfig: `JetBrainsMono Nerd Font` | `ttf-jetbrains-mono-nerd` |
| Glyph fonts | fontconfig: `Phosphor`, `Material Design Icons Desktop` | shipped with the dotfiles |

WhiteSur is a community-made, MIT-licensed macOS-*style* theme
(github.com/vinceliuice/WhiteSur-gtk-theme). No Apple assets are used or
redistributed here.

## Shared dotfiles infrastructure this rice plugs into

| Path | Role |
|------|------|
| `~/.config/bspwm/bin/Theme.sh` | applies a rice: sources `theme-config.bash`, then every module |
| `~/.config/bspwm/config/modules/*.sh` | shared writers (picom, dunst, rofi, gtk, kitty, …) |
| `~/.config/bspwm/config/modules/99-rice-hook.sh` | **added for this rice** — runs `<rice>/apply.sh` if present (generic; any rice can use it) |
| `~/.config/bspwm/config/rofi-themes/shared.rasi` | regenerated per-rice by `04-rofi.sh`; `apply.sh` appends macOS geometry |
| `~/.config/bspwm/config/rofi-themes/*.rasi` | the 16 dialogs — all `@import "shared.rasi"` |
| `~/.config/bspwm/config/system.ini` | polybar hardware IDs (battery `BAT0`, net `wlo1`, backlight) |
| `~/.config/bspwm/wallpapers/` | shared wallpaper pool (17 images) |

## Files this rice writes outside its own folder

| Path | Written by | Note |
|------|-----------|------|
| `~/.icons/default/index.theme` | `03-gtk.sh` | points X at the WhiteSur cursor |
| `~/.config/gtk-{3.0,4.0}/settings.ini` | `03-gtk.sh` | theme/icons/cursor for Electron apps, which ignore xsettingsd |
| `~/.config/bspwm/config/rofi-themes/shared.rasi` | `04-rofi.sh` + `apply.sh` | fully regenerated whenever any rice is applied — safe |
