#!/usr/bin/env python3
#
# Solcycle - Automatic screen temperature adjustment based on time and sunrise/sunset
# https://github.com/dusanx/solcycle
#

import argparse
import json
import os
import sys
import subprocess
import re
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
import urllib.request
import urllib.parse
import urllib.error

# Get config directory (~/.config/solcycle/ with fallback to script directory)
def get_config_dir():
    config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
    config_dir = Path(config_home) / 'solcycle'

    # Create if doesn't exist
    if not config_dir.exists():
        config_dir.mkdir(parents=True, exist_ok=True)

    return config_dir

# Get script directory (for example config)
def get_script_dir():
    return Path(__file__).parent.resolve()

# Get path to config file (always XDG)
def get_config_file():
    return get_config_dir() / 'config.json'

# Get path to sun data file
def get_sun_data_file():
    return get_config_dir() / 'sun_data.json'

# Get path to override file
def get_override_file():
    return get_config_dir() / 'override.json'

# Load JSON from file
def load_json(filepath, default=None):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return default if default is not None else {}
    except json.JSONDecodeError as e:
        print(f"Error parsing {filepath}: {e}", file=sys.stderr)
        return default if default is not None else {}

# Save data to JSON file
def save_json(filepath, data):
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# Load configuration with defaults
def load_config():
    config_path = get_config_file()

    # If XDG config doesn't exist, try to copy from example template
    if not config_path.exists():
        example_template = get_script_dir() / 'config.json.example'
        if example_template.exists():
            # Copy example template to XDG as config.json
            import shutil
            shutil.copy2(example_template, config_path)
            print(f"Copied config template from {example_template} to {config_path}")

    config = load_json(config_path)

    if not config:
        # Create default config
        config = {
            "location": None,
            "temperature_command": "hyprctl hyprsunset temperature {{temperature}}",
            "temperature_points": {
                "SR": 2500,
                "SR+1:00": 6500,
                "23:45": 6500,
                "00:30": 2500
            },
            "presets": {}
        }
        # Save to XDG config directory
        save_json(config_path, config)

    return config

# Geocode city name to coordinates using Nominatim (OpenStreetMap)
def geocode_city(city_name):
    try:
        query = urllib.parse.quote(city_name)
        url = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1"

        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Solcycle/1.0')

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read())
            if data:
                result = data[0]
                return {
                    'name': result['display_name'],
                    'lat': float(result['lat']),
                    'lng': float(result['lon'])
                }
    except Exception as e:
        print(f"Error geocoding: {e}", file=sys.stderr)
    return None

# Reverse geocode coordinates to location name
def reverse_geocode(lat, lng):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}&format=json"

        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Solcycle/1.0')

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read())
            return data.get('display_name', f"{lat}, {lng}")
    except Exception as e:
        print(f"Error reverse geocoding: {e}", file=sys.stderr)
    return f"{lat}, {lng}"

# Fetch sunrise/sunset times from API
def fetch_sun_times(lat, lng, date):
    url = f"https://api.sunrise-sunset.org/json?lat={lat}&lng={lng}&date={date}&formatted=0"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read())
            if data['status'] == 'OK':
                return {
                    'date': date,
                    'sunrise': data['results']['sunrise'],
                    'sunset': data['results']['sunset']
                }
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError) as e:
        print(f"Error fetching data for {date}: {e}", file=sys.stderr)
    return None

# Update sun data cache
def update_sun_data(config, months=6):
    location = config.get('location')
    if not location:
        print("Error: No location set. Use 'solcycle.py location <city>' first.", file=sys.stderr)
        return False

    lat, lng = location['lat'], location['lng']
    name = location.get('name', f"{lat}, {lng}")

    print(f"Fetching sun data for {name}")
    print(f"Downloading {months} months of data...")

    sun_data = []
    today = datetime.now().date()

    for day_offset in range(months * 31):
        date = today + timedelta(days=day_offset)
        date_str = date.strftime('%Y-%m-%d')

        data = fetch_sun_times(lat, lng, date_str)
        if data:
            sun_data.append(data)

        if (day_offset + 1) % 30 == 0:
            print(f"  {day_offset + 1} days downloaded...")

    save_json(get_sun_data_file(), {
        'location': location,
        'data': sun_data,
        'updated': datetime.now().isoformat()
    })

    print(f"Downloaded {len(sun_data)} days of sun data")
    return True

