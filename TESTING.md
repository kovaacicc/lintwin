# Two-Machine Tests (needs laptop + desktop)

These scenarios cannot be tested locally — they require real SSH access between two machines
with lintwin initialized on both.

## Prerequisites
- lintwin initialized on both machines (`lintwin init` on laptop, `lintwin init --join` on desktop)
- SSH key auth working both ways
- Both machines on same network OR Tailscale connected

---

## 1. Sync round-trip (git)
Test that a change on one machine reaches the other.

```bash
# On laptop — make a change:
echo "alias dc='docker compose'" >> ~/.bashrc
lintwin sync --to desktop --dry-run   # verify .bashrc shows as modified
lintwin sync --to desktop             # actually push

# On desktop:
lintwin pull --to laptop
grep "alias dc" ~/.bashrc             # should be there
```
Expected: change appears on desktop without manual copy.

---

## 2. rsync file transfer
Test that large/binary files are transferred over SSH.

```bash
# On laptop — add a file to a tracked rsync path:
cp somefile.pdf ~/Documents/
lintwin sync --to desktop

# On desktop:
ls ~/Documents/somefile.pdf           # should exist
```
Expected: file appears on desktop after sync.

---

## 3. Conflict detection
Test that lintwin detects and prompts when both machines modify the same file.

```bash
# On laptop — edit a file:
echo "set mouse=a" >> ~/.vimrc

# On desktop (WITHOUT syncing first) — edit the same file differently:
echo "set nowrap" >> ~/.vimrc

# Now sync from desktop:
lintwin sync --to laptop
```
Expected: conflict prompt appears for `.vimrc` with options:
`[1] Keep local  [2] Keep remote  [3] Skip  [4] Show diff`

---

## 4. packages diff between machines
Test that package differences are correctly detected.

```bash
# On both machines first:
lintwin packages export

# On desktop:
lintwin packages diff --to laptop
```
Expected: table showing packages on laptop missing from desktop and vice versa.

---

## 5. packages install from other machine
Test that missing packages are installed automatically.

```bash
# On laptop — install something new:
sudo pacman -S cowsay
lintwin packages export

# On desktop:
lintwin packages diff --to laptop     # should show cowsay as missing
lintwin packages install              # should install it
which cowsay                          # should exist now
```
Expected: package installed without manually specifying it.

---

## 6. Dirty repo detection across machines
Test that uncommitted changes in tracked project repos trigger a warning.

```bash
# Create or use an existing git repo inside a tracked path (e.g. ~/projects/myapp):
cd ~/projects/myapp
echo "dirty" > test.txt              # don't commit

lintwin status
```
Expected: `⚠ Dirty repos: ~/projects/myapp — 1 uncommitted` shown in status.

```bash
lintwin sync --to desktop
```
Expected: `⚠ Dirty repos found` prompt → `[s] Skip all / [c] Copy anyway / [r] Decide per repo`

---

## 7. Tailscale connectivity fallback
Test that lintwin correctly uses Tailscale when on different networks.

```bash
# With tailscale_hostname set in config.toml:
# - Disconnect from LAN (use mobile hotspot)
# - Ensure Tailscale is running on both machines

lintwin sync --to desktop
```
Expected: sync succeeds over Tailscale even without LAN.

Then disable Tailscale on desktop and retry:
Expected: `Cannot reach 'desktop' — skipping rsync.` but git sync still works.

---

## 8. pull only (no push)
Test that pull doesn't push local changes.

```bash
# Make a local change but don't want to push yet:
echo "wip" >> ~/.bashrc

lintwin pull --to desktop             # should pull remote changes only
git --git-dir=~/.local/share/lintwin/repo log --oneline -3
```
Expected: remote commits appear locally, but the `.bashrc` change is NOT committed/pushed.

---

## 9. Fresh desktop setup end-to-end
The big one — full flow from a fresh Arch install.

```bash
# On fresh desktop (after base Arch + Hyprland):
sudo pacman -S git rsync github-cli python
gh auth login
git clone https://github.com/you/lintwin
cd lintwin && python -m venv .venv && source .venv/bin/activate && pip install -e .

lintwin init --join git@github.com:you/lintwin-dots.git --name desktop
lintwin packages install
lintwin sync --to laptop
```
Expected: all dotfiles land in correct locations, all packages installed, machine usable
without any manual config copying.

Watch for:
- Hyprland monitor config needs adjustment (different display setup)
- Some AUR packages may need a second pass if build deps conflict
- Services need manual `systemctl enable` (pipewire, bluetooth, tailscaled, etc.)
