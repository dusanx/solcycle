# Solcycle

> Intelligent screen temperature adjustment based on time of day and sunrise/sunset cycles

Solcycle automatically adjusts your screen temperature throughout the day, reducing eye strain and improving sleep quality by following natural light patterns.

## Features

- **Sunrise/Sunset Aware**: Uses real astronomical data for your location
- **Flexible Temperature Curves**: Define unlimited temperature points throughout the day
- **Smart Time Expressions**: Support for absolute times (`23:45`), relative times (`+2:00`), and solar times (`SR+1`, `SS-2`)
- **Custom Presets**: Create your own temperature profiles for different activities
- **Daemon or Cron**: Run as a continuous service or via cron
- **Location Lookup**: Automatic geocoding for city names and coordinates
- **Minimal Dependencies**: Pure Python 3 with only standard library
- **Cross-Platform Ready**: Configurable temperature command works with any display control tool

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/solcycle.git
cd solcycle
```

2. Make the script executable:
```bash
chmod +x solcycle.py
```

3. Copy to your PATH (optional):
```bash
sudo cp solcycle.py /usr/local/bin/solcycle
```

## Quick Start

1. **Set your location**:
```bash
./solcycle.py location "Lisbon, Portugal"
# or with coordinates
./solcycle.py location 38.7223 -9.1393
```

2. **Download sunrise/sunset data**:
```bash
./solcycle.py update
```

3. **Run auto mode**:
```bash
./solcycle.py auto
```

4. **Set up automatic updates** (choose one):

   **Option A - Cron** (runs every minute):
   ```bash
   crontab -e
   # Add: * * * * * /path/to/solcycle.py auto
   ```

   **Option B - Daemon** (runs continuously):
   ```bash
   ./solcycle.py auto 60  # updates every 60 seconds
   ```

## Configuration

Solcycle stores configuration in `~/.config/solcycle/config.json`. On first run, if this file doesn't exist, it will copy `config.json.example` from the script directory (if present) or create a default configuration.

### Example Configuration

```json
{
  "location": {
    "name": "Armação de Pêra, Portugal",
    "lat": 37.1048,
    "lng": -8.3584
  },
  "temperature_command": "hyprctl hyprsunset temperature {{temperature}}",
  "presets": {
    "night": 2500,
    "day": 6500,
    "reading": 4000,
    "gaming": 6500,
    "movie": 3500
  },
  "temperature_points": {
    "SR": "night",
    "SR+1:00": "day",
    "23:45": "day",
    "00:30": "night"
  }
}
```

### Temperature Points

Define your temperature curve with flexible time expressions:

- **Absolute time**: `"23:45": 6500` - exact time
- **Relative time**: `"+2:00": 5000` - 2 hours after previous point
- **Sunrise relative**: `"SR": 2500`, `"SR+1:00": 6500` - based on sunrise
- **Sunset relative**: `"SS": 6500`, `"SS-1": 5500` - based on sunset
- **Preset reference**: `"08:00": "day"` - use a preset temperature

You can reference presets by name in temperature points for better maintainability.

The temperature smoothly interpolates between points.

### Example Curves

**Simple day/night**:
```json
"temperature_points": {
  "06:00": 2500,
  "08:00": 6500,
  "22:00": 6500,
  "00:00": 2500
}
```

**Solar-based with dawn/dusk**:
```json
"temperature_points": {
  "SR-0:30": 2500,
  "SR+1:00": 6500,
  "SS-1:00": 6500,
  "SS+1:00": 2500
}
```

**Complex multi-point curve**:
```json
"temperature_points": {
  "SR": 2500,
  "SR+1": 6500,
  "12:00": 6500,
  "18:00": 5500,
  "23:45": 4500,
  "+0:45": 2500
}
```

### Display Command

Configure the command to set screen temperature. Use `{{temperature}}` as a placeholder:

```json
"temperature_command": "hyprctl hyprsunset temperature {{temperature}}"
```

**Other examples**:
- **Redshift**: `"redshift -P -O {{temperature}}"`
- **Gammastep**: `"gammastep -P -O {{temperature}}"`
- **sct**: `"sct {{temperature}}"`
- **wlsunset** (Wayland): Custom wrapper needed

### Presets

Create custom presets for specific activities:

```json
"presets": {
  "night": 2500,
  "day": 6500,
  "reading": 4000,
  "coding": 5500,
  "gaming": 6500,
  "movie": 3500
}
```

**Two ways to use presets:**

1. **Manual activation** - Override auto mode temporarily:
```bash
./solcycle.py preset reading  # Override to 4000K for 1 hour
```

2. **In temperature points** - Reference presets by name for cleaner config:
```json
"temperature_points": {
  "06:00": "night",
  "08:00": "day",
  "23:00": "reading",
  "00:00": "night"
}
```

This keeps temperatures defined in one place (DRY principle). When you activate a preset manually, it overrides auto mode for 1 hour, then automatically returns to the normal curve.

## Usage

### Commands

**`location [city|lat lng]`** - View or set location
```bash
./solcycle.py location                    # Show current location
./solcycle.py location "Tokyo, Japan"     # Set by city name
./solcycle.py location 35.6762 139.6503   # Set by coordinates
```

**`update [--months N]`** - Download sunrise/sunset data
```bash
./solcycle.py update           # Download 6 months (default)
./solcycle.py update --months 12  # Download 12 months
```

**`auto [interval]`** - Run auto mode
```bash
./solcycle.py auto       # Single run (for cron)
./solcycle.py auto 60    # Daemon mode, update every 60 seconds
./solcycle.py auto -v    # Verbose output
```

**`preset <name>`** - Activate a preset
```bash
./solcycle.py preset reading   # Override to 'reading' preset for 1 hour
```

**`reset`** - Cancel override and return to auto
```bash
./solcycle.py reset
```

**`status [-v]`** - Show current mode and temperature
```bash
./solcycle.py status     # Simple output: "Auto 6500K"
./solcycle.py status -v  # Verbose with details
```

**`plan`** - Visualize temperature curve
```bash
./solcycle.py plan
```
Shows all temperature points, current time, and current temperature.

**`test <temp>`** - Test setting a specific temperature
```bash
./solcycle.py test 5000  # Set to 5000K temporarily
```

### Typical Workflow

```bash
# Initial setup
./solcycle.py location "London, UK"
./solcycle.py update