# Get sunrise/sunset times for a specific date
def get_sun_times_for_date(date):
    sun_data_cache = load_json(get_sun_data_file())
    if not sun_data_cache or 'data' not in sun_data_cache:
        return None

    date_str = date.strftime('%Y-%m-%d')
    for entry in sun_data_cache['data']:
        if entry['date'] == date_str:
            sunrise = datetime.fromisoformat(entry['sunrise'].replace('Z', '+00:00'))
            sunset = datetime.fromisoformat(entry['sunset'].replace('Z', '+00:00'))
            return {
                'sunrise': sunrise.astimezone(),
                'sunset': sunset.astimezone()
            }
    return None

# Parse time expression (e.g., "23:45", "+2:00", "SR+1", "SS-2:30")
def parse_time_expr(expr, sun_times=None):
    expr = expr.strip().replace(' ', '')

    # Check for SR (sunrise) or SS (sunset)
    if expr.startswith('SR') or expr.startswith('SS'):
        if not sun_times:
            return None

        base_time = sun_times['sunrise'] if expr.startswith('SR') else sun_times['sunset']
        remainder = expr[2:]

        if not remainder:
            return base_time

        # Parse offset (+1:30 or -2:00)
        match = re.match(r'([+-])(\d+)(?::(\d+))?', remainder)
        if match:
            sign = 1 if match.group(1) == '+' else -1
            hours = int(match.group(2))
            minutes = int(match.group(3)) if match.group(3) else 0
            offset = timedelta(hours=hours, minutes=minutes) * sign
            return base_time + offset

        return None

    # Check for relative time (+2:00 from previous point)
    if expr.startswith('+'):
        # This will be handled later when we have previous point
        return expr

    # Parse absolute time (HH:MM)
    match = re.match(r'(\d+):(\d+)', expr)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        now = datetime.now().astimezone()
        return now.replace(hour=hours, minute=minutes, second=0, microsecond=0)

    return None

# Resolve temperature value (could be int or preset name)
def resolve_temperature(temp_value, config):
    # If it's already an integer, return it
    if isinstance(temp_value, int):
        return temp_value

    # If it's a string, try to resolve as preset
    if isinstance(temp_value, str):
        presets = config.get('presets', {})
        if temp_value in presets:
            return presets[temp_value]

        # Try parsing as integer string
        try:
            return int(temp_value)
        except ValueError:
            print(f"Warning: Unknown preset '{temp_value}' and not a valid temperature", file=sys.stderr)
            return None

    return None

# Get sorted temperature points for the day
def get_temperature_points(config):
    temp_points = config.get('temperature_points', {})
    sun_times = get_sun_times_for_date(datetime.now().date())

    if not sun_times and any('SR' in k or 'SS' in k for k in temp_points.keys()):
        print("Warning: No sun data available and SR/SS used in config. Run 'solcycle.py update'", file=sys.stderr)
        return []

    points = []
    previous_time = None
    now = datetime.now().astimezone()

    for expr, temp_value in temp_points.items():
        # Resolve temperature (could be preset name or int)
        temp = resolve_temperature(temp_value, config)
        if temp is None:
            continue

        # Handle relative time from previous point
        if expr.strip().startswith('+'):
            if previous_time is None:
                print(f"Warning: Relative time '{expr}' used without previous point", file=sys.stderr)
                continue

            match = re.match(r'\+(\d+)(?::(\d+))?', expr.strip().replace(' ', ''))
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2)) if match.group(2) else 0
                point_time = previous_time + timedelta(hours=hours, minutes=minutes)
            else:
                continue
        else:
            point_time = parse_time_expr(expr, sun_times)

        if point_time:
            points.append((point_time, temp))
            previous_time = point_time

    # Sort by time
    points.sort(key=lambda x: (x[0].hour, x[0].minute))

    return points

