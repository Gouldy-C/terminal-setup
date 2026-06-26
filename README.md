# Terminal Setup

Cross-platform terminal configuration for **Windows (PowerShell)** and **Linux / macOS / WSL (Bash)** — modern tools, productivity shortcuts, and a shared Oh My Posh theme.

## About This Project

This repository is an **expansion of [Chris Titus Tech's PowerShell profile](https://github.com/ChrisTitusTech/powershell-profile)**. Chris's original work established the foundation: hash-based profile auto-updates, the override system, Oh My Posh integration, productivity aliases, and a polished day-to-day shell experience on Windows.

**terminal-setup** builds on that foundation with:

- **Cross-platform support** — a Bash counterpart (`linux/bashrc`) so Linux, macOS, and WSL can share the same look, feel, and workflow
- **Unified installers** — `windows/setup.ps1` and `linux/setup.sh` for one-command setup on each platform
- **Shared theming** — a single Oh My Posh theme (`my_layout.omp.json`) used by both PowerShell and Bash
- **Customizations and additions** — platform-specific tooling, setup scripts, and ongoing improvements while preserving Chris's core patterns (overrides, auto-update, debug mode)

If you find this useful, please also check out and support the [original project by Chris Titus Tech](https://github.com/ChrisTitusTech/powershell-profile).

**Bash users**: See [Quick Installation](#-quick-installation) below for Linux/macOS/WSL setup.

## 📁 Project Structure

```
├── windows/           # Windows / PowerShell
│   ├── setup.ps1      # PowerShell installer
│   ├── profile.ps1    # User override template (theme, debug, etc.)
│   └── Microsoft.PowerShell_profile.ps1   # Reference copy of main profile
├── linux/             # Linux / macOS / WSL / Bash
│   ├── setup.sh       # Bash installer
│   ├── bashrc         # Main bash profile (hash-based auto-update)
│   └── profile.bash   # User override template
├── my_layout.omp.json # Shared Oh My Posh theme (used by both)
└── README.md
```

## 🚀 Quick Installation

### One-Line Run (copy & paste)

**Windows (PowerShell as Administrator):**
```powershell
irm "https://github.com/Gouldy-C/terminal-setup/raw/main/windows/setup.ps1" | iex
```

**Linux / macOS / WSL:**
```bash
curl -sL "https://github.com/Gouldy-C/terminal-setup/raw/main/linux/setup.sh" | bash
```

---

### From a local clone

**Windows**

From the repo root, run:

```powershell
.\windows\setup.ps1
```

**Linux / macOS / WSL**

```bash
git clone <your-repo-url> terminal-setup && cd terminal-setup
chmod +x linux/setup.sh && ./linux/setup.sh
```

Or from an existing clone:

```bash
./linux/setup.sh
```

The script installs Oh My Posh, zoxide, eza (ls with icons), Nerd Fonts, and configures your bash profile. Restart your terminal or run `source ~/.bashrc`.

## ✨ Features

### 🔄 Auto-Update System
- **Profile Updates**: Automatically checks for and installs profile updates every 7 days
- **PowerShell Updates**: Automatically checks for and installs PowerShell updates
- **Debug Mode**: Skip auto-updates during development with debug mode

### 🎨 Enhanced Terminal Experience
- **Oh My Posh Integration**: Beautiful terminal prompt with custom theme
- **Terminal Icons**: File and folder icons for better visual navigation
- **PSReadLine**: Enhanced command-line editing with syntax highlighting
- **Zoxide Integration**: Smart directory jumping (`z` command)

### 🛠️ Productivity Tools
- **Unix-like Aliases**: Familiar commands like `ls`, `grep`, `which`, `head`, `tail`
- **Git Shortcuts**: Quick git operations (`gs`, `ga`, `gc`, `gpush`, `gpull`)
- **File Operations**: Enhanced file management (`la`, `ll`, `mkcd`, `nf`)
- **System Utilities**: Process management, system info, networking tools

### 🎯 Custom Functions
- **WinUtil Integration**: Quick access to Windows utility scripts
- **Clipboard Tools**: Copy/paste utilities (`cpy`, `pst`)
- **Network Tools**: DNS flush, public IP lookup, file sharing (`hb`)
- **Development Helpers**: File search, text replacement, process management

## 🔧 Customization

This profile supports extensive customization through override functions and variables. Create a `profile.ps1` file in your PowerShell directory to customize:

### Override Variables
```powershell
$debug_Override = $true                    # Enable debug mode
$repo_root_Override = "your-fork-url"      # Use your own fork
$timeFilePath_Override = "custom-path"     # Custom update tracking file
$updateInterval_Override = 14              # Custom update interval (days)
$EDITOR_Override = "code"                  # Set preferred editor
```

### Override Functions
```powershell
function Update-Profile_Override {
    # Your custom update logic
}

function Get-Theme_Override {
    # Your custom theme configuration
}

function Clear-Cache_Override {
    # Your custom cache clearing logic
}
```

### Bash Customization

Edit `~/.config/bash/profile.bash` (or `$XDG_CONFIG_HOME/bash/profile.bash`) to add your own aliases and overrides. This file is never overwritten by updates.

**Bash auto-update** (mirrors PowerShell): Hash-based check every 7 days (configurable). Call `update_bashrc` manually anytime. Override via `profile.bash`: `repo_root_Override`, `updateInterval_Override` (-1 = always), `timeFilePath_Override`, `debug_Override` (skip checks).

```bash
# Custom aliases
alias mycommand='something'

# Custom theme path
export OMP_CONFIG="$HOME/.config/bash/my_layout.omp.json"
```

## 📋 Available Commands

### Git Shortcuts
| Command | Description |
|---------|-------------|
| `gs` | git status |
| `ga` | git add . |
| `gc <message>` | git commit -m |
| `gpush` | git push |
| `gpull` | git pull |
| `gcom <message>` | git add . && git commit -m |
| `lazyg <message>` | git add . && git commit -m && git push |

### File Operations
| Command | Description |
|---------|-------------|
| `la` | List files with formatting |
| `ll` | List all files (including hidden) |
| `mkcd <dir>` | Create and change to directory |
| `nf <name>` | Create new file |
| `touch <file>` | Create empty file |
| `unzip <file>` | Extract zip file |

### System Utilities
| Command | Description |
|---------|-------------|
| `sysinfo` | Display system information |
| `uptime` | Show system uptime |
| `flushdns` | Clear DNS cache |
| `Get-PubIP` | Get public IP address |
| `admin` | Run command as administrator |

### Development Tools
| Command | Description |
|---------|-------------|
| `ep` | Edit PowerShell profile |
| `reload-profile` | Reload current profile |
| `winutil` | Run WinUtil (full release) |
| `winutildev` | Run WinUtil (development) |
| `hb <file>` | Upload file to hastebin |

### Navigation
| Command | Description |
|---------|-------------|
| `docs` | Go to Documents folder |
| `dtop` | Go to Desktop folder |
| `z <path>` | Smart directory jumping (zoxide) |

## 📦 Requirements

### PowerShell
- **PowerShell 5.1+** or **PowerShell Core 6+**
- **Windows Terminal** (recommended)
- **Oh My Posh** (auto-installed)
- **Terminal-Icons** module (auto-installed)
- **Zoxide** (auto-installed via winget)

### Bash
- **Bash 4+**
- **curl**, **unzip** (for setup)
- **Oh My Posh** (auto-installed)
- **eza** (auto-installed where available; ls with icons)
- **zoxide** (auto-installed)

## 🎨 Theme Configuration

Both PowerShell and Bash use the same Oh My Posh theme (`my_layout.omp.json`) for a consistent look:
- Clean, modern design with diamond segments
- Git status indicators
- Custom color palette
- User/host name mapping
- Virtual environment support

## 🔍 Debug Mode (PowerShell)

Enable debug mode to skip auto-updates and see detailed information:

```powershell
$debug_Override = $true
```

In debug mode:
- Auto-updates are disabled
- Debug messages are displayed
- Profile changes won't be overwritten

## 📚 Help

**PowerShell**: Run `Show-Help` to display all commands.

**Bash**: Run `show_help` to display all commands.

## 🤝 Contributing

Contributions are welcome. This project extends Chris Titus Tech's PowerShell profile — please be respectful of the upstream work when proposing changes.

1. Fork the repository
2. Make your changes
3. Test thoroughly on the platform(s) you changed (Windows and/or Linux/macOS/WSL)
4. Submit a pull request

## 📄 License

This project is open source. The PowerShell profile derives from [Chris Titus Tech's powershell-profile](https://github.com/ChrisTitusTech/powershell-profile); refer to that repository for original licensing information.

## 🙏 Credits & Acknowledgments

### Chris Titus Tech

This project would not exist without **[Chris Titus Tech](https://github.com/ChrisTitusTech)** and his [PowerShell profile](https://github.com/ChrisTitusTech/powershell-profile). The Windows profile, override architecture, auto-update approach, and much of the command surface area are based on his work. **terminal-setup** is intended as a respectful expansion — not a replacement — of that project.

### Other Projects

- **[Oh My Posh](https://ohmyposh.dev/)** — Terminal prompt theming
- **[Terminal Icons](https://github.com/devblackops/Terminal-Icons)** — File and folder icons (PowerShell)
- **[Zoxide](https://github.com/ajeetdsouza/zoxide)** — Smart directory jumping
- **[eza](https://github.com/eza-community/eza)** — Modern `ls` replacement with icons (Bash)

---

**Note**: This profile automatically updates itself. If you want to make permanent changes, use the override system described in the Customization section.