# Test it works
./solcycle.py auto
./solcycle.py status

# Check your temperature plan
./solcycle.py plan

# Set up automation (choose cron or daemon)
crontab -e  # Add: * * * * * /path/to/solcycle.py auto

# Use presets when needed
./solcycle.py preset movie  # Override for movie watching
./solcycle.py reset         # Return to auto mode
```

## Integration

### Waybar

```json
"custom/solcycle": {
  "exec": "/path/to/solcycle.py status",
  "interval": 60,
  "format": "󰃭 {}",
  "on-click": "/path/to/solcycle.py reset"
}
```

### Systemd Service

Create `~/.config/systemd/user/solcycle.service`:

```ini
[Unit]
Description=Solcycle - Screen temperature adjustment
After=graphical-session.target

[Service]
Type=simple
ExecStart=/path/to/solcycle.py auto 60
Restart=on-failure

[Install]
WantedBy=default.target
```

Enable and start:
```bash
systemctl --user enable --now solcycle.service
```

## Requirements

- Python 3.6+
- Internet connection (for initial location lookup and sun data download only)
- A display temperature control tool (e.g., hyprsunset, redshift, gammastep, sct)

## How It Works

1. **Location**: Geocodes city names to coordinates using OpenStreetMap Nominatim
2. **Sun Data**: Downloads sunrise/sunset times from sunrise-sunset.org API
3. **Temperature Calculation**: Parses time expressions, interpolates between points
4. **Application**: Executes configured command to set screen temperature

All data is cached locally in `~/.config/solcycle/`:
- `config.json` - Your configuration
- `sun_data.json` - Cached sunrise/sunset times
- `override.json` - Active preset/override state

## Troubleshooting

**Temperature not changing?**
- Check the display command is correct: `./solcycle.py test 5000`
- Verify your temperature tool is installed and working
- Check cron/daemon is running: `./solcycle.py status`

**No sun data?**
```bash
./solcycle.py update
```

**Location not found?**
- Try different city name format: "City, Country"
- Use coordinates instead: `./solcycle.py location 40.7128 -74.0060`

**"UPDATE" prefix in status?**
- Sun data running low (< 15 days remaining)
- Run `./solcycle.py update` to refresh

## Contributing

Contributions welcome! Please feel free to submit issues and pull requests.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Credits

- Sunrise/sunset data: [sunrise-sunset.org](https://sunrise-sunset.org/)
- Geocoding: [OpenStreetMap Nominatim](https://nominatim.openstreetmap.org/)

---

**Solcycle** - Better screens, better sleep