# Interpolate temperature between two points
def interpolate_temp(temp1, temp2, progress):
    return int(temp1 + (temp2 - temp1) * progress)

# Calculate current temperature based on points
def calculate_temperature(config):
    points = get_temperature_points(config)

    if not points:
        print("Warning: No temperature points configured", file=sys.stderr)
        return 6500

    now = datetime.now().astimezone()
    now_minutes = now.hour * 60 + now.minute

    # Convert points to minutes since midnight and handle day rollover
    points_minutes = []
    for point_time, temp in points:
        minutes = point_time.hour * 60 + point_time.minute
        points_minutes.append((minutes, temp))

    # Find which segment we're in
    for i in range(len(points_minutes)):
        start_min, start_temp = points_minutes[i]
        end_min, end_temp = points_minutes[(i + 1) % len(points_minutes)]

        # Handle day rollover
        if end_min < start_min:
            # Segment crosses midnight
            if now_minutes >= start_min or now_minutes < end_min:
                if now_minutes >= start_min:
                    elapsed = now_minutes - start_min
                    total = (24 * 60 - start_min) + end_min
                else:
                    elapsed = (24 * 60 - start_min) + now_minutes
                    total = (24 * 60 - start_min) + end_min

                progress = elapsed / total if total > 0 else 0
                return interpolate_temp(start_temp, end_temp, progress)
        else:
            # Normal segment
            if start_min <= now_minutes < end_min:
                elapsed = now_minutes - start_min
                total = end_min - start_min
                progress = elapsed / total if total > 0 else 0
                return interpolate_temp(start_temp, end_temp, progress)

    # Fallback to first point
    return points_minutes[0][1]

