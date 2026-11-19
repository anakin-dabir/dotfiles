#!/usr/bin/env bash
# Sets up this bspwm desktop on a fresh Arch Linux install.
# Safe to re-run: existing files are backed up, never deleted.

set -euo pipefail

REPO_URL="https://github.com/anakin-dabir/dotfiles.git"
DOTS="$HOME/dotfiles"
BACKUP="$HOME/.config-backup-$(date +%Y%m%d-%H%M%S)"

say()  { printf '\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
ask()  { local r; read -rp "$(printf '\033[1;32m  ? %s [y/N] \033[0m' "$1")" r; [[ $r =~ ^[Yy]$ ]]; }

# ── Checks ───────────────────────────────────────────────────────
[ -f /etc/arch-release ] || { echo "This installer is for Arch Linux."; exit 1; }
[ "$(id -u)" -ne 0 ] || { echo "Run as your normal user, not root (sudo is used when needed)."; exit 1; }
ping -c1 -W3 archlinux.org >/dev/null 2>&1 || { echo "No internet connection."; exit 1; }
sudo -v

# ── Get the repo ─────────────────────────────────────────────────
if [ ! -d "$DOTS/.git" ]; then
    say "Cloning dotfiles into $DOTS"
    sudo pacman -S --needed --noconfirm git
    git clone --depth 1 "$REPO_URL" "$DOTS"
fi
cd "$DOTS"

# ── Chaotic-AUR (prebuilt AUR packages) ──────────────────────────
if ! pacman-conf --repo-list | grep -qx chaotic-aur; then
    say "Adding the chaotic-aur repository"
    key=3056513887B78AEB
    sudo pacman-key --recv-key "$key" --keyserver keyserver.ubuntu.com
    sudo pacman-key --lsign-key "$key"
    sudo pacman -U --noconfirm --needed \
        'https://cdn-mirror.chaotic.cx/chaotic-aur/chaotic-keyring.pkg.tar.zst' \
        'https://cdn-mirror.chaotic.cx/chaotic-aur/chaotic-mirrorlist.pkg.tar.zst'
    printf '\n[chaotic-aur]\nInclude = /etc/pacman.d/chaotic-mirrorlist\n' | sudo tee -a /etc/pacman.conf >/dev/null
fi

# ── Packages ─────────────────────────────────────────────────────
install_repo_list() {
    # Only ask pacman for names that exist, so one renamed package can't abort the rest.
    local avail wanted found missing
    avail=$(pacman -Slq)
    wanted=$(grep -vE '^\s*(#|$)' "$1" || true)
    found=$(grep -xFf <(echo "$avail") <<<"$wanted" || true)
    missing=$(grep -vxFf <(echo "$avail") <<<"$wanted" || true)
    [ -n "$found" ] && sudo pacman -S --needed --noconfirm $found
    [ -n "$missing" ] && sed 's/^/  not in repos, skipped: /' <<<"$missing"
    return 0
}
install_aur_list() {
    local wanted
    wanted=$(grep -vE '^\s*(#|$)' "$1" || true)
    [ -n "$wanted" ] || return 0
    command -v yay >/dev/null || sudo pacman -S --needed --noconfirm yay
    yay -S --needed --noconfirm $wanted || warn "Some AUR packages failed; re-run: yay -S --needed - < $1"
}

say "Updating the system and installing packages (this takes a while)"
sudo pacman -Syu --noconfirm
install_repo_list packages/repo.txt
install_aur_list packages/aur.txt

HARDWARE=0
if ask "Install HP Victus / NVIDIA laptop packages and fixes (keyboard RGB, NVIDIA power, suspend fixes)?"; then
    HARDWARE=1
    install_repo_list packages/hardware-repo.txt
    install_aur_list packages/hardware-aur.txt
fi

# ── Link configs ─────────────────────────────────────────────────
link() { # link <source in repo> <target>
    local src=$1 dst=$2
    if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then return; fi
    if [ -e "$dst" ] || [ -L "$dst" ]; then
        mkdir -p "$BACKUP/$(dirname "${dst#"$HOME"/}")"
        mv "$dst" "$BACKUP/${dst#"$HOME"/}"
    fi
    mkdir -p "$(dirname "$dst")"
    ln -s "$src" "$dst"
}

say "Linking configs into ~/.config"
for dir in "$DOTS"/config/*/; do
    name=$(basename "$dir")
    link "$DOTS/config/$name" "$HOME/.config/$name"
done
for f in .zshrc .gtkrc-2.0; do link "$DOTS/home/$f" "$HOME/$f"; done
mkdir -p "$HOME/.icons/default"
cp -n "$DOTS/home/.icons/default/index.theme" "$HOME/.icons/default/index.theme" 2>/dev/null || true

say "Installing themes, icons, fonts and helper scripts"
mkdir -p "$HOME/.local/share/themes" "$HOME/.local/share/icons" "$HOME/.local/share/fonts" "$HOME/.local/bin"
for t in "$DOTS"/misc/themes/*; do link "$t" "$HOME/.local/share/themes/$(basename "$t")"; done
for i in "$DOTS"/misc/icons/*; do link "$i" "$HOME/.local/share/icons/$(basename "$i")"; done
cp -rn "$DOTS"/misc/fonts/* "$HOME/.local/share/fonts/"
fc-cache -f >/dev/null
for b in "$DOTS"/misc/bin/*; do link "$b" "$HOME/.local/bin/$(basename "$b")"; done

# Personal wallpaper folder used by the cupertino rice
if [ ! -d "$HOME/Pictures/wallpapers" ]; then
    mkdir -p "$HOME/Pictures/wallpapers"
    cp -n "$DOTS"/config/bspwm/wallpapers/* "$HOME/Pictures/wallpapers/"
fi

# Machine-local shell settings and secrets (never committed)
[ -f "$HOME/.zshrc.local" ] || { printf '# Secrets and machine-only settings go here.\n' > "$HOME/.zshrc.local"; chmod 600 "$HOME/.zshrc.local"; }

# ── System files ─────────────────────────────────────────────────
install_system_dir() { # copies misc/system/<name>/ into / , filling in @USER@ and @UID@
    local base="$DOTS/misc/system/$1"
    while IFS= read -r -d '' f; do
        local rel=${f#"$base"} tmp
        tmp=$(mktemp)
        sed -e "s/@USER@/$USER/g" -e "s/@UID@/$(id -u)/g" "$f" > "$tmp"
        sudo install -D -m "$(stat -c %a "$f")" "$tmp" "$rel"
        rm -f "$tmp"
    done < <(find "$base" -type f -print0)
}

say "Installing system tweaks (pacman hook, journal size cap, iPhone auto-mount)"
install_system_dir common
sudo udevadm control --reload-rules

if [ "$HARDWARE" = 1 ]; then
    say "Installing HP Victus fixes"
    install_system_dir hp-victus
    sudo systemctl enable kbd-backlight.service disable-wakeups.service
    warn "Kernel parameters are not changed automatically. For the eDP black-screen fix add"
    warn "  i915.enable_psr=0 i915.enable_dc=0 i915.enable_fbc=0  to GRUB_CMDLINE_LINUX_DEFAULT"
    warn "  in /etc/default/grub, then run: sudo grub-mkconfig -o /boot/grub/grub.cfg"
fi

# ── Services ─────────────────────────────────────────────────────
say "Enabling services"
systemctl is-enabled --quiet mpd.service 2>/dev/null && sudo systemctl disable --now mpd.service
systemctl --user daemon-reload
systemctl --user enable mpd.service ArchUpdates.timer battery-warn.timer 2>/dev/null || true
sudo systemctl enable NetworkManager.service bluetooth.service avahi-daemon.service 2>/dev/null || true

if pacman -Qq ly >/dev/null 2>&1; then
    sudo systemctl disable getty@tty1.service 2>/dev/null || true
    sudo systemctl enable ly@tty1.service
fi

# Virtual machines: the glx backend often fails there
if systemd-detect-virt --quiet; then
    sed -i -e 's/backend = "glx"/backend = "xrender"/' -e 's/vsync = true/vsync = false/' \
        "$DOTS/config/bspwm/config/picom/picom.conf"
fi

# ── Shell ────────────────────────────────────────────────────────
if [ "$(getent passwd "$USER" | cut -d: -f7)" != "/usr/bin/zsh" ]; then
    say "Making zsh your default shell"
    chsh -s /usr/bin/zsh
fi

say "Done"
echo "  Reboot, log in through ly and pick bspwm."
[ -d "$BACKUP" ] && echo "  Files that were replaced are saved in: $BACKUP"