# Set screen temperature using configured command
def set_temperature(config, temp, verbose=False):
    command_template = config.get('temperature_command', 'hyprctl hyprsunset temperature {{temperature}}')
    command = command_template.replace('{{temperature}}', str(temp))

    try:
        result = subprocess.run(
            command.split(),
            check=True,
            capture_output=True,
            text=True
        )
        if verbose:
            print(f"Command output: {result.stdout}")
            if result.stderr:
                print(f"Command stderr: {result.stderr}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error setting temperature: {e}", file=sys.stderr)
        if verbose:
            print(f"stdout: {e.stdout}", file=sys.stderr)
            print(f"stderr: {e.stderr}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print(f"Error: Command not found: {command.split()[0]}", file=sys.stderr)
        return False

# Check for active override
def check_override():
    override = load_json(get_override_file())
    if not override:
        return None

    expiry = datetime.fromisoformat(override['expiry'])
    if datetime.now().astimezone() < expiry:
        return override['mode'], override['temp']

    # Override expired, remove it
    get_override_file().unlink(missing_ok=True)
    return None

# Set an override mode
def set_override(mode, temp, duration_hours=1):
    expiry = datetime.now().astimezone() + timedelta(hours=duration_hours)
    override = {
        'mode': mode,
        'temp': temp,
        'expiry': expiry.isoformat()
    }
    save_json(get_override_file(), override)

# Check sun data freshness
def check_sun_data_freshness():
    sun_data_file = get_sun_data_file()
    if not sun_data_file.exists():
        return None

    sun_data_cache = load_json(sun_data_file)
    if not sun_data_cache or 'data' not in sun_data_cache:
        return None

    today = datetime.now().date()
    latest_date = None

    for entry in sun_data_cache['data']:
        entry_date = datetime.strptime(entry['date'], '%Y-%m-%d').date()
        if entry_date >= today:
            if latest_date is None or entry_date > latest_date:
                latest_date = entry_date

    if latest_date is None:
        return None

    return (latest_date - today).days

#
# Command handlers
#

# location: View or set location
def cmd_location(args):
    config = load_config()

    if not args.location:
        # Show current location
        loc = config.get('location')
        if loc:
            print(f"Current location: {loc.get('name', 'Unknown')} ({loc['lat']}, {loc['lng']})")
        else:
            print("No location set")
        return

    # Try parsing as coordinates first (lat lng)
    parts = args.location
    if len(parts) == 2:
        try:
            lat, lng = float(parts[0]), float(parts[1])
            print(f"Looking up location for coordinates {lat}, {lng}...")
            name = reverse_geocode(lat, lng)

            response = input(f"Use location: {name}? [Y/n] ")
            if response.lower() not in ['', 'y', 'yes']:
                print("Cancelled")
                return

            config['location'] = {'name': name, 'lat': lat, 'lng': lng}
            save_json(get_config_file(), config)
            print(f"Location set to: {name}")

            # Auto-update sun data
            print("\nUpdating sun data...")
            update_sun_data(config)
            return
        except ValueError:
            pass

    # Treat as city name
    city_name = ' '.join(parts)
    print(f"Looking up city: {city_name}...")
    result = geocode_city(city_name)

    if not result:
        print("City not found. Please try again or use coordinates.", file=sys.stderr)
        return

    response = input(f"Use location: {result['name']}? [Y/n] ")
    if response.lower() not in ['', 'y', 'yes']:
        print("Cancelled")
        return

    config['location'] = result
    save_json(get_config_file(), config)
    print(f"Location set to: {result['name']}")

    # Auto-update sun data
    print("\nUpdating sun data...")
    update_sun_data(config)

# update: Download sun data
def cmd_update(args):
    config = load_config()
    months = args.months if args.months else 6
    update_sun_data(config, months)

# auto: Run auto mode (once or daemon)
def run_auto_once(config, verbose=False):
    # Check for override
    override = check_override()
    if override:
        mode, temp = override
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] Override: {mode} {temp}K")
        set_temperature(config, temp, verbose=verbose)
        return

    # Calculate temperature
    temp = calculate_temperature(config)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] Auto: {temp}K")
    set_temperature(config, temp, verbose=verbose)

def cmd_auto(args):
    import time

    config = load_config()
    verbose = args.verbose if args.verbose else False
    interval = args.interval if args.interval else None

    if interval:
        # Daemon mode
        print(f"Starting daemon mode: running auto every {interval} seconds")
        print("Press Ctrl+C to stop")
        try:
            while True:
                run_auto_once(config, verbose=verbose)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nDaemon stopped")
            sys.exit(0)
    else:
        # Single run
        run_auto_once(config, verbose=verbose)

# preset: Activate a user-defined preset
def cmd_preset(args):
    config = load_config()
    preset_name = args.preset_name

    presets = config.get('presets', {})
    if preset_name not in presets:
        print(f"Error: Preset '{preset_name}' not found", file=sys.stderr)
        print(f"Available presets: {', '.join(presets.keys()) if presets else 'none'}")
        return

    temp = presets[preset_name]
    set_override(preset_name, temp)
    set_temperature(config, temp)
    print(f"Preset '{preset_name}' activated for 1 hour ({temp}K)")

# reset: Cancel override and return to auto
def cmd_reset(args):
    config = load_config()

    override_file = get_override_file()
    if override_file.exists():
        override_file.unlink()
        print("Override cancelled, returning to auto mode")
    else:
        print("No active override")

    temp = calculate_temperature(config)
    set_temperature(config, temp, verbose=True)
    print(f"Temperature set to {temp}K")

# status: Show current mode and temperature
def cmd_status(args):
    config = load_config()

    # Check sun data freshness
    days_remaining = check_sun_data_freshness()
    needs_update = days_remaining is None or days_remaining < 15
    update_prefix = "UPDATE " if needs_update else ""

    # Check for override
    override = check_override()
    if override:
        mode, temp = override
        print(f"{update_prefix}{mode.capitalize()} {temp}K")
        if args.verbose:
            expiry = datetime.fromisoformat(load_json(get_override_file())['expiry'])
            remaining = expiry - datetime.now().astimezone()
            print(f"Override expires in {remaining.seconds // 60} minutes")
            if days_remaining is not None:
                print(f"Sun data: {days_remaining} days remaining")
    else:
        temp = calculate_temperature(config)
        print(f"{update_prefix}Auto {temp}K")
        if args.verbose and days_remaining is not None:
            print(f"Sun data: {days_remaining} days remaining")

# plan: Show temperature points and current position
def cmd_plan(args):
    config = load_config()
    points = get_temperature_points(config)

    if not points:
        print("No temperature points configured")
        return

    now = datetime.now().astimezone()
    current_temp = calculate_temperature(config)

    print("Temperature plan for today:")
    print(f"Current time: {now.strftime('%H:%M')}")
    print(f"Current temperature: {current_temp}K")
    print()

    print("Temperature points:")
    for point_time, temp in points:
        marker = " <- NOW" if abs((point_time.hour * 60 + point_time.minute) - (now.hour * 60 + now.minute)) < 1 else ""
        print(f"  {point_time.strftime('%H:%M')} → {temp}K{marker}")

    # Show sunrise/sunset if available
    sun_times = get_sun_times_for_date(now.date())
    if sun_times:
        print()
        print(f"Sunrise: {sun_times['sunrise'].strftime('%H:%M')}")
        print(f"Sunset: {sun_times['sunset'].strftime('%H:%M')}")

# test: Test setting a specific temperature
def cmd_test(args):
    config = load_config()
    temp = args.temperature

    if temp < 1000 or temp > 10000:
        print("Error: Temperature must be between 1000K and 10000K", file=sys.stderr)
        sys.exit(1)

    print(f"Testing: setting temperature to {temp}K")
    if set_temperature(config, temp, verbose=True):
        print(f"Success: temperature set to {temp}K")
    else:
        print("Failed to set temperature", file=sys.stderr)
        sys.exit(1)

#
# Main
#

def main():
    parser = argparse.ArgumentParser(
        description='Solcycle - Automatic screen temperature adjustment',
        epilog='For more information: https://github.com/dusanx/solcycle'
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # location
    location_parser = subparsers.add_parser('location', help='View or set location')
    location_parser.add_argument('location', nargs='*', help='City name or "lat lng" coordinates')

    # update
    update_parser = subparsers.add_parser('update', help='Download and cache sun data')
    update_parser.add_argument('--months', type=int, default=6, help='Months of data (default: 6)')

    # auto
    auto_parser = subparsers.add_parser('auto', help='Auto mode - calculate temperature based on time')
    auto_parser.add_argument('interval', nargs='?', type=int, help='Daemon mode: run every N seconds')
    auto_parser.add_argument('-v', '--verbose', action='store_true', help='Show command output')

    # preset
    preset_parser = subparsers.add_parser('preset', help='Activate a user-defined preset')
    preset_parser.add_argument('preset_name', help='Name of preset to activate')

    # reset
    subparsers.add_parser('reset', help='Cancel override and return to auto mode')

    # status
    status_parser = subparsers.add_parser('status', help='Show current mode and temperature')
    status_parser.add_argument('-v', '--verbose', action='store_true', help='Show detailed information')

    # plan
    subparsers.add_parser('plan', help='Show temperature points and current position')

    # test
    test_parser = subparsers.add_parser('test', help='Test setting a specific temperature')
    test_parser.add_argument('temperature', type=int, help='Temperature in Kelvin (1000-10000)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch commands
    commands = {
        'location': cmd_location,
        'update': cmd_update,
        'auto': cmd_auto,
        'preset': cmd_preset,
        'reset': cmd_reset,
        'status': cmd_status,
        'plan': cmd_plan,
        'test': cmd_test
    }

    commands[args.command](args)

if __name__ == '__main__':
    main()
